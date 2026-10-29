# -*- coding: utf-8 -*-
"""安装程序入口。

    双击                     -> 打开安装向导
    --silent [--dir 路径]     -> 静默安装
    --uninstall [--dir 路径]  -> 静默卸载
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import regtool


def _make_logger():
    path = Path(os.environ.get("TEMP", ".")) / f"{regtool.APP_ID}-install.log"

    def log(message: str) -> None:
        try:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(message + "\n")
        except OSError:
            pass
        try:
            if sys.stdout is not None:
                print(message)
        except Exception:
            pass

    return log, path


def main() -> int:
    parser = argparse.ArgumentParser(prog="批量改名工具-安装程序")
    parser.add_argument("--silent", action="store_true", help="不显示界面，直接安装")
    parser.add_argument("--uninstall", action="store_true", help="卸载已安装的版本")
    parser.add_argument("--dir", help="安装/卸载位置")
    parser.add_argument("--no-desktop", action="store_true", help="不创建桌面快捷方式")
    parser.add_argument("--no-menu", action="store_true", help="不添加右键菜单")
    args = parser.parse_args()

    log, log_path = _make_logger()

    if args.uninstall:
        root = Path(args.dir) if args.dir else regtool.installed_root()
        if root is None or not Path(root).exists():
            log("没有找到已安装的程序")
            return 1
        regtool.uninstall(Path(root), log=log)
        log(f"卸载完成：{root}")
        return 0

    if args.silent:
        dest = Path(args.dir) if args.dir else regtool.default_install_dir()
        try:
            gui_exe = regtool.install(
                regtool.program_files_root(), dest,
                desktop_shortcut=not args.no_desktop,
                context_menu=not args.no_menu,
                log=log,
            )
        except Exception as exc:
            import traceback

            log(f"安装失败：{exc}")
            log(traceback.format_exc())
            return 2
        log(f"安装完成：{dest}")
        log(f"主程序：{gui_exe}")
        log(f"日志文件：{log_path}")
        return 0

    from installer_gui import run
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
