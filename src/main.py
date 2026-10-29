# -*- coding: utf-8 -*-
"""无参数启动图形界面，带参数走命令行。

    python main.py                      # 打开界面
    python main.py -d 文件夹 -t 模板    # 命令行预览
    python main.py --help               # 命令行帮助
"""
from __future__ import annotations

import sys


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        from namer import gui

        return gui.run()

    if argv[0] in ("--open", "-o"):
        from namer import gui

        return gui.run(argv[1] if len(argv) > 1 else None)

    if argv[0] == "--uninstall":
        from namer import gui

        return gui.run_uninstall(silent="--silent" in argv)

    from namer import cli

    return cli.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
