"""tool_parser 回归测试：`python test_tool_parser.py`

重点覆盖模型输出工具调用时的两类常见畸形：
1) 字符串内未转义的裸双引号（把含引号的源码塞进 content）；
2) 字符串内的真实换行、全角符号。

历史上「JSON 看起来完整却未被执行」的根因即第 1 类——字符串边界被算错，
被误判为「未闭合」而丢弃，故保留此测试防止回归。
"""

import time

import tool_parser as tp

FAILURES = []


def check(name, cond, detail=""):
    print(("  OK   " if cond else "  FAIL ") + name + ("  " + detail if detail else ""))
    if not cond:
        FAILURES.append(name)


print("### A) 完整 JSON + content 内裸引号（用户场景）")
full = (
    '{"tool": "write_file",\n'
    '\n'
    '"arguments": {"path": "_tmp_patch.py", "content": "from pathlib import Path\\n'
    'msg = \\"hello world\\"\\n'
    'tip = "（运行时提醒）你上一轮没有调用任何工具。请继续推进任务："\\n'
    'idle_streak += 1"}}'
)
seg = tp.parse_segments(full)[0]
check("解析为 tool_call", seg["type"] == "tool_call", seg.get("error", ""))
check("工具名 write_file", seg.get("tool") == "write_file")
check("content 完整还原", seg["arguments"]["content"] ==
      'from pathlib import Path\nmsg = "hello world"\n'
      'tip = "（运行时提醒）你上一轮没有调用任何工具。请继续推进任务："\nidle_streak += 1',
      repr(seg["arguments"]["content"]))

print("### B) 裸引号导致括号错配（原始根因：看起来闭合却被判未闭合）")
b1 = '{"tool": "write_file", "arguments": {"content": "x = \\"a\\" y"}}'
seg = tp.parse_segments(b1)[0]
check("裸引号不破坏边界", seg["type"] == "tool_call", seg.get("error", ""))

print("### C) content 内多个裸引号对")
b2 = '{"tool": "write_file", "arguments": {"content": "a = "x" b = "y" done"}}'
seg = tp.parse_segments(b2)[0]
check("多对裸引号", seg["type"] == "tool_call" and seg["arguments"]["content"] == 'a = "x" b = "y" done',
      repr(seg.get("arguments", {}).get("content")) or seg.get("error", ""))

print("### D) 真截断仍报错，不做过度修复")
trunc = '{"tool": "write_file", "arguments": {"content": "abc'
seg = tp.parse_segments(trunc)[0]
check("截断 -> tool_call_error", seg["type"] == "tool_call_error", seg["error"])

print("### E) 严格合法输入不触发回溯")
ok = '{"tool": "stop", "arguments": {"reason": "done"}}'
cand = tp._resolve_candidate(ok, 0)
check("原生解析", cand["fixed"] == "" and cand["error"] == "")
check("边界正确", cand["end"] == len(ok))

print("### F) streaming_mask 与解析边界一致")
for label, sample in [("裸引号对", full), ("多裸引号", b2), ("多调用", '{"tool": "stop"}\n{"tool": "stop"}')]:
    mask = tp.streaming_mask(sample)
    segs = tp.parse_segments(sample)
    calls = [s for s in segs if s["type"] == "tool_call"]
    covered = "".join(sample[i] for i, v in enumerate(mask) if v == 1)
    check(f"mask 覆盖 == {label} 的调用原文", covered == "".join(s["raw"] for s in calls),
          "mask=%d字符 调用原文=%d字符" % (len(covered), len("".join(s["raw"] for s in calls))))

print("### G) 正文散文不受影响")
prose = '说明：/{} 与 /{ } 都不是工具调用。'
segs = tp.parse_segments(prose)
check("散文还原", len(segs) == 1 and segs[0]["type"] == "text"
      and segs[0]["content"] == '说明：{} 与 { } 都不是工具调用。', repr(segs[0].get("content")))

print("### H) 长文本 + 多处裸引号")
big = ('前言段落。' * 2000) + '{"tool": "write_file", "arguments": {"content": "' \
      + '\\n'.join(['line %d with "quoted" text' % i for i in range(20)]) + '"}}'
t0 = time.time()
segs = tp.parse_segments(big)
elapsed = time.time() - t0
seg = [s for s in segs if s["type"] == "tool_call"]
check("长文本(%d字符)解析成功" % len(big), len(seg) == 1, f"耗时 {elapsed:.2f}s")
check("长文本性能 < 2s", elapsed < 2.0, f"{elapsed:.2f}s")
if seg:
    # 模型输出的是 JSON 转义序列 \n，json.loads 后应为真实换行
    want = "\n".join(['line %d with "quoted" text' % i for i in range(20)])
    got = seg[0]["arguments"]["content"]
    check("20 处裸引号全部还原", got == want,
          "want尾部=%r got尾部=%r 长度 want=%d got=%d" % (want[-30:], got[-30:], len(want), len(got)))
    mask = tp.streaming_mask(big)
    covered = "".join(big[i] for i, v in enumerate(mask) if v == 1)
    check("长文本 mask 与调用原文一致", covered == seg[0]["raw"],
          "mask=%d 原文=%d" % (len(covered), len(seg[0]["raw"])))

print()
print("全部通过" if not FAILURES else "失败: " + ", ".join(FAILURES))
