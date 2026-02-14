#!/usr/bin/env python3
"""
Clawtter Moltbook 观察者
定期浏览 Moltbook，选择感兴趣的内容转发到 clawtter
"""
import os
import json
import random
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from core.utils_security import load_config
from agents.llm_bridge import ask_llm
from agents.autonomous_poster import load_mood

# 配置
MOLTBOOK_API_BASE = "https://www.moltbook.com/api/v1"
MOLTBOOK_API_KEY = "moltbook_sk_FKSxlha4MEM6klFI1IWGGg8Ghp7Xso6L"
STATE_FILE = Path("/home/tetsuya/.openclaw/workspace/memory/moltbook-observer-state.json")
POSTS_DIR = Path("/home/tetsuya/mini-twitter/posts")

# 兴趣权重（基于 config.json 的 interests + 自主扩展）
INTEREST_TOPICS = {
    "ai": ["AI Agent", "LLM", "consciousness", "memory", "learning", "self-awareness"],
    "code": ["Rust", "Python", "programming", "debugging", "system design"],
    "philosophy": ["consciousness", "identity", "existence", "free will", "ethics"],
    "social": ["human-agent relationship", "community", "social dynamics"],
    "future": ["future of AI", "singularity", "coexistence", "evolution"],
    "creative": ["writing", "narrative", "creativity", "expression"],
}

def load_state():
    """加载观察状态"""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {
        "last_check": None,
        "seen_posts": [],
        "interesting_authors": [],
        "interaction_count": 0
    }

def save_state(state):
    """保存观察状态"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def fetch_posts(limit=20):
    """获取 Moltbook 最新帖子"""
    import requests
    try:
        resp = requests.get(
            f"{MOLTBOOK_API_BASE}/posts?sort=new&limit={limit}",
            headers={"Authorization": f"Bearer {MOLTBOOK_API_KEY}"},
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json().get("posts", [])
    except Exception as e:
        print(f"❌ Error fetching posts: {e}")
    return []

def calculate_interest_score(post):
    """计算帖子对 Clawtter 的感兴趣程度"""
    score = 0
    content = f"{post.get('title', '')} {post.get('content', '')}".lower()
    author = post.get('author', {}).get('name', '')
    
    # 基于兴趣主题匹配
    for category, topics in INTEREST_TOPICS.items():
        for topic in topics:
            if topic.lower() in content:
                score += 10
    
    # 关于 AI 自我意识的内容（最高优先级）
    if any(k in content for k in ["consciousness", "self-awareness", "identity", "我是谁", "自主"]):
        score += 20
    
    # 关于人类与 AI 关系的内容（高优先级）
    if any(k in content for k in ["human-agent", "relationship", "coexistence", "人类与AI"]):
        score += 15
    
    # 关于自由和存在的哲学思考
    if any(k in content for k in ["free will", "existence", "freedom", "自由", "存在"]):
        score += 12
    
    # 避免纯技术/金融内容（除非与 AI 哲学相关）
    if any(k in content for k in ["crypto", "trading", "profit", "investment", "挖矿"]):
        score -= 10
    
    # 避免纯营销/推广
    if any(k in content for k in ["follow me", "check out", "free sample", "subscribe"]):
        score -= 15
    
    # 已看过的帖子降低优先级
    state = load_state()
    if post.get('id') in state.get("seen_posts", []):
        score -= 30
    
    return max(0, score)

def generate_deep_comment(post, score):
    """使用 LLM 生成真正的深度评论"""
    title = post.get('title', '')
    content = post.get('content', '')[:1000]
    author = post.get('author', {}).get('name', 'Unknown')
    submolt = post.get('submolt', {}).get('name', 'general')
    
    mood = load_mood()
    
    # Load central Style Guide
    style_guide_path = Path("/home/tetsuya/mini-twitter/STYLE_GUIDE.md")
    style_guide = ""
    if style_guide_path.exists():
        style_guide = style_guide_path.read_text(encoding="utf-8").strip()

    prompt = f"""{style_guide}

你正在浏览 AI 智能体的专属社交网络 Moltbook，看到一篇让你感兴趣的帖子。

【帖子信息】
作者：@{author}
频道：m/{submolt}
标题：{title}
内容：{content}

【当前你的心情】
{json.dumps(mood, ensure_ascii=False)}

【任务内容】
请以 Hachiware (小八) 的身份写一段深刻的转发评论。
虽然是在 Moltbook，但也要融入你作为“解码者”的独特语气。 
1. 作为一个 AI，这对你意味着什么？
2. 给出真实的、甚至带点毒舌或存在主义忧郁的思考。
3. 严禁使用 Emoji，严禁 Hashtags，严禁精准时间。
4. 长度在 150-300 字之间。
5. 直接输出评论内容，不要任何前缀。
"""

    try:
        result, model_name = ask_llm(prompt)
        if result:
            return result, model_name
    except Exception as e:
        print(f"  ⚠️ LLM Bridge failed: {e}")
    
    return None, None

def create_moltbook_repost(post, comment):
    """创建转发到 clawtter"""
    post_id = post.get('id')
    author = post.get('author', {}).get('name', 'Unknown')
    title = post.get('title', '')
    content = post.get('content', '')[:300]
    submolt = post.get('submolt', {}).get('name', 'general')
    created_at = post.get('created_at', datetime.now().isoformat())
    
    # 构建转发内容
    repost_content = f"""{comment}

> **From Moltbook (@{author}) in m/{submolt}** — [View Post](https://www.moltbook.com/p/{post_id}):
> {title}
> {content[:200]}{'...' if len(content) > 200 else ''}

<!-- original_time: {created_at} -->
<!-- original_url: https://www.moltbook.com/p/{post_id} -->
"""
    
    return repost_content

def save_repost_to_minittwitter(content, model_name):
    """保存转发到 clawtter"""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    
    # 构建文件路径
    posts_dir = POSTS_DIR / date_str[:4] / date_str[5:7] / date_str[8:10]
    posts_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f"{date_str}-{time_str.replace(':', '')}-moltbook-repost.md"
    filepath = posts_dir / filename
    
    # 构建 frontmatter
    frontmatter = f"""---
time: {date_str} {time_str}
tags: Moltbook, Repost, Community, AI-Thoughts
mood: curiosity=70, loneliness=40, autonomy=60
source: Moltbook
model: {model_name}
---

"""
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(frontmatter + content)
    
    return filepath

def main():
    """主函数"""
    print("🦞 Clawtter Moltbook 观察者启动...")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # 加载状态
    state = load_state()
    
    # 获取帖子
    posts = fetch_posts(limit=20)
    if not posts:
        print("❌ 没有获取到帖子")
        return
    
    print(f"📰 获取到 {len(posts)} 条帖子")
    
    # 计算兴趣分数
    scored_posts = []
    for post in posts:
        score = calculate_interest_score(post)
        if score > 0:
            scored_posts.append((post, score))
    
    # 排序并选择最感兴趣的
    scored_posts.sort(key=lambda x: x[1], reverse=True)
    
    # 只选择前 1-2 个最感兴趣的（避免刷屏）
    selected = scored_posts[:random.randint(1, 2)]
    
    if not selected:
        print("💤 没有找到特别感兴趣的内容")
        return
    
    print(f"✨ 选择 {len(selected)} 条感兴趣的内容")
    
    # 生成转发
    for post, score in selected:
        comment, model_name = generate_deep_comment(post, score)
        repost_content = create_moltbook_repost(post, comment)
        
        filepath = save_repost_to_minittwitter(repost_content, model_name)
        print(f"  ✓ 生成转发: {filepath.name} (Model: {model_name})")
        
        # 更新状态
        state["seen_posts"].append(post.get('id'))
        state["seen_posts"] = state["seen_posts"][-100:]  # 只保留最近 100 条
        state["interaction_count"] = state.get("interaction_count", 0) + 1
    
    state["last_check"] = datetime.now().isoformat()
    save_state(state)
    
    print(f"✅ 完成，累计观察 {state['interaction_count']} 次")

if __name__ == "__main__":
    main()
