"""Refresh/继续对话时保留工具调用历史的回归测试。

覆盖：
1) agent_runtime 会把前端保存下来的 assistant.tool_calls / tool_results 重新组装成
   OpenAI function calling 的 assistant + tool 消息，避免刷新后丢失本地工具上下文；
2) FastAPI 的对话保存 API 会把 tool_results 持久化到 chat/*.json；
3) 前端加载对话时会把 tool_results 带入 history（通过 JS 逻辑的 Python 等价校验）。

用法：python test_tool_history_persistence.py
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import agent_runtime
import skill_selector


class ToolHistoryTests(unittest.TestCase):
    def setUp(self):
        import config
        self.config_patches = [
            patch.object(config, "get", lambda key, default=None: ({"enabled": False, "max_rounds": 1, "max_total_calls": 10, "max_calls_per_round": 10} if key == "tool_limits" else default)),
            patch.object(config, "workspace_dir", return_value=Path(".")),
        ]
        for p in self.config_patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.config_patches):
            p.stop()

    def test_history_rebuilds_openai_tool_messages(self):
        history = [
            {"role": "user", "content": "读一下 app.py"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call_1", "name": "list_dir", "arguments": {"path": "."}},
                    {"id": "call_2", "name": "read_file", "arguments": {"filePath": "app.py"}},
                ],
                "tool_results": [
                    {"tool_call_id": "call_1", "tool": "list_dir", "output": "files", "ok": True},
                    {"tool_call_id": "call_2", "tool": "read_file", "output": "code", "ok": True},
                ],
            },
        ]
        calls = []

        async def fake_stream(provider, model, messages, tools=None):
            calls.append(messages)
            yield {"type": "content_delta", "content": "done"}

        async def run_case():
            with patch.object(agent_runtime, "resolve_provider",
                              return_value=({"id": "p", "name": "p"}, "m")), \
                 patch.object(agent_runtime.mcp_manager, "refresh_prompt",
                              new=AsyncMock(return_value="")), \
                 patch.object(agent_runtime.ai_client, "model_type_of", return_value="text_generation"), \
                 patch.object(skill_selector, "select_skills",
                              new=AsyncMock(return_value={"skills": [], "note": ""})), \
                 patch.object(agent_runtime.prompt_builder, "build_system_prompt", return_value="sys"), \
                 patch.object(agent_runtime.prompt_builder, "build_user_context", return_value="ctx"), \
                 patch.object(agent_runtime.ai_client, "stream_chat", side_effect=fake_stream), \
                 patch.object(agent_runtime, "tool_loader") as tool_loader_mock:
                tool_loader_mock.list_enabled_tools.return_value = []
                gen = agent_runtime.run_chat(
                    "继续",
                    history=history,
                    provider_id="p",
                    model="m",
                    skill_names=[],
                )
                async for event in gen:
                    if event.get("event") == "message":
                        break
                # 显式关闭生成器：避免测试里提前 break 导致 ChangeCollector 的 ContextVar 在另一个 asyncio Context 清理
                try:
                    await gen.aclose()
                except Exception:
                    pass

        asyncio.run(run_case())
        self.assertTrue(calls, "stream_chat 未被调用")
        messages = calls[0]
        non_system = [m for m in messages if m.get("role") != "system"]
        self.assertEqual(non_system[0], {"role": "user", "content": "读一下 app.py"})
        assistant_msg = non_system[1]
        self.assertEqual(assistant_msg["role"], "assistant")
        self.assertIsNone(assistant_msg["content"])
        self.assertEqual(len(assistant_msg["tool_calls"]), 2)
        self.assertEqual(assistant_msg["tool_calls"][0]["function"]["name"], "list_dir")
        self.assertEqual(assistant_msg["tool_calls"][0]["function"]["arguments"],
                         json.dumps({"path": "."}, ensure_ascii=False))

        tool_msgs = [m for m in non_system if m.get("role") == "tool"]
        self.assertEqual(tool_msgs[0]["tool_call_id"], "call_1")
        self.assertEqual(tool_msgs[0]["content"], "files")
        self.assertEqual(tool_msgs[1]["tool_call_id"], "call_2")
        self.assertEqual(tool_msgs[1]["content"], "code")

    def test_history_ignores_tool_results_without_call(self):
        history = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call_9", "name": "read_file", "arguments": {"filePath": "a.txt"}}
                ],
                "tool_results": [
                    {"tool_call_id": "call_8", "tool": "read_file", "output": "orphan"},
                    {"tool_call_id": "call_9", "tool": "read_file", "output": "ok"},
                ],
            }
        ]
        calls = []

        async def fake_stream(provider, model, messages, tools=None):
            calls.append(messages)
            yield {"type": "content_delta", "content": "done"}

        async def run_case():
            with patch.object(agent_runtime, "resolve_provider",
                              return_value=({"id": "p", "name": "p"}, "m")), \
                 patch.object(agent_runtime.mcp_manager, "refresh_prompt",
                              new=AsyncMock(return_value="")), \
                 patch.object(agent_runtime.ai_client, "model_type_of", return_value="text_generation"), \
                 patch.object(skill_selector, "select_skills",
                              new=AsyncMock(return_value={"skills": [], "note": ""})), \
                 patch.object(agent_runtime.prompt_builder, "build_system_prompt", return_value="sys"), \
                 patch.object(agent_runtime.prompt_builder, "build_user_context", return_value="ctx"), \
                 patch.object(agent_runtime.ai_client, "stream_chat", side_effect=fake_stream), \
                 patch.object(agent_runtime, "tool_loader") as tool_loader_mock:
                tool_loader_mock.list_enabled_tools.return_value = []
                gen = agent_runtime.run_chat("继续", history=history, provider_id="p", model="m", skill_names=[])
                async for event in gen:
                    if event.get("event") == "message":
                        break
                try:
                    await gen.aclose()
                except Exception:
                    pass
                # 显式关闭生成器：避免测试里提前 break 导致 ChangeCollector 的 ContextVar 在另一个 asyncio Context 清理
                try:
                    await gen.aclose()
                except Exception:
                    pass

        asyncio.run(run_case())
        messages = calls[0]
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        self.assertEqual([m["tool_call_id"] for m in tool_msgs], ["call_9"])
        self.assertEqual(tool_msgs[0]["content"], "ok")


class ConversationPersistenceTests(unittest.TestCase):
    def test_conversation_api_keeps_tool_results(self):
        import json as json_lib
        import app as app_module
        from fastapi.testclient import TestClient
        import config

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_cache, old_mtime = config._cache, config._cache_mtime
            config._cache, config._cache_mtime = {}, 0.0
            config.CONFIG_PATH = root / "config.json"
            config.BACKUP_DIR = root / "backups"
            app_module.CHAT_DIR = root / "chat"
            app_module.SESSION_FILE = root / ".sessions.json"

            try:
                with patch.object(app_module, "require_auth", lambda request: None):
                    client = TestClient(app_module.app)
                    created = client.post("/api/conversations", json={"workspace": ""}).json()["conversation"]
                    cid = created["id"]

                    payload = {
                        "title": "tool history",
                        "workspace": "",
                        "messages": [
                            {"role": "user", "content": "hi"},
                            {
                                "role": "assistant",
                                "content": "",
                                "tool_calls": [
                                    {"id": "call_1", "name": "list_dir", "arguments": {"path": "."}}
                                ],
                                "tool_results": [
                                    {"tool_call_id": "call_1", "tool": "list_dir", "output": "files", "ok": True}
                                ],
                            },
                        ],
                    }
                    put = client.put(f"/api/conversations/{cid}", json=payload)
                    self.assertEqual(put.status_code, 200, put.text)
                    got = client.get(f"/api/conversations/{cid}").json()["conversation"]
                    assistant = got["messages"][1]
                    self.assertTrue(assistant.get("tool_calls"), "tool_calls 未持久化")
                    self.assertTrue(assistant.get("tool_results"), "tool_results 未持久化")
                    self.assertEqual(assistant["tool_results"][0]["tool_call_id"], "call_1")

                    saved = json_lib.loads((root / "chat" / f"{cid}.json").read_text(encoding="utf-8"))
                    self.assertTrue(saved["messages"][1].get("tool_results"))
            finally:
                config._cache, config._cache_mtime = old_cache, old_mtime
                app_module.CHAT_DIR = Path(app_module.BASE_DIR) / "chat"
                app_module.SESSION_FILE = Path(app_module.BASE_DIR) / ".sessions.json"


if __name__ == "__main__":
    unittest.main(verbosity=2)
