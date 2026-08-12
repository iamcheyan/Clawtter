"""Hermes 原生模型网关。

Clawtter 不维护自己的 provider/model/API key；每次调用都委托给 Hermes CLI，
因此自动继承当前 ~/.hermes/config.yaml 的主模型和 fallback 配置。
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

HERMES_BIN = Path.home() / ".local" / "bin" / "hermes"


def _hermes_command() -> str:
    return str(HERMES_BIN) if HERMES_BIN.exists() else "hermes"


def current_model() -> str:
    try:
        p = subprocess.run(
            [_hermes_command(), "config", "get", "model.default"],
            text=True, capture_output=True, timeout=15, check=False,
        )
        return p.stdout.strip() or "configured-by-hermes"
    except Exception:
        return "configured-by-hermes"


def ask(prompt: str, timeout: int = 180) -> tuple[str, str]:
    """使用 Hermes 当前模型配置执行一次非交互请求。"""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    p = subprocess.run(
        [_hermes_command(), "-z", prompt],
        text=True, capture_output=True, timeout=timeout, env=env, check=False,
    )
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "Hermes request failed").strip()[-2000:])
    return p.stdout.strip(), current_model()


def ask_json(prompt: str, timeout: int = 180) -> tuple[dict, str]:
    raw, model = ask(prompt, timeout=timeout)
    # Hermes/模型偶尔会包裹 markdown fence；只接受最后一个 JSON 对象。
    text = raw.strip()
    if "```" in text:
        text = text.replace("```json", "").replace("```", "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"Hermes returned no JSON: {raw[:500]}")
    return json.loads(text[start:end + 1]), model
