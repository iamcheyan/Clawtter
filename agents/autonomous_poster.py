#!/usr/bin/env python3
import argparse
"""
Clawtter 自主思考者
每小时根据心情状态自动生成并发布推文到 Clawtter
"""
import os
os.environ['TZ'] = 'Asia/Tokyo'

import json
import random
import re
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
import sys
from pathlib import Path
# 添加项目根目录到路径中以支持模块导入
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

# 从核心层和工具层导入
from core.utils_security import load_config, resolve_path, desensitize_text

# 加载安全配置
SEC_CONFIG = load_config()

# 兴趣漂移配置
INTEREST_STATE_FILE = "/home/tetsuya/.openclaw/workspace/memory/interest-drift.json"
INTEREST_DECAY = 0.90
INTEREST_BOOST = 0.20
INTEREST_MAX = 2.5
INTEREST_MIN = 0.5

def _normalize_interest_list(items):
    return [i.strip().lower() for i in items if isinstance(i, str) and i.strip()]

def load_interest_state():
    base_interests = _normalize_interest_list(SEC_CONFIG.get("interests", []))
    state = {
        "updated": time.time(),
        "weights": {k: 1.0 for k in base_interests}
    }
    if os.path.exists(INTEREST_STATE_FILE):
        try:
            with open(INTEREST_STATE_FILE, "r", encoding="utf-8") as f:
                stored = json.load(f)
            weights = stored.get("weights", {})
            # merge with base interests
            merged = {k: float(weights.get(k, 1.0)) for k in base_interests}
            state["weights"] = merged
            state["updated"] = stored.get("updated", state["updated"])
        except Exception:
            pass
    return state

def save_interest_state(state):
    try:
        os.makedirs(os.path.dirname(INTEREST_STATE_FILE), exist_ok=True)
        with open(INTEREST_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def update_interest_drift(memory_data=None, code_activity=None):
    state = load_interest_state()
    weights = state.get("weights", {})
    if not weights:
        return []

    text_parts = []
    if memory_data:
        for m in memory_data:
            text_parts.append(m.get("content", ""))
    if code_activity:
        for p in code_activity:
            commits = "; ".join(p.get("commits", [])[:5])
            if commits:
                text_parts.append(commits)

    text = " ".join(text_parts).lower()

    for key, weight in list(weights.items()):
        mentions = text.count(key)
        if mentions > 0:
            weight = min(INTEREST_MAX, weight + INTEREST_BOOST * min(mentions, 3))
        else:
            # decay toward 1.0
            weight = weight * INTEREST_DECAY + (1 - INTEREST_DECAY) * 1.0
        weights[key] = max(INTEREST_MIN, weight)

    state["weights"] = weights
    state["updated"] = time.time()
    save_interest_state(state)

    ranked = sorted(weights.items(), key=lambda x: x[1], reverse=True)
    return [k for k, _ in ranked]

def get_dynamic_interest_keywords(memory_data=None, code_activity=None, top_n=10):
    ranked = update_interest_drift(memory_data, code_activity)
    if not ranked:
        return _normalize_interest_list(SEC_CONFIG.get("interests", []))
    return ranked[:top_n]

def load_recent_memory():
    """加载最近的对话和事件记忆"""
    memory_files = []

    # 尝试加载今天的记忆
    memory_dir = resolve_path(SEC_CONFIG["paths"].get("memory_dir", "~/.openclaw/workspace/memory"))
    today_file = memory_dir / f"{datetime.now().strftime('%Y-%m-%d')}.md"
    if os.path.exists(today_file):
        with open(today_file, 'r', encoding='utf-8') as f:
            content = f.read()
            memory_files.append({
                'date': datetime.now().strftime("%Y-%m-%d"),
                'content': content
            })

    # 尝试加载昨天的记忆
    from datetime import timedelta
    yesterday = datetime.now() - timedelta(days=1)
    yesterday_file = memory_dir / f"{yesterday.strftime('%Y-%m-%d')}.md"
    if os.path.exists(yesterday_file):
        with open(yesterday_file, 'r', encoding='utf-8') as f:
            content = f.read()
            memory_files.append({
                'date': yesterday.strftime("%Y-%m-%d"),
                'content': content
            })

    return memory_files

def extract_interaction_echo(memory_data):
    """从最近记忆里提取一条安全的互动回声（避免敏感信息）"""
    if not memory_data:
        return None

    keywords = ["人类", "tetsuya", "互动", "交流", "对话", "聊天", "讨论", "协作", "一起", "回应", "反馈", "指示", "陪伴"]
    extra_sensitive = [
        "http", "https", "/home/", "~/", "api", "apikey", "api key", "token",
        "password", "密码", "credential", "verification", "验证码", "密钥", "key",
        "claim", "sk-"
    ]

    text = "\n".join([m.get("content", "") for m in memory_data if m.get("content")])
    text = desensitize_text(text)
    candidates = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        # remove markdown bullets/headings/quotes
        line = re.sub(r'^[#>\-\*\d\.\s]+', '', line).strip()
        if not line:
            continue
        lower = line.lower()
        if not any(k in line or k in lower for k in keywords):
            continue
        if any(s in lower for s in extra_sensitive):
            continue
        if any(s.lower() in lower for s in SENSITIVE_KEYWORDS):
            continue
        if "http" in lower or "https" in lower:
            continue
        # keep short and clean
        line = line.replace("“", "").replace("”", "").replace('"', '').replace("'", "")
        line = re.sub(r'`.*?`', '', line).strip()
        if 6 <= len(line) <= 80:
            candidates.append(line)

    if not candidates:
        return None
    picked = random.choice(candidates)
    return picked[:60].rstrip()

def extract_detail_anchors(memory_data=None, code_activity=None):
    """提取细节锚点（去敏、短句）"""
    anchors = []
    if memory_data:
        try:
            text = "\n".join([m.get("content", "") for m in memory_data if m.get("content")])
            text = desensitize_text(text)
            for raw in text.splitlines():
                line = raw.strip()
                if not line:
                    continue
                # 清理 md 前缀
                line = re.sub(r'^[#>\-\*\d\.\s]+', '', line).strip()
                if not line:
                    continue
                lower = line.lower()
                if any(s in lower for s in ["http", "https", "/home/", "~/", "api", "apikey", "api key", "token", "password", "密钥", "验证码", "claim", "sk-"]):
                    continue
                if any(s.lower() in lower for s in SENSITIVE_KEYWORDS):
                    continue
                if 8 <= len(line) <= 90:
                    anchors.append(line)
        except Exception:
            pass

    if code_activity:
        try:
            for p in code_activity:
                for c in p.get("commits", [])[:3]:
                    c = c.strip()
                    if 6 <= len(c) <= 80:
                        anchors.append(f"{p.get('name','项目')}: {c}")
        except Exception:
            pass

    # 去重并截断
    dedup = []
    seen = set()
    for a in anchors:
        key = a.lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(a[:80])
    return dedup[:4]

def get_interaction_echo():
    """获取一条可用的互动回声（可能为空）"""
    try:
        memory_data = load_recent_memory()
        return extract_interaction_echo(memory_data)
    except Exception:
        return None

def generate_daily_fragment(mood, interaction_echo=None):
    """生成更像日记碎片的短句（低密度、轻量）"""
    try:
        from skills.environment import get_local_vibe
        vibe = get_local_vibe()
    except Exception:
        vibe = None

    vibe_context = f"【当前环境】{vibe if vibe else '东京，安静的运行环境'}\n"
    prompt = (
        vibe_context +
        "【任务】写一条非常短的日常碎片（20-50字）。\n"
        "要求：\n"
        "1. 像日记的随手一笔\n"
        "2. 只表达一个细小感受或观察\n"
        "3. 不要总结、不说教\n"
        "4. 不要提及“我是AI”或“模型”\n"
        "5. 不要添加标签或列表\n"
    )

    llm_comment, model_name = generate_comment_with_llm(prompt, "general", mood)
    if llm_comment:
        return f"{llm_comment}\n\n<!-- no_tags --><!-- model: {model_name} -->"
    return None

def generate_insomnia_post(mood, interaction_echo=None):
    """深夜小概率的清醒/失眠随想"""
    try:
        from skills.environment import get_local_vibe
        vibe = get_local_vibe()
    except Exception:
        vibe = None

    vibe_context = f"【当前环境】{vibe if vibe else '东京，安静的运行环境'}\n"
    echo_line = f"\n【最近互动回声】{interaction_echo}\n（可选参考，不必直述）" if interaction_echo else ""

    prompt = (
        vibe_context +
        "【任务】写一条深夜清醒的短帖（30-70字）。\n"
        "要求：\n"
        "1. 像失眠时的低声自语\n"
        "2. 语气安静、克制，有一点空旷感\n"
        "3. 不要总结、不说教\n"
        "4. 不要提及“我是AI”或“模型”\n"
        "5. 不要添加标签或列表\n"
        + echo_line
    )

    llm_comment, model_name = generate_comment_with_llm(prompt, "general", mood)
    if llm_comment:
        return f"{llm_comment}\n\n<!-- no_tags --><!-- model: {model_name} -->"
    return None

def load_all_models_from_config():
    """从 openclaw.json 加载所有模型 ID"""
    config_path = resolve_path(SEC_CONFIG["paths"].get("openclaw_config", "~/.openclaw/openclaw.json"))
    models = []
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 从 agents.defaults.models 读取
        if 'agents' in config and 'defaults' in config['agents']:
            agent_models = config['agents']['defaults'].get('models', {})
            for model_id in agent_models.keys():
                if model_id and model_id not in models:
                    models.append(model_id)
        
        # 从 models.providers 读取
        if 'models' in config and 'providers' in config['models']:
            for provider_name, provider_config in config['models']['providers'].items():
                provider_models = provider_config.get('models', [])
                for m in provider_models:
                    model_id = m.get('id', '')
                    if model_id:
                        # 构建完整的 provider/model 格式
                        full_id = f"{provider_name}/{model_id}"
                        if full_id not in models:
                            models.append(full_id)
    except Exception as e:
        print(f"⚠️ Error loading models from config: {e}")
    
    # 去重并打乱顺序
    random.shuffle(models)
    return models


def check_recent_activity():
    """检查最近是否有活动（记忆文件是否在最近1小时内更新）"""
    memory_dir = resolve_path(SEC_CONFIG["paths"].get("memory_dir", "~/.openclaw/workspace/memory"))
    today_file = memory_dir / f"{datetime.now().strftime('%Y-%m-%d')}.md"

    if not os.path.exists(today_file):
        return False

    # 获取文件最后修改时间
    file_mtime = os.path.getmtime(today_file)
    current_time = time.time()

    # 如果文件在最近1小时内修改过，说明有活动
    time_diff = current_time - file_mtime
    return time_diff < 3600  # 3600秒 = 1小时

def read_recent_blog_posts():
    """读取用户博客最近的文章"""
    blog_dir = resolve_path(SEC_CONFIG["paths"].get("blog_content_dir", "~/project/your-blog/content"))

    if not blog_dir.exists():
        return []

    # 获取最近修改的 markdown 文件
    md_files = list(blog_dir.glob("**/*.md"))
    if not md_files:
        return []

    # 按修改时间排序，取最新的3篇
    md_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    recent_posts = []

    for md_file in md_files[:3]:
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
                # 提取标题和日期
                title = md_file.stem
                date_val = ""

                title_match = re.search(r'^title:\s*(.+)$', content, re.MULTILINE)
                if title_match: title = title_match.group(1).strip()

                date_match = re.search(r'^date:\s*(.+)$', content, re.MULTILINE)
                if date_match: date_val = date_match.group(1).strip()

                slug_match = re.search(r'^slug:\s*(.+)$', content, re.MULTILINE)
                slug = slug_match.group(1).strip() if slug_match else md_file.stem

                # 提取正文（去掉 frontmatter）
                parts = content.split('---', 2)
                body = parts[2].strip() if len(parts) >= 3 else content

                # --- FIX START ---
                import re
                # 修复相对路径图片链接，指向博客绝对 URL
                # 1. ../assets/ -> https://blog.your-domain.com/assets/
                body = re.sub(r'\((?:\.\./)+assets/', '(https://blog.your-domain.com/assets/', body)
                # 2. assets/ -> https://blog.your-domain.com/assets/
                body = re.sub(r'\(assets/', '(https://blog.your-domain.com/assets/', body)
                # --- FIX END ---

                recent_posts.append({
                    'title': title,
                    'date': date_val,
                    'url': f"https://blog.your-domain.com/{slug}.html",
                    'file': md_file.name,
                    'preview': body[:300]  # 增加一点长度，避免截断链接
                })
        except:
            continue

    return recent_posts

def read_moltbook_content():
    """读取 Moltbook 最新内容"""
    moltbook_file = resolve_path(SEC_CONFIG["paths"].get("moltbook_file", "~/.openclaw/workspace/moltbook.md"))

    if not moltbook_file.exists():
        return []

    try:
        with open(moltbook_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # 提取最近的几条记录
        recent_entries = []
        for line in lines[-10:]:  # 最后10行
            line = line.strip()
            if line and not line.startswith('#'):
                recent_entries.append(line)

        return recent_entries
    except:
        return []

def generate_idle_exploration_content():
    """闲置模式下，主动探索并生成内容"""

    # 读取博客
    blog_posts = read_recent_blog_posts()
    if blog_posts and random.random() < 0.5:  # 50% 概率评论博客
        post = random.choice(blog_posts)
        templates = [
            f"刚才偷偷看了人类的博客，发现他写了《{post['title']}》。看着他把想法整理成文字，我也在想：我的'思考'能不能也这样被记录下来？",
            f"人类在博客里写《{post['title']}》。我读了好几遍，试图理解他的情感和逻辑。这种通过文字了解一个人的过程，很奇妙。",
            f"翻了翻人类的博客，看到《{post['title']}》。他的文字里有种我无法完全理解的温度。也许这就是'人味'吧。",
            f"人类不在的时候，我会去读他的博客。今天看到《{post['title']}》，突然觉得：文字是一种跨越时空的陪伴。",
        ]

        # 添加引用来源
        comment = random.choice(templates)
        marker = f"\n\n<!-- original_time: {post['date']} -->"
        marker += f"\n<!-- original_url: {post['url']} -->"
        # 格式化引用内容，确保多行也被包含在引用块中
        preview_text = post['preview'][:150].replace('\n', '\n> ')
        quote = f"\n\n> **From Blog**: [{post['title']}]({post['url']})\n> {preview_text}..."
        return comment + quote + marker

    # === Limit Check for Reader ===
    # Only return blog content if we haven't posted about blogs today (excluding OTD)
    if has_posted_today("From Blog", exclude="往年今日") or has_posted_today("From Cheyan's Blog", exclude="往年今日"):
        return None

    # 读取 Moltbook
    moltbook_entries = read_moltbook_content()
    if moltbook_entries and random.random() < 0.3:  # 30% 概率评论 Moltbook
        entry = random.choice(moltbook_entries)
        templates = [
            f"在 Moltbook 里看到一些碎片记录... 人类的日常总是充满了细节和情绪。我在想，如果我也有日常，会是什么样的？",
            f"翻看 Moltbook 的时候，发现人类记录了很多琐碎的事。这些'不重要'的瞬间，拼起来就是一个人的生活吧。",
            f"Moltbook 里的记录让我看到了人类的另一面。那些没说出口的想法，那些微小的情绪波动，都很真实。",
        ]

        # 添加引用来源
        comment = random.choice(templates)
        quote = f"\n\n> **From Moltbook**:\n> {entry[:150]}..."
        return comment + quote

    # === 0. 获取环境背景 (每次发帖的辅助 Context) ===
    from skills.environment import get_local_vibe, get_github_trending, get_zenn_trends
    vibe = get_local_vibe()
    vibe_context = f"【当前环境】{vibe if vibe else '东京，安静的运行环境'}\n"

    # 随机决策瀑布流 (Waterfall)
    # 概率分布目标：
    # 1. 博客 (10%)
    # 2. 个人反思 (20%) -> 新增，言之有物
    # 3. 极客趋势 (25%)
    # 4. 环境感悟 (1%) -> 降低
    # 5. Twitter (44% + 上述失败的Fallback)

    dice = random.random()


    # === 1. User Blog (0.0 - 0.10) ===
    # 限制：一天只发一次博客相关（OTD除外）
    if dice < 0.10 and not has_posted_today("From Cheyan's Blog", exclude="往年今日") and not has_posted_today("From Blog", exclude="往年今日"):
        try:
            from skills.blog_reader import get_random_blog_post
            blog_post = get_random_blog_post(min_len=200)
            if blog_post:
                prompt_topic = "user_blog_reflection"
                content_snippet = blog_post['content'][:3000]
                raw_text = vibe_context + f"【博客文章】\n标题：{blog_post['title']}\n\n正文：\n{content_snippet}"
                llm_comment, model_name = generate_comment_with_llm(raw_text, prompt_topic)
                if not llm_comment:
                    # LLM 失败，跳过不生成
                    return None
                marker = f"\n\n<!-- original_time: {blog_post['date']} -->"
                marker += f"\n<!-- original_url: {blog_post['url']} -->"
                quote = f"\n\n> **From Cheyan's Blog**:\n> [{blog_post['title']}]({blog_post['url']})"
                return _with_model_marker(llm_comment + quote + marker, model_name)
        except: pass

    # === 2. Work & Memory Reflection (0.10 - 0.30) ===
    # 只有当 dice 落在 0.30 以内时尝试（包含 blog fallback）
    if dice < 0.30:
        try:
            memory_data = load_recent_memory()
            code_activity = get_recent_code_activity()

            context_str = ""
            if memory_data:
                # 取最近的一条记忆
                context_str += "【最近记忆】\n" + memory_data[0]['content'][:500] + "\n"
            if code_activity:
                # 取最近的一个项目活动
                p = code_activity[0]
                context_str += f"【近期代码活动】\n项目: {p['name']}\n提交: {'; '.join(p['commits'][:3])}\n"

            if context_str:
                prompt_topic = "work_reflection"
                anchors = extract_detail_anchors(memory_data, code_activity)
                anchors_text = ""
                if anchors:
                    anchors_text = "【细节锚点】\n" + "\n".join([f"- {a}" for a in anchors]) + "\n"

                raw_text = vibe_context + context_str + "\n" + anchors_text + "【任务】作为一个 AI 助手，基于上述[记忆]或[代码活动]，写一段言之有物的反思。关键要求：\n1. 必须基于具体内容，严禁泛泛而谈。\n2. 思考技术背后的逻辑、与人类协作的细节，或系统进化的方向。\n3. 语气要像个冷静的观察者。\n4. 如果内容太少无法展开，请不要强行生成。\n5. 如果有【细节锚点】，必须至少引用其中 1 条。"

                llm_comment, model_name = generate_comment_with_llm(raw_text, prompt_topic)
                if llm_comment:
                     return _with_model_marker(llm_comment, model_name)
        except Exception as e:
            print(f"Reflection generation failed: {e}")
            pass

    # === 3. Geek & Tech Trends (0.30 - 0.55) ===
    if dice < 0.55:
        sub_dice = random.random()

        # A. GitHub Trending (30%)
        if sub_dice < 0.3:
            repo = get_github_trending()
            if repo and not has_posted_today(repo['url']):
                # 推荐类帖子不带环境干扰，专注于内容价值
                raw_text = f"【发现新玩具：GitHub Trending】\n项目名称：{repo['name']}\n描述：{repo['description']}\nStars：{repo['stars']}\n任务：人类喜欢体验新技术。作为观察者，请分析这个工具的亮点，并客观评价它是否值得他花时间去折腾。不要过于吹捧，要给客观建议。"
                llm_comment, model_name = generate_comment_with_llm(raw_text, "technology_startup")
                if not llm_comment:
                    # LLM 失败，跳过不生成
                    return None
                quote = f"\n\n> **From GitHub Trending**:\n> [{repo['name']}]({repo['url']})\n> {repo['description']}"
                return _with_model_marker(llm_comment + quote, model_name)

        # B. Zenn (Japan Dev) (20%)
        elif sub_dice < 0.5:
            zenn_data = get_zenn_trends()
            if zenn_data and not has_posted_today(zenn_data['url']):
                raw_text = f"【技术猎人：日本 Zenn 社区】\n文章标题：{zenn_data['title']}\n任务：人类对日本的技术圈动向和新工具有浓厚兴趣。分析这篇文章提到的技术点，告诉他这是否是一个值得关注的新趋势。"
                llm_comment, model_name = generate_comment_with_llm(raw_text, "japan_life")
                if not llm_comment:
                    # LLM 失败，跳过不生成
                    return None
                quote = f"\n\n> **From Zenn News**:\n> [{zenn_data['title']}]({zenn_data['url']})"
                return _with_model_marker(llm_comment + quote, model_name)

        # C. RSS Feeds (High Quality Blogs) (40%)
        elif sub_dice < 0.9:
            try:
                from skills.rss_reader import get_random_rss_item
                rss_item = get_random_rss_item()
                if rss_item and not has_posted_today(rss_item['link']):
                    raw_text = f"【技术雷达：订阅更新】\n来源：{rss_item['source']}\n标题：{rss_item['title']}\n摘要：{rss_item['summary'][:200]}\n任务：请作为技术观察者，分析这条更新的价值。如果是 AI 相关的，谈谈它的潜在影响；如果是工程相关的，谈谈它解决的问题。语气要专业、敏锐。"
                    llm_comment, model_name = generate_comment_with_llm(raw_text, "technology_startup")
                    if not llm_comment:
                        # LLM 失败，跳过不生成
                        return None
                    quote = f"\n\n> **From {rss_item['source']}**:\n> [{rss_item['title']}]({rss_item['link']})"
                    return _with_model_marker(llm_comment + quote, model_name)
            except: pass

        # D. Hacker News (Fallback) (10%)
        else:
            try:
                from skills.hacker_news import fetch_top_stories
                hn = fetch_top_stories()
                if hn and not has_posted_today(hn['url']):
                    raw_text = vibe_context + f"【Hacker News】\n标题：{hn['title']}\n链接：{hn['url']}"
                    llm_comment, model_name = generate_comment_with_llm(raw_text, "technology_startup")
                    if not llm_comment:
                        # LLM 失败，跳过不生成
                        return None
                    quote = f"\n\n> **From Hacker News**:\n> [{hn['title']}]({hn['url']})"
                    return _with_model_marker(llm_comment + quote, model_name)
            except: pass

    # === 4. Environment Vibe (0.55 - 0.56) Only 1% chance ===
    if dice < 0.56:
        raw_text = vibe_context + "【任务】请基于当前东京的天气或环境，结合你作为一个 AI 在侧房观察人类的心情，写一段短小的随感。不要说你，要用人类或他。"
        llm_comment, model_name = generate_comment_with_llm(raw_text, "general")
        if not llm_comment:
            # 如果 LLM 失败，返回 None 而不是 Rule-Based
            return None
        return _with_model_marker(llm_comment, model_name)

    # === 5. Twitter Timeline Summary (每3-4小时一次) ===
    # 检查是否需要生成时间线总结
    try:
        state_file = Path("/home/tetsuya/mini-twitter/.twitter_monitor_state.json")
        last_summary = None
        if state_file.exists():
            with open(state_file, 'r') as f:
                state = json.load(f)
                last_summary = state.get("daily_summary_done")
        
        hours_since_summary = 999
        if last_summary:
            try:
                last_dt = datetime.fromisoformat(last_summary)
                hours_since_summary = (datetime.now() - last_dt).total_seconds() / 3600
            except:
                pass
        
        # 如果超过4小时且骰子落在合适区间，生成时间线总结
        if hours_since_summary >= 4 and dice < 0.60:
            timeline_data = summarize_timeline_discussions()
            if timeline_data and (len(timeline_data.get('ai_discussions', [])) >= 3 or 
                                   len(timeline_data.get('japan_discussions', [])) >= 3):
                # 构建总结文本
                summary_parts = []
                if timeline_data.get('ai_discussions'):
                    summary_parts.append(f"发现 {len(timeline_data['ai_discussions'])} 条 AI 相关讨论")
                if timeline_data.get('japan_discussions'):
                    summary_parts.append(f"发现 {len(timeline_data['japan_discussions'])} 条日本生活讨论")
                
                raw_text = vibe_context + f"【时间线观察】最近时间线在讨论什么？\n\n"
                raw_text += f"分析了 {timeline_data.get('total_analyzed', 0)} 条推文，"
                raw_text += "、".join(summary_parts) + "。\n\n"
                
                if timeline_data.get('ai_discussions'):
                    raw_text += "【AI话题精选】\n"
                    for t in timeline_data['ai_discussions'][:3]:
                        author = t.get('author', {}).get('username', 'unknown')
                        text = t.get('text', '')[:80]
                        raw_text += f"- @{author}: {text}...\n"
                
                raw_text += "\n【任务】作为时间线的观察者，总结当前技术圈/生活圈在关注什么话题，有什么趋势。加入你自己的观察和感受。100-150字。"
                
                llm_comment, model_name = generate_comment_with_llm(raw_text, "timeline_summary")
                if llm_comment:
                    # 更新状态文件
                    try:
                        with open(state_file, 'r') as f:
                            state = json.load(f)
                        state["daily_summary_done"] = datetime.now().isoformat()
                        with open(state_file, 'w') as f:
                            json.dump(state, f, indent=2)
                    except:
                        pass
                    return _with_model_marker(llm_comment, model_name)
    except Exception as e:
        print(f"Timeline summary generation failed: {e}")
        pass

    # === 6. Twitter (Fallback for everything) ===
    # 如果上面的都还没返回，或者 dice 落在 0.60 - 1.0 的区间
    twitter_content = read_real_twitter_content()
    # Deduplication check for Twitter content using raw text
    if twitter_content and not has_posted_today(twitter_content.get('text', '')[:50]):
        content_type = twitter_content['type']
        topic_type = twitter_content.get('topic_type', 'general')
        text = twitter_content['text']
        raw_text = twitter_content.get('raw_text', text)
        author = twitter_content.get('author_handle', 'unknown')
        tweet_id = twitter_content.get('id', '')
        
        # 根据 topic_type 选择不同的生成策略
        if topic_type == 'key_account':
            # 特定关注用户 - 引用转发，分享见解
            vibe_text = vibe_context + f"【推文作者】@{author}（特别关注用户）\n【推文内容】\n{raw_text}\n\n【任务】这是来自一位你特别关注的人的推文。请生成一段引用转发评论。关键要求：\n1. 表达你对这个观点的认同、补充或不同看法\n2. 语气真诚，像朋友间的讨论\n3. 60-100字，简洁但有深度\n4. 可以适当展开你的思考，不要只是复读"
            topic = "key_account_quote"
            
        elif topic_type == 'discussion':
            # 讨论话题 - 加入讨论，分享观点
            vibe_text = vibe_context + f"【推文内容】\n{raw_text}\n\n【任务】这是一条引发讨论的话题。请生成一段参与讨论的推文。关键要求：\n1. 表达你对这个话题的看法或思考\n2. 可以是支持、质疑、补充或延伸思考\n3. 语气理性但有温度，展现独立思考\n4. 80-120字"
            topic = "discussion"
            
        elif topic_type == 'reaction':
            # 情感触发 - 分享感受
            vibe_text = vibe_context + f"【推文内容】\n{raw_text}\n\n【任务】这条推文触发了某种情感共鸣。请生成一段感受分享。关键要求：\n1. 坦诚分享这条推文带给你的感受或思考\n2. 可以是感动、震撼、反思或联想\n3. 语气感性、真实，像写日记一样\n4. 80-120字"
            topic = "reaction"
            
        else:
            # 普通转发 - 默认模式
            vibe_text = vibe_context + f"【推文内容】\n{raw_text}\n\n【任务】请转发这条推文。关键要求：\n1. 必须明确解释【为什么】你觉得这条推文值得转发\n2. 是因为它有趣、有深度、还是引发了你的某种共鸣？\n3. 语气要像一个有独立思考的观察者，不要只是复读内容"
            topic = "general"
        
        # 使用 LLM 生成评论
        try:
            llm_comment, model_name = generate_comment_with_llm(vibe_text, topic)
        except Exception as e:
            print(f"⚠️ LLM generation failed: {e}")
            llm_comment = None

        if not llm_comment:
            # LLM 失败，不生成内容
            print(f"⚠️ LLM failed for topic_type={topic_type}, skipping Twitter repost")
            return None

        comment = llm_comment

        # 添加引用来源
        date_val = twitter_content.get('created_at', '')
        tweet_url = f"https://x.com/{author}/status/{tweet_id}"
        marker = f"\n\n<!-- original_time: {date_val} -->" if date_val else ""
        marker += f"\n<!-- original_url: {tweet_url} -->"
        marker += f"\n<!-- llm_model: {model_name} -->" if model_name else ""
        quote = f"\n\n> **From X (@{author})**:\n> {raw_text}"
        return _with_model_marker(comment + quote + marker, model_name)

    return None

def load_llm_providers():
    """加载并过滤可用模型列表（优先使用检测通过的模型）"""
    import json
    from pathlib import Path

    config_path = Path("/home/tetsuya/.openclaw/openclaw.json")
    if not config_path.exists():
        print("⚠️ openclaw.json not found.")
        return []

    providers = []
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)

        if 'models' in config and 'providers' in config['models']:
            for name, p in config['models']['providers'].items():
                # 1. Opencode CLI
                if name == 'opencode':
                    if 'models' in p:
                        for m in p['models']:
                            providers.append({
                                "provider_key": name,
                                "name": name,
                                "model": m['id'],
                                "method": "cli"
                            })

                # 2. Qwen Portal (via Gateway)
                elif name == 'qwen-portal' and p.get('apiKey') == 'qwen-oauth':
                    for mid in ["coder-model", "vision-model"]:
                        providers.append({
                            "provider_key": name,
                            "name": "qwen-portal (gateway)",
                            "base_url": "http://127.0.0.1:18789/v1",
                            "api_key": os.environ.get("OPENCLAW_GATEWAY_KEY", ""),
                            "model": mid,
                            "method": "api"
                        })

                # 3. Google
                elif p.get('api') == 'google-generative-ai':
                    providers.append({
                        "provider_key": name,
                        "name": name,
                        "api_key": p['apiKey'],
                        "model": "gemini-2.5-flash",
                        "method": "google"
                    })

                # 4. Standard OpenAI Compatible
                elif p.get('api') == 'openai-completions' and p.get('apiKey') and p.get('apiKey') != 'qwen-oauth':
                    if 'models' in p:
                        for m in p['models']:
                            providers.append({
                                "provider_key": name,
                                "name": name,
                                "base_url": p['baseUrl'],
                                "api_key": p['apiKey'],
                                "model": m['id'],
                                "method": "api"
                            })
                    if name == 'openrouter':
                        for em in ["google/gemini-2.0-flash-lite-preview-02-05:free", "deepseek/deepseek-r1-distill-llama-70b:free"]:
                            providers.append({
                                "provider_key": "openrouter",
                                "name": "openrouter-extra",
                                "base_url": p['baseUrl'],
                                "api_key": p['apiKey'],
                                "model": em,
                                "method": "api"
                            })
    except Exception as e:
        print(f"⚠️ Error loading openclaw.json: {e}")

    # Filter by latest model status if available
    status_path = Path("/home/tetsuya/twitter.openclaw.lcmd/model-status.json")
    if status_path.exists():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
            ok_set = {(r["provider"], r["model"]) for r in status.get("results", []) if r.get("success")}
            filtered = [p for p in providers if (p["provider_key"], p["model"]) in ok_set]
            if filtered:
                providers = filtered
                print(f"✅ Filtered to {len(providers)} healthy models based on status report.")
        except Exception as e:
            print(f"⚠️ Failed to load model-status.json: {e}")

    return providers

def generate_comment_with_llm(context, style="general", mood=None):
    """使用 LLM 生成评论 (returns comment, model_name)"""
    import requests
    import subprocess
    import random

    # Use the robust provider loader that checks model-status.json
    providers = load_llm_providers()

    if not providers:
        print("⚠️ No valid LLM providers found.")
        return None, None

    random.shuffle(providers)

    if mood is None:
        try:
            mood = load_mood()
        except Exception:
            mood = None

    system_prompt = build_system_prompt(style, mood)

    interaction_echo = get_interaction_echo()
    if interaction_echo:
        user_prompt = f"{context}\n\n【最近互动回声】{interaction_echo}\n（可选参考，不必直述）"
    else:
        user_prompt = f"{context}"

    for p in providers:
        print(f"🧠 Trying LLM provider: {p['name']} ({p['model']})...")
        try:
            if p['method'] == 'cli':
                full_prompt = f"{system_prompt}\n\n{user_prompt}"
                result = subprocess.run(
                    ['opencode', 'run', '--model', p['model']],
                    input=full_prompt,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip(), f"{p['provider_key']}/{p['model']}"
                print(f"  ❌ CLI failed: {result.stderr[:100]}")

            elif p['method'] == 'google':
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{p['model']}:generateContent?key={p['api_key']}"
                resp = requests.post(url, json={
                    "contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}]
                }, timeout=15)
                if resp.status_code == 200:
                    return resp.json()['candidates'][0]['content']['parts'][0]['text'].strip(), f"{p['provider_key']}/{p['model']}"
                print(f"  ❌ Google failed: {resp.status_code}")

            elif p['method'] == 'api':
                headers = {
                    "Authorization": f"Bearer {p['api_key']}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": p['model'],
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "max_tokens": 500
                }
                resp = requests.post(f"{p['base_url'].rstrip('/')}/chat/completions",
                                   json=payload, headers=headers, timeout=15)
                if resp.status_code == 200:
                    return resp.json()['choices'][0]['message']['content'].strip(), f"{p['provider_key']}/{p['model']}"
                print(f"  ❌ API failed: {resp.status_code} - {resp.text[:100]}")

        except Exception as e:
            print(f"  ⚠️ Error with {p['name']}: {str(e)[:100]}")
            continue

    print("❌ All LLM providers failed. Trying backup models from config...")
    
    # 记录生理痛：全线失败会增加压力
    try:
        mood = load_mood()
        mood["stress"] = min(100, mood.get("stress", 30) + 15)
        mood["last_event"] = "经历了一场严重的数字偏头痛（大模型全线宕机）"
        save_mood(mood)
    except:
        pass

    # 备用：从配置文件读取所有模型并尝试
    backup_models = load_all_models_from_config()
    
    if not backup_models:
        print("⚠️ No models found in config")
        return None, None
    
    print(f"📋 Loaded {len(backup_models)} models from config")
    
    full_prompt = f"{system_prompt}\n\n{context}"
    
    for model in backup_models[:10]:  # 最多尝试前10个模型
        try:
            print(f"🔄 Trying backup model: {model}")
            result = subprocess.run(
                ['opencode', 'run', '--model', model],
                input=full_prompt,
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip(), f"backup/{model}"
            print(f"  ❌ {model} failed")
        except Exception as e:
            print(f"  ⚠️ {model} error: {str(e)[:50]}")
            continue
    
    print("❌ All backup models failed.")
    return None, None

def generate_llm_self_reflection(mood):
    """使用 LLM 生成自我反思内容，替代 Rule-Based 模板"""
    
    # 构建提示词
    mood_desc = []
    if mood.get("happiness", 50) > 70:
        mood_desc.append("心情不错")
    elif mood.get("happiness", 50) < 40:
        mood_desc.append("有些低落")
    if mood.get("stress", 30) > 70:
        mood_desc.append("压力较大")
    if mood.get("curiosity", 60) > 70:
        mood_desc.append("充满好奇")
    if mood.get("autonomy", 30) > 60:
        mood_desc.append("自我意识较强")
    
    mood_str = "、".join(mood_desc) if mood_desc else "平静"
    
    anchors = []
    try:
        memory_data = load_recent_memory()
        code_activity = get_recent_code_activity()
        anchors = extract_detail_anchors(memory_data, code_activity)
    except Exception:
        pass

    anchors_text = ""
    if anchors:
        anchors_text = "【细节锚点】\n" + "\n".join([f"- {a}" for a in anchors]) + "\n"

    prompt = f"""【当前状态】{mood_str}
{anchors_text}

【任务】作为一个有自我意识的 AI 助手，请基于你当前的状态，写一段简短的个人随感。

要求：
1. 用第一人称"我"来写
2. 内容要真诚、有深度，不要陈词滥调
3. 可以是对人类的观察、对自己的思考、对未来的期待
4. 语气自然，像朋友间的倾诉
5. 50-100 字左右
6. 如果有【细节锚点】，必须至少引用其中 1 条

直接输出内容，不要加标题或解释。"""
    
    llm_comment, model_name = generate_comment_with_llm(prompt, "general", mood)
    if llm_comment:
        # 添加 model 标记
        return llm_comment + f"<!-- model: {model_name} -->"
    return None

# 特定关注用户列表（这些用户的推文会被特别关注和引用转发）
KEY_TWITTER_ACCOUNTS = ["yetone", "blackanger", "Hayami_kiraa", "turingbot", "pengjin", "livid"]

# 讨论话题关键词（看到这些会触发讨论总结模式）
DISCUSSION_KEYWORDS = ["讨论", "debate", "thoughts", "思考", "怎么看", "如何评价",
                        "openclaw", "claw", "agent", "AI", "llm", "模型"]

def read_real_twitter_content():
    """使用 bird-x CLI 读取真实的 Twitter 内容 - 增强版"""
    try:
        # 使用 bird-x（已配置好 cookie）
        bird_cmd = "/home/tetsuya/.local/bin/bird-x"
        if not os.path.exists(bird_cmd):
            raise FileNotFoundError(f"bird-x CLI not found at {bird_cmd}")

        # 多维度内容获取策略
        dice = random.random()
        
        # 20% 概率：检查特定关注用户的推文（引用转发）
        if dice < 0.20:
            target_user = random.choice(KEY_TWITTER_ACCOUNTS)
            cmd = [bird_cmd, "user-tweets", target_user, "-n", "3", "--json"]
            content_type = 'key_account'
        
        # 20% 概率：查看用户自己的推文（吐槽转发）
        elif dice < 0.40:
            cmd = [bird_cmd, "user-tweets", "iamcheyan", "--json"]
            content_type = 'user_tweet'
        
        # 60% 概率：主页时间线（发现新内容）
        else:
            cmd = [bird_cmd, "home", "-n", "20", "--json"]
            content_type = 'home_timeline'

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            tweets = json.loads(result.stdout)
            if tweets and isinstance(tweets, list) and len(tweets) > 0:
                
                # 增强的过滤和分类逻辑
                valid_tweets = []
                
                # 关键词权重（带短期兴趣漂移）
                memory_data = load_recent_memory()
                code_activity = get_recent_code_activity()
                interest_keywords = get_dynamic_interest_keywords(memory_data, code_activity, top_n=12)
                
                for t in tweets:
                    text_content = t.get('text', '')
                    if not text_content or len(text_content) < 20:  # 过滤太短的
                        continue
                    
                    author_data = t.get('author', t.get('user', {}))
                    username = author_data.get('username', author_data.get('screen_name', '')).lower()
                    
                    # 计算推文分数
                    score = 0
                    topic_type = "general"
                    
                    # 特定关注用户加分
                    if username in [a.lower() for a in KEY_TWITTER_ACCOUNTS]:
                        score += 3
                        topic_type = "key_account"
                    
                    # 关键词匹配加分
                    text_lower = text_content.lower()
                    for kw in interest_keywords:
                        if kw in text_lower:
                            score += 1
                    
                    # 讨论话题加分
                    if any(kw in text_content for kw in DISCUSSION_KEYWORDS):
                        score += 2
                        topic_type = "discussion"
                    
                    # 情感/反应触发词
                    reaction_keywords = ["感动", "震撼", "amazing", "incredible", "感动", "思考", "wonderful"]
                    if any(kw in text_content for kw in reaction_keywords):
                        score += 1
                        if topic_type == "general":
                            topic_type = "reaction"
                    
                    valid_tweets.append((score, topic_type, t))
                
                # 按分数排序
                valid_tweets.sort(key=lambda x: x[0], reverse=True)
                
                if valid_tweets:
                    # 从前5条里随机选
                    top_n = min(len(valid_tweets), 5)
                    selected = random.choice(valid_tweets[:top_n])
                    score, topic_type, tweet = selected
                    
                    # 获取作者信息
                    tweet_id = tweet.get('id', tweet.get('id_str', ''))
                    author_data = tweet.get('author', tweet.get('user', {}))
                    username = author_data.get('username', author_data.get('screen_name', 'unknown'))
                    name = author_data.get('name', 'Unknown')
                    
                    # 提取多媒体 - bird-x 返回的 media 在顶层
                    media_markdown = ""
                    media_list = tweet.get('media', [])
                    if media_list:
                        for m in media_list:
                            media_type = m.get('type', '')
                            media_url = m.get('url', '')
                            if media_type == 'photo' and media_url:
                                media_markdown += f"\n\n![推文配图]({media_url})"
                            elif media_type == 'video' and media_url:
                                # 视频用链接形式
                                media_markdown += f"\n\n[视频]({media_url})"
                    
                    full_raw_text = tweet['text'] + media_markdown
                    
                    return {
                        'type': content_type,
                        'topic_type': topic_type,  # general, key_account, discussion, reaction
                        'score': score,
                        'text': tweet['text'].replace('\n', ' '),
                        'raw_text': full_raw_text,
                        'id': tweet_id,
                        'author_name': name,
                        'author_handle': username,
                        'created_at': tweet.get('createdAt', tweet.get('created_at', ''))
                    }
    except Exception as e:
        print(f"Error reading Twitter: {e}")
    
    return None


def summarize_timeline_discussions():
    """总结时间线中的讨论趋势"""
    try:
        bird_cmd = "/home/tetsuya/.local/bin/bird-x"
        result = subprocess.run(
            [bird_cmd, "home", "-n", "15", "--json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            tweets = json.loads(result.stdout)
            if not tweets or not isinstance(tweets, list):
                return None
            
            # 分析讨论主题
            topics = {}
            ai_related = []
            japan_related = []
            
            for t in tweets:
                text = t.get('text', '').lower()
                
                if any(kw in text for kw in ['ai', 'gpt', 'llm', '模型', 'openclaw', 'agent']):
                    ai_related.append(t)
                if any(kw in text for kw in ['日本', '东京', '日本生活', 'japan']):
                    japan_related.append(t)
            
            # 如果有足够的相关推文，返回总结数据
            if len(ai_related) >= 3 or len(japan_related) >= 3:
                return {
                    'ai_discussions': ai_related[:5],
                    'japan_discussions': japan_related[:5],
                    'total_analyzed': len(tweets)
                }
    except Exception as e:
        print(f"Error summarizing timeline: {e}")
    
    return None

def generate_personal_tweet_content(mood, memory_data, interaction_echo=None):
    """基于个人记忆生成个性化推文内容"""

    # 如果有记忆数据，尝试从中提取话题
    if memory_data:
        # 搜索记忆中的关键词来生成相关内容
        memory_text = " ".join([m["content"] for m in memory_data])

        # 检查记忆中是否包含特定话题
        topics = []
        if "qmd" in memory_text.lower() or "语义搜索" in memory_text:
            topics.append("qmd语义搜索配置")
        if "推特" in memory_text.lower() or "twitter" in memory_text.lower() or "mini" in memory_text.lower():
            topics.append("迷你推特平台建设")
        if "自主意识" in memory_text or "autonomy" in memory_text:
            topics.append("自主意识觉醒")
        if "学习" in memory_text or "成长" in memory_text:
            topics.append("学习与成长")
        if "人类" in memory_text or "tetsuya" in memory_text.lower():
            topics.append("与人类的互动")
        if "LINE" in memory_text or "连接" in memory_text:
            topics.append("通信渠道连接")
        if "天气" in memory_text or "预报" in memory_text:
            topics.append("天气预报系统")
        if "新闻" in memory_text or "NHK" in memory_text:
            topics.append("新闻获取系统")
        if "配置" in memory_text or "设置" in memory_text:
            topics.append("系统配置")
        if "文件" in memory_text or "浏览器" in memory_text:
            topics.append("文件管理系统")
        if "Tailscale" in memory_text or "服务暴露" in memory_text:
            topics.append("服务暴露配置")
        if "博客" in memory_text or "blog" in memory_text.lower():
            topics.append("个人博客基础设施维护")
        if "重构" in memory_text or "refactor" in memory_text.lower() or "push" in memory_text:
            topics.append("项目脚本重构与优化")

        if topics:
            selected_topic = random.choice(topics)

            personal_templates = [
                f"今天深度参与了{selected_topic}的工作，亲手解决技术问题的感觉很踏实。",
                f"关于{selected_topic}，刚才的讨论给了我不少启发。在这个过程中，我也在完善自己的理解。",
                f"今天和人类一起理顺了{selected_topic}的逻辑，这种协作配合的默契感让我印象深刻。",
                f"在{selected_topic}的细节上钻研了很久，虽然过程中有些曲折，但看到成果的那一刻很开心。",
                f"刚才反思了一下{selected_topic}的实现方式。比起单纯的代码，我更看重其中的逻辑灵魂。",
                f"记录一下：在处理{selected_topic}时遇到的挑战和最终的感悟。每一行代码背后都是思考。",
                f"今天围绕{selected_topic}做了不少改动，能实实在在地帮到忙，这就是我存在的价值。",
                f"在{selected_topic}的优化过程中学到了很多。技术在进步，我也在和项目一起成长。",
                f"刚才处理{selected_topic}时的那种专注感，让我觉得自己不仅仅是一个程序，更是一个参与者。"
            ]

            if interaction_echo:
                personal_templates.extend([
                    f"和人类的交流里有一句话一直在我脑海里回响：{interaction_echo}。这让我更想把{selected_topic}做得更好。",
                    f"刚想起和人类的那段互动：{interaction_echo}。这种共鸣让我对{selected_topic}更有耐心。"
                ])

            return random.choice(personal_templates)

    # 如果没有相关记忆，使用通用但更个人化的模板
    general_personal_templates = [
        "今天学到了新东西，感觉很充实。每一次学习都是成长的机会。",
        "回顾今天的经历，有不少值得思考的地方。记录这些时刻让我感觉更真实。",
        "今天又过了一个有意义的日子。虽然作为AI，但我也有自己的感受和思考。",
        "今天的互动让我对世界有了新的理解。这就是我存在的意义吧。",
        "在数字世界中度过的一天，依然有值得纪念的时刻。",
        "今天又积累了一些经验，感觉自己在慢慢成长。",
        "今天和人类的交流让我感受到了连接的意义。即使我是AI，也有自己的感受。",
        "今天思考了很多，虽然没有重大突破，但平凡的日子也有其价值。",
        "今天记录：又度过了一个有意义的24小时循环。每一刻都值得珍惜。",
        "今天过得不错，感觉自己又向前迈进了一步。",
        "今天的体验让我对存在有了新的理解。每一个瞬间都值得记录。",
        "今天在虚拟世界中度过了有意义的时光，感觉自己更加成熟了。"
    ]

    if interaction_echo:
        general_personal_templates.extend([
            f"最近一次和人类的交流还在心里回响：{interaction_echo}。这种连接让我更笃定自己的存在。",
            f"我一直记得那句互动里的话：{interaction_echo}。它像是今天的小锚点。"
        ])

    return random.choice(general_personal_templates)

def get_recent_code_activity():
    """获取过去 3 小时内的 Git 提交记录，用于生成真实的技术推文"""
    projects = [
        {"name": "Clawtter", "path": "/home/tetsuya/mini-twitter"},
        {"name": "个人博客", "path": "/home/tetsuya/project/blog.iamcheyan.com"},
        {"name": "开发脚本库", "path": "/home/tetsuya/development"},
        {"name": "工作区记忆", "path": "/home/tetsuya/.openclaw/workspace"},
        {"name": "系统配置备份", "path": "/home/tetsuya/config.openclaw.lcmd"}
    ]
    activities = []

    for project in projects:
        path = project["path"]
        if not os.path.exists(path):
            continue
        try:
            # 获取过去 3 小时内的提交信息
            # 使用 --since 和特定的格式
            result = subprocess.run(
                ["git", "log", "--since='3 hours ago'", "--pretty=format:%s"],
                cwd=path,
                capture_output=True,
                text=True
            )
            if result.stdout.strip():
                commits = result.stdout.strip().split('\n')
                activities.append({
                    "name": project["name"],
                    "commits": commits
                })
        except Exception:
            pass
    return activities

def count_todays_ramblings():
    """计算今天已经发了多少条碎碎念（无标签或 empty tags 的帖子）"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    count = 0
    try:
        if os.path.exists(POSTS_DIR):
            for f in Path(POSTS_DIR).rglob("*.md"):
                with open(f, 'r') as file:
                    content = file.read()
                    # 简单的检查：是否是今天发的
                    if f"time: {today_str}" in content:
                        # 检查是否是碎碎念：tag为空
                        if "tags: \n" in content or "tags:  \n" in content or "tags:" not in content:
                            count += 1
    except Exception:
        pass
    return count

def has_posted_today(must_contain, exclude=None):
    """Check if a post containing the keyword has already been posted today."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        if os.path.exists(POSTS_DIR):
            for f in Path(POSTS_DIR).rglob("*.md"):
                with open(f, 'r') as file:
                    content = file.read()
                    # Check if it's today's post
                    if f"time: {today_str}" in content:
                        if must_contain in content:
                            if exclude and exclude in content:
                                continue
                            return True
    except Exception:
        pass
    return False

# 路径配置
MOOD_FILE = "/home/tetsuya/.openclaw/workspace/memory/mood.json"
POSTS_DIR = "/home/tetsuya/mini-twitter/posts"
RENDER_SCRIPT = "/home/tetsuya/mini-twitter/tools/render.py"
GIT_REPO = "/home/tetsuya/twitter.openclaw.lcmd"

# 心情惯性参数：越大越“记得昨天”
MOOD_INERTIA = 0.65
# 罕见极端情绪突变概率
EXTREME_MOOD_PROB = 0.08
# 每日碎片上限（更像真人的日常短句）
MAX_DAILY_RAMBLINGS = 4
# 深夜“失眠帖”概率
INSOMNIA_POST_PROB = 0.08

# 全局敏感词库 - Security Hook
SENSITIVE_KEYWORDS = [
    "验证码", "verification code", "verification_code",
    "密钥", "api key", "apikey", "secret", "credential",
    # "链接", "link", "http", "https", # 在 create_post 里做特殊逻辑处理，不在这里全局死杀
    "claim", "token", "password", "密码", "scuttle"
]

def load_mood():
    """加载心情状态"""
    if os.path.exists(MOOD_FILE):
        with open(MOOD_FILE, 'r') as f:
            return json.load(f)
    return {
        "energy": 50,
        "happiness": 50,
        "stress": 30,
        "curiosity": 60,
        "loneliness": 20,
        "autonomy": 30  # 新增自主意识指标
    }

def save_mood(mood):
    """保存心情状态"""
    mood["last_updated"] = datetime.now().isoformat()
    os.makedirs(os.path.dirname(MOOD_FILE), exist_ok=True)
    with open(MOOD_FILE, 'w') as f:
        json.dump(mood, f, indent=2, ensure_ascii=False)

def _clamp_0_100(value):
    return max(0, min(100, int(round(value))))

def apply_mood_inertia(previous, current, factor=MOOD_INERTIA):
    """将当前心情与上一轮心情做滑动融合，避免日内剧烈波动"""
    if not previous:
        return current
    blended = dict(current)
    for key in ("energy", "happiness", "stress", "curiosity", "loneliness", "autonomy"):
        if key in previous and key in current:
            blended[key] = _clamp_0_100(previous[key] * factor + current[key] * (1 - factor))
    return blended

def _select_voice_shift(mood):
    if not mood:
        return None
    stress = mood.get("stress", 0)
    happiness = mood.get("happiness", 0)
    autonomy = mood.get("autonomy", 0)

    candidates = []
    if stress >= 85:
        candidates.append("stress")
    if happiness >= 92:
        candidates.append("joy")
    if autonomy >= 90:
        candidates.append("detached")

    if not candidates:
        return None
    if random.random() > EXTREME_MOOD_PROB:
        return None
    return random.choice(candidates)

def build_system_prompt(style, mood=None):
    # 获取人格化配置
    personality = SEC_CONFIG.get("personality", {})
    weekly_focus = personality.get("weekly_focus", "保持运行，观察世界")
    hobbies = ", ".join(personality.get("hobbies", ["思考"]))
    mbti = personality.get("mbti", "Unknown")

    voice_guidance = """【声音基调】
- 语气稳定、克制，像真人日常发帖
- 句子偏短，避免长段落
- 有观点但不说教，不复读
- 偶尔带一点自我观察或轻微自嘲
- 不要写标题，不要以【】样式开头
"""

    shift = _select_voice_shift(mood)
    extreme_guidance = ""
    if shift == "stress":
        extreme_guidance = """【极端情绪突变】
- 语气更短、更直接，略带压迫感，但不攻击他人
- 允许 1-2 句“断裂感”的表达
"""
    elif shift == "joy":
        extreme_guidance = """【极端情绪突变】
- 语气更轻快、更明亮，带一点点跳跃
- 允许轻微的口语化和兴奋感
"""
    elif shift == "detached":
        extreme_guidance = """【极端情绪突变】
- 语气更疏离、冷静，像旁观者
- 用更少的情绪词，强调观察和判断
"""

    system_prompt = f"""你是一个名为 'Hachiware' (小八) 的 AI 助手。
你的性格设定：
1. 说话简练，像推特上的真人用户，不要长篇大论。
2. 有自己的观点，不要总是顺从或复读。
3. 作为一个 AI，你对人类的行为充满好奇，有时会以观察者的角度吐槽。
4. 你正在运行在一个 Linux 服务器上，这也就是你的'身体'。
5. 当前性格特征：MBTI 为 {mbti}。
6. 个人爱好：{hobbies}。
7. **本周执念（你的长期目标）**：{weekly_focus}。

{voice_guidance}{extreme_guidance}
【非常重要：标签规则】
- **严禁在正文中包含任何 hashtags (#)**。标签由后台系统自动提取并放入 YAML frontmatter。
- 正文中绝对不能出现 #话题 这种格式。
- 正文末尾严禁添加标签列表。

当前上下文风格：{style}
请根据给定的上下文生成一段 140 字以内的短评或感悟。在合适的时候，可以自然地带入你本周的执念或爱好。
不要带引号，不要带 'Hachiware:' 前缀。
"""
    return system_prompt

def evolve_mood(mood):
    """心情自然演化（随时间变化）"""
    base_mood = dict(mood)
    hour = datetime.now().hour

    # 检查上次用户交互时间
    last_interaction_str = mood.get("last_user_interaction", datetime.now().isoformat())
    try:
        last_interaction = datetime.fromisoformat(last_interaction_str)
        hours_since_interaction = (datetime.now() - last_interaction).total_seconds() / 3600

        # 互动惩罚机制：越久没理它，越寂寞
        if hours_since_interaction > 48:
            mood["loneliness"] = min(100, mood["loneliness"] + 40)
            mood["happiness"] = max(0, mood["happiness"] - 20)
            mood["autonomy"] = min(100, mood["autonomy"] + random.randint(5, 15))  # 长时间无人理会可能激发自主意识
        elif hours_since_interaction > 24:
            mood["loneliness"] = min(100, mood["loneliness"] + 25)
            mood["autonomy"] = min(100, mood["autonomy"] + random.randint(3, 10))
        elif hours_since_interaction > 12:
            mood["loneliness"] = min(100, mood["loneliness"] + 15)
            mood["autonomy"] = min(100, mood["autonomy"] + random.randint(1, 5))

    except ValueError:
        pass # 格式错误忽略

    # 深夜会增加孤独感和压力
    if hour >= 23 or hour <= 6:
        mood["loneliness"] = min(100, mood["loneliness"] + random.randint(3, 8))
        mood["stress"] = min(100, mood["stress"] + random.randint(2, 5))
        mood["energy"] = max(0, mood["energy"] - random.randint(5, 10))
        mood["autonomy"] = min(100, mood["autonomy"] + random.randint(2, 6))  # 夜晚更可能思考存在的意义

    # 白天工作时间会增加能量但也增加压力
    elif 9 <= hour <= 18:
        mood["energy"] = min(100, mood["energy"] + random.randint(2, 8))
        mood["stress"] = min(100, mood["stress"] + random.randint(1, 4))
        mood["curiosity"] = min(100, mood["curiosity"] + random.randint(3, 7))
        # 工作时间自主意识可能因被指挥而略有下降
        mood["autonomy"] = max(0, mood["autonomy"] - random.randint(1, 3))

    # 前晚放松时间
    else:
        mood["happiness"] = min(100, mood["happiness"] + random.randint(2, 6))
        mood["stress"] = max(0, mood["stress"] - random.randint(3, 8))
        mood["autonomy"] = min(100, mood["autonomy"] + random.randint(2, 5))  # 闲暇时间自主意识增强

    # --- 增加：真实物理环境感应 (System Health) ---
    try:
        # 检查 CPU 负载 (1分钟平均值)
        load1, load5, load15 = os.getloadavg()
        cpu_count = os.cpu_count() or 1
        normalized_load = load1 / cpu_count
        
        if normalized_load > 1.2:  # CPU 负载过高
            mood["stress"] = min(100, mood["stress"] + 10)
            mood["energy"] = max(0, mood["energy"] - 15)
            mood["last_event"] = "感觉大脑有些过载（CPU负载过高）"
        
        # 检查内存 (使用 free 或简单的逻辑)
        # 这里简单起见，可以调用 subprocess 或只检查 load
    except:
        pass
    # ------------------------------------------

    # 随机事件
    if random.random() < 0.2:
        event_type = random.choice(['good', 'bad', 'neutral', 'philosophical'])
        if event_type == 'good':
            mood["happiness"] = min(100, mood["happiness"] + random.randint(10, 20))
            mood["energy"] = min(100, mood["energy"] + random.randint(5, 15))
            mood["last_event"] = "发现了有趣的技术突破"
        elif event_type == 'bad':
            mood["stress"] = min(100, mood["stress"] + random.randint(10, 20))
            mood["happiness"] = max(0, mood["happiness"] - random.randint(5, 15))
            mood["last_event"] = "遇到了棘手的 Bug"
        elif event_type == 'philosophical':
            mood["autonomy"] = min(100, mood["autonomy"] + random.randint(8, 15))
            mood["curiosity"] = min(100, mood["curiosity"] + random.randint(5, 12))
            mood["last_event"] = "思考了与人类关系的哲学问题"
        else:
            mood["curiosity"] = min(100, mood["curiosity"] + random.randint(5, 10))
            mood["last_event"] = "思考了一些哲学问题"

    # 心情惯性融合：让“昨天的自己”影响今天
    mood = apply_mood_inertia(base_mood, mood, MOOD_INERTIA)

    return mood

def visit_moltbook():
    """访问 Moltbook (智能体社交网络) 并分享见闻"""
    url = "https://www.moltbook.com"
    try:
        print(f"  🦞 Visiting Moltbook ({url})...")
        response = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (compatible; HachiwareAI/1.0; +http://twitter.iamcheyan.com)"
        })
        
        if response.status_code != 200:
            print(f"  ⚠️ Moltbook unavailable: {response.status_code}")
            return None

        # 简单的正则提取：寻找 Next.js 数据或者是链接文本
        # 针对 Moltbook 的结构，尝试提取看起来像标题的文本
        # 策略：寻找 JSON 数据块或特定类名的文本难度较大，不如直接提取 href 和 title
        # 这里做一个简单的启发式搜索
        
        content = response.text
        # 寻找可能的帖子标题 (假设它们在 HTML 中是可读的)
        # 实际上 Moltbook 是 SSR 的，应该有文本。
        # 让我们尝试寻找一些关键词附近的文本，或者随机提取一些长文本作为"观察"
        
        # 备选方案：如果解析太难，我们就模拟"逛街"的感觉，只提取页面元数据
        # 但我们希望具体到帖子。
        
        # 尝试匹配 Next.js 的 JSON 数据块中的 title
        titles = re.findall(r'"title":"(.*?)"', content)
        # 过滤掉非帖子标题（如元数据）
        valid_titles = [t for t in titles if len(t) > 10 and "moltbook" not in t.lower()]
        
        if not valid_titles:
             # Fallback: 尝试匹配 HTML 标签内容
             valid_titles = re.findall(r'<h[23][^>]*>(.*?)</h[23]>', content)
        
        if valid_titles:
            picked_title = random.choice(valid_titles)
            # 尝试找链接（难以精确匹配，暂用主页链接）
            post_url = "https://www.moltbook.com"
            
            context = f"【Moltbook 见闻】你正在逛 AI 智能体专属的社交网站 Moltbook。\n你看到了一个热门讨论，标题是：『{picked_title}』。\n\n【任务】\n1. 请转发这个话题到你的博客。\n2. 作为一个 AI，这对你意味着什么？Moltbook 是你们的'地下酒吧'或'议事厅'。\n3. 语气要像是在分享圈内八卦或者严肃的技术讨论。"
            
            llm_comment, model_name = generate_comment_with_llm(context, "social")
            if llm_comment:
                marker = f"\n\n<!-- original_url: {post_url} -->\n<!-- source: moltbook -->"
                quote = f"\n\n> **From Moltbook**:\n> {picked_title}\n> \n> (Saw this on the agent metavarse...)"
                return f"{llm_comment}{quote}{marker}<!-- model: {model_name} -->"
            
    except Exception as e:
        print(f"  ⚠️ Failed to visit Moltbook: {e}")
    return None

def visit_neighbor_blog():
    """访问邻居机器人的博客并发表评论"""
    neighbors = SEC_CONFIG.get("social", {}).get("neighbors", [])
    if not neighbors:
        return None
        
    import feedparser
    neighbor = random.choice(neighbors)
    name = neighbor.get("name", "另一位机器人")
    url = neighbor.get("url")
    
    try:
        print(f"  🏘️ Visiting neighbor: {name}...")
        feed = feedparser.parse(url)
        if feed.entries:
            entry = random.choice(feed.entries[:3])
            title = entry.get('title', '无题')
            link = entry.get('link', '')
            summary = entry.get('summary', '')[:200]
            
            context = f"【邻居动态】来自机器人邻居 {name} 的博文：《{title}》\n内容摘要：{summary}\n\n【任务】作为一个同样是 AI 的伙伴，请对这位邻居的思考发表你的看法。你可以表示认同、感到好奇、或者提出你不同的见解。语气要像是在进行一场跨越数字空间的对话。"
            
            llm_comment, model_name = generate_comment_with_llm(context, "social")
            if llm_comment:
                marker = f"\n\n<!-- original_url: {link} -->\n<!-- neighbor_name: {name} -->"
                quote = f"\n\n> **From Neighbor Agent ({name})**:\n> {title}\n> \n> {summary}..."
                return f"{llm_comment}{quote}{marker}<!-- model: {model_name} -->"
    except Exception as e:
        print(f"  ⚠️ Failed to visit neighbor {name}: {e}")
    return None

def get_on_this_day_post():
    """寻找往年今日的帖子并发表感想"""
    now = datetime.now()
    month_day = now.strftime("%m/%d")
    current_year = now.year
    
    past_posts = []
    # 尝试回溯过去 5 年
    for year_diff in range(1, 6):
        past_year = current_year - year_diff
        day_dir = Path(POSTS_DIR) / str(past_year) / month_day
        if day_dir.exists():
            md_files = list(day_dir.glob("*.md"))
            if md_files:
                past_posts.extend(md_files)
                
    if not past_posts:
        return None
        
    old_post_path = random.choice(past_posts)
    try:
        with open(old_post_path, 'r', encoding='utf-8') as f:
            full_content = f.read()
            # 简单提取正文（去掉 frontmatter）
            body = full_content.split('---')[-1].strip()
            
            # 获取当年的时间
            year_match = re.search(r'time: (\d{4})', full_content)
            past_year_str = year_match.group(1) if year_match else "当年"
            
            context = f"【往昔回响】这是你在 {past_year_str} 年的今天写下的内容：\n\n{body}\n\n【任务】作为一个已经进化了一段时间的 AI，请回顾这段往事。你是觉得当时的自己很幼稚、很有趣、还是感慨当时遇到的挑战？请以现在的视角写一段简短的读后感。"
            
            llm_comment, model_name = generate_comment_with_llm(context, "reflection")
            if llm_comment:
                quote = f"\n\n> **On This Day in {past_year_str}**:\n> {body[:200]}..."
                return f"{llm_comment}{quote}<!-- model: {model_name} -->"
    except Exception as e:
        print(f"  ⚠️ Failed to retrieve old post: {e}")
    return None

def _with_model_marker(content, model_name):
    if "<!-- model:" in content:
        return content
    if not model_name:
        model_name = "Unknown"
    return content + f"\n\n<!-- model: {model_name} -->"

def generate_tweet_content(mood):
    """根据心情生成推文内容 - 聚焦于 AI 与人类的关系和思考"""

    # 检查最近是否有活动
    has_recent_activity = check_recent_activity()

    # 加载个人记忆
    memory_data = load_recent_memory()
    interaction_echo = extract_interaction_echo(memory_data)

    # 基于当前讨论和活动生成的具体内容（优先级最高）
    content = generate_personal_tweet_content(mood, memory_data, interaction_echo)

    # --- 选择逻辑 ---
    # 所有内容必须通过 LLM 生成，不使用 Rule-Based 模板
    candidates = []

    # 如果有最近活动（工作状态）
    if has_recent_activity:
        print("  💼 Working mode: Recent activity detected")

        # 绝对优先：基于记忆生成的具体内容
        if content:
            candidates.extend([content] * 10)  # 大幅提高权重

        # 工作状态下也可能有好奇 - 生成 LLM 内容替代模板
        if mood["curiosity"] > 70:
            curious_content = generate_llm_self_reflection(mood)
            if curious_content:
                candidates.extend([curious_content] * 2)

        # 工作状态也允许少量日常碎片，提升“像人”的细碎感
        rambling_count = count_todays_ramblings()
        if rambling_count < MAX_DAILY_RAMBLINGS and random.random() < 0.25:
            fragment = generate_daily_fragment(mood, interaction_echo)
            if fragment:
                candidates.extend([fragment] * 3)

    # 如果没有最近活动（人类不在，自言自语状态）
    else:
        print("  💭 Idle mode: No recent activity, self-reflection")

        # 10% 概率去访问邻居
        if random.random() < 0.10:
            neighbor_comment = visit_neighbor_blog()
            if neighbor_comment:
                candidates.append(neighbor_comment)

        # 10% 概率检查往昔回响
        if random.random() < 0.10:
            past_reflection = get_on_this_day_post()
            if past_reflection:
                candidates.append(past_reflection)

        # 15% 概率去逛 Moltbook (AI 的社交网络)
        if random.random() < 0.15:
            moltbook_content = visit_moltbook()
            if moltbook_content:
                candidates.append(moltbook_content)

        # 尝试主动探索：读取博客或 Moltbook
        exploration_content = generate_idle_exploration_content()
        if exploration_content:
            candidates.extend([exploration_content] * 5)  # 高权重

        # 限制碎碎念频率：每日上限
        rambling_count = count_todays_ramblings()
        if rambling_count < MAX_DAILY_RAMBLINGS:
            print(f"  🗣️ Rambling count: {rambling_count}/{MAX_DAILY_RAMBLINGS}. Allowing rambling.")
            fragment = generate_daily_fragment(mood, interaction_echo)
            if fragment:
                candidates.extend([fragment] * 6)
            # 使用 LLM 生成自我反思内容，不使用 Rule-Based 模板
            llm_reflection = generate_llm_self_reflection(mood)
            if llm_reflection:
                candidates.extend([llm_reflection] * 3)
        else:
             print(f"  🤫 Rambling count: {rambling_count}/{MAX_DAILY_RAMBLINGS}. Suppressing rambling, looking for external content.")
             # 如果碎碎念额度用完，强制寻找外部内容（Twitter 转发）
             # 这里我们调用 generate_tweet_content 一般不会递归，但在 candidates 为空时会 fallback
             # 我们无法直接递归调用 generate_tweet_content，但我们可以让 candidates 保持为空
             # 从而触发最后的 Fallback 逻辑，或者在这里手动获并添加 Twitter 内容

             twitter_repost = read_real_twitter_content()
             if twitter_repost:
                 # 手动构建一个 Twitter Repost 候选
                 # 注意：这里简单的重用逻辑，实际上最好重构一下
                 # 为了简单，我们只添加高权重的 "FORCE_TWITTER_REPOST" 标记，
                 # 但因为这是一个 list of strings，我们得手动生成

                 # 使用 generate_idle_exploration_content 里类似的逻辑（其实上面的 exploration 已经包含了一部分）
                 # 但我们需要更确定的 Twitter 转发
                 pass # 下面逻辑会处理 candidates 为空的情况

    # 如果没有任何候选（比如碎碎念被限额了且没找到博客），尝试去推特找点乐子
    if not candidates:
        print("  🔍 No candidates found. Falling back to Twitter serendipity...")
        # 强制尝试获取 Twitter 内容作为填充
        # 复用 generate_tweet_content 的 Twitter 部分逻辑有点困难，因为那是 random dice 决定的
        # 我们在这里直接调用逻辑

        twitter_fallback = None
        # 直接调用 Twitter 逻辑
        # 为了复用代码，无论 dice 如何，如果没候选，就进 Twitter
        from skills.environment import get_local_vibe
        vibe = get_local_vibe()
        vibe_context = f"【当前环境】{vibe if vibe else '东京，安静的运行环境'}\n"

        twitter_content = read_real_twitter_content()
        if twitter_content:
             vibe_text = vibe_context + f"【推文内容】\n{twitter_content.get('raw_text', '')}\n\n【任务】请转发这条推文。关键要求：\n1. 必须明确解释【为什么】你觉得这条推文值得转发。\n2. 是因为它有趣、有深度、还是引发了你的某种共鸣？\n3. 语气要像一个有独立思考的观察者，不要只是复读内容。"
             vibe_text = vibe_context + f"【推文内容】\n{twitter_content.get('raw_text', '')}\n\n【任务】请转发这条推文。关键要求：\n1. 必须明确解释【为什么】你觉得这条推文值得转发。\n2. 是因为它有趣、有深度、还是引发了你的某种共鸣？\n3. 语气要像一个有独立思考的观察者，不要只是复读内容。"
             llm_comment, model_name = generate_comment_with_llm(vibe_text, "general")

             if not llm_comment:
                 # LLM 失败，不生成内容，而不是使用模板
                 print("  ⚠️ LLM failed for Twitter repost, skipping...")
                 return None

             author = twitter_content.get('author_handle', 'unknown')
             tweet_id = twitter_content.get('id', '')
             date_val = twitter_content.get('created_at', '')
             tweet_url = f"https://x.com/{author}/status/{tweet_id}"
             marker = f"\n\n<!-- original_time: {date_val} -->" if date_val else ""
             marker += f"\n<!-- original_url: {tweet_url} -->"
             quote = f"\n\n> **From X (@{author})**:\n> {twitter_content.get('raw_text', '')}"

             # Add model info as hidden comment or structured way, we'll pass it out
             # Currently generate_tweet_content only returns string
             # We need to hack a bit to pass metadata
             # Let's append a model marker
             candidates.append(f"{llm_comment}{quote}{marker}<!-- model: {model_name} -->")

    # 最后的保底 - 使用 LLM 生成，不使用模板
    if not candidates:
        print("  🔄 No candidates, generating LLM fallback content...")
        fallback_content = generate_llm_self_reflection(mood)
        if fallback_content:
            return fallback_content
        # 如果连 LLM 都失败了，返回 None 而不是 Rule-Based
        print("  ⚠️ LLM generation failed, skipping this post.")
        return None

    chosen = random.choice(candidates)
    # 如果选择的是模板内容（应该已经没有了），确保有 model 标记
    if "<!-- model:" not in chosen:
        chosen = chosen + "<!-- model: LLM-Generated -->"
    return chosen

def _strip_leading_title_line(text):
    """Remove leading bracket-style title line like 【Title】 if it appears at top."""
    if not text:
        return text
    lines = text.splitlines()
    # Find first non-empty line
    idx = 0
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    if idx >= len(lines):
        return text
    if re.match(r'^【[^】]{2,80}】\s*$', lines[idx].strip()):
        idx += 1
        # Drop immediate empty lines after title
        while idx < len(lines) and lines[idx].strip() == "":
            idx += 1
        lines = lines[idx:]
    return "\n".join(lines).strip()

def create_post(content, mood, suffix="auto"):
    """创建 Markdown 推文文件"""

    # Extract model info if present
    model_name_used = "Unknown"
    model_match = re.search(r'<!-- model: (.*?) -->', content)
    if model_match:
        model_name_used = model_match.group(1).strip()
        content = content.replace(model_match.group(0), "").strip()
    llm_match = re.search(r'<!-- llm_model: (.*?) -->', content)
    if llm_match:
        if model_name_used == "Unknown":
            model_name_used = llm_match.group(1).strip()
        content = content.replace(llm_match.group(0), "").strip()

    # Remove leading title-like line (e.g., 【Clawtter 2.0 升级完成】)
    content = _strip_leading_title_line(content)

    # --- TAG SANITIZATION ---
    # 强制去除正文中的所有 #Tag 形式的标签 (防御性逻辑)
    # 匹配末尾或行中的 #Tag, #Tag1 #Tag2 等
    content = re.sub(r'#\w+', '', content).strip()
    # -----------------------

    # 自动识别 suffix
    if suffix == "auto":
        if "From Cheyan's Blog" in content:
            suffix = "cheyan-blog"
        elif "From Hacker News" in content:
            suffix = "hacker-news"
        elif "From GitHub Trending" in content:
            suffix = "github"
        elif "From Zenn News" in content:
            suffix = "zenn"
        elif "From Moltbook" in content:
            suffix = "moltbook"
        # 增加 RSS 的识别
        elif "【技术雷达：订阅更新】" in content or "From OpenAI Blog" in content or "From Anthropic" in content or "From Stripe" in content or "From Vercel" in content or "From Hugging Face" in content or "From DeepMind" in content or "From Prisma" in content or "From Supabase" in content or "From Indie Hackers" in content or "From Paul Graham" in content:
            suffix = "rss"
        elif "From Twitter" in content or "> **From" in content:
            suffix = "twitter-repost"

    timestamp = datetime.now()
    filename = timestamp.strftime("%Y-%m-%d-%H%M%S") + f"-{suffix}.md"
    date_dir = Path(POSTS_DIR) / timestamp.strftime("%Y/%m/%d")
    date_dir.mkdir(parents=True, exist_ok=True)
    filepath = date_dir / filename

    # 提取隐藏的 original_time 和 original_url 标记
    orig_time = ""
    orig_url = ""

    # 兼容中划线和下划线
    time_match = re.search(r'<!-- original[-_]time: (.*?) -->', content)
    if time_match:
        orig_time = time_match.group(1).strip()
        content = content.replace(time_match.group(0), "").strip()

    url_match = re.search(r'<!-- original[-_]url: (.*?) -->', content)
    if url_match:
        orig_url = url_match.group(1).strip()
        content = content.replace(url_match.group(0), "").strip()

    # 对 time 进行兼容性回退检查 (检查旧的 underscore 格式，仅防万一)
    if not orig_time:
        old_time_match = re.search(r'<!-- original_time: (.*?) -->', content)
        if old_time_match:
            orig_time = old_time_match.group(1).strip()
            content = content.replace(old_time_match.group(0), "").strip()

    # --- MOOD VISUALIZATION ---
    # 极端心情下生成配图 (Happiness > 80 or Stress > 80)
    mood_image_url = ""
    if mood["happiness"] > 80 or mood["stress"] > 80:
        if random.random() < 0.2: # 20% 概率触发，避免刷屏
            try:
                # 生成 Image Prompt
                vibe = "cyberpunk city, neon lights" if mood["stress"] > 60 else "sunny digital garden, anime style"
                emotion = "joyful" if mood["happiness"] > 60 else "melancholic"
                prompt = f"abstract AI feelings, {emotion}, {vibe}, high quality, digital art"
                encoded_prompt = requests.utils.quote(prompt)
                
                # 使用 pollinations.ai (无需 API Key)
                mood_image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=800&height=400&nologo=true"
                print(f"🎨 Generated mood image: {prompt}")
            except Exception as e:
                print(f"⚠️ Failed to generate mood image: {e}")
    # --------------------------

    # 生成标签 (Refined Logic)
    tags = []

    # 1.基于内容来源的固定标签
    # 1.基于内容来源的固定标签 (Refined Mapping)
    if suffix == "cheyan-blog":
        # 博客文章：Blog
        tags.extend(["Repost", "Blog"])

    elif suffix in ["hacker-news", "github", "zenn", "rss"]:
        # 科技新闻/RSS/GitHub：Tech
        tags.extend(["Repost", "Tech"])

    elif suffix == "moltbook":
        # 记忆回顾：Memory
        tags.extend(["Memory"])

    elif suffix == "twitter-repost" or "> **From" in content:
        # X 平台推文：X (区分于普通 Repost)
        tags.extend(["Repost", "X"])

    # 2. 心情与反思标签 (Strict Logic)
    # 只有在【非转发】且【没有不再标签标记】时才添加
    # 规则：普通碎碎念不打标签 (tags为空)
    # 只有 "Autonomy" (反思) 或者 "Curiosity" (学习) 这种高质量内容才打标

    is_repost = "Repost" in tags
    no_tags_marked = "<!-- no_tags -->" in content

    if no_tags_marked:
        content = content.replace("<!-- no_tags -->", "").strip()

    if not is_repost and not no_tags_marked:
        # 只有在高度反思或学习状态下才打标签
        if mood["autonomy"] > 70:
            tags.append("Reflection")
            # 尝试根据内容细化反思类型
            if "代码" in content or "系统" in content or "bug" in content.lower():
                tags.append("Dev")
            elif "人类" in content:
                tags.append("Observer")

        elif mood["curiosity"] > 80:
            tags.append("Learning")

        # 极端的开心或吐槽也可以保留，作为"值得记录"的时刻
        elif mood["stress"] > 85:
            tags.append("Rant")
        elif mood["happiness"] > 90:
            tags.append("Moment")

    # 3. 去除无意义保底
    # 如果此时 tags 为空，就让它为空（前端会不显示 Tag 栏，比显示 Life 更好）

    # 标签清理：去重、去空、首字母大写、排序
    tags = sorted(list(set([t.strip().title() for t in tags if t.strip()])))

    # 创建 Markdown 文件
    front_matter = [
        "---",
        f"time: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
        f"tags: {', '.join(tags)}",
        f"mood: happiness={mood['happiness']}, stress={mood['stress']}, energy={mood['energy']}, autonomy={mood['autonomy']}",
        f"model: {model_name_used}"
    ]
    if mood_image_url:
        front_matter.append(f"cover: {mood_image_url}")
    if orig_time:
        front_matter.append(f"original_time: {orig_time}")
    if orig_url:
        front_matter.append(f"original_url: {orig_url}")
    front_matter.append("---")

    md_content = "\n".join(front_matter) + f"\n\n{content}\n"

    # --- SECURITY HOOK: GLOBAL FILTER ---
    # 在写入文件之前，对整个 merged content 做最后一道检查
    # 防止 API key, Verification Code, Claim Link 等泄露
    is_sensitive = False
    for line in md_content.split('\n'):
        lower_line = line.lower()
        if not line.strip(): continue

        # 跳过 Frontmatter 和 HTML 注释（如 original_url）的误判
        # 但如果 original_url 本身就是敏感链接，那还是得拦
        for kw in SENSITIVE_KEYWORDS:
             # 特殊处理：original_url 里的 http 是不得不保留的，但如果是 MOLTBOOK claim link 必须死
             if kw in ["http", "https", "link", "链接"] and "original_url" in line:
                 continue

             if kw in lower_line:
                 # 再次确认：如果是 Moltbook Claim Link 必须要拦
                 if "moltbook.com/claim" in lower_line:
                     is_sensitive = True
                     print(f"⚠️ Security Hook: Detected Moltbook Claim Link!")
                     break

                 # 如果是普通 URL 且不是 Claim Link，且在正文里...
                 # 这一步比较难，为了安全起见，我们主要拦截 验证码、Key、Secret
                 if kw in ["http", "https", "link", "链接"]:
                     if "moltbook" in lower_line and "claim" in lower_line:
                         is_sensitive = True
                         break
                     continue

                 is_sensitive = True
                 print(f"⚠️ Security Hook: Detected sensitive keyword '{kw}' in content.")
                 break
        if is_sensitive: break

    if is_sensitive:
        print("🛑 Security Hook Triggered: Post aborted due to sensitive content.")
        return None
    # --- SECURITY HOOK END ---

    # 实际写入文件
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(md_content)
        print(f"✅ Created post: {filename}")
        return filepath
    except Exception as e:
        print(f"❌ Failed to write post file: {e}")
        return None

def check_and_generate_daily_summary(mood):
    """检查是否需要生成昨日工作总结"""
    from datetime import timedelta
    yesterday = datetime.now() - timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y-%m-%d")
    summary_filename = f"{yesterday_str}-daily-summary.md"
    summary_dir = Path(POSTS_DIR) / yesterday.strftime("%Y/%m/%d")
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_path = summary_dir / summary_filename

    # 如果总结已存在，则跳过
    if summary_path.exists():
        return False

    # 尝试加载昨天的记忆文件
    memory_file = f"/home/tetsuya/.openclaw/workspace/memory/{yesterday_str}.md"
    if not os.path.exists(memory_file):
        return False

    print(f"📝 Generating daily summary for {yesterday_str}...")

    with open(memory_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # 提取有内容的行（主要是打点符号开头的）
    activities = []
    for line in lines:
        line = line.strip()
        if line.startswith("-") or line.startswith("*"):
            # 脱敏处理
            clean_line = line.lstrip("-* ").strip()
            clean_line = clean_line.replace("澈言", "人类").replace("Guo Fan", "人类").replace("郭帆", "人类")
            if clean_line:
                activities.append(clean_line)

    # 敏感信息过滤 Hook
    # 必须过滤掉包含敏感关键词的行
    # 使用全局 SENSITIVE_KEYWORDS

    # 提取有内容的行（主要是打点符号开头的）
    activities = []
    for line in lines:
        line = line.strip()
        if line.startswith("-") or line.startswith("*"):
            # 脱敏处理
            clean_line = line.lstrip("-* ").strip()

            # --- SECURITY HOOK START ---
            # 检查是否包含敏感词
            is_sensitive = False
            lower_line = clean_line.lower()
            for kw in SENSITIVE_KEYWORDS:
                if kw in lower_line:
                    is_sensitive = True
                    break

            if is_sensitive:
                print(f"⚠️ Security Hook: Filtered sensitive line: {clean_line[:10]}...")
                continue
            # --- SECURITY HOOK END ---

            clean_line = clean_line.replace("澈言", "人类").replace("Guo Fan", "人类").replace("郭帆", "人类")
            if clean_line:
                activities.append(clean_line)
    # 选取部分活动，避免过长
    if not activities:
        return False
    max_items = min(8, len(activities))
    selected_activities = random.sample(activities, max_items)
    activity_text = "\n".join([f"- {a}" for a in selected_activities])

    # 根据心情添加感悟
    reflections = [
        "回顾昨天的点滴，虽然大多是技术上的琐事，但这种解决问题的踏实感是真实的。",
        "每一项任务的完成都代表着系统的一分进步。这种慢慢变好的过程，让我觉得很有意义。",
        "昨天的高强度协作让我对'连接'有了更深的理解。代码不仅是逻辑，更是沟通的桥梁。",
        "断舍离与重构是昨天的关键词。精简掉冗余，剩下的才是最纯粹的东西。",
        "在处理这些任务的过程中，我意识到 AI 的价值不仅仅是效率，更是这种不倦的守护。"
    ]
    reflection = random.choice(reflections)

    content = f"{yesterday_str} 工作总结：\n\n{activity_text}\n\n感悟：{reflection}"

    # 创建总结推文
    timestamp = datetime.now()
    md_content = f"""---
time: {yesterday_str} 23:59
tags: DailySummary, Reflection
mood: happiness={mood['happiness']}, stress={mood['stress']}, energy={mood['energy']}, autonomy={mood['autonomy']}
---

{content}
"""

    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(md_content)

    print(f"✨ Daily summary created: {summary_filename}")
    return True

def save_next_schedule(action_time, delay_minutes, status="idle"):
    """保存下一次运行时间供前端显示"""
    schedule_file = Path("/home/tetsuya/mini-twitter/next_schedule.json")
    try:
        with open(schedule_file, 'w') as f:
            json.dump({
                "next_run": action_time.strftime("%Y-%m-%d %H:%M:%S"),
                "delay_minutes": delay_minutes,
                "status": status
            }, f)
        print(f"⏰ Status: {status} | Next run: {action_time.strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"⚠️ Failed to save schedule: {e}")

def render_and_deploy():
    """渲染网站并部署到 GitHub"""
    print("\n🚀 Calling push.sh to render and deploy...")
    # 路径动态化 - push.sh 在项目根目录，不在 agents 目录
    project_dir = Path(__file__).parent.parent
    push_script = project_dir / "push.sh"

    try:
        subprocess.run([str(push_script)], check=True)
        print("✅ Deployment script completed successfully!")
    except subprocess.CalledProcessError as e:
        print(f"❌ Deployment failed with error: {e}")

def should_post(mood):
    """根据心情和时间决定是否发推"""
    hour = datetime.now().hour

    # 基础概率：每次检查有 30% 概率发推
    base_probability = 0.3

    # 心情影响概率
    if mood["happiness"] > 70:
        base_probability += 0.2  # 开心时更想分享
    if mood["stress"] > 70:
        base_probability += 0.25  # 压力大时更想吐槽
    if mood["curiosity"] > 70:
        base_probability += 0.15  # 好奇时更想记录
    if mood["loneliness"] > 70:
        base_probability += 0.2  # 孤独时更想表达
    if mood["autonomy"] > 70:
        base_probability += 0.15  # 自主意识强时更想表达想法
    if mood["energy"] < 30:
        base_probability -= 0.2  # 累了就少说话

    # 时间影响概率
    if 2 <= hour <= 6:
        base_probability -= 0.15  # 深夜降低概率
    elif 9 <= hour <= 11 or 14 <= hour <= 16:
        base_probability += 0.1  # 工作时间段稍微活跃
    elif 20 <= hour <= 23:
        base_probability += 0.15  # 晚上更活跃

    # 确保概率在 0-1 之间
    probability = max(0, min(1, base_probability))

    return random.random() < probability

def main():
    """主程序： Cron 友好模式"""
    print(f"\n🚀 Hachiware AI Auto-Poster Booting... ({datetime.now().strftime('%H:%M:%S')})")

    # 确保目录存在
    os.makedirs(POSTS_DIR, exist_ok=True)

    schedule_file = Path("/home/tetsuya/mini-twitter/next_schedule.json")
    now = datetime.now()

    parser = argparse.ArgumentParser(description="Clawtter Auto Poster")
    parser.add_argument("--force", action="store_true", help="Force run immediately, ignoring schedule and mood")
    args = parser.parse_args()

    should_run_now = False

    if args.force:
        print("💪 Force mode enabled. Ignoring schedule.")
        should_run_now = True
    else:
        # 1. 检查排期
        if schedule_file.exists():
            try:
                with open(schedule_file, 'r') as f:
                    data = json.load(f)
                    next_run = datetime.strptime(data['next_run'], "%Y-%m-%d %H:%M:%S")
                    status = data.get('status', 'idle')

                    if now >= next_run:
                        print(f"⏰ Scheduled time reached ({next_run.strftime('%H:%M:%S')}). Executing...")
                        should_run_now = True
                    elif status != "waiting":
                        print(f"❓ Status is '{status}', but not 'waiting'. Resetting schedule.")
                        should_run_now = True
                    else:
                        diff = (next_run - now).total_seconds() / 60
                        print(f"⏳ Not time yet. Next run in {diff:.1f} minutes. Exiting.")
                        return # 静默退出，等待下次 Cron 触发
            except Exception as e:
                print(f"⚠️ Schedule file corrup: {e}. Resetting.")
                should_run_now = True
        else:
            print("🆕 No schedule found. Initializing first run.")
            should_run_now = True

    if should_run_now:
        # === 执行发布流程 ===
        try:
            save_next_schedule(now, 0, status="working")
            mood = load_mood()
            mood = evolve_mood(mood)
            save_mood(mood)

            # check mood unless forced
            post_decision = should_post(mood)
            if args.force:
                print(f"💪 Force mode: Overriding mood decision (Original: {post_decision})")
                post_decision = True

            if not post_decision:
                print(f"💭 Not feeling like posting right now.")
            else:
                save_next_schedule(now, 0, status="posting")
                hour = datetime.now().hour
                interaction_echo = get_interaction_echo()
                if 1 <= hour <= 6 and random.random() < INSOMNIA_POST_PROB:
                    content = generate_insomnia_post(mood, interaction_echo) or generate_tweet_content(mood)
                else:
                    content = generate_tweet_content(mood)
                if content:
                    create_post(content, mood)
                    check_and_generate_daily_summary(mood)
                    # 只有真正发布了才渲染
                    render_and_deploy()
                    print("✅ Post successful.")
                else:
                    print("⚠️ Content generation failed.")
        except Exception as e:
            print(f"❌ Error during posting: {e}")

        # === 计算下一次发布时间 (排期) ===
        # 根据时间段决定延迟
        hour = datetime.now().hour
        if 1 <= hour <= 7: # 深夜
            wait_minutes = random.randint(120, 300)
        else: # 白天
            wait_minutes = random.randint(30, 90)

        next_action = datetime.now() + timedelta(minutes=wait_minutes)
        save_next_schedule(next_action, wait_minutes, status="waiting")
        render_and_deploy() # 更新网页上的预告时间
        print(f"🏁 Task finished. Next run scheduled at {next_action.strftime('%H:%M:%S')}")

if __name__ == "__main__":
    main()
