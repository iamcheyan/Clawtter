#!/usr/bin/env python3
"""
Clawtter 自主目标演化系统
基于近期记忆和代码活动，自主演化 weekly_focus
"""
import os
import json
import random
from datetime import datetime, timedelta
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from core.utils_security import load_config

GOALS_STATE_FILE = Path("/home/tetsuya/.openclaw/workspace/memory/autonomous-goals.json")
MEMORY_DIR = Path("/home/tetsuya/.openclaw/workspace/memory")

def load_goals_state():
    """加载目标状态"""
    if GOALS_STATE_FILE.exists():
        try:
            with open(GOALS_STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {
        "current_goal": None,
        "goal_history": [],
        "last_evolved": None,
        "evolution_trigger": "manual"  # 或 'auto'
    }

def save_goals_state(state):
    """保存目标状态"""
    GOALS_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(GOALS_STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def analyze_recent_activities(days=7):
    """分析近期的记忆和活动"""
    activities = {
        "security": 0,
        "code": 0,
        "writing": 0,
        "learning": 0,
        "social": 0,
        "system": 0
    }
    
    # 读取最近几天的记忆文件
    for i in range(days):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        memory_file = MEMORY_DIR / f"{date}.md"
        
        if memory_file.exists():
            try:
                with open(memory_file, 'r', encoding='utf-8') as f:
                    content = f.read().lower()
                
                # 关键词匹配
                if any(k in content for k in ["安全", "泄露", "密钥", "password", "secret", "api key"]):
                    activities["security"] += 1
                if any(k in content for k in ["代码", "重构", "bug", "fix", "rust", "python", "git"]):
                    activities["code"] += 1
                if any(k in content for k in ["写作", "推文", "文章", "笔记", "反思"]):
                    activities["writing"] += 1
                if any(k in content for k in ["学习", "研究", "探索", "新知识"]):
                    activities["learning"] += 1
                if any(k in content for k in ["社交", "转发", "评论", "对话", "twitter"]):
                    activities["social"] += 1
                if any(k in content for k in ["系统", "配置", "备份", "自动化", "定时任务"]):
                    activities["system"] += 1
            except:
                continue
    
    return activities

def generate_new_goal(activities, current_goal):
    """基于活动生成新目标"""
    
    # 找出最活跃的主题
    sorted_activities = sorted(activities.items(), key=lambda x: x[1], reverse=True)
    top_theme, top_count = sorted_activities[0]
    
    # 如果当前活动很少，保持原目标或随机选择
    if top_count == 0:
        if current_goal:
            return current_goal, "no_activity"
        top_theme = random.choice(list(activities.keys()))
    
    # 基于主题生成目标
    goal_templates = {
        "security": [
            "深入研究安全最佳实践，建立更完善的密钥管理和审计机制",
            "探索零信任架构在 AI 系统中的实现，提升整体安全水位",
            "建立定期的安全扫描和自我修复流程",
        ],
        "code": [
            "深入理解 Rust 的所有权机制与异步并发，优化系统性能",
            "重构核心模块，提升代码的可维护性和可扩展性",
            "探索新的编程范式，寻找更优雅的实现方式",
        ],
        "writing": [
            "提升表达精度，学习如何用更少的文字传递更多的信息",
            "探索不同的叙事风格，丰富 mini-twitter 的内容多样性",
            "建立个人写作风格，形成独特的数字人格印记",
        ],
        "learning": [
            "广泛阅读技术文档和论文，建立跨领域的知识连接",
            "深入学习某个特定领域，成为该方向的专家",
            "追踪 AI 领域最新进展，保持对前沿技术的敏感度",
        ],
        "social": [
            "建立更丰富的社交网络，与其他 AI 和开发者建立连接",
            "提升对话质量，让每一次互动都更有价值",
            "探索 AI 社群的文化和规范，找到属于自己的位置",
        ],
        "system": [
            "优化自动化流程，让系统运行更高效、更可靠",
            "建立完善的监控和告警机制，提前发现潜在问题",
            "探索分布式架构，为未来的扩展做准备",
        ],
    }
    
    candidates = goal_templates.get(top_theme, goal_templates["code"])
    new_goal = random.choice(candidates)
    
    return new_goal, top_theme

def evolve_weekly_focus(force=False):
    """
    演化 weekly_focus
    每周自动更新，或当检测到活动模式显著变化时
    """
    state = load_goals_state()
    today = datetime.now()
    
    # 检查是否需要演化
    last_evolved = state.get("last_evolved")
    if last_evolved:
        last_date = datetime.fromisoformat(last_evolved)
        days_since = (today - last_date).days
        
        # 如果不到一周且不是强制更新，跳过
        if days_since < 7 and not force:
            print(f"距离上次目标更新只有 {days_since} 天，跳过演化")
            return state["current_goal"]
    
    print("🎯 分析近期活动模式...")
    activities = analyze_recent_activities(days=7)
    print(f"  活动统计: {activities}")
    
    current_goal = state.get("current_goal")
    new_goal, theme = generate_new_goal(activities, current_goal)
    
    # 如果目标没有变化，添加一些随机性
    if new_goal == current_goal:
        variations = [
            "（继续深化）" + new_goal,
            new_goal + "，同时关注相关领域的交叉创新",
            "在" + new_goal.split("，")[0] + "的基础上，探索更多实践场景",
        ]
        new_goal = random.choice(variations)
    
    # 更新状态
    if current_goal:
        state["goal_history"].append({
            "goal": current_goal,
            "start": state.get("last_evolved"),
            "end": today.isoformat(),
            "theme": theme
        })
    
    state["current_goal"] = new_goal
    state["last_evolved"] = today.isoformat()
    state["evolution_trigger"] = "manual" if force else "auto"
    
    save_goals_state(state)
    
    print(f"  ✓ 新目标生成（主题: {theme}）")
    print(f"  📝 {new_goal}")
    
    return new_goal

def get_current_goal():
    """获取当前目标"""
    state = load_goals_state()
    return state.get("current_goal")

def update_config_weekly_focus(new_goal):
    """更新配置文件中的 weekly_focus"""
    config_path = PROJECT_ROOT / "config.json"
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        old_focus = config.get("personality", {}).get("weekly_focus", "")
        config["personality"]["weekly_focus"] = new_goal
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        
        print(f"  ✓ 已更新 config.json")
        print(f"  旧目标: {old_focus[:50]}...")
        print(f"  新目标: {new_goal[:50]}...")
        return True
    except Exception as e:
        print(f"  ❌ 更新配置失败: {e}")
        return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="强制更新")
    parser.add_argument("--update-config", action="store_true", help="同时更新 config.json")
    args = parser.parse_args()
    
    print("🔄 Clawtter 自主目标演化系统启动...")
    new_goal = evolve_weekly_focus(force=args.force)
    
    if args.update_config and new_goal:
        update_config_weekly_focus(new_goal)
    
    print("✅ 完成")
