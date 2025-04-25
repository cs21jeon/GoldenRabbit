import os
import requests
import mimetypes
import urllib.request
from urllib.parse import urlparse
from pathlib import Path
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = 'appGSg5QfDNKgFf73'
TABLE_ID = 'tblnR438TK52Gr0HB'
VIEW_ID = 'viweFlrK1v4aXqYH8'
OUTPUT_DIR = '/home/sftpuser/www/images/recomm_building/'

headers = {
    "Authorization": f"Bearer {AIRTABLE_API_KEY}"
}

def fetch_airtable_images():
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}?view={VIEW_ID}"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print("Airtable API 요청 실패:", response.status_code)
        return

    data = response.json()
    records = data.get('records', [])

    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    for i, record in enumerate(records):
        fields = record.get("fields", {})
        photos = fields.get("대표사진") or []
        if isinstance(photos, str):
            try:
                import json
                photos = json.loads(photos)
            except Exception as e:
                print(f"JSON 파싱 실패: {e}")
                continue

        if isinstance(photos, list) and photos:
            photo_url = photos[0]['url']
            
            # URL에서 콘텐츠 타입 확인
            try:
                # 파일 확장자 결정 (URL에서 직접 추출하지 않고 고정 확장자나 콘텐츠 타입 활용)
                file_ext = ".jpg"  # 기본 확장자 설정
                
                # 선택적: 콘텐츠 타입을 확인하여 확장자 결정
                response = requests.head(photo_url)
                if 'content-type' in response.headers:
                    content_type = response.headers['content-type']
                    ext = mimetypes.guess_extension(content_type)
                    if ext:
                        file_ext = ext
                
                # 간단한 숫자 기반 파일명 사용
                local_filename = f"recomm_{i + 1}{file_ext}"
                local_path = os.path.join(OUTPUT_DIR, local_filename)
                
                # 직접 파일 다운로드
                response = requests.get(photo_url)
                if response.status_code == 200:
                    with open(local_path, 'wb') as f:
                        f.write(response.content)
                    print(f"{local_filename} 저장 완료")
                else:
                    print(f"{photo_url} 다운로드 실패: HTTP {response.status_code}")
            except Exception as e:
                print(f"{photo_url} 다운로드 실패: {e}")
if __name__ == "__main__":
    fetch_airtable_images()
