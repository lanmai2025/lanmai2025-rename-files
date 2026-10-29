# -*- coding: utf-8 -*-
"""安装程序界面（tkinter 向导）。"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import regtool


class InstallerWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{regtool.APP_NAME} 安装程序")
        self.geometry("620x520")
        self.minsize(560, 460)
        self.resizable(True, True)
        self._font = ("Microsoft YaHei UI", 10)
        self._busy = False
        self._style()
        self._widgets()
        self._show_installed_state()

    # ------------------------------------------------------------ 界面
    def _style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure(".", font=self._font)
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 14, "bold"))
        style.configure("Hint.TLabel", foreground="#666666")

    def _widgets(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(5, weight=1)

        ttk.Label(root, text=f"{regtool.APP_NAME}  v{regtool.VERSION}",
                  style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            root,
            text="把各种格式的作业文件名统一成「学号-姓名-第N次作业」。\n"
                 "安装会复制程序、创建快捷方式，并写入当前用户的注册表项（不需要管理员权限）。",
            style="Hint.TLabel", justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(4, 10))

        box = ttk.LabelFrame(root, text="安装选项", padding=10)
        box.grid(row=2, column=0, sticky="ew")
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text="安装位置").grid(row=0, column=0, sticky="w")
        self.dir_var = tk.StringVar(value=str(regtool.default_install_dir()))
        ttk.Entry(box, textvariable=self.dir_var).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(box, text="浏览…", command=self._browse, width=8).grid(row=0, column=2)

        self.desktop_var = tk.BooleanVar(value=True)
        self.menu_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(box, text="创建桌面快捷方式",
                        variable=self.desktop_var).grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Checkbutton(box, text="添加右键菜单「用批量改名工具整理」（推荐）",
                        variable=self.menu_var).grid(row=2, column=1, sticky="w")

        self.installed_var = tk.StringVar(value="")
        ttk.Label(root, textvariable=self.installed_var,
                  style="Hint.TLabel").grid(row=3, column=0, sticky="w", pady=(8, 0))

        bar = ttk.Frame(root)
        bar.grid(row=4, column=0, sticky="ew", pady=(10, 6))
        self.install_btn = ttk.Button(bar, text="开始安装", command=self._install, width=14)
        self.install_btn.pack(side="left")
        self.uninstall_btn = ttk.Button(bar, text="卸载", command=self._uninstall, width=10)
        self.uninstall_btn.pack(side="left", padx=8)
        ttk.Button(bar, text="打开说明", command=self._open_readme, width=10).pack(side="left")
        ttk.Button(bar, text="退出", command=self.destroy, width=8).pack(side="right")

        log_box = ttk.LabelFrame(root, text="安装日志", padding=6)
        log_box.grid(row=5, column=0, sticky="nsew")
        log_box.columnconfigure(0, weight=1)
        log_box.rowconfigure(0, weight=1)
        self.log_text = tk.Text(log_box, height=9, wrap="word",
                                font=("Microsoft YaHei UI", 9), state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_box, orient="vertical", command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)

    # ------------------------------------------------------------ 逻辑
    def log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _show_installed_state(self) -> None:
        root = regtool.installed_root()
        if root:
            self.installed_var.set(f"检测到已安装版本：{root}（再次安装将覆盖更新）")
            self.install_btn.configure(text="重新安装")
        else:
            self.installed_var.set("当前未安装")
        if not regtool.registry_writable():
            self.installed_var.set(
                "⚠ 当前目录不能写注册表（安装包在受限制的文件夹里）："
                "请把安装程序复制到桌面后再运行"
            )
            self.log("警告：无法写入注册表，先把安装程序复制到桌面再运行。")
            self.log(regtool.REGISTRY_HINT)

    def _browse(self) -> None:
        folder = filedialog.askdirectory(title="选择安装位置",
                                         initialdir=str(regtool.default_install_dir().parent))
        if folder:
            self.dir_var.set(folder)

    def _install(self) -> None:
        if self._busy:
            return
        dest = Path(self.dir_var.get().strip().strip('"'))
        if not dest.is_absolute():
            messagebox.showerror("路径不对", "请填写完整路径，例如：\n" + str(regtool.default_install_dir()))
            return
        root = regtool.installed_root()
        if root and root.resolve() != dest.resolve():
            if not messagebox.askyesno(
                "已经装过一个版本",
                f"检测到 {root} 已经安装。\n继续会在 {dest} 再装一份，要换位置建议先卸载旧的。\n\n继续吗？",
            ):
                return
        available = regtool.program_files_root()
        if not available.is_dir():
            messagebox.showerror("安装包损坏", f"找不到安装内容：\n{available}")
            return

        self._set_busy(True)
        try:
            regtool.install(
                available, dest,
                desktop_shortcut=self.desktop_var.get(),
                context_menu=self.menu_var.get(),
                log=self.log,
            )
        except PermissionError as exc:
            self.log(f"失败：{exc}")
            messagebox.showerror("无法写入注册表", str(exc))
            return
        except Exception as exc:  # 安装过程任何异常都别让向导卡死
            self.log(f"失败：{exc}")
            messagebox.showerror("安装失败", str(exc))
            return
        finally:
            self._set_busy(False)

        self._show_installed_state()
        if messagebox.askyesno("安装完成", f"已安装到：\n{dest}\n\n现在打开程序吗？"):
            gui_exe = dest / regtool.GUI_DIR_NAME / regtool.GUI_EXE_NAME
            try:
                import os
                os.startfile(gui_exe)  # type: ignore[attr-defined]
            except Exception as exc:
                messagebox.showwarning("启动失败", f"请自己双击打开：\n{gui_exe}\n\n{exc}")
        self.destroy()

    def _uninstall(self) -> None:
        if self._busy:
            return
        root = regtool.installed_root() or Path(self.dir_var.get().strip())
        if not root.exists():
            messagebox.showinfo("提示", "没有找到已安装的程序。")
            return
        if not messagebox.askyesno(
            "确认卸载",
            f"将删除：\n{root}\n\n并移除右键菜单、快捷方式和注册表项。\n"
            "改名日志会保留在程序目录外，不受影响。\n\n确定卸载吗？",
        ):
            return
        self._set_busy(True)
        try:
            regtool.uninstall(root, log=self.log)
        finally:
            self._set_busy(False)
        messagebox.showinfo("卸载完成", "已移除。程序文件会在几秒后自动删除。")
        self.destroy()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        for btn in (self.install_btn, self.uninstall_btn):
            btn.configure(state=state)
        self.update_idletasks()

    def _open_readme(self) -> None:
        candidates = (
            regtool.program_files_root() / "使用说明.md",
            Path(__file__).resolve().parent.parent / "docs" / "使用说明.md",
        )
        for readme in candidates:
            if readme.exists():
                try:
                    import os
                    os.startfile(readme)  # type: ignore[attr-defined]
                except Exception:
                    messagebox.showinfo("使用说明", str(readme))
                return
        messagebox.showinfo("使用说明", "安装包里没有找到说明文件。")


def run() -> int:
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = InstallerWindow()
    app.mainloop()
    return 0
