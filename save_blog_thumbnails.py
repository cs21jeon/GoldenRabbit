import feedparser
import os
import re
import requests
from bs4 import BeautifulSoup

save_dir = '/home/sftpuser/www/blog_thumbs/'
os.makedirs(save_dir, exist_ok=True)

feed_url = 'https://rss.blog.naver.com/goldenrabbit7377.xml'
feed = feedparser.parse(feed_url)

# 네이버 이미지 다운로드를 위한 헤더 설정
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Referer': 'https://blog.naver.com/'
}

for entry in feed.entries[:10]:
    # ✅ 슬래시 뒤 숫자 추출
    match = re.search(r'/(\d+)', entry.link)
    if not match:
        print(f"❌ logNo 추출 실패: {entry.link}")
        continue

    log_no = match.group(1)
    image_filename = f"{log_no}.jpg"
    save_path = os.path.join(save_dir, image_filename)
    
    # 이미 존재하는 경우 스킵
    if os.path.exists(save_path):
        print(f"⏭️  이미 존재: {image_filename}")
        continue

    soup = BeautifulSoup(entry.summary, 'html.parser')
    img_tag = soup.find('img')

    if img_tag and 'src' in img_tag.attrs:
        img_url = img_tag['src']
        print(f"✅ 이미지 저장 중: {image_filename} ← {img_url}")

        try:
            img_data = requests.get(img_url, headers=headers, timeout=10)
            if img_data.status_code == 200:
                with open(save_path, 'wb') as f:
                    f.write(img_data.content)
                print(f"✅ 저장 완료: {image_filename}")
            else:
                print(f"❌ 다운로드 실패 ({img_data.status_code}): {img_url}")
        except Exception as e:
            print(f"❌ 예외 발생: {e}")
    else:
        print(f"❌ 이미지 없음: {entry.title}")