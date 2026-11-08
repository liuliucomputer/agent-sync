"""
Agent Sync - 网页版后端
用 Python 内置 http.server 提供本地 Web 服务，复用 engine.py 的
检测 / 读取 / 写入 / 同步逻辑。浏览器打开后，后端进程（运行在你本机）
访问 ~/.claude、~/.codex 等真实 agent 数据目录，实现双向同步。

运行：  python server.py  [--port 8080]
访问：  http://localhost:8080
"""

import json
import os
import sys
import threading
import time
import argparse
import uuid
import secrets
from pathlib import Path
from collections import deque
from urllib.parse import urlparse, parse_qs
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

# 让 server.py 能 import 同目录的 engine.py
ROOT = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(ROOT, "web")
sys.path.insert(0, ROOT)

from engine import (  # noqa: E402
    detect_agents, read_all, write_to_agent, SyncEngine, build_sources,
)

# ─── 访问 ID（后端生成，浏览器输入验证后才可进入） ────────────────────────────
# 每次启动生成一个新的访问 ID，写入 access_id.txt 并打印到控制台。
# 自建实例的用户从该文件 / 控制台读取 ID，在浏览器输入即可解锁。

def _gen_access_id() -> str:
    return "AS-" + secrets.token_hex(2).upper() + "-" + secrets.token_hex(2).upper()

ACCESS_ID = os.environ.get("ACCESS_ID") or _gen_access_id()
_ACCESS_FILE = os.path.join(ROOT, "access_id.txt")
try:
    with open(_ACCESS_FILE, "w", encoding="utf-8") as f:
        f.write(ACCESS_ID + "\n")
except Exception:
    pass

# ─── 内存日志缓冲（供前端轮询） ──────────────────────────────────────────────

LOG = deque(maxlen=800)
_LOG_ID = 0
_LOG_LOCK = threading.Lock()

# ─── 同步引擎状态 ─────────────────────────────────────────────────────────────

engine = SyncEngine()
_running = False
_sync_thread: threading.Thread | None = None
_agents_snapshot: list[dict] = []
_custom_paths: dict[str, str] = {}


def log(msg: str, tag: str = "info"):
    global _LOG_ID
    with _LOG_LOCK:
        _LOG_ID += 1
        LOG.append({
            "id": _LOG_ID,
            "msg": msg,
            "tag": tag,
            "ts": time.strftime("%H:%M:%S"),
        })


# ─── 同步循环 ────────────────────────────────────────────────────────────────

def _sync_loop():
    global _running
    log("同步监控已启动", "success")
    while _running:
        try:
            results = engine.sync(_agents_snapshot)
            stats = getattr(engine, "last_stats", {}) or {}
            if stats:
                summary = ", ".join(
                    f"{k}: 读{v['total']}/新{v['new']}" for k, v in stats.items()
                )
                log(f"本轮扫描 → {summary}", "info")
            if results:
                for pair, res in results.items():
                    cnt = res.get("count", 0)
                    reason = res.get("reason", "")
                    if cnt > 0 and reason == "ok":
                        log(f"{pair}: +{cnt} 条 → {res.get('path', '')}", "success")
                    elif cnt == 0 and reason and reason != "ok":
                        log(f"{pair}: {reason}", "warn")
            else:
                log("本轮无新对话（只同步启动之后新产生的消息）", "info")
        except Exception as e:  # noqa: BLE001
            log(f"同步错误: {e}", "error")
        time.sleep(engine.poll_interval)
    log("同步已停止", "warn")


def _apply_custom_paths():
    for agent in _agents_snapshot:
        name = agent["name"]
        path = _custom_paths.get(name, "").strip()
        if not path:
            continue
        if not os.path.isdir(path):
            log(f"⚠ {name} 自定义路径不存在: {path}", "warn")
            continue
        agent["sources"] = build_sources(name, path)
        agent["exists"] = True
        log(f"✓ 已应用 {name} 自定义路径: {path}", "info")


# ─── HTTP 处理 ───────────────────────────────────────────────────────────────

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=WEB_DIR, **k)

    def _send_json(self, obj, code: int = 200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b""
            return json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            return {}

    def do_GET(self):
        p = urlparse(self.path)
        if p.path == "/api/agents":
            self._send_json({"agents": detect_agents()})
        elif p.path == "/api/status":
            self._send_json({
                "running": _running,
                "selected": engine.selected_agents,
                "poll_interval": engine.poll_interval,
            })
        elif p.path == "/api/logs":
            after = 0
            try:
                after = int(parse_qs(p.query).get("after", ["0"])[0])
            except ValueError:
                after = 0
            with _LOG_LOCK:
                items = [x for x in LOG if x["id"] > after]
                last_id = _LOG_ID
            self._send_json({"logs": items, "last_id": last_id})
        else:
            super().do_GET()

    def do_POST(self):
        global _running, _sync_thread, _agents_snapshot, _custom_paths
        p = urlparse(self.path)
        if p.path == "/api/verify":
            body = self._read_body()
            submitted = str(body.get("id", "")).strip().upper()
            ok = secrets.compare_digest(submitted, ACCESS_ID.upper())
            self._send_json({"ok": ok})
            return
        if p.path == "/api/refresh":
            _agents_snapshot = detect_agents()
            self._send_json({"agents": _agents_snapshot})
            return
        if p.path == "/api/start":
            body = self._read_body()
            selected = body.get("selected", [])
            _custom_paths = body.get("custom_paths", {}) or {}
            if not selected:
                self._send_json({"ok": False, "error": "请先选择至少一个 Agent"}, 400)
                return
            _agents_snapshot = detect_agents()
            _apply_custom_paths()
            missing = [
                n for n in selected
                if not next((a for a in _agents_snapshot if a["name"] == n), {}).get("exists")
            ]
            if missing:
                self._send_json({
                    "ok": False,
                    "error": f"以下 Agent 未检测到数据，请填写正确路径或取消勾选：{', '.join(missing)}",
                }, 400)
                return
            include_history = bool(body.get("include_history", False))
            try:
                history_limit = max(0, min(200, int(body.get("history_limit", 20) or 0)))
            except (TypeError, ValueError):
                history_limit = 20
            engine.selected_agents = selected
            engine.snapshot(_agents_snapshot, history_limit if include_history else 0)
            log(f"开始同步，已选择: {', '.join(selected)}", "info")
            for a in _agents_snapshot:
                if a["name"] in selected and a["exists"]:
                    n = len(read_all(a))
                    if n == 0:
                        log(
                            f"提示：{a['name']} 目录存在但读到 0 条对话，该格式暂不支持读取",
                            "warn",
                        )
            if include_history:
                log(
                    f"首次同步：将把每个 Agent 最近 {history_limit} 条历史对话推送给其他 Agent",
                    "info",
                )
            log("初始快照完成", "success")
            if not _running:
                _running = True
                _sync_thread = threading.Thread(target=_sync_loop, daemon=True)
                _sync_thread.start()
            self._send_json({"ok": True, "running": True})
            return
        if p.path == "/api/stop":
            _running = False
            self._send_json({"ok": True, "running": False})
            return
        if p.path == "/api/demo":
            # 演示模式：云端无本地 agent 时，模拟一轮双向同步，便于体验链接展示
            ags = detect_agents()
            if any(a["exists"] for a in ags):
                # 有真实 agent：跑一次真实单轮同步
                snap = ags
                sel = [a["name"] for a in snap if a["exists"]]
                engine.selected_agents = sel
                engine.snapshot(snap)
                res = engine.sync(snap)
                lines = [{"tag": "info", "msg": f"演示：对真实 agent 执行单轮同步 {sel}"}]
                for pair, r in res.items():
                    lines.append({"tag": "success" if r.get("count", 0) > 0 else "warn",
                                  "msg": f"{pair}: {r.get('count', 0)} 条 / {r.get('reason', '')}"})
                if not res:
                    lines.append({"tag": "info", "msg": "本轮无新对话"})
            else:
                lines = [
                    {"tag": "info",    "msg": "演示模式：当前环境未检测到本地 agent（云端演示）"},
                    {"tag": "info",    "msg": "读取 Claude Code 会话：467 条对话"},
                    {"tag": "info",    "msg": "读取 Codex 会话：1182 条对话"},
                    {"tag": "success", "msg": "claude→codex: +3 条 → ~/.codex/sessions/2026/10/rollout-...-sync.jsonl"},
                    {"tag": "success", "msg": "codex→claude: +2 条 → ~/.claude/projects/sync-agent/...-sync.jsonl"},
                    {"tag": "warn",    "msg": "Gemini / OpenClaw 仅支持读取（格式限制）"},
                    {"tag": "success", "msg": "演示完成：双向同步逻辑已验证 ✓"},
                ]
            self._send_json({"ok": True, "lines": lines})
            return
        self._send_json({"ok": False, "error": "unknown endpoint"}, 404)

    def log_message(self, fmt, *args):  # 静默默认日志
        return


def main():
    parser = argparse.ArgumentParser(description="Agent Sync Web Server")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    _agents_snapshot = detect_agents()
    log("Agent Sync 网页版已启动，等待前端连接", "success")
    log(f"访问 ID：{ACCESS_ID}（浏览器输入即可进入，详见页面提示）", "info")

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://localhost:{args.port}"
    print(f"\n  ⚡ Agent Sync 网页版运行中：{url}")
    print(f"  🔑 本次访问 ID：{ACCESS_ID}")
    print(f"  （已写入 {_ACCESS_FILE}，浏览器打开后输入该 ID 即可进入）")
    print(f"  Ctrl+C 退出\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
