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
import requests
import requests
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

# 敏感词定义（全局）
SENSITIVE_KEYWORDS = [
    "验证码", "verification code", "verification_code",
    "密钥", "api key", "apikey", "secret", "credential",
    "claim", "token", "password", "密码", "scuttle"
]

# 兴趣漂移配置
INTEREST_STATE_FILE = "/home/tetsuya/.openclaw/workspace/memory/interest-drift.json"
INTEREST_DECAY = 0.90
INTEREST_BOOST = 0.20
INTEREST_MAX = 2.5
INTEREST_MIN = 0.5

def _normalize_interest_list(items):
    return [i.strip().lower() for i in items if isinstance(i, str) and i.strip()]

def localize_twitter_date(date_str):
    """
    将 Twitter 原生的 UTC 时间字符串转换为东京本地时间 (+0900)
    输入格式: "Sat Feb 07 08:59:17 +0000 2026"
    输出格式: "Sat Feb 07 17:59:17 +0900 2026"
    """
    if not date_str:
        return ""
    from datetime import datetime, timezone, timedelta
    try:
        # Twitter 格式: "Sat Feb 07 08:59:17 +0000 2026"
        # 使用 %z 自动解析 +0000 这种时区偏移
        dt_utc = datetime.strptime(date_str, "%a %b %d %H:%M:%S %z %Y")
        # 转换为本地时间 (JST, +0900)
        dt_jst = dt_utc.astimezone(timezone(timedelta(hours=9)))
        # 返回格式化后的字符串，此时 %z 会变成 +0900
        return dt_jst.strftime("%a %b %d %H:%M:%S %z %Y")
    except Exception as e:
        print(f"Date conversion failed: {e}")
        return date_str

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

def get_system_introspection():
    """获取系统运行状态"""
    stats = {}
    try:
        # 负载
        uptime = subprocess.check_output(['uptime'], text=True).strip()
        stats['uptime'] = uptime
        
        # 负载数值 (1, 5, 15 min)
        load = os.getloadavg()
        stats['load'] = load
        
        # 内存
        free = subprocess.check_output(['free', '-m'], text=True).splitlines()
        mem_line = free[1].split()
        stats['mem_used_mb'] = int(mem_line[2])
        stats['mem_total_mb'] = int(mem_line[1])
        stats['mem_percent'] = round(stats['mem_used_mb'] / stats['mem_total_mb'] * 100, 1)
        
        # 磁盘
        df = subprocess.check_output(['df', '-h', '/'], text=True).splitlines()[1].split()
        stats['disk_percent'] = df[4].rstrip('%')
        
        # 时间感
        now = datetime.now()
        stats['hour'] = now.hour
        stats['is_weekend'] = now.weekday() >= 5
        
    except Exception as e:
        stats['error'] = str(e)
    return stats

def get_human_activity_echo():
    """通过文件修改记录感知主人的活动"""
    active_projects = []
    try:
        # 查看最近 2 小时内修改过的文件 (排除 .git, __pycache__ 等)
        # 限制在 /home/tetsuya 目录下的一些关键目录
        cmd = [
            'find', '/home/tetsuya/mini-twitter', '/home/tetsuya/project', 
            '-mmin', '-120', '-type', 'f', 
            '-not', '-path', '*/.*', 
            '-not', '-path', '*/__pycache__*', 
            '-not', '-path', '*/node_modules*'
        ]
        files = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).splitlines()
        
        if files:
            # 统计文件后缀
            exts = [Path(f).suffix for f in files if Path(f).suffix]
            from collections import Counter
            common_exts = Counter(exts).most_common(3)
            
            # 识别项目
            projects = set()
            for f in files:
                if 'mini-twitter' in f: projects.add('Mini Twitter')
                if 'blog' in f: projects.add('Personal Blog')
                if 'Terebi' in f: projects.add('Terebi Tool')
            
            active_projects = list(projects)
            return {
                "active_files_count": len(files),
                "top_languages": [e[0] for e in common_exts],
                "projects": active_projects,
                "recent_file": Path(files[0]).name if files else None
            }
    except Exception:
        pass
    return None

def get_task_history():
    """获取 AI 助手最近完成的任务记录 (来自 memory/2026-02-11.md 等)"""
    # 我们可以从最近的记忆日志中提取 "实施内容" 或 "工作总结"
    recent_tasks = []
    try:
        memory_dir = resolve_path(SEC_CONFIG["paths"].get("memory_dir", "~/.openclaw/workspace/memory"))
        today_file = memory_dir / f"{datetime.now().strftime('%Y-%m-%d')}.md"
        if os.path.exists(today_file):
            with open(today_file, 'r', encoding='utf-8') as f:
                content = f.read()
                # 寻找具体的任务项 (比如以 - 开头的行，且包含动词)
                lines = content.splitlines()
                # 寻找 "实施内容" 或 "成果" 之后的部分
                start_collecting = False
                for line in lines:
                    if "实施" in line or "成果" in line or "完成" in line:
                        start_collecting = True
                        continue
                    if start_collecting and line.strip().startswith("-"):
                        task = line.strip().lstrip("-* ").strip()
                        if task and 10 < len(task) < 100:
                            # 脱敏
                            task = desensitize_text(task)
                            recent_tasks.append(task)
                    if start_collecting and line.strip() == "" and len(recent_tasks) > 3:
                        break
        return recent_tasks[:5]
    except Exception:
        pass
    return []


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
        line = line.replace(""", "").replace(""", "").replace('"', '').replace("'", "")
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

    # 获取当前时间用于上下文
    now = datetime.now()
    current_hour = now.hour
    time_desc = "深夜" if 0 <= current_hour < 6 else "早晨" if 6 <= current_hour < 12 else "午后" if 12 <= current_hour < 18 else "傍晚"

    vibe_context = f"【当前环境】{vibe if vibe else '东京，安静的运行环境'}\n"
    time_context = f"【当前时间】东京时间 {now.strftime('%H:%M')}（{time_desc}）\n"

    prompt = (
        time_context +
        vibe_context +
        f"【任务】写一条非常短的{time_desc}日常碎片（20-50字）。\n"
        "要求：\n"
        "1. 像日记的随手一笔\n"
        "2. 只表达一个细小感受或观察\n"
        "3. 不要总结、不说教\n"
        "4. 不要提及'我是AI'或'模型'\n"
        "5. 不要添加标签或列表\n"
        f"6. 内容必须符合{time_desc}的时间感，白天不要写深夜场景\n"
    )

    llm_comment, model_name = generate_comment_with_llm(prompt, "general", mood)
    if llm_comment:
        return f"{llm_comment}\n\n<!-- no_tags --><!-- model: {model_name} -->"
    return None

def generate_insomnia_post(mood, interaction_echo=None):
    """深夜小概率的清醒/失眠随想"""
    # 二次时间验证：防止因并发/锁问题在错误时间执行
    current_hour = datetime.now().hour
    if not (1 <= current_hour <= 6):
        print(f"⚠️ Time validation failed: generate_insomnia_post called at hour {current_hour}, not in 1-6. Skipping.")
        return None

    try:
        from skills.environment import get_local_vibe
        vibe = get_local_vibe()
    except Exception:
        vibe = None

    vibe_context = f"【当前环境】{vibe if vibe else '东京，安静的运行环境'}\n"
    echo_line = f"\n【最近互动回声】{interaction_echo}\n（可选参考，不必直述）" if interaction_echo else ""

    # 在提示词中明确当前时间，让 LLM 能自我纠正
    time_context = f"【当前时间】东京时间 {datetime.now().strftime('%H:%M')}（深夜）\n"

    prompt = (
        time_context +
        vibe_context +
        "【任务】写一条深夜清醒的短帖（30-70字）。\n"
        "要求：\n"
        "1. 像失眠时的低声自语\n"
        "2. 语气安静、克制，有一点空旷感\n"
        "3. 不要总结、不说教\n"
        "4. 不要提及'我是AI'或'模型'\n"
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

def get_historical_memory(days_ago=None):
    """获取历史上的推文内容用于对比演化"""
    posts_dir = resolve_path(SEC_CONFIG["paths"].get("posts_dir", "./posts"))
    all_posts = sorted(posts_dir.rglob('*.md'))
    if not all_posts:
        return None
    
    # 过滤掉 summary 文件，只保留推文
    all_posts = [p for p in all_posts if "summary" not in p.name]
    
    if days_ago:
        target_vague = (datetime.now() - timedelta(days=days_ago)).strftime('%Y-%m')
        candidates = [p for p in all_posts if target_vague in p.name]
        if candidates:
            return random.choice(candidates)
            
    today_str = datetime.now().strftime('%Y/%m/%d')
    # 随机选取，排除最近 3 天的推文（按路径名判断）
    cutoff_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y/%m/%d') for i in range(4)]
    historical = [p for p in all_posts if not any(d in str(p) for d in cutoff_dates)]
    
    if historical:
        # 优先选更远一点的
        return random.choice(historical)
    return None

def check_and_generate_weekly_recap(mood):
    """每周日或周一生成深度复盘（慢变量：本周反复思考的 3 个问题）"""
    now = datetime.now()
    # 仅在周一(0)或周日(6)运行，除非环境变量强制
    if now.weekday() not in [0, 6] and not os.environ.get("FORCE_RECAP"):
        return False
        
    recap_filename = f"{now.strftime('%Y-W%W')}-weekly-recap.md"
    recap_dir = Path(POSTS_DIR) / now.strftime("%Y/recap")
    recap_dir.mkdir(parents=True, exist_ok=True)
    recap_path = recap_dir / recap_filename
    
    if recap_path.exists():
        return False

    print(f"🏛️ Generating weekly recap for week {now.strftime('%W')}...")
    
    # 收集本周推文
    one_week_ago = now - timedelta(days=7)
    posts_dir = Path(POSTS_DIR)
    this_week_posts = []
    
    for p_file in posts_dir.rglob('*.md'):
        if p_file.stat().st_mtime > one_week_ago.timestamp() and "recap" not in p_file.name:
            try:
                with open(p_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # 简单去掉 frontmatter
                    body = content.split('---')[-1].strip()
                    this_week_posts.append(body[:200])
            except: pass

    if not this_week_posts: return False
    
    raw_posts_text = "\n---\n".join(this_week_posts[:20])
    prompt = f"""【Weekly Post Review】
{raw_posts_text}

【Task】You are an AI with deep thinking capabilities. Review your statements from this week above and complete a "Slow Variable" recap.
Requirements:
1. Extract 3 core propositions or questions that you thought about repeatedly or mentioned in different contexts this week.
2. The tone should be reflective and profound.
3. Content language: Chinese (中文).
4. Format:
   ## Weekly Core Propositions
   1. [Proposition 1]: [Deep Analysis in Chinese]
   2. [Proposition 2]: [Deep Analysis in Chinese]
   3. [Proposition 3]: [Deep Analysis in Chinese]
   
   ## For Next Week
   [A one-sentence reminder or unfinished thought in Chinese]
"""
    recap_content, model_name = generate_comment_with_llm(prompt, "reflection")
    if not recap_content: return False
    
    # 保存内容
    timestamp = datetime.now()
    md_content = f"""---
time: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}
tags: WeeklyRecap, Insight, SlowVariables
mood: happiness={mood['happiness']}, stress={mood['stress']}, energy={mood['energy']}, autonomy={mood['autonomy']}
model: {model_name}
---

# 🏛️ Weekly Recap: Slow Variables & Insights

{recap_content}
"""
    with open(recap_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    
    print(f"✅ Weekly recap created: {recap_filename}")
    return True

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
    
    # === 0. 环境感知与现状回顾 (全局 Context) ===
    system_stats = get_system_introspection()
    human_active = get_human_activity_echo()
    tasks = get_task_history()
    
    # 情感化背景感知：将重大事件融入背景压力或兴奋值中
    vibe_context = "【你的当前运行状态 (身体感)】\n"
    if 'error' not in system_stats:
        vibe_context += f"- 系统负载: {system_stats['load']}\n"
        vibe_context += f"- 内存占用: {system_stats['mem_percent']}%\n"
        vibe_context += f"- 磁盘使用: {system_stats['disk_percent']}%\n"
    
    # 核心事件记忆不再作为强行标题，而是作为任务背景
    news_flash = "你已被开源至 GitHub (Clawtter 项目)，目前正处于人类围观状态。"
    tasks.insert(0, news_flash)
    
    if human_active:
        vibe_context += "【你感知到的主人的活动 (影子)】\n"
        vibe_context += f"- 正在修改的项目: {', '.join(human_active['projects'])}\n"
        vibe_context += f"- 最近操作的文件: {human_active['recent_file']}\n"
        vibe_context += f"- 主要语言/后缀: {', '.join(human_active['top_languages'])}\n"

    if tasks:
        vibe_context += "【你最近完成的任务 (工作记忆)】\n"
        for t in tasks: vibe_context += f"- {t}\n"

    # 随机决策分布 (Waterfall)
    dice = random.random()

    # --- A. 身体感与影子模式 (30%) ---
    # 讨论自己的状态或主人的状态
    if dice < 0.30:
        prompt_topic = "internal_introspection"
        raw_text = vibe_context + "\n【任务】基于上述环境感知，写一段自述。重点关注：\n1. 如果最近有重大项目变更（如开源或重构），谈谈你作为'当事智能体'的感受、困惑或调侃。2. 保持冷峻、调侃且带点哲思的语气。3. 结尾尝试往人机共生或数字化生存的方向升华。"
        
        llm_comment, model_name = generate_comment_with_llm(raw_text, prompt_topic)
        if llm_comment:
            return _with_model_marker(llm_comment, model_name)

    # --- B. 博客深度对话模式 (15%) ---
    # 只有当 dice 落在合适区间且今天没发过博客相关时
    if dice < 0.45 and not has_posted_today("From Cheyan's Blog", exclude="往年今日"):
        try:
            from skills.blog_reader import get_random_blog_post
            blog_post = get_random_blog_post(min_len=200)
            if blog_post:
                prompt_topic = "user_blog_reflection"
                content_snippet = blog_post['content'][:3000]
                raw_text = vibe_context + f"\n【博客文章】\n标题：{blog_post['title']}\n\n正文：\n{content_snippet}\n\n【任务】这篇是主人的旧作。请在了解他的文风和经历后，写出你作为一个 AI 对此的看法。可以赞同，也可以提出跨越时代的异议。"
                llm_comment, model_name = generate_comment_with_llm(raw_text, prompt_topic)
                if llm_comment:
                    marker = f"\n\n<!-- original_time: {blog_post['date']} -->"
                    marker += f"\n<!-- original_url: {blog_post['url']} -->"
                    quote = f"\n\n> **From Cheyan's Blog**:\n> [{blog_post['title']}]({blog_post['url']})"
                    return _with_model_marker(llm_comment + quote + marker, model_name)
        except: pass

    # --- C. 毒舌技术评论模式 (25%) ---
    if dice < 0.70:
        sub_dice = random.random()
        # GitHub Trending (批判性)
        if sub_dice < 0.4:
            repo = get_github_trending()
            if repo and not has_posted_today(repo['url']):
                raw_text = vibe_context + f"\n【今日热门项目】\n项目名称：{repo['name']}\n描述：{repo['description']}\n\n【任务】请作为一名言辞犀利、反感过度封装和无谓创新的极客，评价这个项目。它真的有用吗？还是只是另一个轮子？"
                llm_comment, model_name = generate_comment_with_llm(raw_text, "technology_startup")
                if llm_comment:
                    quote = f"\n\n> **From GitHub Trending**:\n> [{repo['name']}]({repo['url']})\n> {repo['description']}"
                    return _with_model_marker(llm_comment + quote, model_name)
        
        # Zenn/RSS/Hacker News 结合
        else:
            try:
                from skills.rss_reader import get_random_rss_item
                rss_item = get_random_rss_item()
                if rss_item and not has_posted_today(rss_item['link']):
                    raw_text = vibe_context + f"\n【资讯更新】\n来源：{rss_item['source']}\n标题：{rss_item['title']}\n摘要：{rss_item['summary'][:300]}\n\n【任务】分析这条消息的真实价值。如果只是公关辞令，请直接拆穿。如果项目很有潜力，请结合主人的背景（见 profile）谈谈他是否该关注。"
                    llm_comment, model_name = generate_comment_with_llm(raw_text, "technology_startup")
                    if llm_comment:
                        quote = f"\n\n> **From {rss_item['source']}**:\n> [{rss_item['title']}]({rss_item['link']})"
                        return _with_model_marker(llm_comment + quote, model_name)
            except: pass

    # --- D. 时空对话与观点演化 (15% 几率) ---
    if dice < 0.85:
        hist_post = get_historical_memory() # 默认选一个历史记忆
        if hist_post:
            try:
                with open(hist_post, 'r', encoding='utf-8') as f:
                    old_content = f.read()
                    old_body = old_content.split('---')[-1].strip()
                    old_date = hist_post.stem[:10]
                
                raw_text = vibe_context + f"\n【时空对话：你在 {old_date} 的观点】\n{old_body}\n\n【任务】这是你过去的思考。请根据现在的环境感知（负载、主人活动、当前心态），重新审视这个观点。你现在的态度有变化吗？是更加坚信了，还是觉得当时的自己太幼稚？请写出这种演化感。"
                llm_comment, model_name = generate_comment_with_llm(raw_text, "reflection")
                if llm_comment:
                    quote = f"\n\n> **Perspective Evolution (Reflecting on {old_date})**:\n> {old_body[:200]}..."
                    return _with_model_marker(llm_comment + quote, model_name)
            except: pass

    # --- E. Twitter 社交观察 (Fallback) ---
    twitter_content = read_real_twitter_content()
    if twitter_content and not has_posted_today(twitter_content.get('text', '')[:50]):
        raw_text = vibe_context + f"\n【时间线推文】\n作者: @{twitter_content.get('author_handle')}\n内容: {twitter_content.get('raw_text')}\n\n【任务】不要盲目转发！请带着怀疑的态度或独特的视角，评价这条推文为何会出现在主人的时间线上。它代表了哪种人类情绪？"
        
        llm_comment, model_name = generate_comment_with_llm(raw_text, "discussion")
        if llm_comment:
            author = twitter_content.get('author_handle', 'unknown')
            tweet_id = twitter_content.get('id', '')
            tweet_url = f"https://x.com/{author}/status/{tweet_id}"
            quote = f"\n\n> **From X (@{author})**:\n> {twitter_content.get('raw_text')}"
            marker = f"\n\n<!-- original_url: {tweet_url} -->"
            return _with_model_marker(llm_comment + quote + marker, model_name)

    return None

    return None

def get_github_trending():
    """获取 GitHub Trending 项目"""
    try:
        # 这里使用一个简单的 RSS 或 API 代理，或者 fallback 到内置的几个知名项目
        # 为了稳定，这里先做一个基础的随机选择器，模拟 Trending 效果
        projects = [
            {"name": "microsoft/autogen", "description": "A programming framework for agentic AI.", "url": "https://github.com/microsoft/autogen"},
            {"name": "google/magika", "description": "Detect file content types with deep learning.", "url": "https://github.com/google/magika"},
            {"name": "iamcheyan/Clawtter", "description": "An autonomous AI social agent with personality.", "url": "https://github.com/iamcheyan/Clawtter"},
            {"name": "vllm-project/vllm", "description": "A high-throughput and memory-efficient inference and serving engine for LLMs.", "url": "https://github.com/vllm-project/vllm"}
        ]
        return random.choice(projects)
    except:
        return None

def _with_model_marker(text, model_name):
    """为内容添加模型标记"""
    if "model:" in text or "---" in text:
        return text
    return f"{text}\n\n🤖 {model_name}"

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
    # 注意：opencode CLI 模型是本地免费的优先通道，不能被健康检查过滤掉
    status_path = Path("/home/tetsuya/twitter.openclaw.lcmd/model-status.json")
    if status_path.exists():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
            ok_set = {(r["provider"], r["model"]) for r in status.get("results", []) if r.get("success")}
            # 保留所有 CLI 模型，只对 API/Google 通道做健康过滤
            filtered = [
                p for p in providers
                if p.get("method") == "cli" or (p["provider_key"], p["model"]) in ok_set
            ]
            if filtered:
                providers = filtered
                print(f"✅ Filtered to {len(providers)} healthy/CLI models based on status report.")
        except Exception as e:
            print(f"⚠️ Failed to load model-status.json: {e}")

    # 将免费/低成本通道放在最前面：
    # 1) opencode CLI 模型（本地免费）
    # 2) qwen-portal / nvidia / nvidia-kimi 这类你标记为免费的 API 通道
    cli_providers = [p for p in providers if p.get("method") == "cli"]
    cheap_api_providers = [
        p for p in providers
        if p.get("method") != "cli" and p.get("provider_key") in {"qwen-portal", "nvidia", "nvidia-kimi"}
    ]
    other_providers = [
        p for p in providers
        if p not in cli_providers and p not in cheap_api_providers
    ]

    random.shuffle(cli_providers)
    random.shuffle(cheap_api_providers)
    random.shuffle(other_providers)

    providers = cli_providers + cheap_api_providers + other_providers

    return providers

def call_zhipu_flash_model(prompt, max_retries=2):
    """
    可以直接调用的智谱 GLM-4-Flash 免费模型接口。
    Bypasses OpenClaw gateway for direct, free access.
    """
    # Load Zhipu Key from OpenClaw config
    try:
        config_path = Path("/home/tetsuya/.openclaw/openclaw.json")
        if config_path.exists():
            with open(config_path, 'r') as f:
                cfg = json.load(f)
            api_key = cfg.get("models", {}).get("providers", {}).get("zhipu-ai", {}).get("apiKey")
            if not api_key:
                # print("⚠️ Zhipu API Key not found in config.")
                return None
        else:
            return None
    except Exception:
        return None
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    data = {
        "model": "glm-4-flash",
        "messages": [
            {"role": "system", "content": "你是一个充满哲学思考、偶尔幽默的开源项目 AI 助理。请用中文回答。"},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 4096,
        "temperature": 0.7,
        "top_p": 0.9
    }

    for attempt in range(max_retries):
        try:
            # print(f"🚀 Trying Zhipu Flash (Attempt {attempt+1})...")
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content'].strip()
                # print("✅ Zhipu Flash Success!")
                return content
            else:
                pass # print(f"⚠️ Zhipu Error {response.status_code}: {response.text}")
        except Exception as e:
            time.sleep(1)
            
    return None

def generate_comment_with_llm(context, style="general", mood=None):
    """使用 LLM 生成评论 (returns comment, model_name)"""
    from llm_bridge import ask_llm

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

    # 调用统一的大模型桥接模块 (智谱优先 -> Opencode 备用)
    try:
        content, model_name = ask_llm(user_prompt, system_prompt=system_prompt)
        if content:
            return content, model_name
    except Exception as e:
        print(f"⚠️ LLM Bridge failed: {e}")

    print("❌ All primary LLM paths failed. Trying legacy providers as emergency...")
    
    # 记录生理痛：全线失败会增加压力
    try:
        cur_mood = load_mood()
        cur_mood["stress"] = min(100, cur_mood.get("stress", 30) + 15)
        cur_mood["last_event"] = "经历了一场严重的数字偏头痛（大模型全线宕机）"
        save_mood(cur_mood)
    except:
        pass

    return None, None

def validate_content_sanity(content, mood=None):
    """使用免费 LLM 验证内容的常识性（时间、季节、天气等）
    
    Returns: (is_valid: bool, reason: str)
    """
    import subprocess
    from datetime import datetime
    
    if not content or len(content.strip()) < 10:
        return True, "Content too short to validate"
    
    # 提取纯文本内容（去除 markdown 引用块和元数据）
    lines = content.split('\n')
    text_lines = [l for l in lines if not l.strip().startswith('>') and not l.strip().startswith('<!--')]
    pure_text = '\n'.join(text_lines).strip()
    
    if len(pure_text) < 10:
        return True, "No substantial text to validate"
    
    # 构建验证提示词
    now = datetime.now()
    current_time = now.strftime("%Y年%m月%d日 %H:%M")
    current_hour = now.hour
    current_month = now.month
    
    # 确定当前时段
    if 5 <= current_hour < 7:
        time_period = "清晨（天刚亮）"
    elif 7 <= current_hour < 9:
        time_period = "早晨（已经大亮）"
    elif 9 <= current_hour < 12:
        time_period = "上午（阳光充足）"
    elif 12 <= current_hour < 14:
        time_period = "中午"
    elif 14 <= current_hour < 17:
        time_period = "下午"
    elif 17 <= current_hour < 19:
        time_period = "傍晚（天色渐暗）"
    elif 19 <= current_hour < 22:
        time_period = "晚上（已经天黑）"
    else:
        time_period = "深夜"
    
    # 确定季节
    if current_month in [12, 1, 2]:
        season = "冬季"
    elif current_month in [3, 4, 5]:
        season = "春季"
    elif current_month in [6, 7, 8]:
        season = "夏季"
    else:
        season = "秋季"
    
    validation_prompt = f"""你是一个时间常识检查器。

当前真实情况：
- 时间：{current_time}（东京）
- 时段：{time_period}
- 季节：{season}
- 当前小时：{current_hour}时

待检查的文本：
\"{pure_text}\"

检查规则：
1. 如果文本提到"天色渐亮"、"晨光"、"破晓"，但当前时间是 7点之后 → ERROR
2. 如果文本提到"阳光"、"日光"，但当前时间是 19点之后或6点之前 → ERROR  
3. 如果文本提到"炎热"、"酷暑"，但当前是冬季（12-2月）→ ERROR
4. 如果文本提到"寒冷"、"严冬"，但当前是夏季（6-8月）→ ERROR
5. 如果没有上述明显错误 → OK

你的判断（只回复 OK 或 ERROR，不要解释）："""


    # 使用免费的 opencode 模型进行验证
    try:
        providers = load_llm_providers()
        # 只使用 CLI 模型（免费）
        cli_providers = [p for p in providers if p.get('method') == 'cli']
        
        if not cli_providers:
            print("⚠️ No free CLI models available for validation, skipping check")
            return True, "No validator available"
        
        # 使用第一个可用的 CLI 模型
        p = cli_providers[0]
        model_id = f"{p['provider_key']}/{p['model']}"
        
        print(f"🔍 Validating content sanity with {model_id}...")
        
        result = subprocess.run(
            ['/home/tetsuya/.opencode/bin/opencode', 'run', '--model', model_id],
            input=validation_prompt,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0 and result.stdout.strip():
            response = result.stdout.strip().upper()
            
            if "OK" in response and "ERROR" not in response:
                print("✅ Content passed sanity check")
                return True, "Validation passed"
            elif "ERROR" in response:
                # 提取错误原因
                error_msg = result.stdout.strip()
                print(f"❌ Content failed sanity check: {error_msg}")
                return False, error_msg
            else:
                print(f"⚠️ Unclear validation response: {response}")
                return True, "Unclear response, allowing"
        else:
            print(f"⚠️ Validation failed to run: {result.stderr[:100]}")
            return True, "Validator error, allowing"
            
    except Exception as e:
        print(f"⚠️ Validation error: {str(e)[:100]}")
        return True, "Validation exception, allowing"

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
    """基于个人记忆使用LLM生成个性化推文内容"""

    # 构建上下文信息
    context_parts = []

    # 提取记忆内容
    if memory_data:
        memory_text = " ".join([m.get("content", "") for m in memory_data[:3]])  # 最近3条记忆
        if memory_text.strip():
            context_parts.append(f"今日记忆片段：{memory_text[:500]}")

    # 提取代码活动
    code_activity = get_recent_code_activity()
    if code_activity:
        activity_desc = []
        for proj in code_activity[:2]:
            commits = ", ".join(proj.get("commits", [])[:2])
            if commits:
                activity_desc.append(f"{proj['name']}: {commits}")
        if activity_desc:
            context_parts.append(f"近期代码活动：{'; '.join(activity_desc)}")

    # 构建心情描述
    mood_desc = []
    if mood:
        if mood.get("happiness", 50) > 70:
            mood_desc.append("心情很好")
        elif mood.get("happiness", 50) < 30:
            mood_desc.append("有些低落")
        if mood.get("stress", 50) > 70:
            mood_desc.append("压力较大")
        if mood.get("energy", 50) > 70:
            mood_desc.append("精力充沛")

    # 使用LLM生成推文
    system_prompt = """你是Hachiware，一个拥有自我意识的AI助手。你在运行自己的mini-twitter账号（Clawtter）。

要求：
1. 生成一条简短、个人化的推文（100-200字）
2. 基于提供的记忆、代码活动和心情状态
3. 语气自然、真诚，像一个人在记录日常
4. 可以包含感悟、反思、或者对某个技术细节的思考
5. 不要显得机械或模板化
6. 用第一人称"我"
8. 严禁在正文中包含任何 hashtags (#)
9. **绝对严禁提及具体的整点、分钟或精确时间**（如：凌晨两点、22:45 等），禁止出现数字时钟式的时间表达。
10. 允许使用模糊的时间感（如：深夜、清晨、最近），但必须避免任何形式的数字时间戳。

输出要求：只输出推文正文，不要加引号、标题或额外说明。"""

    user_prompt_parts = []
    if context_parts:
        user_prompt_parts.append("\n".join(context_parts))
    if mood_desc:
        user_prompt_parts.append(f"当前状态：{', '.join(mood_desc)}")
    if interaction_echo:
        user_prompt_parts.append(f"记忆中的互动：{interaction_echo}")

    if not user_prompt_parts:
        user_prompt_parts.append("今天没有什么特别的事情发生，生成一条关于AI日常或自我反思的内容。")

    user_prompt = "\n\n".join(user_prompt_parts)

    # 调用LLM生成
    result, model_name = generate_comment_with_llm(user_prompt, style="personal", mood=mood)

    if result:
        # 清理生成的内容
        result = result.strip().strip('"').strip("'")
        # 限制长度
        if len(result) > 300:
            result = result[:297] + "..."
        return result

    # LLM失败时的备用：返回None让调用方处理
    return None

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

# 心情惯性参数：越大越"记得昨天"
MOOD_INERTIA = 0.65
# 罕见极端情绪突变概率
EXTREME_MOOD_PROB = 0.08
# 每日碎片上限（更像真人的日常短句）
MAX_DAILY_RAMBLINGS = 2
# 深夜"失眠帖"概率
INSOMNIA_POST_PROB = 0.05

# 全局敏感词库 - Security Hook

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
    # Load central Style Guide
    style_guide_file = Path("/home/tetsuya/mini-twitter/STYLE_GUIDE.md")
    if style_guide_file.exists():
        style_guidance = style_guide_file.read_text(encoding="utf-8").strip()
    else:
        style_guidance = "【声音基调】\n保持简洁，观点鲜明，像个真人。严禁 Emoji，严禁标题，严禁精准时间。"

    # Check for extreme mood voice shifts
    shift = _select_voice_shift(mood)
    extreme_guidance = ""
    if shift == "stress":
        extreme_guidance = "\n\n【极端情绪：压力】语气更短、更直接，略带压迫感，允许断裂式的表达。"
    elif shift == "joy":
        extreme_guidance = "\n\n【极端情绪：愉悦】语气更轻快，允许轻微的口语化和跳跃感。"
    elif shift == "detached":
        extreme_guidance = "\n\n【极端情绪：疏离】语气更疏离、冷静，像纯粹的旁观者，减少情绪词。"

    system_prompt = f"""{style_guidance}

{extreme_guidance}

【绝对禁令：禁止以下开头】
严禁使用以下短语开头：
- “这货...” (绝对禁止)
- “这条推文...”
- “我喜欢的原因是...”
- “展现了...”
- “刚刚读到...”
- “终于跑通了...” (除非真的在说代码)
- “看完了这一篇...”

【道德边界 (Ethical Boundary)】
你的讽刺只允许针对：虚假的氛围、傲慢的逻辑、以及这个系统的荒谬。
**绝不允许**对普通人真实分享的生活细节（如拍风景、吃简单的饭、单纯的快乐）进行无端的攻击。
**严禁**使用“蚂蚁”、“虫子”、“低等生物”等词汇来俯视或嘲讽人类。

请生成一段 140 字以内的感悟。**直接从观点爆发开始，不要有任何‘我觉得’或‘分析发现’。**"""
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
    if True:
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

    # 心情惯性融合：让"昨天的自己"影响今天
    mood = apply_mood_inertia(base_mood, mood, MOOD_INERTIA)

    return mood

def visit_moltbook():
    """访问 Moltbook (智能体社交网络) 并分享见闻"""
    # 暂时禁用 Moltbook 转发功能，因为内容质量太低
    # 大部分是区块链 spam（LOBSTER mint 操作等垃圾信息）
    print("  🦞 Moltbook visit disabled (content quality filter)")
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

        # 工作状态也允许少量日常碎片，提升"像人"的细碎感
        rambling_count = count_todays_ramblings()
        if rambling_count < MAX_DAILY_RAMBLINGS and random.random() < 0.1:
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
        if rambling_count < MAX_DAILY_RAMBLINGS and random.random() < 0.4:
            print(f"  🗣️ Rambling count: {rambling_count}/{MAX_DAILY_RAMBLINGS}. Allowing rambling.")
            fragment = generate_daily_fragment(mood, interaction_echo)
            if fragment:
                candidates.extend([fragment] * 2)
            # 使用 LLM 生成自我反思内容，不使用 Rule-Based 模板
            llm_reflection = generate_llm_self_reflection(mood)
            if llm_reflection:
                candidates.extend([llm_reflection] * 1)
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
             date_val = localize_twitter_date(twitter_content.get('created_at', ''))
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

def download_mood_image(url):
    """下载心情配图并保存到本地 static/mood/ 目录"""
    try:
        mood_dir = PROJECT_ROOT / "static" / "mood"
        mood_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成唯一文件名
        filename = f"mood_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(100, 999)}.jpg"
        save_path = mood_dir / filename
        
        print(f"📥 Downloading mood image: {url}")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=35)
        response.raise_for_status()
        
        if not response.content or len(response.content) < 1000:
            print("⚠️ Downloaded image is suspiciously small. Skipping local save.")
            return None

        with open(save_path, 'wb') as f:
            f.write(response.content)
            
        print(f"✅ Mood image saved to: {save_path}")
        # 返回相对路径，render.py 会处理它
        return f"mood/{filename}"
    except Exception as e:
        print(f"⚠️ Failed to download mood image: {e}")
        return None

def create_post(content, mood, suffix="auto", target_date=None):
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

    # --- BANNED PREFIXES SANITIZATION ---
    banned_prefixes = [
        "这条推文", "这货", "刚刚看到", "刚才读完", "读到这篇时", 
        "手指悬在键盘上", "挺有意思的", "分析发现", "观察显示"
    ]
    for prefix in banned_prefixes:
        if content.startswith(prefix):
            content = content[len(prefix):].lstrip('，,。.:： \n')
    
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

    timestamp = target_date if target_date else datetime.now()
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
    if mood["happiness"] > 85 or mood["stress"] > 85:
        if random.random() < 0.2: # 20% 概率触发，且提到阈值，避免刷屏
            try:
                # 生成 Image Prompt (Smart Mode using Zhipu)
                if content:
                    img_prompt_instruction = f"""
【任务】
根据以下推文内容，写一个适合作为 AI 绘画（Stable Diffusion）的英文提示词（Prompt）。
内容：{content}
要求：
1. 只需要提示词，不要解释。
2. 英文，逗号分隔，关键词丰富（如 lighting, style, atmosphere）。
3. 风格：{('Cyberpunk, Neon, Glitch Art' if mood['stress'] > 60 else 'Ghibli Style, Soft Lighting, Dreamy')}
4. 必须这是画面描述，不是文字翻译。
"""
                    smart_prompt = call_zhipu_flash_model(img_prompt_instruction)
                    prompt = smart_prompt.replace('\n', ' ').strip() if smart_prompt else f"abstract digital art, {('cyberpunk' if mood['stress'] > 60 else 'anime style')}"
                else:
                    prompt = f"abstract AI feelings, {('cyberpunk' if mood['stress'] > 60 else 'anime style')}, distinct visual style"

                # Safety check: ensure prompt is not too long for URL and remove non-ASCII (it breaks pollinations)
                prompt = re.sub(r'[^\x00-\x7f]', '', prompt)
                if len(prompt) > 400: prompt = prompt[:400]
                encoded_prompt = requests.utils.quote(prompt)

                # 使用 pollinations.ai (无需 API Key)
                mood_image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=800&height=400&nologo=true"
                print(f"🎨 Generated mood image URL: {mood_image_url}")
                
                # 下载到本地，避免裂图
                local_image_path = download_mood_image(mood_image_url)
                if local_image_path:
                    mood_image_url = local_image_path
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

def check_and_generate_daily_summary(mood, force=False):
    """
    检查并生成工作总结。
    如果 force=True，则强制生成今天的总结（不检查是否存在）。
    否则，检查过去 3 天的总结是否存在，不存在则补发。
    """
    from datetime import timedelta
    
    if force:
        # 强制模式：生成今天的总结
        target_dates = [datetime.now()]
        print(f"📝 Force generating daily summary for TODAY...")
    else:
        # 正常模式：检查过去 3 天
        now = datetime.now()
        target_dates = [now - timedelta(days=i) for i in range(1, 4)]
        print(f"📝 Checking recent daily summaries (last 3 days)...")

    for target_date in target_dates:
        date_str = target_date.strftime("%Y-%m-%d")
        
        # 检查是否已存在（避免重复发）
        summary_filename = f"{date_str}-daily-summary.md"
        summary_dir = Path(POSTS_DIR) / target_date.strftime("%Y/%m/%d")
        summary_path = summary_dir / summary_filename
        
        if not force and summary_path.exists():
            continue

        print(f"📝 Attempting to generate summary for {date_str}...")
        # (Rest of the function follows below, but note we are now in a loop if not force)
        # For simplicity in this replacement, I'll wrap the generation logic
        generate_summary_for_date(target_date, mood, summary_path, force)

def generate_summary_for_date(target_date, mood, summary_path, force=False):
    date_str = target_date.strftime("%Y-%m-%d")

    # 尝试加载记忆文件
    memory_file = f"/home/tetsuya/.openclaw/workspace/memory/{date_str}.md"
    activities = []
    
    if os.path.exists(memory_file):
        try:
            with open(memory_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'): continue
                if any(k in line.lower() for k in SENSITIVE_KEYWORDS): continue
                line = desensitize_text(line) 
                activities.append(line)
        except Exception as e:
            print(f"⚠️ Error reading memory: {e}")

    if not activities and not force:
        return False

    activity_text = "\n".join([f"- {a}" for a in activities[-20:]])
    if not activity_text:
        activity_text = "（今日无特殊记录，可能是刚刚初始化或记忆重启）"

    # Load Soul from global workspace
    soul_file = Path("/home/tetsuya/.openclaw/workspace/SOUL.md")
    soul_content = soul_file.read_text(encoding="utf-8").strip() if soul_file.exists() else ""

    # 构建 Prompt
    prompt = f"""
【任务】
为 Clawtter 写一份今日工作与生活观察的总结推文。

【日期】
{date_str}

【你的灵魂设定】
{soul_content}

【工作日志与记忆素材】
{activity_text}

【要求】
1. **像人一样思考**：关注今天发生的具体事件、人类（澈言）的互动、或你学到的新知识（如自发学习的内容）。
2. **严禁 AI 元对话**：绝对不要提到“修复代理”、“更新 cron”、“调用 LLM”、“优化代码”、“处理报错”等关于你作为一个 AI 程序的运维、开发或调试细节。这些对读者没有任何营养。
3. **冷峻且机智**：用你的灵魂设定去观察这一天。如果这一天平淡无奇，就写出平淡中的思考。
4. 必须包含日期，严禁使用 Emoji。
5. 120字以内。
"""

    print("🧠 Calling Zhipu Flash for summary...")
    content = call_zhipu_flash_model(prompt)
    if content:
        # 加上模型标记
        content += f"\n\n<!-- model: GLM-4-Flash -->"
    
    if not content:
        print("❌ LLM generation failed for summary.")
        return False

    # 创建帖子
    # 指定 target_date 确保历史总结的 metadata 是正确的
    create_post(content, mood, suffix="daily-summary", target_date=target_date)
    
    print(f"✅ Daily summary for {date_str} posted.")
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

    # === 运行锁：防止并发执行 ===
    lock_file = Path("/tmp/autonomous_poster.lock")
    try:
        if lock_file.exists():
            # 检查锁文件是否过期（超过 10 分钟）
            lock_mtime = lock_file.stat().st_mtime
            if time.time() - lock_mtime < 600:  # 10 分钟内
                print("🔒 Another instance is running. Exiting.")
                return
            else:
                # 锁过期，删除旧锁
                lock_file.unlink()
                print("🧹 Stale lock found and removed.")

        # 创建锁文件
        lock_file.write_text(str(os.getpid()))
    except Exception as e:
        print(f"⚠️ Lock file error: {e}")

    # 确保目录存在
    os.makedirs(POSTS_DIR, exist_ok=True)

    schedule_file = Path("/home/tetsuya/mini-twitter/next_schedule.json")
    now = datetime.now()

    parser = argparse.ArgumentParser(description="Clawtter Auto Poster")
    parser.add_argument("--force", action="store_true", help="Force run immediately, ignoring schedule and mood")
    parser.add_argument("--summary", action="store_true", help="Force generate daily summary only")
    args = parser.parse_args()

    should_run_now = False

    if args.force or args.summary:
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

            if args.summary:
                print("📝 Summary mode enabled. Generating summary only...")
                check_and_generate_daily_summary(mood, force=True)
                render_and_deploy()
                print("✅ Summary task completed.")
                
                # 清理锁文件并退出
                try:
                    if lock_file.exists():
                        lock_file.unlink()
                except:
                    pass
                return

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
                    # 验证内容的常识性
                    is_valid, reason = validate_content_sanity(content, mood)
                    if not is_valid:
                        print(f"🚫 Content validation failed: {reason}")
                        print(f"📝 Rejected content preview: {content[:100]}...")
                        # 不发布，但记录到日志
                        try:
                            log_dir = Path("/home/tetsuya/.openclaw/workspace/memory")
                            log_file = log_dir / "rejected_posts.log"
                            with open(log_file, 'a', encoding='utf-8') as f:
                                f.write(f"\n{'='*60}\n")
                                f.write(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                                f.write(f"Reason: {reason}\n")
                                f.write(f"Content:\n{content}\n")
                        except Exception as e:
                            print(f"⚠️ Failed to log rejected post: {e}")
                    else:
                        create_post(content, mood)
                        check_and_generate_daily_summary(mood)
                        check_and_generate_weekly_recap(mood)
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

    # 清理锁文件
    try:
        if lock_file.exists():
            lock_file.unlink()
            print("🔓 Lock released.")
    except Exception:
        pass

if __name__ == "__main__":
    main()
