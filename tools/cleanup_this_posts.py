import os
from pathlib import Path

posts_dir = Path("/home/tetsuya/mini-twitter/posts")
deleted_count = 0

def should_delete(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Skip frontmatter
        in_frontmatter = False
        dash_count = 0
        body_start_line = -1
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == '---':
                dash_count += 1
                if dash_count == 2:
                    body_start_line = i + 1
                    break
        
        if body_start_line != -1:
            # Look for the first non-empty line in the body
            for i in range(body_start_line, len(lines)):
                line = lines[i].strip()
                if line:
                    if line.startswith("这") or line.startswith("這"):
                        return True
                    break # Found the first line, doesn't start with '这'
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
    return False

files_to_delete = []
for root, dirs, files in os.walk(posts_dir):
    for file in files:
        if file.endswith(".md"):
            filepath = Path(root) / file
            if should_delete(filepath):
                files_to_delete.append(filepath)

print(f"Found {len(files_to_delete)} files to delete.")
for f in files_to_delete:
    print(f"Deleting: {f}")
    f.unlink()
    deleted_count += 1

print(f"Total deleted: {deleted_count}")
