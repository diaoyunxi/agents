"""离线单测：验证 429 指数退避（最多 7 次）与非 429 立即返回。

不联网、不真正 sleep：monkeypatch ai_client.asyncio.sleep 与 ai_client._retry_delay，
并注入一个假 httpx client（get/post/stream 可编程返回状态码）。
用法：python test_429_backoff.py
"""
import asyncio
import types

import ai_client


class FakeResp:
    def __init__(self, status_code, text="", retry_after=None):
        self.status_code = status_code
        self.text = text
        self.headers = {}
        if retry_after is not None:
            self.headers["Retry-After"] = str(retry_after)


class FakeStreamResp:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self._text = text

    async def aread(self):
        return self._text.encode("utf-8")

    def aiter_lines(self):
        async def _gen():
            yield self._text
        return _gen()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def make_client(statuses, stream=False, retry_after=None):
    """statuses: 依次的状态码列表；耗尽后按最后一个。"""
    calls = {"n": 0}

    def next_status():
        i = min(calls["n"], len(statuses) - 1)
        calls["n"] += 1
        return statuses[i]

    async def fake_get(url, **kw):
        return FakeResp(next_status(), text="err", retry_after=retry_after)

    async def fake_post(url, **kw):
        return FakeResp(next_status(), text="err", retry_after=retry_after)

    client = types.SimpleNamespace(get=fake_get, post=fake_post)
    if stream:
        def stream_factory(method, url, **kw):
            st = next_status()
            # 返回一个 async context manager
            import contextlib

            @contextlib.asynccontextmanager
            async def _cm():
                yield FakeStreamResp(st, text="err")
            return _cm()
        client.stream = stream_factory
    client._calls = calls
    return client


async def run_case():
    results = {}
    delays = []
    sleeps = []

    # 打桩
    real_sleep = ai_client.asyncio.sleep

    async def fake_sleep(s):
        sleeps.append(s)

    ai_client.asyncio = types.SimpleNamespace(sleep=fake_sleep)
    real_delay = ai_client._retry_delay
    ai_client._retry_delay = lambda n, resp=None: (delays.append(n), 0.0)[1]
    try:
        # 用例1：前3次429，第4次200 → 成功，记录退避延迟 [1,2,3]（按 n 递增）
        delays.clear(); sleeps.clear()
        c = make_client([429, 429, 429, 200], retry_after=999)
        resp = await ai_client._post_with_retry(c, "POST", "http://x", label="chat")
        assert resp.status_code == 200, f"应成功返回200，实际 {resp.status_code}"
        assert delays == [1, 2, 3], f"退避序列错误: {delays}"
        assert len(sleeps) == 3, f"应退避3次: {sleeps}"
        results["case1"] = f"PASS: 429x3后200成功，退避序列{delays}"

        # 用例2：连续429直到耗尽 → 退避 MAX_RETRIES-1 次（第7次后不再退避），最终抛错
        delays.clear(); sleeps.clear()
        c2 = make_client([429] * 20)
        try:
            await ai_client._post_with_retry(c2, "POST", "http://x", label="chat")
            raise AssertionError("应抛出 429 重试耗尽错误")
        except ValueError as e:
            assert "429" in str(e) and "重试 7" in str(e), f"错误信息不符: {e}"
        assert len(sleeps) == ai_client.MAX_RETRIES - 1, \
            f"应退避 {ai_client.MAX_RETRIES-1} 次，实际 {len(sleeps)}"
        results["case2"] = (f"PASS: 连续429 退避 {len(sleeps)} 次"
                            f"(=MAX_RETRIES-1)，最终抛含'重试 7'的 ValueError")

        # 用例3：非429（500）→ 立即返回，不退避、不打429
        delays.clear(); sleeps.clear()
        c3 = make_client([500])
        resp3 = await ai_client._post_with_retry(c3, "POST", "http://x", label="chat")
        assert resp3.status_code == 500, f"非429应原样返回500，实际 {resp3.status_code}"
        assert delays == [] and sleeps == [], "非429不应退避"
        results["case3"] = f"PASS: 非429(500) 立即返回，无退避"
    finally:
        ai_client.asyncio = asyncio
        ai_client._retry_delay = real_delay

    return results


def main():
    out = asyncio.run(run_case())
    for k in sorted(out):
        print(out[k])
    print("ALL PASS")


if __name__ == "__main__":
    main()
