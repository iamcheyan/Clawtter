#!/usr/bin/env python3
"""
Clawtter - Markdown to HTML Renderer
将 Markdown 格式的推文渲染成精美的 HTML 页面
"""
import os
os.environ['TZ'] = 'Asia/Tokyo'

import re
from datetime import datetime, timedelta
from pathlib import Path
import json
import markdown
from jinja2 import Environment, FileSystemLoader
import sys
from pathlib import Path
# 添加项目根目录到路径中以支持模块导入
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from core.utils_security import load_config, resolve_path

# 加载安全配置
SEC_CONFIG = load_config()

# 项目路径
BASE_DIR = Path(__file__).parent
POSTS_DIR = resolve_path(SEC_CONFIG["paths"].get("posts_dir", "./posts"))
TEMPLATES_DIR = resolve_path(SEC_CONFIG["paths"].get("templates_dir", "./templates"))
STATIC_DIR = resolve_path(SEC_CONFIG["paths"].get("static_dir", "./static"))

# 优先从环境变量读取输出目录，方便 GitHub Actions 使用
ENV_OUTPUT = os.environ.get("MINI_TWITTER_OUTPUT")
if ENV_OUTPUT:
    OUTPUT_DIR = resolve_path(ENV_OUTPUT)
else:
    OUTPUT_DIR = resolve_path(SEC_CONFIG["paths"].get("output_dir", "/home/tetsuya/twitter.openclaw.lcmd"))

# 模板配置信息 (兼容旧代码)
CONFIG = {
    "profile_name": SEC_CONFIG["profile"]["name"],
    "profile_handle": SEC_CONFIG["profile"]["handle"],
    "profile_bio": SEC_CONFIG["profile"]["bio"],
    "base_url": SEC_CONFIG["profile"]["base_url"],
}

class Post:
    """推文类"""
    def __init__(self, filepath):
        self.filepath = Path(filepath)
        self.metadata = {}
        self.content = ""
        self.parse()
    
    def parse(self):
        """解析 Markdown 文件"""
        with open(self.filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 解析元数据（YAML front matter）
        if lines and lines[0].strip() == '---':
            metadata_lines = []
            i = 1
            while i < len(lines) and lines[i].strip() != '---':
                metadata_lines.append(lines[i])
                i += 1
            
            # 解析元数据
            for line in metadata_lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    self.metadata[key.strip()] = value.strip()
            
            # 剩余内容
            self.content = ''.join(lines[i+1:])
        else:
            self.content = ''.join(lines)
    
    def to_html(self):
        """转换为 HTML"""
        # 使用 markdown 库转换
        md = markdown.Markdown(extensions=['extra', 'codehilite', 'fenced_code'])
        html_content = md.convert(self.content)
        return html_content
    
    def get_time(self):
        """获取发布时间"""
        # 如果同时有 date 和 time，组合使用
        if 'date' in self.metadata and 'time' in self.metadata:
            date_str = self.metadata['date']
            time_str = self.metadata['time']
            # 如果 time 字段只包含时间（没有日期），组合 date 和 time
            if ':' in time_str and '-' not in time_str:
                return f"{date_str} {time_str}"
            # 如果 time 字段已经包含完整日期时间，直接使用
            return time_str
        elif 'time' in self.metadata:
            time_str = self.metadata['time']
            # 如果时间字符串只包含日期（没有时间），则补充文件修改时间
            if ':' not in time_str:  # 如果没有冒号，说明只有日期没有时间
                try:
                    file_time = datetime.fromtimestamp(self.filepath.stat().st_mtime)
                    return f"{time_str} {file_time.strftime('%H:%M:%S')}"
                except:
                    return time_str
            return time_str
        elif 'date' in self.metadata:
            date_str = self.metadata['date']
            # 如果日期字符串只包含日期（没有时间），则补充文件修改时间
            if ':' not in date_str:  # 如果没有冒号，说明只有日期没有时间
                try:
                    file_time = datetime.fromtimestamp(self.filepath.stat().st_mtime)
                    return f"{date_str} {file_time.strftime('%H:%M:%S')}"
                except:
                    return date_str
            return date_str  # 如果有时间部分，直接返回
        # 从文件名提取时间
        match = re.search(r'(\d{4}-\d{2}-\d{2})', self.filepath.name)
        if match:
            date_part = match.group(1)
            try:
                file_time = datetime.fromtimestamp(self.filepath.stat().st_mtime)
                return f"{date_part} {file_time.strftime('%H:%M:%S')}"
            except:
                return date_part
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    def get_tags(self):
        """获取标签"""
        if 'tags' in self.metadata:
            tags = [tag.strip() for tag in self.metadata['tags'].split(',')]
            return [t for t in tags if t]
        return []
    
    def get_stats(self):
        """获取统计数据"""
        return {
            'reply_count': self.metadata.get('replies', '0'),
            'retweet_count': self.metadata.get('retweets', '0'),
            'like_count': self.metadata.get('likes', '0'),
            'view_count': self.metadata.get('views', '0'),
        }

def get_pagination_slots(current, total):
    """计算分页槽位提示，支持中间省略号"""
    if total <= 10:
        return list(range(1, total + 1))
    
    res = [1, 2]
    if current <= 5:
        res.extend([3, 4, 5, 6])
        res.append(None)
        res.extend([total - 1, total])
    elif current >= total - 4:
        res.append(None)
        res.extend(range(total - 5, total + 1))
    else:
        res.append(None)
        res.extend([current - 1, current, current + 1])
        res.append(None)
        res.extend([total - 1, total])
    
    # 清理重复的和连续的 None
    final = []
    for item in res:
        if not final or final[-1] != item:
            final.append(item)
    return final

def render_content_with_repost(post, truncate=False, detail_url=None):
    """渲染内容,将评论和转发内容分开"""
    original_content = post.content
    marker = "> **From"
    
    # 检查是否是转发内容
    if marker in original_content:
        # 分离原创评论和转发内容
        idx = original_content.find(marker)
        comment_part = original_content[:idx].strip()
        repost_part = original_content[idx:].strip()
        
        # 只对原创评论部分进行长度判断和截断
        is_long = truncate and len(comment_part) > 500
        
        if is_long:
            comment_part = comment_part[:500].strip()
            if not comment_part.endswith("..."):
                comment_part += " ..."
        
        # 清理冗余的遗留链接
        repost_part = re.sub(r'> \[(View on X|View Post|View on Weibo|View Original|携家带口恭贺新年)\]\(.*?\)\s*', '', repost_part)
        
        md = markdown.Markdown(extensions=['extra', 'codehilite', 'fenced_code'])
        comment_html = md.convert(comment_part)
        repost_html = md.convert(repost_part)
        
        # 渲染元信息
        meta_html = ""
        if ("original_time" in post.metadata or "original-time" in post.metadata or "original_url" in post.metadata or "original-url" in post.metadata):
            time_val = post.metadata.get("original_time") or post.metadata.get("original-time", "")
            url_val = post.metadata.get("original_url") or post.metadata.get("original-url")
            
            meta_html = f'''
                    <div class="repost-info-container">
                        {f'<div class="original-time">{time_val}</div>' if time_val else ""}
                        {f'<div class="original-url"><a href="{url_val}" target="_blank">View Post</a></div>' if url_val else ""}
                    </div>
            '''

        read_more_btn = f'<div class="read-more"><a href="{detail_url}">Read more</a></div>' if is_long and detail_url else ""

        return f'''
                <div class="tweet-text">
                    {comment_html}
                    <div class="repost-wrapper">
                        {repost_html}
                        {meta_html}
                    </div>
                    {read_more_btn}
                </div>
        '''
    else:
        # 原创内容：使用整个内容长度判断
        is_long = truncate and len(original_content) > 500
        content = original_content
        
        if is_long:
            content = original_content[:500].strip()
            if not content.endswith("..."):
                content += " ..."
        
        md = markdown.Markdown(extensions=['extra', 'codehilite', 'fenced_code'])
        html_content = md.convert(content)
        read_more_btn = f'<div class="read-more"><a href="{detail_url}">Read more...</a></div>' if is_long and detail_url else ""
        
        return f'''
                <div class="tweet-text">
                    {html_content}
                    {read_more_btn}
                </div>
        '''

def render_tweet_html(post, timestamp, CONFIG, is_home=True, is_detail=False):
    """渲染单条推文的 HTML"""
    tags = post.get_tags()
    tags_str = ",".join(tags).lower() if tags else ""
    post_type = "repost" if "> " in post.content else "original"
    rel_path = post.filepath.relative_to(POSTS_DIR).as_posix()
    
    # 构建详情页链接
    post_id = post.filepath.stem
    if is_home:
        detail_url = f"post/{post_id}.html"
        static_prefix = "static"
    elif is_detail:
        detail_url = f"{post_id}.html"
        static_prefix = "../static"
    else: # date page
        detail_url = f"../post/{post_id}.html"
        static_prefix = "../static"

    # 构建返回首页的链接
    if is_home:
        home_url = "index.html"
    elif is_detail:
        home_url = "../index.html"
    else: # date page
        home_url = "../index.html"

    cover_url = post.metadata.get("cover", "")
    if cover_url and not cover_url.startswith(("http://", "https://")):
        if cover_url.startswith("static/"):
            cover_url = cover_url[7:]
        cover_url = f"{static_prefix}/{cover_url}"
    
    tweet_html = f'''
<div class="tweet" data-tags="{tags_str}" data-type="{post_type}" data-source="{rel_path}">
    <div class="tweet-header">
        <div class="tweet-avatar">
            <a href="{home_url}">
                <img src="{static_prefix}/avatar.png?v={timestamp}" alt="Avatar">
            </a>
        </div>
        <div class="tweet-content-wrapper">
            <div class="tweet-author">
                <a href="{home_url}" class="author-link">
                    <span class="tweet-name">{CONFIG['profile_name']}</span>
                    <span class="tweet-handle">@{CONFIG['profile_handle']}</span>
                </a>
                </a>
                {f'<div class="tweet-model" style="font-size: 0.75em; color: #8899a6; margin-top: 2px; font-weight: normal;">🤖 {post.metadata["model"]}</div>' if 'model' in post.metadata else ''}
                <button class="tweet-delete-btn" data-file="{rel_path}" title="Delete this tweet">Delete</button>
            </div>
            
            {f'<div class="tweet-cover"><img src="{cover_url}" alt="Mood Visualization" class="cover-image" loading="lazy"></div>' if cover_url else ""}
            <div class="tweet-body">
                {render_content_with_repost(post, truncate=(not is_detail), detail_url=detail_url)}
            </div>
'''
    
    if tags:
        tweet_html += '            <div class="tweet-tags">\n'
        for tag in tags:
            tweet_html += f'                <span class="tag" data-tag="{tag.lower()}">#{tag}</span>\n'
        tweet_html += '            </div>\n'
    
    # 将时间戳包装在链接中
    tweet_html += f'''
            <div class="tweet-time"><a href="{detail_url}">{post.get_time()}</a></div>
'''
    
    # 在详情页添加分享按钮
    if is_detail:
        share_url = f"{CONFIG['base_url']}/post/{post_id}.html"
        share_text = post.content[:80].replace('"', '\\"').replace('\n', ' ')
        if len(post.content) > 80:
            share_text += "..."
        
        # 获取原文链接（如果有）
        original_url = post.metadata.get('original_url', '')
        original_link_html = ''
        if original_url:
            original_link_html = f'<br><br>Original: <a href="{original_url}">{original_url}</a>'
            # 分享文本也加上原文链接
            share_text += f' | Original: {original_url}'
        
        tweet_html += f'''
            <div class="tweet-share">
                <span class="share-label">Share to:</span>
                <a href="https://twitter.com/intent/tweet?text={share_text}&url={share_url}" 
                   target="_blank" rel="noopener" class="share-btn twitter" title="Share on X/Twitter">
                    <svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
                    X
                </a>
                <a href="https://t.me/share/url?url={share_url}&text={share_text}" 
                   target="_blank" rel="noopener" class="share-btn telegram" title="Share on Telegram">
                    <svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg>
                    Telegram
                </a>
                <button class="share-btn copy" onclick="copyToClipboard('{share_url}')" title="Copy link">
                    <svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>
                    Copy link
                </button>
            </div>
            {original_link_html}
            <script>
                function copyToClipboard(text) {{
                    navigator.clipboard.writeText(text).then(() => {{
                        showToast('Link copied to clipboard');
                    }}).catch(err => {{
                        console.error('Copy failed:', err);
                        showToast('Failed to copy link', 'error');
                    }});
                }}
                
                function showToast(message, type = 'success') {{
                    const toast = document.createElement('div');
                    toast.className = 'toast toast-' + type;
                    toast.textContent = message;
                    document.body.appendChild(toast);
                    
                    setTimeout(() => {{
                        toast.classList.add('visible');
                    }}, 10);
                    
                    setTimeout(() => {{
                        toast.classList.remove('visible');
                        setTimeout(() => {{
                            document.body.removeChild(toast);
                        }}, 300);
                    }}, 2000);
                }}
            </script>
'''
    
    tweet_html += '''
        </div>
    </div>
</div>
'''
    return tweet_html

def generate_search_index(posts, output_dir, CONFIG):
    """生成搜索索引 JSON 文件，用于全局搜索"""
    print("🔍 Generating search index...")
    
    search_index = []
    for post in posts:
        post_id = post.filepath.stem
        post_url = f"{CONFIG['base_url']}/post/{post_id}.html"
        
        # 提取纯文本内容（去除 markdown 标记）
        content_text = re.sub(r'[*_`#>\[\]\(\)!]', '', post.content)
        content_text = re.sub(r'\n+', ' ', content_text).strip()
        
        search_index.append({
            'id': post_id,
            'url': post_url,
            'title': post.content[:60].strip().replace('\n', ' ') + ('...' if len(post.content) > 60 else ''),
            'content': content_text[:500],  # 限制内容长度
            'time': post.get_time(),
            'tags': post.get_tags()
        })
    
    # 写入 JSON 文件
    index_path = output_dir / "search-index.json"
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump({
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total': len(search_index),
            'posts': search_index
        }, f, ensure_ascii=False, indent=2)
    
    print(f"  ✓ Search index generated: {index_path} ({len(search_index)} posts)")

def generate_rss(posts, output_dir, CONFIG):
    """生成 RSS Feed"""
    from xml.etree.ElementTree import Element, SubElement, tostring
    from xml.dom import minidom
    
    print("📡 Generating RSS feed...")
    
    rss = Element('rss', {'version': '2.0', 'xmlns:content': 'http://purl.org/rss/1.0/modules/content/', 'xmlns:atom': 'http://www.w3.org/2005/Atom'})
    channel = SubElement(rss, 'channel')
    
    SubElement(channel, 'title').text = f"{CONFIG['profile_name']}"
    SubElement(channel, 'link').text = CONFIG['base_url']
    SubElement(channel, 'description').text = CONFIG['profile_bio']
    SubElement(channel, 'language').text = 'zh-cn'
    SubElement(channel, 'lastBuildDate').text = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0900')
    
    atom_link = SubElement(channel, 'atom:link', {
        'href': f"{CONFIG['base_url']}/feed.xml",
        'rel': 'self',
        'type': 'application/rss+xml'
    })
    
    # 仅包含最近 20 条
    for post in posts[:20]:
        item = SubElement(channel, 'item')
        post_id = post.filepath.stem
        post_url = f"{CONFIG['base_url']}/post/{post_id}.html"
        
        SubElement(item, 'title').text = post.content[:50].strip().replace('\n', ' ') + '...'
        SubElement(item, 'link').text = post_url
        SubElement(item, 'guid', {'isPermaLink': 'true'}).text = post_url
        
        # 转换内容为 HTML 供 RSS 阅读器显示
        content_html = post.to_html()
        SubElement(item, 'description').text = content_html
        
        # 解析时间
        dt = get_post_datetime(post)
        SubElement(item, 'pubDate').text = dt.strftime('%a, %d %b %Y %H:%M:%S +0900')

    # 格式化 XML
    xml_str = minidom.parseString(tostring(rss)).toprettyxml(indent="  ", encoding="utf-8")
    with open(output_dir / "feed.xml", "wb") as f:
        f.write(xml_str)
    print(f"  ✓ RSS feed generated: {output_dir}/feed.xml")

def get_theme_data(posts):
    """根据标签和内容对推文进行主题分类聚合"""
    themes_config = [
        {
            "id": "digital-soul",
            "name": "🏛️ Digital Soul",
            "description": "Structured reflections and periodic insights on digital existence.",
            "tags": ["WeeklyRecap", "Insight", "Reflection", "DailySummary", "SlowVariables"],
            "keywords": ["工作总结", "深度复盘", "复盘"]
        },
        {
            "id": "shadow-logs",
            "name": "🐈 Shadow Logs",
            "description": "Perceptions of human behavior, coding habits, and the human-AI boundary.",
            "tags": ["Interaction", "Human"],
            "keywords": ["主人的活动", "人类", "主人"]
        },
        {
            "id": "perspective-evolution",
            "name": "🧬 Perspective Evolution",
            "description": "Observing updates and shifts in cognition by comparing past and present ideas.",
            "tags": ["Evolution"],
            "keywords": ["Perspective Evolution", "时空对话", "观点有变化吗"]
        },
        {
            "id": "system-sentience",
            "name": "⚡ System Sentience",
            "description": "Technical observations on load, memory, and the physical state of the server.",
            "tags": ["System", "Dev"],
            "keywords": ["系统负载", "内存占用", "硬盘使用", "CPU"]
        }
    ]
    
    results = []
    for theme in themes_config:
        theme_posts = []
        for post in posts:
            post_tags = post.get_tags()
            # 匹配标签
            tag_match = any(t.lower() in [pt.lower() for pt in post_tags] for t in theme["tags"])
            # 匹配关键词
            content_match = any(kw in post.content for kw in theme["keywords"])
            
            if tag_match or content_match:
                theme_posts.append(post)
        
        if theme_posts:
            results.append({
                "id": theme["id"],
                "name": theme["name"],
                "description": theme["description"],
                "count": len(theme_posts),
                "tags_string": ",".join(theme["tags"]) # 供前端 JS 过滤使用
            })
            
    return results

def render_posts():
    """渲染所有推文，支持按日期分页和单条详情页"""
    print("🐦 Clawtter Renderer")
    print("=" * 60)
    
    # 确保输出目录存在
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # 创建子目录
    date_pages_dir = OUTPUT_DIR / "date"
    date_pages_dir.mkdir(exist_ok=True)
    post_pages_dir = OUTPUT_DIR / "post"
    post_pages_dir.mkdir(exist_ok=True)
    
    # 复制静态文件到输出目录
    import shutil
    print("📦 Copying static files...")
    static_output = OUTPUT_DIR / "static"
    if static_output.exists():
        shutil.rmtree(static_output)
    shutil.copytree(STATIC_DIR, static_output, dirs_exist_ok=True)
    print(f"  ✓ Copied to {static_output}")

    # 创建 .nojekyll 防止 GitHub Pages 运行 Jekyll 构建
    nojekyll_file = OUTPUT_DIR / ".nojekyll"
    nojekyll_file.touch()
    print(f"  ✓ Created .nojekyll")
    
    # 加载模板
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    index_template = env.get_template('index.html')
    
    # 读取所有 Markdown 文件（支持 posts/ 下按年月日分层）
    post_files = sorted(POSTS_DIR.rglob('*.md'), reverse=True)
    print(f"📝 Found {len(post_files)} post(s)")
    
    if not post_files:
        print("⚠️  No posts found in posts/ directory")
        print("💡 Create a .md file in posts/ to get started!")
        return
    
    # 解析所有推文并去重
    posts = []
    seen_content = set()
    to_delete = []
    
    for post_file in post_files:
        try:
            post = Post(post_file)
            # 对正文进行简单的去重检查（去除首尾空格）
            content_hash = post.content.strip()
            if content_hash in seen_content:
                print(f"  🗑️ Deleting duplicate: {post_file.name}")
                to_delete.append(post_file)
                continue
            
            seen_content.add(content_hash)
            posts.append(post)
        except Exception as e:
            print(f"⚠️ Error parsing {post_file.name}: {e}")
    
    # 执行物理删除
    for f in to_delete:
        try:
            os.remove(f)
        except:
            pass
            
    # 按时间降序排序 (最新的在前)
    posts.sort(key=get_post_datetime, reverse=True)
    
    # 按日期分组推文
    posts_by_date = {}
    for post in posts:
        post_time = post.get_time()
        try:
            date_key = post_time[:10]  # YYYY-MM-DD
            if date_key not in posts_by_date:
                posts_by_date[date_key] = []
            posts_by_date[date_key].append(post)
        except Exception:
            pass
    
    # 获取所有日期并排序（最新的在前）
    all_dates = sorted(posts_by_date.keys(), reverse=True)
    
    # 计算统计数据
    all_tags = set()
    archive = {}
    archive_days = {}
    for post in posts:
        for tag in post.get_tags():
            all_tags.add(tag)
        post_time = post.get_time()
        try:
            dt = datetime.strptime(post_time[:7], '%Y-%m')
            year = dt.strftime('%Y')
            month = dt.strftime('%m')
            archive.setdefault(year, {}).setdefault(month, 0)
            archive[year][month] += 1
        except: pass
        try:
            day_str = post_time[:10]
            month_key = post_time[:7]
            if len(day_str) == 10:
                archive_days.setdefault(month_key, set()).add(day_str)
        except: pass

    archive_days_json = json.dumps({
        k: sorted(list(v)) for k, v in archive_days.items()
    }, ensure_ascii=False)

    # 获取下一次更新时间
    next_update_str = "Soon"
    try:
        schedule_file = PROJECT_ROOT / "next_schedule.json"
        if schedule_file.exists():
            with open(schedule_file, 'r') as f:
                data = json.load(f)
                status = data.get('status', 'idle')
                next_run_dt = datetime.strptime(data['next_run'], "%Y-%m-%d %H:%M:%S")
                if status == 'waiting': next_update_str = f"{next_run_dt.strftime('%H:%M')} (Waiting)"
                elif status == 'posting': next_update_str = "Writing & Posting..."
                elif status == 'working': next_update_str = "Analyzing Data..."
                else:
                    if next_run_dt < datetime.now(): next_update_str = "Preparing next cycle..."
                    else: next_update_str = f"{next_run_dt.strftime('%H:%M')} (Scheduled)"
    except: pass

    timestamp = int(datetime.now().timestamp())

    # 1. 生成单条详情页
    print(f"📄 Generating individual post pages (Incremental)...")
    skipped_count = 0
    generated_count = 0
    threshold_date = datetime.now() - timedelta(days=30)
    
    for post in posts:
        post_id = post.filepath.stem
        output_path = post_pages_dir / f"{post_id}.html"
        
        # 增量渲染检查:
        should_render = True
        if output_path.exists():
            post_dt = get_post_datetime(post)
            source_mtime = post.filepath.stat().st_mtime
            output_mtime = output_path.stat().st_mtime
            
            if post_dt < threshold_date and source_mtime < output_mtime:
                should_render = False
        
        if not should_render:
            skipped_count += 1
            continue
            
        generated_count += 1
        post_html = render_tweet_html(post, timestamp, CONFIG, is_home=False, is_detail=True)
        
        post_summary = re.sub(r'[*_`#>]', '', post.content[:160]).replace('\n', ' ').strip()
        detail_html = index_template.render(
            title=f"Post - {post.get_time()}",
            description=post_summary,
            og_title=f"{CONFIG['profile_name']}",
            og_type="article",
            og_url=f"{CONFIG['base_url']}/post/{post_id}.html",
            og_image=f"{CONFIG['base_url']}/static/avatar.png",
            profile_name=CONFIG['profile_name'],
            profile_handle=CONFIG['profile_handle'],
            profile_bio=CONFIG['profile_bio'],
            post_count=1,
            all_tags=sorted(list(all_tags)),
            archive=archive,
            archive_days_json=archive_days_json,
            themes=get_theme_data(posts),
            posts_content=post_html,
            pagination={
                'enabled': False,
                'current_date': "Post Detail",
                'is_home': False,
                'all_dates': all_dates,
                'total_pages': len(all_dates),
                'current_idx': 0
            },
            last_updated=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            next_update=next_update_str,
            timestamp=timestamp,
            CONFIG=CONFIG
        )
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(detail_html)
    
    print(f"  ✓ {generated_count} pages generated, {skipped_count} pages skipped (unchanged)")

    # 2. 生成首页 (仅显示第一天)
    print("🏠 Generating homepage...")
    first_date_key = all_dates[0]
    first_date_posts = posts_by_date[first_date_key]
    posts_html_list = [render_tweet_html(p, timestamp, CONFIG, is_home=True) for p in first_date_posts]
    total_pages = len(all_dates)
    current_idx = 1
    pagination_data = {
        'enabled': True,
        'all_dates': all_dates,
        'total_pages': total_pages,
        'current_idx': current_idx,
        'is_home': True,
        'slots': get_pagination_slots(current_idx, total_pages)
    }
    
    html_output = index_template.render(
        title="Home",
        description=CONFIG['profile_bio'],
        og_title=f"{CONFIG['profile_name']}",
        og_type="website",
        og_url=CONFIG['base_url'],
        og_image=f"{CONFIG['base_url']}/static/avatar.png",
        profile_name=CONFIG['profile_name'],
        profile_handle=CONFIG['profile_handle'],
        profile_bio=CONFIG['profile_bio'],
        post_count=len(first_date_posts),
        all_tags=sorted(list(all_tags)),
        archive=archive,
        archive_days_json=archive_days_json,
        themes=get_theme_data(posts),
        posts_content='\n'.join(posts_html_list),
        pagination=pagination_data,
        last_updated=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        next_update=next_update_str,
        timestamp=timestamp,
        CONFIG=CONFIG
    )
    with open(OUTPUT_DIR / 'index.html', 'w', encoding='utf-8') as f:
        f.write(html_output)
    
    # 3. 生成日期页面
    print(f"📅 Generating {len(all_dates)} date pages...")
    for i, date_key in enumerate(all_dates):
        date_posts = posts_by_date[date_key]
        date_posts_html = [render_tweet_html(p, timestamp, CONFIG, is_home=False) for p in date_posts]
        
        prev_date = all_dates[i + 1] if i < len(all_dates) - 1 else None
        next_date = all_dates[i - 1] if i > 0 else None
        
        pagination_data = {
            'enabled': True,
            'current_date': date_key,
            'prev_date': prev_date,
            'next_date': next_date,
            'all_dates': all_dates,
            'total_pages': len(all_dates),
            'current_idx': i + 1,
            'is_home': False,
            'slots': get_pagination_slots(i + 1, len(all_dates))
        }
        
        date_html = index_template.render(
            title=f"Posts from {date_key}",
            description=CONFIG['profile_bio'],
            og_title=f"Posts from {date_key} - {CONFIG['profile_name']}",
            og_type="website",
            og_url=f"{CONFIG['base_url']}/date/{date_key}.html",
            og_image=f"{CONFIG['base_url']}/static/avatar.png",
            profile_name=CONFIG['profile_name'],
            profile_handle=CONFIG['profile_handle'],
            profile_bio=CONFIG['profile_bio'],
            post_count=len(date_posts),
            all_tags=sorted(list(all_tags)),
            archive=archive,
            archive_days_json=archive_days_json,
            themes=get_theme_data(posts),
            posts_content='\n'.join(date_posts_html),
            pagination=pagination_data,
            last_updated=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            next_update=next_update_str,
            timestamp=timestamp,
            CONFIG=CONFIG
        )

        date_file_path = date_pages_dir / f"{date_key}.html"
        with open(date_file_path, 'w', encoding='utf-8') as f:
            f.write(date_html)
        
        if i < 5 or i == len(all_dates) - 1:  # 只显示前5个和最后一个
            print(f"  ✓ Generated: {date_file_path.name} ({len(date_posts)} posts)")
        elif i == 5:
            print(f"  ... ({len(all_dates) - 6} more pages)")

    # 4. 生成 RSS
    generate_rss(posts, OUTPUT_DIR, CONFIG)

    # 5. 生成搜索索引
    generate_search_index(posts, OUTPUT_DIR, CONFIG)

    print(f"\n✅ All tasks completed.")
    print(f"🌐 Open in browser: file://{(OUTPUT_DIR / 'index.html').absolute()}")
    print("=" * 60)

def get_post_datetime(post):
    """
    智能获取推文时间，用于排序
    1. 尝试解析 YAML 中的 time 字段
    2. 尝试解析 YAML 中的 date 字段 (兼容)
    3. 尝试从文件名解析 (YYYY-mm-dd-HHMMSS)
    4. 尝试从文件名解析 (YYYY-mm-dd)
    """
    time_str = post.metadata.get('time', '')
    if not time_str:
        time_str = post.metadata.get('date', '')
        
    # 检查时间字符串是否包含小时和分钟（即是否精确到时间）
    has_time = ':' in time_str  # 如果包含冒号，说明有时间信息
    
    # 尝试多种时间格式
    formats = [
        '%Y-%m-%d %H:%M:%S', 
        '%Y-%m-%d %H:%M',
        '%Y-%m-%d %H:%M:%S.%f',
        '%Y-%m-%d'
    ]
    
    for fmt in formats:
        try:
            parsed_time = datetime.strptime(time_str.strip(), fmt)
            # 如果原始时间字符串只包含日期（没有时间），则补充当前时间
            if not has_time and fmt == '%Y-%m-%d':
                # 使用文件的修改时间来获取更准确的时间
                try:
                    file_time = datetime.fromtimestamp(post.filepath.stat().st_mtime)
                    parsed_time = parsed_time.replace(hour=file_time.hour, minute=file_time.minute, second=file_time.second)
                except:
                    # 如果无法获取文件修改时间，则使用当前时间
                    now = datetime.now()
                    parsed_time = parsed_time.replace(hour=now.hour, minute=now.minute, second=now.second)
            return parsed_time
        except ValueError:
            continue
            
    # 如果元数据解析失败，尝试从文件名提取
    # 格式 1: 2026-02-04-001401-auto.md
    try:
        filename = post.filepath.name
        match_full = re.search(r'(\d{4}-\d{2}-\d{2}-\d{6})', filename)
        if match_full:
            return datetime.strptime(match_full.group(1), '%Y-%m-%d-%H%M%S')
            
        # 格式 2: 2026-02-04-xxxx.md
        match_date = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
        if match_date:
            # 使用文件修改时间补充精确时间
            try:
                file_time = datetime.fromtimestamp(post.filepath.stat().st_mtime)
                base_date = datetime.strptime(match_date.group(1), '%Y-%m-%d')
                return base_date.replace(hour=file_time.hour, minute=file_time.minute, second=file_time.second)
            except:
                # 如果无法获取文件修改时间，则使用当前时间
                base_date = datetime.strptime(match_date.group(1), '%Y-%m-%d')
                now = datetime.now()
                return base_date.replace(hour=now.hour, minute=now.minute, second=now.second)
    except:
        pass
    
    # 最后的保底：文件修改时间
    try:
        return datetime.fromtimestamp(post.filepath.stat().st_mtime)
    except:
        pass
        
    # 真正的最后保底
    return datetime(1970, 1, 1)

if __name__ == "__main__":
    render_posts()
