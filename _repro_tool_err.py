import asyncio, json, sys
sys.path.insert(0, ".")
from tools import loader as L

L.registry()


async def main():
    print("== 1) 漏传必填: web_search 不传 query ==")
    print(json.dumps(await L.call_tool("web_search", {}), ensure_ascii=False))

    print("\n== 2) 多传未知参数: read_file 传 bogus ==")
    out = await L.call_tool("read_file", {"filePath": "app.py", "limit": 1, "bogus": 1})
    print("ok=", out["ok"])
    print("output=", out["output"].replace("\n", " ")[:200])

    print("\n== 3) __raw__ 兜底: read_file 传 {'__raw__': ...} ==")
    print(json.dumps(await L.call_tool("read_file", {"__raw__": '{"filePath": "app.py"}'}), ensure_ascii=False))

    print("\n== 4) 正常调用不受影响: read_file ==")
    out = await L.call_tool("read_file", {"filePath": "app.py", "offset": 1, "limit": 2})
    print("ok=", out["ok"])
    print("output=", out["output"].replace("\n", " ")[:120])

    print("\n== 5) 正常调用 calculator ==")
    out = await L.call_tool("calculator", {"expression": "2**10 + 1"})
    print("ok=", out["ok"], "output=", out["output"][:120].replace("\n", " "))

    print("\n== 6) 缺必填 + 多传同时: web_search 传 bogus、漏 query ==")
    print(json.dumps(await L.call_tool("web_search", {"bogus": 1}), ensure_ascii=False))


asyncio.run(main())
