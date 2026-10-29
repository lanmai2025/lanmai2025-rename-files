# -*- coding: utf-8 -*-
"""图形界面（tkinter，不依赖浏览器）。"""
from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import core

TEMPLATE_PRESETS = (
    core.DEFAULT_TEMPLATE,
    "{姓名}-{学号}-第4次作业",
    "{学号}-{姓名}-{作业}",
    "{姓名}_{学号}_{作业}",
    "第4次作业-{学号}-{姓名}",
)

STATUS_COLORS = {
    core.STATUS_RENAME: ("#1b5e20", "#e8f5e9"),
    core.STATUS_SAME: ("#616161", "#f5f5f5"),
    core.STATUS_CONFLICT: ("#e65100", "#fff3e0"),
    core.STATUS_EXISTS: ("#e65100", "#fff3e0"),
    core.STATUS_ILLEGAL: ("#b71c1c", "#ffebee"),
    core.STATUS_UNPARSED: ("#b71c1c", "#ffebee"),
}


class RenameApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("批量改名工具 · 学号-姓名-作业")
        self.geometry("1000x640")
        self.minsize(820, 520)
        self.plan: core.Plan | None = None
        self._font = ("Microsoft YaHei UI", 10)

        self._build_style()
        self._build_widgets()

    # ------------------------------------------------------------ 界面
    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure(".", font=self._font)
        style.configure("Treeview", rowheight=26, font=self._font)
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 12, "bold"))
        style.configure("Hint.TLabel", foreground="#666666")

    def _build_widgets(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)

        ttk.Label(root, text="文件夹", width=6).grid(row=0, column=0, sticky="w", pady=4)
        self.dir_var = tk.StringVar()
        self.dir_entry = ttk.Entry(root, textvariable=self.dir_var)
        self.dir_entry.grid(row=0, column=1, sticky="ew", padx=6)
        self.dir_entry.bind("<Return>", self._on_enter)
        ttk.Button(root, text="浏览…", command=self.choose_folder, width=8).grid(row=0, column=2)

        ttk.Label(root, text="模板", width=6).grid(row=1, column=0, sticky="w", pady=4)
        self.template_var = tk.StringVar(value=core.DEFAULT_TEMPLATE)
        self.combo = ttk.Combobox(root, textvariable=self.template_var, values=TEMPLATE_PRESETS)
        self.combo.grid(row=1, column=1, sticky="ew", padx=6)
        self.combo.bind("<Return>", self._on_enter)
        ttk.Label(root, text="常用格式", style="Hint.TLabel").grid(row=1, column=2, sticky="w")

        hint = ttk.Label(
            root,
            text="占位符：{学号}  {姓名}  {作业}  {内容}    例：{学号}-{姓名}-第4次作业"
                 "    ·    「第4次作业」也可直接写成固定文字",
            style="Hint.TLabel",
        )
        hint.grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 6))

        opts = ttk.Frame(root)
        opts.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        self.recursive_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="包含子文件夹", variable=self.recursive_var).pack(side="left")
        ttk.Label(opts, text="学号最少位数：", style="Hint.TLabel").pack(side="left", padx=(16, 2))
        self.id_len_var = tk.StringVar(value="6")
        ttk.Spinbox(opts, from_=4, to=15, width=4, textvariable=self.id_len_var).pack(side="left")

        bar = ttk.Frame(root)
        bar.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        ttk.Button(bar, text="预览", command=self.preview).pack(side="left")
        self.apply_btn = ttk.Button(bar, text="开始改名", command=self.apply, state="disabled")
        self.apply_btn.pack(side="left", padx=6)
        ttk.Button(bar, text="撤销上次改名", command=self.undo).pack(side="left", padx=6)
        ttk.Button(bar, text="打开日志目录", command=self.open_log_dir).pack(side="left")

        table = ttk.Frame(root)
        table.grid(row=5, column=0, columnspan=3, sticky="nsew")
        root.rowconfigure(5, weight=1)
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)

        columns = ("old", "new", "status")
        self.tree = ttk.Treeview(table, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("old", text="原文件名")
        self.tree.heading("new", text="新文件名")
        self.tree.heading("status", text="状态")
        self.tree.column("old", width=380, anchor="w")
        self.tree.column("new", width=380, anchor="w")
        self.tree.column("status", width=110, anchor="center", stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self.show_detail)
        for status, (fg, bg) in STATUS_COLORS.items():
            self.tree.tag_configure(status, foreground=fg, background=bg)

        self.detail_var = tk.StringVar(value="选中一行可查看识别结果")
        ttk.Label(root, textvariable=self.detail_var, style="Hint.TLabel").grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(6, 0)
        )

        self.status_var = tk.StringVar(value="在「文件夹」里粘贴路径后按回车，或点「浏览…」选择")
        ttk.Label(root, textvariable=self.status_var, style="Title.TLabel").grid(
            row=7, column=0, columnspan=3, sticky="w", pady=(4, 0)
        )

    # ------------------------------------------------------------ 行为
    def choose_folder(self) -> None:
        folder = filedialog.askdirectory(title="选择要改名的文件夹")
        if folder:
            self.dir_var.set(folder)
            self.preview()

    def _on_enter(self, _event=None):
        """在地址框/模板框里按回车直接预览。"""
        self.preview()
        return "break"

    def _folder(self) -> Path | None:
        raw = self.dir_var.get().strip().strip('"').strip("'").strip()
        if not raw:
            messagebox.showwarning("提示", "先输入或选择要处理的文件夹")
            return None
        raw = os.path.expandvars(os.path.expanduser(raw))
        folder = Path(raw)
        if folder.is_file():  # 粘贴的是文件路径时，用它所在的文件夹
            folder = folder.parent
        if not folder.is_dir():
            messagebox.showerror("出错", f"文件夹不存在：\n{folder}")
            return None
        return folder

    def preview(self) -> None:
        folder = self._folder()
        if folder is None:
            return
        self.dir_var.set(str(folder))
        template = self.template_var.get().strip()
        try:
            id_len = int(self.id_len_var.get())
        except ValueError:
            id_len = 6
        try:
            self.plan = core.build_plan(
                folder, template=template, recursive=self.recursive_var.get(), id_min_len=id_len
            )
        except core.TemplateError as exc:
            messagebox.showerror("模板有误", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("出错", str(exc))
            return

        self.tree.delete(*self.tree.get_children())
        for index, entry in enumerate(self.plan.entries):
            detail = entry.new_name or entry.reason
            self.tree.insert(
                "", "end", iid=str(index), values=(entry.old_name, detail, entry.status),
                tags=(entry.status,),
            )
        self.detail_var.set("选中一行可查看识别结果")
        todo = len(self.plan.to_rename)
        self.apply_btn.configure(state="normal" if todo else "disabled")
        if self.plan.entries:
            self.status_var.set(
                f"共 {len(self.plan.entries)} 个文件，{todo} 个待改名，"
                f"{self.plan.count(core.STATUS_SAME)} 个已符合，"
                f"{len(self.plan.entries) - todo - self.plan.count(core.STATUS_SAME)} 个有问题"
            )
        else:
            self.status_var.set("这个文件夹里没有文件")

    def show_detail(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection or self.plan is None:
            return
        entry = self.plan.entries[int(selection[0])]
        parts = entry.parts or {}
        order = ("学号", "姓名", "作业", "内容")
        detail = "  ·  ".join(f"{key}={parts[key]}" for key in order if parts.get(key))
        if not detail:
            detail = "没有识别出任何字段"
        if entry.reason:
            detail += f"    （{entry.reason}）"
        self.detail_var.set(detail)

    def apply(self) -> None:
        if self.plan is None:
            return
        todo = self.plan.to_rename
        if not todo:
            messagebox.showinfo("提示", "没有需要改名的文件")
            return
        if not messagebox.askyesno(
            "确认改名前请核对",
            f"即将把 {len(todo)} 个文件改成模板格式：\n{self.plan.template}\n\n"
            f"目录：{self.plan.folder}\n\n改名后可使用「撤销上次改名」还原。继续吗？",
        ):
            return
        try:
            result = core.apply_plan(self.plan)
        except Exception as exc:
            messagebox.showerror("改名失败", str(exc))
            return
        msg = f"已改名 {result.renamed} 个文件"
        if result.failed:
            msg += f"\n失败 {len(result.failed)} 个：\n" + "\n".join(
                f"· {name}（{reason}）" for name, reason in result.failed[:10]
            )
        if result.log_path:
            msg += f"\n\n日志：\n{result.log_path}"
        messagebox.showinfo("完成", msg)
        self.preview()

    def undo(self) -> None:
        log_dir = core.default_log_dir()
        logs = sorted(log_dir.glob("改名日志-*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not logs:
            messagebox.showinfo("提示", f"日志目录里没有可撤销的记录：\n{log_dir}")
            return
        latest = logs[0]
        if not messagebox.askyesno(
            "撤销确认",
            f"按下面这份日志把文件名还原？\n{latest}\n\n（只会还原日志里记录为「成功」的文件）",
        ):
            return
        restored, failed = core.undo_log(latest)
        msg = f"已还原 {restored} 个文件"
        if failed:
            msg += "\n未还原：\n" + "\n".join(f"· {n}（{r}）" for n, r in failed[:10])
        messagebox.showinfo("撤销完成", msg)
        self.preview()

    def open_log_dir(self) -> None:
        log_dir = core.default_log_dir()
        try:
            os.startfile(log_dir)  # type: ignore[attr-defined]
        except Exception:
            messagebox.showinfo("日志目录", str(log_dir))


def run(initial_dir: str | None = None) -> int:
    try:  # 高分屏下避免界面发虚
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = RenameApp()
    if initial_dir:
        app.dir_var.set(initial_dir)
        app.after(120, app.preview)
    app.mainloop()
    return 0


def run_uninstall(silent: bool = False) -> int:
    """卸载：清注册表、快捷方式，程序文件交给延迟批处理删除。"""
    import regtool

    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent.parent
    else:
        root = Path(__file__).resolve().parent.parent

    registered = regtool.installed_root()
    if registered and registered.resolve() != root.resolve():
        root = registered.resolve()

    if silent:
        regtool.uninstall(root)
        return 0

    window = tk.Tk()
    window.withdraw()
    try:
        if not messagebox.askyesno(
            "卸载批量改名工具",
            f"将删除程序目录：\n{root}\n\n"
            "同时移除右键菜单、开始菜单/桌面快捷方式和注册表项。\n"
            "改名日志在「用户目录\\改名日志」里，不受影响。\n\n确定卸载吗？",
        ):
            return 0
        regtool.uninstall(root)
        messagebox.showinfo("已卸载", "右键菜单和快捷方式已移除，程序文件会在几秒后自动删除。")
        return 0
    except Exception as exc:
        messagebox.showerror("卸载失败", str(exc))
        return 1
    finally:
        window.destroy()
