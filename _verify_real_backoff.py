import asyncio, time, types
import ai_client as A


class FakeResp:
    def __init__(self, sc, text="", retry_after=None):
        self.status_code, self.text = sc, text
        self.headers = {}
        if retry_after is not None:
            self.headers["Retry-After"] = str(retry_after)


def make(statuses, retry_after=None):
    n = {"i": 0}

    def st():
        i = min(n["i"], len(statuses) - 1)
        n["i"] += 1
        return statuses[i]

    async def fake_post(u, **kw):
        return FakeResp(st(), "err", retry_after)

    return types.SimpleNamespace(get=fake_post, post=fake_post)


async def main():
    print("== A) 真实sleep: 429,429,200 (无Retry-After) ==")
    c = make([429, 429, 200])
    t0 = time.monotonic()
    r = await A._post_with_retry(c, "POST", "http://x", label="t")
    el = time.monotonic() - t0
    print("   最终状态={}  墙钟耗时≈{:.2f}s  (期望≈1+2=3s)".format(r.status_code, el))

    print("== B) 真实sleep: 429,200 (带 Retry-After=5) ==")
    c2 = make([429, 200], retry_after=5)
    t0 = time.monotonic()
    r2 = await A._post_with_retry(c2, "POST", "http://x", label="t")
    el2 = time.monotonic() - t0
    print("   最终状态={}  墙钟耗时≈{:.2f}s  (Retry-After=5 > 退避1s → 应睡5s)".format(r2.status_code, el2))

    print("== C) _retry_delay 边界行为核验 ==")
    for att in range(1, 8):
        print("   attempt={}  无Retry-After → {}s".format(att, A._retry_delay(att)))
    big = FakeResp(429, retry_after=999)
    print("   attempt=1, Retry-After=999 → {}s  (CAP=60)".format(A._retry_delay(1, big)))
    small = FakeResp(429, retry_after=2)
    print("   attempt=1, Retry-After=2   → {}s  (退避1s, RA2>1 → 取2)".format(A._retry_delay(1, small)))
    tiny = FakeResp(429, retry_after=0.5)
    print("   attempt=1, Retry-After=0.5 → {}s  (RA0.5<1 → 取1)".format(A._retry_delay(1, tiny)))


asyncio.run(main())
