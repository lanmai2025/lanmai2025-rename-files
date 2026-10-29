# -*- coding: utf-8 -*-
"""核心逻辑测试：用需求里的三个例子做验收，另加边界情况。"""
from __future__ import annotations

import shutil
import sys
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from namer import core  # noqa: E402


class ExamplesTest(unittest.TestCase):
    """需求文档「预期效果」里的三个例子，输出必须和预设顺序一致。"""

    CASES = [
        ("徐阳-2034005-数据结构第4次作业-字符串的使用.docx", "2034005-徐阳-第4次作业.docx"),
        ("23530503杨丽第四次作业.pdf", "23530503-杨丽-第4次作业.pdf"),
        ("23443433-李虎-第4次作业.zip", "23443433-李虎-第4次作业.zip"),
    ]

    def test_default_template(self):
        for old, expected in self.CASES:
            with self.subTest(old=old):
                stem = Path(old).stem
                parts = core.parse_name(stem)
                new = core.build_new_name(parts, core.split_template(core.DEFAULT_TEMPLATE))
                self.assertEqual(new + Path(old).suffix, expected)

    def test_fixed_literal_outputs(self):
        segs = core.split_template("{学号}-{姓名}-第4次作业")
        expected = ["2034005-徐阳-第4次作业", "23530503-杨丽-第4次作业", "23443433-李虎-第4次作业"]
        for (old, _), want in zip(self.CASES, expected):
            new = core.build_new_name(core.parse_name(Path(old).stem), segs)
            self.assertEqual(new, want)


class ParseTest(unittest.TestCase):
    def test_three_char_name(self):
        parts = core.parse_name("王小明-20240001-实验3")
        self.assertEqual(parts["姓名"], "王小明")
        self.assertEqual(parts["学号"], "20240001")
        self.assertEqual(parts["作业"], "实验3")

    def test_compound_surname(self):
        parts = core.parse_name("欧阳娜娜-20240002-第2次作业")
        self.assertEqual(parts["姓名"], "欧阳娜娜")
        self.assertEqual(parts["作业"], "第2次作业")

    def test_no_separator(self):
        parts = core.parse_name("20231234张三第十二次作业")
        self.assertEqual(parts["学号"], "20231234")
        self.assertEqual(parts["姓名"], "张三")
        self.assertEqual(parts["作业"], "第12次作业")

    def test_content_kept(self):
        parts = core.parse_name("数据结构第3次作业-李雷-20230009")
        self.assertEqual(parts["姓名"], "李雷")
        self.assertEqual(parts["学号"], "20230009")
        self.assertIn("数据结构", parts["内容"])

    def test_missing_id(self):
        parts = core.parse_name("张三第4次作业")
        self.assertNotIn("学号", parts)

    def test_glued_name_and_ten_digit_id(self):
        """用户反馈过的真实格式：学号 10 位，姓名紧贴学号且无分隔符。"""
        parts = core.parse_name("数据结构第1次作业-2025123509肖涵郡")
        self.assertEqual(parts["学号"], "2025123509")
        self.assertEqual(parts["姓名"], "肖涵郡")
        self.assertEqual(parts["作业"], "第1次作业")
        self.assertIn("数据结构", parts["内容"])

    def test_glued_three_char_name_build(self):
        parts = core.parse_name("数据结构第1次作业-2025123509肖涵郡")
        new = core.build_new_name(parts, core.split_template(core.DEFAULT_TEMPLATE))
        self.assertEqual(new, "2025123509-肖涵郡-第1次作业")

    def test_name_ending_with_xin(self):
        """用户反馈：朱雅新里的"新"被当成作业关键字。"""
        parts = core.parse_name("20251243454-朱雅新-第1次实验报告")
        self.assertEqual(parts["学号"], "20251243454")
        self.assertEqual(parts["姓名"], "朱雅新")
        self.assertEqual(parts["作业"], "第1次实验报告")

    def test_ethnic_four_char_name(self):
        """用户反馈：少数民族姓名（巴桑嘉布）没有常见姓，需要兜底识别。"""
        parts = core.parse_name("2023567112532-巴桑嘉布-第1次实验报告")
        self.assertEqual(parts["学号"], "2023567112532")
        self.assertEqual(parts["姓名"], "巴桑嘉布")
        self.assertEqual(parts["作业"], "第1次实验报告")

    def test_ethnic_name_build(self):
        parts = core.parse_name("2023567112532-巴桑嘉布-第1次实验报告")
        new = core.build_new_name(parts, core.split_template(core.DEFAULT_TEMPLATE))
        self.assertEqual(new, "2023567112532-巴桑嘉布-第1次实验报告")


class PlanTest(unittest.TestCase):
    def setUp(self):
        origin = Path(__file__).resolve().parent.parent / "_tmp"
        origin.mkdir(exist_ok=True)
        # 不用 tempfile.mkdtemp：它会把目录权限设成仅本进程可访问，沙箱里反而写不进去
        self.dir = origin / ("case-" + uuid.uuid4().hex[:8])
        self.dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def touch(self, name: str) -> Path:
        path = self.dir / name
        path.write_text("x", encoding="utf-8")
        return path

    def test_plan_statuses(self):
        self.touch("徐阳-2034005-数据结构第4次作业.docx")
        self.touch("23530503杨丽第四次作业.pdf")
        self.touch("23330001-李雷-第4次作业.doc")  # 已经是目标格式
        self.touch("语文笔记.md")                   # 无法识别
        plan = core.build_plan(self.dir)
        self.assertEqual(len(plan.entries), 4)
        statuses = {e.old_name: e.status for e in plan.entries}
        self.assertEqual(statuses["23330001-李雷-第4次作业.doc"], core.STATUS_SAME)
        self.assertEqual(statuses["语文笔记.md"], core.STATUS_UNPARSED)
        self.assertEqual(statuses["徐阳-2034005-数据结构第4次作业.docx"], core.STATUS_RENAME)

    def test_conflict(self):
        self.touch("徐阳-2034005-第4次作业.docx")
        self.touch("2034005-徐阳-第4次作业.xlsx")
        # 两个不同文件映射到不同名字；用固定模板制造冲突
        self.touch("徐阳-2034005-第4次作业.txt")
        self.touch("徐阳2034005第4次作业.txt")  # 与上一个同名目标
        plan = core.build_plan(self.dir, template="{学号}-{姓名}-第4次作业")
        flagged = [e for e in plan.entries if e.status == core.STATUS_CONFLICT]
        self.assertTrue(flagged, "应当检测到计划内重名")

    def test_apply_and_undo(self):
        self.touch("徐阳-2034005-数据结构第4次作业.docx")
        self.touch("23530503杨丽第四次作业.pdf")
        plan = core.build_plan(self.dir)
        result = core.apply_plan(plan, log_dir=self.dir / "log")
        self.assertEqual(result.renamed, 2)
        names = sorted(p.name for p in self.dir.iterdir() if p.is_file())
        self.assertEqual(names, ["2034005-徐阳-第4次作业.docx", "23530503-杨丽-第4次作业.pdf"])

        restored, failed = core.undo_log(result.log_path)
        self.assertEqual(restored, 2)
        self.assertEqual(failed, [])
        names = sorted(p.name for p in self.dir.iterdir() if p.is_file())
        self.assertEqual(names, ["23530503杨丽第四次作业.pdf", "徐阳-2034005-数据结构第4次作业.docx"])

    def test_recursive(self):
        sub = self.dir / "子文件夹"
        sub.mkdir()
        (sub / "徐阳-2034005-第4次作业.docx").write_text("x", encoding="utf-8")
        plan = core.build_plan(self.dir, recursive=True)
        self.assertEqual(len(plan.entries), 1)
        plan2 = core.build_plan(self.dir, recursive=False)
        self.assertEqual(len(plan2.entries), 0)

    def test_bad_template(self):
        with self.assertRaises(core.TemplateError):
            core.build_plan(self.dir, template="{姓名}-{生日}")
        with self.assertRaises(core.TemplateError):
            core.build_plan(self.dir, template="固定文字")


if __name__ == "__main__":
    unittest.main(verbosity=2)
