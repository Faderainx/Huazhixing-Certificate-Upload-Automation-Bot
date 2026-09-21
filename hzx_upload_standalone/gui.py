#!/usr/bin/env python3
"""
华之星证书上传 —— GUI 外壳（tkinter，Python 3.12 自带，零额外依赖）。
底层逻辑全部复用 main.run_pipeline，本文件只做「界面 + 实时日志 + 结果展示」，不重写业务。
双击 启动GUI.bat 即可运行。
"""
import os
import sys
import threading
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

PACKAGE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PACKAGE_DIR))

from main import run_pipeline  # noqa: E402


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("华之星证书上传 - 独立版")
        self.root.minsize(720, 560)
        self.running = False

        # ---- 顶部：任务包目录 ----
        f0 = tk.Frame(root)
        f0.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(f0, text="任务包目录：").pack(side="left")
        self.pkg_var = tk.StringVar(value=str(PACKAGE_DIR.parent))
        tk.Entry(f0, textvariable=self.pkg_var, width=60).pack(side="left", fill="x", expand=True, padx=4)
        tk.Button(f0, text="浏览...", command=self._browse).pack(side="left")

        # ---- 选项区 ----
        f1 = tk.Frame(root)
        f1.pack(fill="x", padx=10, pady=2)
        self.level1_var = tk.BooleanVar(value=False)
        self.level2_var = tk.BooleanVar(value=True)
        self.dry_var = tk.BooleanVar(value=True)
        self.save_cred_var = tk.BooleanVar(value=False)
        tk.Checkbutton(f1, text="一级代办（截图上传，待 API）", variable=self.level1_var).pack(side="left", padx=6)
        tk.Checkbutton(f1, text="二级代办（证书上传）", variable=self.level2_var).pack(side="left", padx=6)
        tk.Checkbutton(f1, text="模拟运行（不实际上传）", variable=self.dry_var).pack(side="left", padx=6)
        tk.Checkbutton(f1, text="保存凭证", variable=self.save_cred_var).pack(side="left", padx=6)

        # ---- 日期 / 账号 / 密码 ----
        f2 = tk.Frame(root)
        f2.pack(fill="x", padx=10, pady=2)
        tk.Label(f2, text="日期(一级用)：").pack(side="left")
        self.date_var = tk.StringVar()
        tk.Entry(f2, textvariable=self.date_var, width=14).pack(side="left", padx=2)
        tk.Label(f2, text="  账号：").pack(side="left")
        self.user_var = tk.StringVar()
        tk.Entry(f2, textvariable=self.user_var, width=18).pack(side="left", padx=2)
        tk.Label(f2, text="  密码：").pack(side="left")
        self.pass_var = tk.StringVar()
        tk.Entry(f2, textvariable=self.pass_var, width=18, show="*").pack(side="left", padx=2)

        # ---- 操作按钮 ----
        f3 = tk.Frame(root)
        f3.pack(fill="x", padx=10, pady=(6, 2))
        self.run_btn = tk.Button(f3, text="开始运行", command=self._on_run, bg="#2e7d32", fg="white", width=12)
        self.run_btn.pack(side="left")
        tk.Button(f3, text="清空日志", command=self._clear_log, width=10).pack(side="left", padx=6)
        tk.Button(f3, text="打开结果目录", command=self._open_results, width=12).pack(side="left")

        # ---- 日志区 ----
        tk.Label(root, text="运行日志：").pack(anchor="w", padx=10)
        self.log = scrolledtext.ScrolledText(root, height=18, state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=10, pady=(2, 6))
        self.log.tag_config("ERROR", foreground="#c62828")
        self.log.tag_config("WARNING", foreground="#ef6c00")
        self.log.tag_config("INFO", foreground="#222222")
        self.log.tag_config("DEBUG", foreground="#777777")

        # ---- 状态栏 ----
        self.status_var = tk.StringVar(value="就绪。默认模拟运行，先点「开始运行」预览映射。")
        tk.Label(root, textvariable=self.status_var, relief="sunken", anchor="w").pack(fill="x", side="bottom")

    # ---------- 交互 ----------
    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.pkg_var.get() or str(PACKAGE_DIR.parent))
        if d:
            self.pkg_var.set(d)

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _open_results(self):
        p = PACKAGE_DIR / "results"
        try:
            os.startfile(str(p))
        except Exception as e:  # noqa: BLE001
            messagebox.showinfo("提示", f"无法打开目录：{e}\n路径：{p}")

    def _on_run(self):
        if self.running:
            return
        pkg = self.pkg_var.get().strip()
        if not pkg:
            messagebox.showwarning("缺少任务包", "请先选择任务包目录。")
            return
        if not self.level1_var.get() and not self.level2_var.get():
            messagebox.showwarning("未选层级", "请至少勾选「一级代办」或「二级代办」。")
            return

        opts = {
            "task_package": pkg,
            "level1": self.level1_var.get(),
            "level2": self.level2_var.get(),
            "dry_run": self.dry_var.get(),
            "date": self.date_var.get().strip(),
            "username": self.user_var.get().strip() or None,
            "password": self.pass_var.get() or None,
            "save_cred": self.save_cred_var.get(),
        }
        self.running = True
        self.run_btn.configure(state="disabled", text="运行中...")
        self.status_var.set("运行中...")
        self._append("INFO", "=== 开始 ===")

        t = threading.Thread(target=self._worker, args=(opts,), daemon=True)
        t.start()

    def _worker(self, opts):
        try:
            summary = run_pipeline(opts, log_sink=self._log_sink)
        except Exception as e:  # noqa: BLE001
            self._log_sink("ERROR", f"运行异常：{e}")
            summary = None
        # 回主线程更新 UI
        self.root.after(0, self._on_done, summary)

    def _log_sink(self, level: str, message: str):
        # 来自工作线程，必须回到主线程操作控件
        self.root.after(0, self._append, level, message)

    def _append(self, level: str, message: str):
        tag = level if level in ("ERROR", "WARNING", "INFO", "DEBUG") else "INFO"
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n", tag)
        self.log.configure(state="disabled")
        self.log.see("end")

    def _on_done(self, summary):
        self.running = False
        self.run_btn.configure(state="normal", text="开始运行")
        if summary:
            self.status_var.set(
                f"完成：共 {summary.get('total', 0)} | 成功 {summary.get('success', 0)} | "
                f"未找到 {summary.get('not_found', 0)} | 缺文件 {summary.get('no_file', 0)} | "
                f"错误 {summary.get('error', 0)}"
            )
        else:
            self.status_var.set("结束（无二级汇总或异常，详见日志）。")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
