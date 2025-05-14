import feedparser
import os
import re
import requests
from bs4 import BeautifulSoup

# 썸네일 저장 경로
save_dir = '/home/sftpuser/www/blog_thumbs/'
os.makedirs(save_dir, exist_ok=True)

# 네이버 블로그 RSS URL
feed_url = 'https://rss.blog.naver.com/goldenrabbit7377.xml'
feed = feedparser.parse(feed_url)

for entry in feed.entries[:10]:  # 최신 10개 가져오기
    # logNo 추출
    match = re.search(r'logNo=(\d+)', entry.link)
    if not match:
        print(f"❌ logNo 추출 실패: {entry.link}")
        continue

    log_no = match.group(1)
    image_filename = f"{log_no}.jpg"
    save_path = os.path.join(save_dir, image_filename)

    # entry.summary에서 <img> 추출
    soup = BeautifulSoup(entry.summary, 'html.parser')
    img_tag = soup.find('img')

    if img_tag and 'src' in img_tag.attrs:
        img_url = img_tag['src']
        print(f"✅ 이미지 저장 중: {image_filename} ← {img_url}")

        try:
            img_data = requests.get(img_url, timeout=5)
            if img_data.status_code == 200:
                with open(save_path, 'wb') as f:
                    f.write(img_data.content)
            else:
                print(f"❌ 다운로드 실패: {img_url}")
        except Exception as e:
            print(f"❌ 예외 발생: {e}")
    else:
        print(f"❌ 이미지 없음: {entry.title}")
