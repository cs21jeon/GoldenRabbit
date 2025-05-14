import os
import feedparser
from bs4 import BeautifulSoup
import requests
from urllib.parse import urlparse, parse_qs

feed_url = "https://rss.blog.naver.com/goldenrabbit7377.xml"
save_dir = "/home/sftpuser/www/blog_thumbs"
os.makedirs(save_dir, exist_ok=True)

def extract_log_no(link):
    parsed = urlparse(link)
    return parse_qs(parsed.query).get('logNo', [None])[0]

def extract_image_url(summary):
    soup = BeautifulSoup(summary, 'html.parser')
    img = soup.find('img')
    return img['src'] if img and 'src' in img.attrs else None

feed = feedparser.parse(feed_url)

for entry in feed.entries[:10]:
    log_no = extract_log_no(entry.link)
    if not log_no:
        continue

    image_url = extract_image_url(entry.summary)
    if not image_url:
        continue

    file_path = os.path.join(save_dir, f"{log_no}.jpg")
    if os.path.exists(file_path):
        continue  # 이미 저장된 경우 건너뜀

    try:
        r = requests.get(image_url, timeout=10)
        if r.status_code == 200:
            with open(file_path, 'wb') as f:
                f.write(r.content)
            print(f"✅ Saved: {file_path}")
        else:
            print(f"❌ Failed ({r.status_code}): {image_url}")
    except Exception as e:
        print(f"⚠️ Error fetching {image_url}: {e}")
