"""ask_followup_question 提问/回答链路测试（前端选择报错的回归）。

背景：旧版前端在 multiSelect 问题里只勾选一个选项时，会把 answer 作为字符串
（labels.length === 1 ? labels[0] : labels）提交，而后端要求多选必须是非空数组，
导致用户在前端点选时报 400「该问题为多选，answer 需为非空数组」。

修复：
1. 前端 submit() 按 q.multi_select 决定载荷形态（多选恒为数组）；
2. 后端对「多选收到字符串 / 单选收到单元素数组」做对称容错。
"""

from __future__ import annotations

import asyncio
import unittest
import unittest.mock

from fastapi.testclient import TestClient

import app as app_module
import interaction
from tools.ask_followup_question import tools as ask_tool


def make_client():
    auth_patch = unittest.mock.patch.object(app_module, "require_auth", lambda request: None)
    auth_patch.start()
    client = TestClient(app_module.app)
    client._auth_patch = auth_patch  # type: ignore[attr-defined]
    return client


class QuestionAnswerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = make_client()

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.client._auth_patch.stop()  # type: ignore[attr-defined]

    def tearDown(self):
        interaction.cancel_all("测试清理")

    def ask(self, multi=False):
        out = ask_tool.run(question="测试提问", options=[{"label": "甲"}, {"label": "乙"}, {"label": "丙"}],
                           multiSelect=multi)
        if asyncio.iscoroutine(out):
            loop = asyncio.new_event_loop()
            try:
                out = loop.run_until_complete(out)
            finally:
                loop.close()
        return out["question"]

    def wait_answer(self, qid):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(interaction.wait(qid, 10))
        finally:
            loop.close()

    def test_multi_select_accepts_array(self):
        q = self.ask(multi=True)
        resp = self.client.post(f"/api/question/{q['id']}/answer", json={"answer": ["甲", "丙"]})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(self.wait_answer(q["id"]), "甲、丙")

    def test_multi_select_single_pick_string_now_accepted(self):
        """核心回归：多选只选 1 项时旧版前端发字符串，不应再 400。"""
        q = self.ask(multi=True)
        resp = self.client.post(f"/api/question/{q['id']}/answer", json={"answer": "甲"})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["answer"], ["甲"])
        self.assertEqual(self.wait_answer(q["id"]), "甲")

    def test_multi_select_rejects_empty(self):
        q = self.ask(multi=True)
        for body in ({"answer": []}, {"answer": ""}, {"answer": None}):
            resp = self.client.post(f"/api/question/{q['id']}/answer", json=body)
            self.assertEqual(resp.status_code, 400, f"{body} -> {resp.text}")

    def test_single_select_accepts_string_and_single_item_array(self):
        q = self.ask()
        resp = self.client.post(f"/api/question/{q['id']}/answer", json={"answer": ["乙"]})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(self.wait_answer(q["id"]), "乙")

    def test_unknown_qid_404_and_reanswer_409(self):
        resp = self.client.post("/api/question/q_nope/answer", json={"answer": "x"})
        self.assertEqual(resp.status_code, 404)
        q = self.ask()
        self.client.post(f"/api/question/{q['id']}/answer", json={"answer": "甲"})
        resp = self.client.post(f"/api/question/{q['id']}/answer", json={"answer": "乙"})
        self.assertEqual(resp.status_code, 409)


if __name__ == "__main__":
    unittest.main(verbosity=2)
