import os
import requests
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
            except:
                continue
        if isinstance(photos, list) and photos:
            photo_url = photos[0]['url']
            file_ext = photo_url.split('.')[-1].split('?')[0]
            local_filename = f"recomm_{i + 1}.{file_ext}"
            local_path = os.path.join(OUTPUT_DIR, local_filename)

            # 이미지 다운로드
            try:
                img_data = requests.get(photo_url).content
                with open(local_path, 'wb') as f:
                    f.write(img_data)
                print(f"{local_filename} 저장 완료")
            except Exception as e:
                print(f"{photo_url} 다운로드 실패: {e}")

if __name__ == "__main__":
    fetch_airtable_images()
