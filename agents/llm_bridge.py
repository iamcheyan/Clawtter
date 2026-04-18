#!/usr/bin/env python3
"""
统一 LLM 调用桥接模块
优先使用 Opencode 免费模型，失败回退到智谱 GLM-4-Flash
"""
import json
import requests
import subprocess
from pathlib import Path

# Opencode 免费模型池（按优先级排序）
OPENCODE_FREE_MODELS = [
    "kimi-k2.5-free",
    "minimax-m2.5-free",
    "nemotron-3-super-free",
]

OPENCODE_PATH = "/home/tetsuya/.opencode/bin/opencode"


def call_opencode_llm(prompt, model="kimi-k2.5-free"):
    """
    调用 Opencode CLI 免费模型。
    """
    model_id = f"opencode/{model}" if '/' not in model else model

    print(f"🤖 Calling Opencode CLI ({model_id})...")

    try:
        result = subprocess.run(
            [OPENCODE_PATH, 'run', '--model', model_id],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            return result.stdout.strip(), model_id
    except Exception as e:
        print(f"⚠️ Opencode CLI failed: {e}")
    return None, None


def call_opencode_with_fallback(prompt):
    """
    尝试多个 Opencode 免费模型，返回第一个成功的结果。
    """
    for model in OPENCODE_FREE_MODELS:
        content, model_id = call_opencode_llm(prompt, model=model)
        if content:
            return content, model_id
    return None, None


def call_zhipu_llm(prompt, system_prompt="You are a helpful assistant."):
    """
    备用方案：调用智谱 GLM-4-Flash 免费模型。
    """
    try:
        config_path = Path("/home/tetsuya/.openclaw/openclaw.json")
        if not config_path.exists():
            return None, None

        with open(config_path, 'r') as f:
            cfg = json.load(f)

        api_key = cfg.get("models", {}).get("providers", {}).get("zhipu-ai", {}).get("apiKey")
        if not api_key:
            return None, None

        url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        data = {
            "model": "glm-4-flash",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 4096,
            "temperature": 0.7
        }

        response = requests.post(url, headers=headers, json=data, timeout=60)
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content'].strip(), "zhipu/glm-4-flash"
    except Exception as e:
        print(f"⚠️ Zhipu call failed: {e}")
    return None, None


def ask_llm(prompt, system_prompt=None, fallback_model="kimi-k2.5-free"):
    """
    统一 LLM 调用接口：
    1. 优先尝试 Opencode 免费模型（kimi-k2.5-free -> minimax-m2.5-free -> nemotron-3-super-free）
    2. 全部失败则回退到智谱 GLM-4-Flash
    """
    # 1. 优先尝试 Opencode 免费模型池
    full_prompt = prompt
    if system_prompt:
        full_prompt = f"{system_prompt}\n\n{prompt}"

    content, model_name = call_opencode_with_fallback(full_prompt)
    if content:
        return content, model_name

    # 2. 回退到智谱
    print("🔄 All Opencode models failed. Falling back to Zhipu GLM-4-Flash...")
    content, model_name = call_zhipu_llm(prompt, system_prompt) if system_prompt else call_zhipu_llm(prompt)
    if content:
        return content, model_name

    return None, None
