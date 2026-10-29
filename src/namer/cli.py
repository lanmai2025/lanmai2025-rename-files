# -*- coding: utf-8 -*-
"""命令行入口：预览（默认）或执行改名。

    python main.py                     # 预览当前目录
    python main.py -d D:\\作业 -t "{学号}-{姓名}-第4次作业"
    python main.py -d D:\\作业 --apply  # 真正改名
    python main.py --undo 改名日志\\xxx.csv
"""
from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path

from . import core


def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _width(text))


def _truncate(text: str, width: int) -> str:
    if _width(text) <= width:
        return text
    out = ""
    used = 0
    for ch in text:
        w = 2 if unicodedata.east_asian_width(ch) in "WF" else 1
        if used + w > width - 1:
            break
        out += ch
        used += w
    return out + "…"


def _setup_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


def print_plan(plan: core.Plan) -> None:
    print(f"目录：{plan.folder}")
    print(f"模板：{plan.template}")
    print(f"共 {len(plan.entries)} 个文件\n")
    if not plan.entries:
        return

    w_state = max(_width(e.status) for e in plan.entries)
    w_old = min(48, max(_width(e.old_name) for e in plan.entries))
    w_new = min(48, max([_width(e.new_name) for e in plan.entries] + [8]))
    header = f"{_pad('状态', w_state)}  {_pad('原文件名', w_old)}  {'新文件名 / 说明'}"
    print(header)
    print("-" * min(120, _width(header) + 4))
    for entry in plan.entries:
        state = _pad(entry.status, w_state)
        old = _pad(_truncate(entry.old_name, w_old), w_old)
        if entry.status == core.STATUS_RENAME:
            detail = _truncate(entry.new_name, w_new)
        else:
            detail = f"{_truncate(entry.new_name, w_new)}（{entry.reason}）" if entry.new_name and entry.reason else (entry.reason or entry.new_name)
        print(f"{state}  {old}  {detail}")

    print()
    for status in (core.STATUS_RENAME, core.STATUS_SAME, core.STATUS_CONFLICT,
                   core.STATUS_EXISTS, core.STATUS_ILLEGAL, core.STATUS_UNPARSED):
        count = plan.count(status)
        if count:
            print(f"  {status}：{count}")


def cmd_undo(log_path: Path) -> int:
    if not log_path.exists():
        print(f"找不到日志文件：{log_path}")
        return 1
    restored, failed = core.undo_log(log_path)
    print(f"已撤销 {restored} 个文件")
    for name, reason in failed:
        print(f"  未撤销：{name}（{reason}）")
    return 0 if not failed else 2


def cmd_rename(args: argparse.Namespace) -> int:
    folder = Path(args.dir).expanduser()
    if not folder.is_absolute():
        folder = Path.cwd() / folder
    try:
        plan = core.build_plan(
            folder,
            template=args.template,
            recursive=args.recursive,
            id_min_len=args.id_min_len,
        )
    except (FileNotFoundError, core.TemplateError) as exc:
        print(f"错误：{exc}")
        return 1

    print_plan(plan)

    if not args.apply:
        if plan.to_rename:
            print("\n以上仅为预览，确认无误后加 --apply 执行改名。")
        return 0

    todo = plan.to_rename
    if not todo:
        print("\n没有需要改名的文件。")
        return 0

    result = core.apply_plan(plan)
    print(f"\n已改名 {result.renamed} 个文件")
    for name, reason in result.failed:
        print(f"  失败：{name}（{reason}）")
    if result.log_path:
        print(f"日志：{result.log_path}")
        tool = Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "改名工具-命令行.exe"
        print(f'如需撤销："{tool}" --undo "{result.log_path}"')
    return 0 if not result.failed else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="改名工具",
        description="按模板批量规范文件名为「学号-姓名-第N次作业」等格式。默认只预览，不改文件。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "模板占位符：{学号} {姓名} {作业} {内容}\n"
            "示例：{学号}-{姓名}-{作业}       -> 2034005-徐阳-第4次作业\n"
            "      {学号}-{姓名}-第4次作业     -> 固定写成第4次作业\n"
            "      {姓名}_{学号}_{作业}\n"
            "      第4次作业-{学号}-{姓名}"
        ),
    )
    parser.add_argument("-d", "--dir", default=".", help="要处理的文件夹，默认当前目录")
    parser.add_argument("-t", "--template", default=core.DEFAULT_TEMPLATE,
                        help=f"目标模板，默认 {core.DEFAULT_TEMPLATE}")
    parser.add_argument("-r", "--recursive", action="store_true", help="包含子文件夹")
    parser.add_argument("--apply", action="store_true", help="真正执行改名（默认只预览）")
    parser.add_argument("--undo", metavar="日志文件", help="按日志撤销上一次改名")
    parser.add_argument("--id-min-len", type=int, default=6, metavar="N",
                        help="学号最少位数，默认 6")
    parser.add_argument("--gui", action="store_true", help="打开图形界面")
    return parser


def main(argv: list[str] | None = None) -> int:
    _setup_console()
    args = build_parser().parse_args(argv)
    if args.undo:
        return cmd_undo(Path(args.undo))
    return cmd_rename(args)
