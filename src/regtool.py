# -*- coding: utf-8 -*-
"""安装/卸载的公共逻辑：复制程序、写注册表、建快捷方式、自删除。

全部写在 HKCU（当前用户）下，不需要管理员权限：
  HKCU\\Software\\Classes\\Directory\\shell\\BatchRenameTool           右键文件夹
  HKCU\\Software\\Classes\\Directory\\Background\\shell\\BatchRenameTool 右键文件夹空白处
  HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BatchRenameTool
  HKCU\\Software\\BatchRenameTool                                     安装记录
"""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
import tempfile
import winreg
from datetime import date
from pathlib import Path

APP_NAME = "批量改名工具"
APP_ID = "BatchRenameTool"
VERSION = "1.0.0"
PUBLISHER = "个人学习项目"

GUI_DIR_NAME = "改名工具"
CLI_DIR_NAME = "改名工具-命令行"
GUI_EXE_NAME = "改名工具.exe"

UNINSTALL_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}"
APP_KEY = rf"Software\{APP_ID}"
MENU_DIR_KEY = rf"Software\Classes\Directory\shell\{APP_ID}"
MENU_BG_KEY = rf"Software\Classes\Directory\Background\shell\{APP_ID}"

CREATE_NO_WINDOW = 0x08000000


# ---------------------------------------------------------------- 路径

def program_files_root() -> Path:
    """安装包内 program 文件的位置（单文件 exe 解压后的临时目录）。"""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "app"


def default_install_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "Programs" / APP_NAME


def installed_root() -> Path | None:
    """从注册表读出安装目录；没装过返回 None。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APP_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "InstallPath")
            return Path(value)
    except OSError:
        return None


# ---------------------------------------------------------------- 注册表

def _write_key(path: str, values: dict[str, object]) -> None:
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_WRITE) as key:
        for name, value in values.items():
            kind = winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ
            winreg.SetValueEx(key, name, 0, kind, value)


def _delete_tree(path: str) -> bool:
    """递归删注册表键，返回是否真的删掉了东西。"""
    try:
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ).Close()
    except OSError:
        return False

    def walk(node, sub: str) -> None:
        with winreg.OpenKey(node, sub, 0, winreg.KEY_READ) as key:
            children = []
            index = 0
            while True:
                try:
                    children.append(winreg.EnumKey(key, index))
                    index += 1
                except OSError:
                    break
        for child in children:
            walk(node, rf"{sub}\{child}")
        winreg.DeleteKey(node, sub)

    walk(winreg.HKEY_CURRENT_USER, path)
    return True


def registry_entries(gui_exe: Path, install_root: Path) -> dict[str, dict[str, object]]:
    """要写入的全部注册表内容，单独抽出来便于测试。"""
    gui = str(gui_exe)
    command = f'"{gui}" --open "%1"'
    command_bg = f'"{gui}" --open "%V"'
    return {
        MENU_DIR_KEY: {
            "": "用批量改名工具整理",
            "Icon": gui,
        },
        rf"{MENU_DIR_KEY}\command": {"": command},
        MENU_BG_KEY: {
            "": "用批量改名工具整理此文件夹",
            "Icon": gui,
        },
        rf"{MENU_BG_KEY}\command": {"": command_bg},
        APP_KEY: {
            "InstallPath": str(install_root),
            "Version": VERSION,
            "InstallDate": date.today().strftime("%Y-%m-%d"),
        },
        UNINSTALL_KEY: {
            "DisplayName": APP_NAME,
            "DisplayVersion": VERSION,
            "Publisher": PUBLISHER,
            "DisplayIcon": gui,
            "InstallLocation": str(install_root),
            "UninstallString": f'"{gui}" --uninstall',
            "QuietUninstallString": f'"{gui}" --uninstall --silent',
            "NoModify": 1,
            "NoRepair": 1,
        },
    }


def registry_writable() -> bool:
    """能不能写当前用户的注册表（低完整性目录里运行的 exe 会被拒绝）。"""
    probe = r"Software\_BatchRenameTool_probe"
    try:
        key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, probe, 0, winreg.KEY_WRITE)
        winreg.CloseKey(key)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, probe)
        return True
    except OSError:
        return False


def write_registry(gui_exe: Path, install_root: Path, *, context_menu: bool = True) -> None:
    for path, values in registry_entries(gui_exe, install_root).items():
        if not context_menu and "\\shell\\" in path:
            continue
        _write_key(path, values)
    # 估算占用空间，让「应用和功能」里显示大小
    size_kb = sum(p.stat().st_size for p in install_root.rglob("*") if p.is_file()) // 1024
    _write_key(UNINSTALL_KEY, {"EstimatedSize": size_kb})


def remove_registry() -> None:
    for path in (rf"{MENU_DIR_KEY}\command", MENU_DIR_KEY,
                 rf"{MENU_BG_KEY}\command", MENU_BG_KEY,
                 UNINSTALL_KEY, APP_KEY):
        try:
            _delete_tree(path)
        except OSError:
            pass


# ---------------------------------------------------------------- 快捷方式

def _powershell(script: str) -> None:
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        creationflags=CREATE_NO_WINDOW, capture_output=True, timeout=60,
    )


def _ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def shortcut_paths() -> dict[str, Path]:
    desktop = Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop"
    start_menu = (Path(os.environ.get("APPDATA", "")) /
                  "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return {
        "desktop": desktop / f"{APP_NAME}.lnk",
        "start": start_menu / f"{APP_NAME}.lnk",
    }


def create_shortcut(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    script = (
        "$ws = New-Object -ComObject WScript.Shell\n"
        f"$s = $ws.CreateShortcut({_ps_quote(str(link))})\n"
        f"$s.TargetPath = {_ps_quote(str(target))}\n"
        f"$s.WorkingDirectory = {_ps_quote(str(target.parent))}\n"
        f"$s.Description = {_ps_quote(APP_NAME)}\n"
        "$s.Save()\n"
    )
    _powershell(script)


def remove_shortcuts() -> None:
    for link in shortcut_paths().values():
        try:
            link.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------- 安装 / 卸载

def _log_to(log, message: str) -> None:
    log(message)


def copy_program(src: Path, dest: Path, log=print) -> None:
    if not src.is_dir():
        raise FileNotFoundError(f"安装包内容缺失：{src}")
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dest / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
    _log_to(log, f"程序文件已复制到 {dest}")


REGISTRY_HINT = (
    "无法写入当前用户的注册表（拒绝访问）。\n\n"
    "常见原因：安装程序放在了受限制的目录里（例如 D:\\DeepSeekHarness 这种带"
    "「低完整性」标记的文件夹，在里面生成的 exe 会被系统降权）。\n"
    "办法：把安装程序复制到桌面或其它普通文件夹，再双击运行。"
)


def install(src: Path, dest: Path, *, desktop_shortcut: bool = True,
            context_menu: bool = True, log=print) -> Path:
    if not registry_writable():
        raise PermissionError(REGISTRY_HINT)
    copy_program(src, dest, log=log)
    gui_exe = dest / GUI_DIR_NAME / GUI_EXE_NAME
    if not gui_exe.exists():
        raise FileNotFoundError(f"没有找到 {gui_exe}")
    write_registry(gui_exe, dest, context_menu=context_menu)
    _log_to(log, "注册表写入完成（右键菜单 / 卸载信息）")

    links = shortcut_paths()
    create_shortcut(links["start"], gui_exe)
    _log_to(log, f"开始菜单快捷方式：{links['start']}")
    if desktop_shortcut:
        create_shortcut(links["desktop"], gui_exe)
        _log_to(log, f"桌面快捷方式：{links['desktop']}")
    return gui_exe


def schedule_self_delete(path: Path, *, delay: int = 2) -> None:
    """程序自己删不掉自己，交给一个临时批处理收尾。"""
    bat = Path(tempfile.gettempdir()) / f"_uninstall_{APP_ID}.bat"
    lines = (
        "@echo off\r\n"
        f"timeout /t {delay} /nobreak >nul\r\n"
        f'rmdir /s /q "{path}"\r\n'
        'del "%~f0"\r\n'
    )
    for encoding in ("mbcs", "utf-8"):
        try:
            bat.write_text(lines, encoding=encoding)
            break
        except (LookupError, UnicodeEncodeError):
            continue
    subprocess.Popen(["cmd", "/c", "start", "/min", "", str(bat)],
                     creationflags=CREATE_NO_WINDOW)


def uninstall(install_root: Path, *, remove_files: bool = True, log=print) -> None:
    remove_registry()
    _log_to(log, "注册表项已删除")
    remove_shortcuts()
    _log_to(log, "快捷方式已删除")
    if remove_files and install_root.exists():
        schedule_self_delete(install_root)
        _log_to(log, "程序文件将在程序退出后删除")
