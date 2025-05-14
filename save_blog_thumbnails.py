import os
import re
import requests
import feedparser
from urllib.parse import urlparse
from datetime import datetime

# 저장 경로
SAVE_DIR = "/home/sftpuser/www/blog_thumbnails/"
RSS_FEED_URL = "https://rss.blog.naver.com/goldenrabbit7377.xml"

# 디렉토리 생성
os.makedirs(SAVE_DIR, exist_ok=True)

# RSS 파싱
feed = feedparser.parse(RSS_FEED_URL)
print(f"{len(feed.entries)}개의 글을 찾았습니다.")

def extract_image_url(summary):
    """ summary에서 이미지 URL 추출 """
    match = re.search(r'<img[^>]+src="([^"]+)"', summary)
    return match.group(1) if match else None

def sanitize_filename(url):
    """ URL에서 파일명 추출 후 안전하게 변경 """
    parsed = urlparse(url)
    filename = os.path.basename(parsed.path)
    filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    return filename

# 썸네일 저장
for i, entry in enumerate(feed.entries[:10]):
    image_url = extract_image_url(entry.summary)
    if not image_url:
        print(f"[{i}] 이미지 없음 - {entry.title}")
        continue

    filename = sanitize_filename(image_url)
    save_path = os.path.join(SAVE_DIR, filename)

    if os.path.exists(save_path):
        print(f"[{i}] 이미 존재함 - {filename}")
        continue

    try:
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()
        with open(save_path, 'wb') as f:
            f.write(response.content)
        print(f"[{i}] 저장 완료 - {filename}")
    except Exception as e:
        print(f"[{i}] 실패 - {filename} ({e})")
