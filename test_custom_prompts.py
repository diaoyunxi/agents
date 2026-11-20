"""用户自定义 Prompt 的配置 API 与 System Prompt 注入测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app as app_module
import config
import prompt_builder


class CustomPromptTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.path_patch = patch.multiple(
            config,
            CONFIG_PATH=root / "config.json",
            BACKUP_DIR=root / "backups",
        )
        self.path_patch.start()
        self.old_cache = config._cache
        self.old_cache_mtime = config._cache_mtime
        config._cache = {}
        config._cache_mtime = 0.0
        self.auth_patch = patch.object(app_module, "require_auth", lambda request: None)
        self.auth_patch.start()
        self.client = TestClient(app_module.app)

    def tearDown(self):
        self.client.close()
        self.auth_patch.stop()
        config._cache = self.old_cache
        config._cache_mtime = self.old_cache_mtime
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def create_prompt(self, name="代码助手", content="先写测试。", enabled=True):
        response = self.client.post("/api/prompts", json={
            "name": name,
            "content": content,
            "enabled": enabled,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["prompt"]

    def test_empty_old_config_is_compatible(self):
        response = self.client.get("/api/prompts")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"prompts": []})
        self.assertEqual(prompt_builder.build_custom_prompt_section(), "")

    def test_create_list_and_persist_prompt(self):
        item = self.create_prompt(name="  代码助手  ", content="  先写测试。\n再实现。  ")
        self.assertTrue(item["id"].startswith("prompt_"))
        self.assertEqual(item["name"], "代码助手")
        self.assertEqual(item["content"], "先写测试。\n再实现。")
        self.assertTrue(item["enabled"])

        listed = self.client.get("/api/prompts").json()["prompts"]
        self.assertEqual(listed, [item])
        saved = json.loads(config.CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(saved["custom_prompts"], [item])

    def test_required_type_length_and_name_validation(self):
        invalid_payloads = [
            {},
            {"name": "只有名称"},
            {"content": "只有内容"},
            {"name": "  ", "content": "内容"},
            {"name": "名称", "content": "  \n "},
            {"name": "跨\n行", "content": "内容"},
            {"name": "名" * 81, "content": "内容"},
            {"name": "名称", "content": "长" * 20001},
            {"name": [], "content": "内容"},
            {"name": "名称", "content": 123},
            {"name": "名称", "content": "内容", "enabled": "yes"},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.client.post("/api/prompts", json=payload)
                self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.client.get("/api/prompts").json()["prompts"], [])

    def test_duplicate_names_are_rejected_case_insensitively(self):
        first = self.create_prompt(name="Reviewer")
        duplicate = self.client.post("/api/prompts", json={"name": " reviewer ", "content": "其它内容"})
        self.assertEqual(duplicate.status_code, 409)

        second = self.create_prompt(name="Writer")
        conflict = self.client.put(f"/api/prompts/{second['id']}", json={"name": "REVIEWER"})
        self.assertEqual(conflict.status_code, 409)

        renamed = self.client.put(f"/api/prompts/{first['id']}", json={"name": "REVIEWER"})
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()["prompt"]["name"], "REVIEWER")

    def test_partial_update_toggle_and_delete(self):
        item = self.create_prompt()
        prompt_id = item["id"]

        disabled = self.client.put(f"/api/prompts/{prompt_id}", json={"enabled": False})
        self.assertEqual(disabled.status_code, 200)
        self.assertEqual(disabled.json()["prompt"], {
            "id": prompt_id,
            "name": item["name"],
            "content": item["content"],
            "enabled": False,
        })

        edited = self.client.put(f"/api/prompts/{prompt_id}", json={
            "name": "新名称",
            "content": "新内容",
        })
        self.assertEqual(edited.status_code, 200)
        self.assertFalse(edited.json()["prompt"]["enabled"])
        self.assertEqual(edited.json()["prompt"]["content"], "新内容")

        empty_update = self.client.put(f"/api/prompts/{prompt_id}", json={})
        self.assertEqual(empty_update.status_code, 400)
        missing_update = self.client.put("/api/prompts/prompt_missing", json={"enabled": True})
        self.assertEqual(missing_update.status_code, 404)

        deleted = self.client.delete(f"/api/prompts/{prompt_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get("/api/prompts").json()["prompts"], [])
        self.assertEqual(self.client.delete(f"/api/prompts/{prompt_id}").status_code, 404)

    def test_legacy_prompt_without_enabled_supports_partial_edit(self):
        config.set_value("custom_prompts", [
            {"id": "prompt_legacy", "name": "旧条目", "content": "旧内容"},
        ])
        response = self.client.put("/api/prompts/prompt_legacy", json={"name": "新名称"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["prompt"], {
            "id": "prompt_legacy",
            "name": "新名称",
            "content": "旧内容",
            "enabled": True,
        })

    def test_prompt_section_only_contains_enabled_valid_items(self):
        config.set_value("custom_prompts", [
            {"id": "a", "name": "启用一", "content": "规则一", "enabled": True},
            {"id": "b", "name": "停用", "content": "不应出现", "enabled": False},
            {"id": "c", "name": "缺省启用", "content": "规则二"},
            {"id": "d", "name": "空内容", "content": "  ", "enabled": True},
            {"id": "e", "name": "异常内容", "content": 42, "enabled": True},
            "异常项目",
        ])
        section = prompt_builder.build_custom_prompt_section()
        self.assertIn("# 用户自定义 Prompt", section)
        self.assertIn("## 启用一\n\n规则一", section)
        self.assertIn("## 缺省启用\n\n规则二", section)
        self.assertNotIn("不应出现", section)
        self.assertNotIn("异常内容", section)
        self.assertLess(section.index("规则一"), section.index("规则二"))

    def test_full_system_prompt_appends_enabled_custom_prompts(self):
        config.set_value("custom_prompts", [
            {"id": "a", "name": "回答语言", "content": "使用简体中文回答。", "enabled": True},
            {"id": "b", "name": "已停用", "content": "停用内容不应出现。", "enabled": False},
        ])
        with patch.object(prompt_builder.tool_loader, "build_prompt_section", return_value=""), \
                patch.object(prompt_builder.skill_loader, "build_prompt_section", return_value=""), \
                patch.object(prompt_builder, "_mcp_section", return_value=""), \
                patch("common.workspace_dir", return_value=Path(self.temp_dir.name)):
            text = prompt_builder.build_system_prompt(skill_names=[])
        self.assertIn("# 用户自定义 Prompt\n\n## 回答语言\n\n使用简体中文回答。", text)
        self.assertNotIn("停用内容不应出现", text)
        self.assertLess(text.index("# 输出风格"), text.index("# 用户自定义 Prompt"))


if __name__ == "__main__":
    unittest.main()
