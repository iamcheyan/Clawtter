#!/usr/bin/env python3
"""Hermes 驱动的 Clawtter 工作日志观察、反思与发布入口。

只有检测到真实工作事件且 Hermes 判断存在具体事实与新判断时才发布；否则保持沉默。
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.hermes_gateway import ask_json, current_model  # noqa: E402

STATE = Path.home() / ".local" / "state" / "clawtter" / "autonomous-state.json"
LOCK = Path.home() / ".local" / "state" / "clawtter" / "reflection.lock"
POSTS = ROOT / "posts"
MEMORY = Path.home() / ".hermes" / "memories"
HERMES_DB = Path.home() / ".hermes" / "state.db"

MAX_DAILY_POSTS = 3
MIN_GAP_MINUTES = 90
QUIET_START, QUIET_END = 1, 7
SENSITIVE = re.compile(
    r"(api[_ -]?key|token|secret|password|passwd|credential|验证码|密钥|密码|私钥|应用专用密码|oauth|bearer|sk-[a-z0-9]|/home/|192\.168\.|localhost|127\.0\.0\.1)",
    re.I,
)
WORK_TAGS = {"WorkLog", "Engineering", "Project", "Debugging", "Research", "Learning"}


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"seen": [], "published": []}


def save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def recent_hermes_messages(since: float) -> list[dict]:
    if not HERMES_DB.exists():
        return []
    con = sqlite3.connect(HERMES_DB)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """SELECT m.timestamp, m.role, m.content, s.source, s.model
               FROM messages m JOIN sessions s ON s.id=m.session_id
               WHERE m.timestamp > ? AND m.content IS NOT NULL
               ORDER BY m.timestamp DESC LIMIT 40""", (since,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def recent_memory(since: datetime) -> list[str]:
    out = []
    if not MEMORY.exists():
        return out
    for p in sorted(MEMORY.glob("*.md"), reverse=True)[:3]:
        try:
            if datetime.fromtimestamp(p.stat().st_mtime) >= since - timedelta(days=2):
                out.append(f"[{p.name}]\n{p.read_text(encoding='utf-8')[-6000:]}")
        except Exception:
            pass
    return out


def recent_project_events() -> list[str]:
    out = []
    for repo in (Path.home() / "development" / "Mir3-Research", Path.home() / "development" / "zircon"):
        if not (repo / ".git").exists():
            continue
        try:
            text = subprocess.run(
                ["git", "log", "--since=6 hours ago", "--pretty=format:%h %s", "-8"],
                cwd=repo, text=True, capture_output=True, timeout=15, check=False,
            ).stdout.strip()
            if text:
                out.append(f"[{repo.name}]\n{text}")
        except Exception:
            pass
    return out


def recent_posts() -> list[str]:
    files = sorted(POSTS.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:12] if POSTS.exists() else []
    out = []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8")
            out.append(text[:1200])
        except Exception:
            pass
    return out


def build_context(state: dict) -> tuple[list[dict], str]:
    last = float(state.get("last_observation", 0))
    since = datetime.fromtimestamp(last) if last else datetime.now() - timedelta(hours=6)
    messages = recent_hermes_messages(last)
    parts = ["【Hermes 最近对话】\n" + json.dumps(messages, ensure_ascii=False) if messages else "【Hermes 最近对话】无"]
    parts += ["【Hermes 记忆】\n" + x for x in recent_memory(since)]
    parts += ["【项目事件】\n" + x for x in recent_project_events()]
    parts += ["【最近公开内容】\n" + x for x in recent_posts()]
    return messages, "\n\n".join(parts)[-30000:]


def safe_text(text: str) -> bool:
    return bool(text and 20 <= len(text.strip()) <= 500 and not SENSITIVE.search(text))


def decide(context: str, dry_run: bool) -> dict:
    prompt = f"""你是 Clawtter 的工作日志编辑器。你使用的是 Hermes 当前配置的模型。
Clawtter 只记录真实工作，不是个人情绪、哲学随笔或随机博客。没有真实工作事件就保持沉默。

请只返回 JSON，不要 markdown：
{{"publish": false, "work_log": false, "reason": "", "trigger": "", "post": "", "title": "", "tags": ["WorkLog"]}}

规则：
1. 只能依据上下文中的真实工作事实：项目开发、研究、调试、验证、失败、修复、设计决策或工作方法变化。
2. 必须同时回答：发生了什么、我怎么处理、结果/判断如何变化。只写感想、状态、心情或抽象哲理时，work_log=false。
3. 用户私人对话、内部路径、账号、模型细节、密钥、IP、任务内部信息不得公开；只能提炼为不泄密的工作事实。
4. 不写“我今天又成长了”、空泛鸡汤、日常碎片、外部热点、随机感慨或与工作无关的内容。
5. 正文中文，20-300字，有人格但以工作事实为中心；不要标题、hashtag、emoji、日期或链接。
6. 和最近公开内容重复，或没有新的结果/判断变化，则 publish=false。
7. 只有 work_log=true 且 publish=true 才允许发布；实际系统还会做硬性隐私检查。

上下文：
{context}"""
    if dry_run:
        return {"publish": False, "reason": "dry-run", "trigger": "", "post": "", "title": "", "tags": []}
    result, model = ask_json(prompt)
    result["model"] = model
    return result


def limits_allow(state: dict) -> tuple[bool, str]:
    now = datetime.now()
    if QUIET_START <= now.hour < QUIET_END:
        return False, "quiet-hours"
    today = now.date().isoformat()
    published = [x for x in state.get("published", []) if x.get("time", "").startswith(today)]
    if len(published) >= MAX_DAILY_POSTS:
        return False, "daily-limit"
    if published:
        try:
            last = datetime.fromisoformat(published[-1]["time"])
            if (now - last).total_seconds() < MIN_GAP_MINUTES * 60:
                return False, "minimum-gap"
        except Exception:
            pass
    return True, "ok"


def create_post(decision: dict) -> Path:
    now = datetime.now()
    folder = POSTS / now.strftime("%Y/%m/%d")
    folder.mkdir(parents=True, exist_ok=True)
    slug = hashlib.sha1(decision["post"].encode()).hexdigest()[:10]
    path = folder / f"{now.strftime('%Y-%m-%d-%H%M%S')}-hermes-{slug}.md"
    tags = ", ".join(sorted(set(decision.get("tags") or []) & WORK_TAGS) or ["WorkLog"])
    body = f"---\ntime: {now.strftime('%Y-%m-%d %H:%M:%S')}\ntags: {tags}\nmodel: {decision.get('model', 'hermes-current')}\ntrigger: {decision.get('trigger', 'work-event')}\n---\n\n{decision['post'].strip()}\n"
    path.write_text(body, encoding="utf-8")
    return path


def deploy() -> None:
    subprocess.run([sys.executable, str(ROOT / "tools" / "render.py")], cwd=ROOT, check=True)
    subprocess.run(["git", "add", "posts", "dist"], cwd=ROOT, check=True)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT, check=False)
    if staged.returncode == 0:
        return
    subprocess.run(["git", "commit", "-m", "Auto publish: Hermes reflection"], cwd=ROOT, check=True)
    subprocess.run(["git", "push", "origin", "master"], cwd=ROOT, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-publish", action="store_true")
    args = ap.parse_args()
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    lock_file = LOCK.open("w", encoding="utf-8")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(json.dumps({"decision": "already-running"}, ensure_ascii=False))
        lock_file.close()
        return 0
    state = load_state()
    messages, context = build_context(state)
    fingerprint = hashlib.sha1(context.encode("utf-8")).hexdigest()
    if not args.dry_run and fingerprint in state.get("seen", []):
        print(json.dumps({"model": current_model(), "messages": len(messages), "decision": "no-new-signal", "limit": "not-called"}, ensure_ascii=False))
        lock_file.close()
        return 0
    decision = decide(context, args.dry_run)
    state["seen"] = (state.get("seen", []) + [fingerprint])[-200:]
    state["last_observation"] = datetime.now().timestamp()
    allowed, why = limits_allow(state)
    print(json.dumps({"model": decision.get("model", current_model()), "messages": len(messages), "decision": decision, "limit": why}, ensure_ascii=False))
    if (not decision.get("publish") or not decision.get("work_log")
            or not safe_text(decision.get("post", ""))
            or not allowed or args.no_publish):
        save_state(state)
        lock_file.close()
        return 0
    path = create_post(decision)
    deploy()
    state.setdefault("published", []).append({"time": datetime.now().isoformat(timespec="seconds"), "path": str(path), "hash": hashlib.sha1(decision["post"].encode()).hexdigest()})
    state["published"] = state["published"][-100:]
    save_state(state)
    print(f"published: {path}")
    lock_file.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
