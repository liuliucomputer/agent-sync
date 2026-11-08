"""
Agent Sync - 多 AI Agent 对话记录同步工具
自动检测已安装的 Agent，双向同步对话记录
支持环境变量自定义安装路径
"""

import os
import sys
import json
import sqlite3
import time
import threading
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional

# ─── 统一中间格式 ──────────────────────────────────────────────────────────────
# 所有对话统一为: {role, text, timestamp, session_id}

class Msg:
    def __init__(self, role: str, text: str, ts: float = 0, session_id: str = ""):
        self.role = role
        self.text = text
        self.ts = ts or time.time()
        self.session_id = session_id

    def to_dict(self):
        return {"role": self.role, "text": self.text, "timestamp": self.ts, "session_id": self.session_id}


# ─── Agent 检测（支持环境变量覆盖安装位置） ─────────────────────────────────────

def _cfg(agent: str, default_rel: list[str]) -> str:
    """优先读环境变量，否则用默认相对路径"""
    env_map = {
        "claude": "CLAUDE_CONFIG_DIR",
        "codex": "CODEX_HOME",
        "openclaw": "OPENCLAW_STATE_DIR",
        "qclaw": "QCLAW_CONFIG_DIR",
        "gemini": "GEMINI_CONFIG_DIR",
        "workbuddy": "WORKBUDDY_CONFIG_DIR",
        "opencode": "OPENCODE_CONFIG_DIR",
        "mavis": "MAVIS_CONFIG_DIR",
    }
    env = env_map.get(agent)
    if env and os.environ.get(env):
        return os.environ[env]
    return str(Path.home().joinpath(*default_rel))

def build_sources(name: str, root: str) -> dict:
    """根据给定「配置根目录」重建该 agent 的 sources 字典。
    root 指各自的数据目录（如 Claude 的 .claude、WorkBuddy 的 .workbuddy）。
    """
    root = root.rstrip("/\\")
    if name == "claude":
        return {
            "history": os.path.join(root, "history.jsonl"),
            "projects": os.path.join(root, "projects"),
        }
    if name == "codex":
        return {"sessions": os.path.join(root, "sessions")}
    if name == "openclaw":
        return {"db": os.path.join(root, "state", "openclaw.sqlite")}
    if name == "qclaw":
        return {"root": root}
    if name == "gemini":
        return {"root": root}
    if name == "workbuddy":
        return {
            "ws_sessions": os.path.join(root, "workspace", "sessions"),
            "sessions": os.path.join(root, "sessions"),
        }
    if name == "opencode":
        return {"root": root}
    if name == "mavis":
        return {"root": root}
    return {}


def detect_agents():
    """返回 [{name, display, exists, sources, env_var}] 列表
    sources 现在是 dict: {key: path}
    """
    checks = [
        ("claude",     "Claude Code",   "CLAUDE_CONFIG_DIR"),
        ("codex",      "Codex (OpenAI)", "CODEX_HOME"),
        ("openclaw",   "OpenClaw",      "OPENCLAW_STATE_DIR"),
        ("qclaw",      "QClaw",         "QCLAW_CONFIG_DIR"),
        ("gemini",     "Gemini CLI",    "GEMINI_CONFIG_DIR"),
        ("workbuddy",  "WorkBuddy",     "WORKBUDDY_CONFIG_DIR"),
        ("opencode",   "OpenCode",      "OPENCODE_CONFIG_DIR"),
        ("mavis",      "Mavis",         "MAVIS_CONFIG_DIR"),
    ]

    result = []
    for name, display, env_name in checks:
        root = _cfg(name, _default_rel(name))
        sources = build_sources(name, root)
        exists = any(os.path.exists(p) for p in sources.values())
        result.append({
            "name": name,
            "display": display,
            "exists": exists,
            "env_var": env_name,
            "sources": sources,
        })
    return result


def _default_rel(name: str) -> list[str]:
    """各 agent 默认相对家目录的路径（配置根目录）"""
    return {
        "claude":    [".claude"],
        "codex":     [".codex"],
        "openclaw":  [".openclaw"],
        "qclaw":     [".qclaw"],
        "gemini":    [".config", "gemini"],
        "workbuddy": [".workbuddy"],
        "opencode":  [".opencode"],
        "mavis":     [".mavis"],
    }.get(name, [f".{name}"])


# ─── 读取器 ────────────────────────────────────────────────────────────────────

def _ts(d: dict) -> float:
    """统一时间戳提取，支持毫秒或 ISO 字符串"""
    ts = d.get("timestamp")
    if not ts:
        return 0
    if isinstance(ts, (int, float)):
        return ts / 1000 if ts > 1e12 else ts  # 毫秒转秒
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        except:
            return 0
    return 0


def read_claude_sessions(projects_path: str) -> list[Msg]:
    """从 Claude projects 目录读取所有对话消息"""
    msgs = []
    if not os.path.isdir(projects_path):
        return msgs
    for proj_dir in os.listdir(projects_path):
        proj_path = os.path.join(projects_path, proj_dir)
        if not os.path.isdir(proj_path):
            continue
        for sf in os.listdir(proj_path):
            if not sf.endswith(".jsonl"):
                continue
            fp = os.path.join(proj_path, sf)
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                            t = d.get("type")
                            sid = d.get("sessionId", sf.replace(".jsonl", ""))
                            msg_data = d.get("message", {})
                            content = msg_data.get("content", [])
                            text = ""
                            if isinstance(content, list):
                                parts = []
                                for c in content:
                                    if isinstance(c, dict) and c.get("type") == "text":
                                        parts.append(c.get("text", ""))
                                text = "\n".join(parts)
                            elif isinstance(content, str):
                                text = content
                            if text and t in ("user", "assistant"):
                                msgs.append(Msg(t, text, _ts(d), sid))
                        except json.JSONDecodeError:
                            continue
            except Exception:
                continue
    # 也读 history.jsonl（入口摘要，只记 user 消息）
    hp = os.path.join(os.path.dirname(projects_path), "history.jsonl")
    if os.path.isfile(hp):
        try:
            with open(hp, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        sid = d.get("sessionId", "")
                        display = d.get("display", "")
                        if display:
                            msgs.append(Msg("user", display, _ts(d), sid))
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
    return msgs


def read_codex_sessions(sessions_path: str) -> list[Msg]:
    """从 Codex sessions 目录读取"""
    msgs = []
    if not os.path.isdir(sessions_path):
        return msgs
    for root, dirs, files in os.walk(sessions_path):
        for sf in files:
            if not sf.endswith(".jsonl"):
                continue
            fp = os.path.join(root, sf)
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                            if d.get("type") != "response_item":
                                continue
                            payload = d.get("payload", {})
                            if not isinstance(payload, dict):
                                continue
                            role = payload.get("role", "unknown")
                            if role not in ("user", "assistant"):
                                continue
                            content = payload.get("content", [])
                            text = ""
                            if isinstance(content, list):
                                parts = []
                                for c in content:
                                    if isinstance(c, dict):
                                        if c.get("type") == "input_text":
                                            parts.append(c.get("text", ""))
                                        elif c.get("type") == "output_text":
                                            parts.append(c.get("text", ""))
                                text = "\n".join(parts)
                            elif isinstance(content, str):
                                text = content
                            if text:
                                sid = payload.get("session_id", "") or payload.get("id", "")
                                msgs.append(Msg(role, text, _ts(d), sid))
                        except json.JSONDecodeError:
                            continue
            except Exception:
                continue
    return msgs


def read_workbuddy_sessions(sessions_paths: dict) -> list[Msg]:
    """
    WorkBuddy 真实对话文件在 workspace/sessions/<uuid>/<something>.jsonl
    sessions/ 目录里是 heartbeat 文件，跳过。
    """
    msgs = []
    ws_sessions = sessions_paths.get("ws_sessions")
    if ws_sessions and os.path.isdir(ws_sessions):
        for sess_dir in os.listdir(ws_sessions):
            sess_path = os.path.join(ws_sessions, sess_dir)
            if not os.path.isdir(sess_path):
                continue
            for sf in os.listdir(sess_path):
                if not sf.endswith(".jsonl"):
                    continue
                fp = os.path.join(sess_path, sf)
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                d = json.loads(line)
                                t = d.get("type")
                                if t in ("user", "assistant"):
                                    text = d.get("text", "") or d.get("display", "")
                                    if text:
                                        msgs.append(Msg(t, text[:2000], _ts(d), sess_dir))
                            except json.JSONDecodeError:
                                continue
                except Exception:
                    continue
    return msgs


def read_qclaw_sessions(qclaw_path: str) -> list[Msg]:
    """QClaw 基于 OpenClaw，数据在 .qclaw/agents/main/agent/sessions/ 下"""
    msgs = []
    sessions_dir = os.path.join(qclaw_path, "agents", "main", "agent", "sessions")
    if not os.path.isdir(sessions_dir):
        return msgs
    for sf in os.listdir(sessions_dir):
        fp = os.path.join(sessions_dir, sf)
        if not os.path.isfile(fp) or not sf.endswith(".jsonl"):
            continue
        try:
            with open(fp, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        t = d.get("type")
                        if t in ("user", "assistant"):
                            text = d.get("text", "") or d.get("display", "")
                            if text:
                                msgs.append(Msg(t, text[:2000], _ts(d), sf.replace(".jsonl", "")))
                    except json.JSONDecodeError:
                        continue
        except Exception:
            continue
    return msgs


def read_gemini_sessions(config_path: str) -> list[Msg]:
    """Gemini CLI 对话数据"""
    msgs = []
    if not os.path.isdir(config_path):
        return msgs
    for root, dirs, files in os.walk(config_path):
        for sf in files:
            if not sf.endswith((".jsonl", ".json")):
                continue
            fp = os.path.join(root, sf)
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    if sf.endswith(".jsonl"):
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                d = json.loads(line)
                                role = d.get("role", "")
                                if role in ("user", "assistant"):
                                    text = ""
                                    parts = d.get("parts", [])
                                    if isinstance(parts, list) and parts:
                                        text = parts[0].get("text", "") if isinstance(parts[0], dict) else str(parts[0])
                                    else:
                                        text = d.get("text", "")
                                    if text:
                                        msgs.append(Msg(role, text[:2000], _ts(d), sf))
                            except json.JSONDecodeError:
                                continue
                    else:
                        data = json.load(f)
                        if isinstance(data, list):
                            for item in data:
                                role = item.get("role", "")
                                if role in ("user", "assistant"):
                                    text = item.get("text", "")
                                    parts = item.get("parts", [])
                                    if not text and isinstance(parts, list) and parts:
                                        text = parts[0].get("text", "") if isinstance(parts[0], dict) else str(parts[0])
                                    if text:
                                        msgs.append(Msg(role, text[:2000], _ts(item), sf.replace(".json", "")))
            except Exception:
                continue
    return msgs


def read_openclaw_sessions(db_path: str) -> list[Msg]:
    """从 OpenClaw SQLite 数据库读取"""
    msgs = []
    if not os.path.isfile(db_path):
        return msgs
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [t[0] for t in c.fetchall()]
        if "command_log_entries" in tables:
            try:
                c.execute("SELECT id, timestamp_ms, action, entry_json FROM command_log_entries ORDER BY id DESC LIMIT 50")
                for row in c.fetchall():
                    eid, ts_ms, action, ej = row
                    if ej:
                        try:
                            ed = json.loads(ej)
                            text = ed.get("text", "") or ed.get("display", "")
                            if text:
                                msgs.append(Msg("system", text[:500], ts_ms / 1000, f"ocl-{eid}"))
                        except:
                            pass
            except:
                pass
        conn.close()
    except Exception:
        pass
    return msgs


def read_all(agent: dict) -> list[Msg]:
    """读取指定 agent 的所有对话消息。agent 是 detect_agents() 返回的 dict"""
    all_msgs = []
    sources = agent["sources"]
    name = agent["name"]
    try:
        if name == "claude":
            all_msgs.extend(read_claude_sessions(sources.get("projects", "")))
        elif name == "codex":
            all_msgs.extend(read_codex_sessions(sources.get("sessions", "")))
        elif name == "workbuddy":
            all_msgs.extend(read_workbuddy_sessions(sources))
        elif name == "qclaw":
            all_msgs.extend(read_qclaw_sessions(sources.get("root", "")))
        elif name == "gemini":
            all_msgs.extend(read_gemini_sessions(sources.get("root", "")))
        elif name == "openclaw":
            all_msgs.extend(read_openclaw_sessions(sources.get("db", "")))
        # opencode / mavis：暂不支持读取（格式未知）
    except Exception:
        pass
    all_msgs.sort(key=lambda m: m.ts)
    return all_msgs


# ─── 写入器 ────────────────────────────────────────────────────────────────────
# 每个写入函数返回 dict: {count, path, reason}
# reason 为 "ok" 或失败原因（中文），main.py 可直接展示到日志

def write_claude(msgs: list[Msg]) -> dict:
    """Claude Code：新建一个 sync session 文件，并把 user 消息追加到 history.jsonl"""
    cfg_dir = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    projects_dir = os.path.join(cfg_dir, "projects")
    if not msgs:
        return {"count": 0, "path": projects_dir, "reason": "无消息可写入"}
    if not os.path.isdir(projects_dir):
        try:
            os.makedirs(projects_dir, exist_ok=True)
        except Exception as e:
            return {"count": 0, "path": projects_dir, "reason": f"无法创建目录: {e}"}

    # 新建 session：projects/sync-agent/<ts>-sync.jsonl
    sync_dir = os.path.join(projects_dir, "sync-agent")
    os.makedirs(sync_dir, exist_ok=True)
    ts_tag = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    fp = os.path.join(sync_dir, f"{ts_tag}-sync.jsonl")
    try:
        with open(fp, "a", encoding="utf-8") as f:
            for m in msgs:
                entry = {
                    "type": m.role,
                    "sessionId": f"sync-{ts_tag}",
                    "timestamp": datetime.fromtimestamp(m.ts).isoformat() + "Z",
                    "message": {
                        "role": m.role,
                        "content": [{"type": "text", "text": m.text}],
                    },
                    "delta": {"type": "text", "text": m.text},
                    "display": m.text[:200],
                    "uuid": hashlib.md5(f"{m.session_id}-{m.text[:50]}-{m.ts}".encode()).hexdigest()[:16],
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        # 同时追加 user 消息到 history.jsonl
        history_fp = os.path.join(cfg_dir, "history.jsonl")
        if os.path.isfile(history_fp):
            with open(history_fp, "a", encoding="utf-8") as f:
                for m in msgs:
                    if m.role == "user":
                        entry = {
                            "display": m.text[:300],
                            "timestamp": int(m.ts * 1000),
                            "sessionId": f"sync-{ts_tag}",
                            "project": "sync-agent",
                        }
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return {"count": len(msgs), "path": fp, "reason": "ok"}
    except Exception as e:
        return {"count": 0, "path": fp, "reason": f"写入失败: {e}"}


def write_codex(msgs: list[Msg]) -> dict:
    """新建一个 Codex session rollout 文件"""
    cfg_dir = os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")
    sessions_dir = os.path.join(cfg_dir, "sessions")
    if not msgs:
        return {"count": 0, "path": sessions_dir, "reason": "无消息可写入"}
    if not os.path.isdir(sessions_dir):
        try:
            os.makedirs(sessions_dir, exist_ok=True)
        except Exception as e:
            return {"count": 0, "path": sessions_dir, "reason": f"无法创建目录: {e}"}
    now_ms = int(time.time() * 1000)
    sid = f"sync-{now_ms // 1000}"
    year_month = datetime.now().strftime("%Y/%m")
    dest = os.path.join(sessions_dir, year_month)
    os.makedirs(dest, exist_ok=True)
    fname = f"rollout-{datetime.now().strftime('%Y-%m-%dT%H-%M-%S')}-{sid[:8]}-sync.jsonl"
    fp = os.path.join(dest, fname)
    if os.path.isfile(fp):
        return {"count": 0, "path": fp, "reason": "文件已存在（去重）"}
    try:
        with open(fp, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "timestamp": now_ms, "type": "session_meta",
                "payload": {"session_id": sid, "id": sid, "originator": "agent-sync",
                            "cli_version": "sync", "cwd": os.getcwd()},
            }) + "\n")
            for m in msgs:
                f.write(json.dumps({
                    "timestamp": int(m.ts * 1000),
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": m.role,
                        "content": [{"type": "input_text", "text": m.text}],
                        "session_id": sid,
                        "id": hashlib.md5(f"{m.session_id}-{m.text[:50]}-{m.ts}".encode()).hexdigest()[:16],
                    },
                }) + "\n")
        return {"count": len(msgs), "path": fp, "reason": "ok"}
    except Exception as e:
        return {"count": 0, "path": fp, "reason": f"写入失败: {e}"}


def write_workbuddy(msgs: list[Msg]) -> dict:
    """WorkBuddy 真实对话在 workspace/sessions/<uuid>/，新建一个 sync-<ts>.jsonl"""
    cfg_dir = os.environ.get("WORKBUDDY_CONFIG_DIR") or str(Path.home() / ".workbuddy")
    ws_dir = os.path.join(cfg_dir, "workspace", "sessions")
    if not msgs:
        return {"count": 0, "path": ws_dir, "reason": "无消息可写入"}
    if not os.path.isdir(ws_dir):
        try:
            os.makedirs(ws_dir, exist_ok=True)
        except Exception as e:
            return {"count": 0, "path": ws_dir, "reason": f"无法创建目录: {e}"}
    sid = f"sync-{int(time.time())}"
    dest_dir = os.path.join(ws_dir, sid)
    os.makedirs(dest_dir, exist_ok=True)
    fp = os.path.join(dest_dir, f"{sid}.jsonl")
    if os.path.isfile(fp):
        return {"count": 0, "path": fp, "reason": "文件已存在（去重）"}
    try:
        with open(fp, "w", encoding="utf-8") as f:
            for m in msgs:
                entry = {"type": m.role, "text": m.text, "timestamp": int(m.ts * 1000), "sessionId": sid}
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return {"count": len(msgs), "path": fp, "reason": "ok"}
    except Exception as e:
        return {"count": 0, "path": fp, "reason": f"写入失败: {e}"}


def write_qclaw(msgs: list[Msg]) -> dict:
    """QClaw：在 .qclaw/agents/main/agent/sessions/ 下新建 jsonl"""
    cfg_dir = os.environ.get("QCLAW_CONFIG_DIR") or str(Path.home() / ".qclaw")
    agent_dir = os.path.join(cfg_dir, "agents", "main", "agent", "sessions")
    if not msgs:
        return {"count": 0, "path": agent_dir, "reason": "无消息可写入"}
    os.makedirs(agent_dir, exist_ok=True)
    sid = f"sync-{int(time.time())}"
    fp = os.path.join(agent_dir, f"{sid}.jsonl")
    if os.path.isfile(fp):
        return {"count": 0, "path": fp, "reason": "文件已存在（去重）"}
    try:
        with open(fp, "w", encoding="utf-8") as f:
            for m in msgs:
                entry = {
                    "type": m.role,
                    "text": m.text,
                    "timestamp": int(m.ts * 1000),
                    "sessionId": sid,
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return {"count": len(msgs), "path": fp, "reason": "ok"}
    except Exception as e:
        return {"count": 0, "path": fp, "reason": f"写入失败: {e}"}


def write_gemini(msgs: list[Msg]) -> dict:
    """Gemini CLI 暂不支持写入（仅读取）"""
    return {"count": 0, "path": os.environ.get("GEMINI_CONFIG_DIR", str(Path.home() / ".config" / "gemini")),
            "reason": "Gemini 仅支持读取"}


def write_openclaw(msgs: list[Msg]) -> dict:
    """OpenClaw 数据库复杂，暂不支持写入"""
    return {"count": 0, "path": os.environ.get("OPENCLAW_STATE_DIR", str(Path.home() / ".openclaw")),
            "reason": "OpenClaw 仅支持读取（SQLite）"}


def write_opencode(msgs: list[Msg]) -> dict:
    """OpenCode 格式未知，暂不支持写入"""
    return {"count": 0, "path": os.environ.get("OPENCODE_CONFIG_DIR", str(Path.home() / ".opencode")),
            "reason": "OpenCode 暂不支持写入"}


def write_mavis(msgs: list[Msg]) -> dict:
    """Mavis 格式未知，暂不支持写入"""
    return {"count": 0, "path": os.environ.get("MAVIS_CONFIG_DIR", str(Path.home() / ".mavis")),
            "reason": "Mavis 暂不支持写入"}


def write_to_agent(agent: dict, msgs: list[Msg]) -> dict:
    """将消息写入指定 agent，返回 {count, path, reason}"""
    name = agent["name"]
    dispatch = {
        "claude": write_claude,
        "codex": write_codex,
        "workbuddy": write_workbuddy,
        "qclaw": write_qclaw,
        "gemini": write_gemini,
        "openclaw": write_openclaw,
        "opencode": write_opencode,
        "mavis": write_mavis,
    }
    fn = dispatch.get(name)
    if fn is None:
        return {"count": 0, "path": "", "reason": f"未知 agent: {name}"}
    return fn(msgs)


# ─── 变更检测 ─────────────────────────────────────────────────────────────────

class ChangeDetector:
    def __init__(self):
        self.known: dict[str, set] = {}  # agent -> {msg_hash, ...}

    def _hash(self, m: Msg) -> str:
        return hashlib.md5(f"{m.role}:{m.text[:100]}:{m.ts}".encode()).hexdigest()[:12]

    def snapshot(self, agent_name: str, msgs: list[Msg]):
        self.known[agent_name] = {self._hash(m) for m in msgs}

    def find_new(self, agent_name: str, msgs: list[Msg]) -> list[Msg]:
        known = self.known.get(agent_name, set())
        return [m for m in msgs if self._hash(m) not in known]


# ─── 同步引擎 ──────────────────────────────────────────────────────────────────

class SyncEngine:
    def __init__(self):
        self.detector = ChangeDetector()
        self.running = False
        self.selected_agents: list[str] = []
        self.poll_interval = 10
        self.last_stats: dict[str, dict] = {}

    def snapshot(self, agents: list[dict], history_limit: int = 0):
        """初始快照：把现有消息记为已知，避免启动时全量推送。

        history_limit > 0 时，每个 agent 最近 N 条不计入已知，
        第一轮 sync 会把它们当作新消息推送（用于首次同步 / 验证链路）。
        """
        for a in agents:
            if a["name"] not in self.selected_agents or not a["exists"]:
                continue
            msgs = read_all(a)
            if history_limit > 0:
                ordered = sorted(msgs, key=lambda m: m.ts, reverse=True)
                known_msgs = ordered[history_limit:]
            else:
                known_msgs = msgs
            self.detector.snapshot(a["name"], known_msgs)

    def sync(self, agents: list[dict]) -> dict[str, dict]:
        """执行一轮同步，返回 {src→dst: {count, path, reason}}"""
        results: dict[str, dict] = {}
        self.last_stats = {}
        # 1. 收集每个选中 agent 的新消息（此处不标记，等写入成功后再标记）
        new_by_agent: dict[str, list[Msg]] = {}
        for a in agents:
            if a["name"] not in self.selected_agents or not a["exists"]:
                continue
            msgs = read_all(a)
            new = self.detector.find_new(a["name"], msgs)
            self.last_stats[a["name"]] = {"total": len(msgs), "new": len(new)}
            if new:
                new_by_agent[a["name"]] = new

        # 2. 双向推送：每个源的新消息推给其他所有选中 agent
        for src_name, src_msgs in new_by_agent.items():
            succeeded = False
            targets = 0
            for a in agents:
                if a["name"] not in self.selected_agents or not a["exists"]:
                    continue
                if a["name"] == src_name:
                    continue
                targets += 1
                res = write_to_agent(a, src_msgs)
                results[f"{src_name}→{a['name']}"] = res
                if res.get("count", 0) > 0 and res.get("reason", "") == "ok":
                    succeeded = True
            # 至少一个目标写入成功（或没有目标）才标记为已知，否则下轮重试
            if succeeded or targets == 0:
                for m in src_msgs:
                    self.detector.known.setdefault(src_name, set()).add(
                        self.detector._hash(m)
                    )
        return results
