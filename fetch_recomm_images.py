import os
import requests
import mimetypes
import urllib.request
from urllib.parse import urlparse
from pathlib import Path
from dotenv import load_dotenv
import json

# 환경 변수 로드
load_dotenv()

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = 'appGSg5QfDNKgFf73'
TABLE_ID = 'tblnR438TK52Gr0HB'

# 카테고리별 뷰 설정
CATEGORY_VIEWS = {
    'land': {
        'view_id': 'viwzEVzrr47fCbDNU',
        'name': '재건축용 토지',
        'filename': 'category_land.jpg'
    },
    'building': {
        'view_id': 'viwxS4dKAcQWmB0Be', 
        'name': '고수익률 건물',
        'filename': 'category_building.jpg'
    },
    'house': {
        'view_id': 'viwUKnawSP8SkV9Sx',
        'name': '저가단독주택',
        'filename': 'category_house.jpg'
    }
}

OUTPUT_DIR = '/home/sftpuser/www/images/'
DEFAULT_IMAGE_PATH = '/home/sftpuser/www/images/default-thumb.jpg'

headers = {
    "Authorization": f"Bearer {AIRTABLE_API_KEY}"
}

def fetch_representative_property(view_id):
    """특정 뷰에서 '대표' 필드가 체크된 매물 조회"""
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}"
    
    params = {
        'view': view_id,
        'filterByFormula': '{대표} = TRUE()',  # '대표' 필드가 체크된 항목만
        'maxRecords': 1,  # 하나만 가져오기
        'sort[0][field]': '매가(만원)',  # 매가 기준 정렬
        'sort[0][direction]': 'asc'
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code != 200:
            print(f"뷰 {view_id} API 요청 실패: {response.status_code}")
            print(f"응답: {response.text}")
            return None
            
        data = response.json()
        records = data.get('records', [])
        
        if not records:
            print(f"뷰 {view_id}에서 대표 매물을 찾을 수 없습니다.")
            return None
            
        return records[0]
        
    except Exception as e:
        print(f"뷰 {view_id} 조회 중 오류: {e}")
        return None

def download_image(photo_url, local_path):
    """이미지 다운로드"""
    try:
        # 파일 확장자 결정
        file_ext = ".jpg"  # 기본 확장자
        
        # 콘텐츠 타입을 확인하여 확장자 결정 (선택적)
        try:
            response = requests.head(photo_url, timeout=10)
            if 'content-type' in response.headers:
                content_type = response.headers['content-type']
                ext = mimetypes.guess_extension(content_type)
                if ext:
                    file_ext = ext
        except:
            pass  # HEAD 요청 실패 시 기본 확장자 사용
        
        # 확장자가 없으면 추가
        if not local_path.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
            local_path = local_path.rsplit('.', 1)[0] + file_ext
        
        # 실제 이미지 다운로드
        response = requests.get(photo_url, timeout=30)
        if response.status_code == 200:
            with open(local_path, 'wb') as f:
                f.write(response.content)
            print(f"✅ {os.path.basename(local_path)} 저장 완료")
            return True
        else:
            print(f"❌ {photo_url} 다운로드 실패: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ {photo_url} 다운로드 실패: {e}")
        return False

def copy_default_image(target_path):
    """기본 이미지를 대상 경로로 복사"""
    try:
        if os.path.exists(DEFAULT_IMAGE_PATH):
            import shutil
            shutil.copy2(DEFAULT_IMAGE_PATH, target_path)
            print(f"📋 기본 이미지를 {os.path.basename(target_path)}로 복사")
            return True
        else:
            print(f"⚠️ 기본 이미지가 없습니다: {DEFAULT_IMAGE_PATH}")
            return False
    except Exception as e:
        print(f"❌ 기본 이미지 복사 실패: {e}")
        return False

def fetch_category_images():
    """카테고리별 대표 매물 이미지 가져오기"""
    print("🚀 카테고리별 대표 매물 이미지 다운로드 시작")
    print(f"📁 출력 디렉토리: {OUTPUT_DIR}")
    
    # 출력 디렉토리 생성
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    
    success_count = 0
    total_count = len(CATEGORY_VIEWS)
    
    for category_key, config in CATEGORY_VIEWS.items():
        view_id = config['view_id']
        category_name = config['name']
        filename = config['filename']
        local_path = os.path.join(OUTPUT_DIR, filename)
        
        print(f"\n📂 처리 중: {category_name} (뷰 ID: {view_id})")
        
        # 대표 매물 조회
        record = fetch_representative_property(view_id)
        
        if not record:
            print(f"⚠️ {category_name}: 대표 매물이 없어 기본 이미지 사용")
            if copy_default_image(local_path):
                success_count += 1
            continue
        
        # 매물 정보 출력
        fields = record.get("fields", {})
        address = fields.get("지번 주소", "주소 없음")
        print(f"📍 대표 매물: {address}")
        
        # 대표사진 처리
        photos = fields.get("대표사진")
        photo_url = None
        
        if photos:
            if isinstance(photos, str):
                try:
                    photos = json.loads(photos)
                except Exception as e:
                    print(f"⚠️ JSON 파싱 실패: {e}")
                    photos = None
            
            if isinstance(photos, list) and photos:
                photo_url = photos[0].get('url')
            elif isinstance(photos, dict):
                photo_url = photos.get('url')
        
        # 이미지 다운로드 시도
        if photo_url:
            print(f"🔗 이미지 URL: {photo_url}")
            if download_image(photo_url, local_path):
                success_count += 1
            else:
                print(f"⚠️ 다운로드 실패로 기본 이미지 사용")
                if copy_default_image(local_path):
                    success_count += 1
        else:
            print(f"⚠️ {category_name}: 대표사진이 없어 기본 이미지 사용")
            if copy_default_image(local_path):
                success_count += 1
    
    print(f"\n🎯 완료: {success_count}/{total_count} 개의 카테고리 이미지 처리")
    
    # 결과 요약
    print("\n📊 처리 결과:")
    for category_key, config in CATEGORY_VIEWS.items():
        filename = config['filename']
        local_path = os.path.join(OUTPUT_DIR, filename)
        if os.path.exists(local_path):
            file_size = os.path.getsize(local_path)
            print(f"✅ {config['name']}: {filename} ({file_size:,} bytes)")
        else:
            print(f"❌ {config['name']}: {filename} (파일 없음)")

def test_airtable_connection():
    """에어테이블 연결 테스트"""
    print("🔍 에어테이블 연결 테스트 중...")
    
    if not AIRTABLE_API_KEY:
        print("❌ AIRTABLE_API_KEY 환경 변수가 설정되지 않았습니다.")
        return False
    
    # 간단한 테스트 요청
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}"
    params = {'maxRecords': 1}
    
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            print("✅ 에어테이블 연결 성공")
            return True
        else:
            print(f"❌ 에어테이블 연결 실패: {response.status_code}")
            print(f"응답: {response.text}")
            return False
    except Exception as e:
        print(f"❌ 에어테이블 연결 오류: {e}")
        return False

def main():
    """메인 실행 함수"""
    print("=" * 60)
    print("🏢 금토끼부동산 카테고리별 대표 매물 이미지 다운로더")
    print("=" * 60)
    
    # 연결 테스트
    if not test_airtable_connection():
        print("❌ 에어테이블 연결에 실패했습니다. 프로그램을 종료합니다.")
        return
    
    # 기본 이미지 존재 확인
    if not os.path.exists(DEFAULT_IMAGE_PATH):
        print(f"⚠️ 기본 이미지를 찾을 수 없습니다: {DEFAULT_IMAGE_PATH}")
        print("기본 이미지가 없어도 계속 진행합니다.")
    else:
        print(f"✅ 기본 이미지 확인: {DEFAULT_IMAGE_PATH}")
    
    # 카테고리 이미지 다운로드
    fetch_category_images()
    
    print("\n🎉 작업 완료!")

if __name__ == "__main__":
    main()