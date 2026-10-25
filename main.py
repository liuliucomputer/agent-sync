"""
Agent Sync - GUI 界面
半透明样式，勾选框选择 Agent，开始/停止同步
纯 tkinter，不依赖 ttk 样式
"""

import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog
import os
from datetime import datetime
import threading
import time
import ctypes
import sys
from engine import detect_agents, SyncEngine, build_sources


# ─── 颜色 ──────────────────────────────────────────────────────────────────────

BG       = "#1e1e2e"
FG       = "#cdd6f4"
FG_DIM   = "#6c7086"
GREEN    = "#a6e3a1"
RED      = "#f38ba8"
BLUE     = "#89b4fa"
YELLOW   = "#f9e2af"
CARD_BG  = "#181825"


# ─── 半透明 ────────────────────────────────────────────────────────────────────

def enable_transparency(window: tk.Tk):
    if sys.platform != "win32":
        return
    try:
        HWND = window.winfo_id()
        ctypes.windll.user32.SetWindowLongW(
            HWND, -20,
            ctypes.windll.user32.GetWindowLongW(HWND, -20) | 0x00080000
        )
        ctypes.windll.user32.SetLayeredWindowAttributes(HWND, 0, 220, 0x0002)
    except Exception:
        pass


# ─── 主窗口 ────────────────────────────────────────────────────────────────────

class AgentSyncApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Agent Sync · 对话同步工具")
        self.root.geometry("580x560")
        self.root.minsize(500, 420)
        self.root.configure(bg=BG)

        self.root.update_idletasks()
        wx = (self.root.winfo_screenwidth() // 2) - (580 // 2)
        wy = (self.root.winfo_screenheight() // 2) - (560 // 2)
        self.root.geometry(f"580x560+{wx}+{wy}")

        enable_transparency(self.root)

        self.agents = detect_agents()
        self.variable_map: dict[str, tk.BooleanVar] = {}
        self.sync_engine: SyncEngine | None = None
        self.sync_thread: threading.Thread | None = None
        self.is_syncing = False

        # UI 引用（供刷新使用）
        self.canvas: tk.Canvas | None = None
        self.scroll_frame: tk.Frame | None = None
        self.status_var: tk.StringVar | None = None
        self.status_label: tk.Label | None = None
        self.path_entries: dict[str, tk.Entry] = {}
        self._custom_paths: dict[str, str] = {}

        self._build_ui()

    # ── 构建 ──

    def _build_ui(self):
        self._clear_except_canvas_area()

        # 标题
        tk.Label(
            self.root, text="⚡ Agent Sync",
            font=("Microsoft YaHei UI", 18, "bold"),
            fg="#ffffff", bg=BG
        ).pack(anchor=tk.W, padx=20, pady=(20, 2))

        tk.Label(
            self.root, text="多 AI Agent 对话记录同步工具",
            font=("Microsoft YaHei UI", 9),
            fg=FG_DIM, bg=BG
        ).pack(anchor=tk.W, padx=20, pady=(0, 10))

        # Agent 提示
        tk.Label(
            self.root,
            text="选择要同步的 Agent（检测到的已安装程序）",
            font=("Microsoft YaHei UI", 9),
            fg=FG_DIM, bg=BG
        ).pack(anchor=tk.W, padx=20, pady=(0, 2))

        # Canvas + Scrollbar 容器
        cf = tk.Frame(self.root, bg=BG)
        cf.pack(fill=tk.BOTH, expand=True, padx=20, pady=(2, 6))

        self.canvas = tk.Canvas(cf, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(cf, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scroll_frame = tk.Frame(self.canvas, bg=BG)

        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        self._render_cards()

        # 按钮行
        bf = tk.Frame(self.root, bg=BG)
        bf.pack(fill=tk.X, padx=20, pady=(6, 2))

        self.start_btn = tk.Button(
            bf, text="▶ 开始同步",
            font=("Microsoft YaHei UI", 11, "bold"),
            fg=BG, bg=BLUE,
            activebackground="#74c7ec", activeforeground=BG,
            relief=tk.FLAT, cursor="hand2",
            command=self._on_start
        )
        self.start_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.stop_btn = tk.Button(
            bf, text="⏹ 停止",
            font=("Microsoft YaHei UI", 11, "bold"),
            fg=BG, bg=RED,
            activebackground="#eba0ac", activeforeground=BG,
            relief=tk.FLAT, cursor="hand2",
            state=tk.DISABLED,
            command=self._on_stop
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 8))

        refresh_btn = tk.Button(
            bf, text="🔄 刷新",
            font=("Microsoft YaHei UI", 11),
            fg=FG, bg="#313244",
            activebackground="#45475a", activeforeground=FG,
            relief=tk.FLAT, cursor="hand2",
            command=self._on_refresh
        )
        refresh_btn.pack(side=tk.LEFT)

        # 状态栏
        self.status_var = tk.StringVar(value="● 就绪 — 选择 Agent 后点击开始")
        self.status_label = tk.Label(
            self.root, textvariable=self.status_var,
            font=("Microsoft YaHei UI", 10),
            fg=GREEN, bg=BG
        )
        self.status_label.pack(anchor=tk.W, padx=20, pady=(6, 2))

        # 日志
        tk.Label(
            self.root, text="同步日志",
            font=("Microsoft YaHei UI", 9),
            fg=FG_DIM, bg=BG
        ).pack(anchor=tk.W, padx=20, pady=(4, 2))

        self.log_box = scrolledtext.ScrolledText(
            self.root, height=6, wrap=tk.WORD, state=tk.DISABLED,
            bg=CARD_BG, fg=FG,
            font=("Consolas", 9),
            insertbackground=FG,
            relief=tk.FLAT,
            selectbackground="#313244",
        )
        self.log_box.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 16))

        self.log_box.tag_config("info",    foreground=BLUE)
        self.log_box.tag_config("success", foreground=GREEN)
        self.log_box.tag_config("error",   foreground=RED)
        self.log_box.tag_config("warn",    foreground=YELLOW)

    def _clear_except_canvas_area(self):
        """重建 UI 时清除旧内容"""
        for w in list(self.root.winfo_children()):
            w.destroy()

    def _render_cards(self):
        if not self.scroll_frame:
            return
        for agent in self.agents:
            card = tk.Frame(
                self.scroll_frame, bg=BG,
                highlightthickness=1, highlightbackground="#313244"
            )
            card.pack(fill=tk.X, pady=4)

            var = tk.BooleanVar(value=agent["exists"])
            self.variable_map[agent["name"]] = var

            tk.Checkbutton(
                card, variable=var,
                bg=BG, fg=FG,
                activebackground=BG, activeforeground=FG,
                selectcolor="#313244",
                command=self._on_agent_toggle,
            ).pack(side=tk.LEFT, padx=(12, 8), pady=8)

            color = GREEN if agent["exists"] else RED
            tk.Label(
                card, text=agent["display"],
                font=("Microsoft YaHei UI", 11),
                fg=color, bg=BG
            ).pack(side=tk.LEFT)

            status = "✓ 已安装" if agent["exists"] else "✗ 未检测到"
            tk.Label(
                card, text=f"  {status}",
                font=("Microsoft YaHei UI", 9),
                fg=color, bg=BG
            ).pack(side=tk.LEFT, padx=(8, 0))

            # 自定义安装路径（可选）
            row = tk.Frame(card, bg=BG)
            row.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 12))
            tk.Label(
                row, text="路径:", fg=FG_DIM, bg=BG,
                font=("Microsoft YaHei UI", 8)
            ).pack(side=tk.LEFT)
            entry = tk.Entry(
                row, bg="#11111b", fg=FG, insertbackground=FG,
                font=("Consolas", 8), relief=tk.FLAT, width=22
            )
            entry.insert(0, self._custom_paths.get(agent["name"], ""))
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4))
            self.path_entries[agent["name"]] = entry
            btn = tk.Button(
                row, text="浏览", fg=FG, bg="#313244", relief=tk.FLAT,
                font=("Microsoft YaHei UI", 8), cursor="hand2",
                command=lambda nm=agent["name"]: self._browse_path(nm)
            )
            btn.pack(side=tk.LEFT)

        tk.Label(
            self.scroll_frame,
            text="  提示：未自动检测到的 Agent，可手动填写其配置目录（如 Claude 的 .claude、WorkBuddy 的 .workbuddy）后勾选",
            font=("Microsoft YaHei UI", 9),
            fg=FG_DIM, bg=BG, wraplength=520, justify=tk.LEFT
        ).pack(anchor=tk.W, pady=(8, 0))

    # ── 事件 ──

    def _on_agent_toggle(self):
        any_selected = any(v.get() for v in self.variable_map.values())
        if not any_selected:
            self.status_var.set("● 警告：未选择任何 Agent")
            if self.status_label:
                self.status_label.configure(fg=RED)
        else:
            self.status_var.set("● 就绪 — 点击「开始同步」启动监听")
            if self.status_label:
                self.status_label.configure(fg=GREEN)

    def _log(self, msg: str, tag: str = "info"):
        self.log_box.configure(state=tk.NORMAL)
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.insert(tk.END, f"[{ts}] {msg}\n", tag)
        self.log_box.see(tk.END)
        self.log_box.configure(state=tk.DISABLED)

    def _browse_path(self, name: str):
        d = filedialog.askdirectory(title=f"选择 {name} 的配置目录")
        if d:
            self._custom_paths[name] = d
            entry = self.path_entries.get(name)
            if entry:
                entry.delete(0, tk.END)
                entry.insert(0, d)

    def _apply_custom_paths(self):
        """把 UI 中填写的自定义路径应用到 agents 列表，覆盖默认 sources"""
        for agent in self.agents:
            name = agent["name"]
            entry = self.path_entries.get(name)
            path = entry.get().strip() if entry else ""
            if not path:
                continue
            if not os.path.isdir(path):
                self._log(f"⚠ {name} 自定义路径不存在: {path}", "warn")
                continue
            agent["sources"] = build_sources(name, path)
            agent["exists"] = True
            self._log(f"✓ 已应用 {name} 自定义路径: {path}", "info")

    def _on_start(self):
        selected = [n for n, v in self.variable_map.items() if v.get()]
        if not selected:
            messagebox.showwarning("提示", "请先选择至少一个 Agent")
            return

        self._apply_custom_paths()
        # 重新校验：所选 agent 必须存在可读取的数据
        missing = [n for n in selected if not next((a for a in self.agents if a["name"] == n), {}).get("exists")]
        if missing:
            messagebox.showwarning(
                "提示",
                f"以下 Agent 未检测到数据，请填写正确的安装路径或取消勾选：\n{', '.join(missing)}"
            )
            return

        self.sync_engine = SyncEngine()
        self.sync_engine.selected_agents = selected
        self.is_syncing = True

        self.start_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)
        self.status_var.set(f"● 同步中 — 监控: {', '.join(selected)}")
        self.status_label.configure(fg=GREEN)
        self._log(f"开始同步，已选择: {', '.join(selected)}", "info")
        self.sync_engine.snapshot(self.agents)
        self._log("初始快照完成", "success")

        def run_sync():
            while self.is_syncing:
                try:
                    results = self.sync_engine.sync(self.agents)
                    if results:
                        for pair, res in results.items():
                            cnt = res.get("count", 0)
                            reason = res.get("reason", "")
                            if cnt > 0 and reason == "ok":
                                path = res.get("path", "")
                                self._log(f"{pair}: +{cnt} 条 → {path}", "success")
                            elif cnt == 0 and reason and reason != "ok":
                                self._log(f"{pair}: {reason}", "warn")
                    else:
                        self._log("本轮无新对话", "info")
                except Exception as e:
                    self._log(f"同步错误: {e}", "error")
                time.sleep(self.sync_engine.poll_interval)

        self.sync_thread = threading.Thread(target=run_sync, daemon=True)
        self.sync_thread.start()

    def _on_stop(self):
        self.is_syncing = False
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)
        self.status_var.set("● 已停止")
        self.status_label.configure(fg=RED)
        self._log("同步已停止", "warn")

    def _on_refresh(self):
        for w in list(self.root.winfo_children()):
            w.destroy()
        self.agents = detect_agents()
        self.variable_map.clear()
        self._build_ui()
        self._log("已刷新 Agent 列表", "info")

    def run(self):
        self.root.mainloop()


def main():
    app = AgentSyncApp()
    app.run()


if __name__ == "__main__":
    main()
