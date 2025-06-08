import os
from dotenv import load_dotenv
import json
import time
import requests
import logging
import traceback
import hashlib
from urllib.parse import urlparse
from pathlib import Path
from datetime import datetime
import schedule

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

# 로깅 설정
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    filename='/home/sftpuser/logs/airtable_backup.log')
logger = logging.getLogger('airtable_backup')

# 백업 디렉토리 설정
BACKUP_DIR = '/home/sftpuser/www/airtable_backup'
os.makedirs(BACKUP_DIR, exist_ok=True)

# 에어테이블 설정
AIRTABLE_KEY = os.environ.get("AIRTABLE_API_KEY")
BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "appGSg5QfDNKgFf73")
TABLE_ID = os.environ.get("AIRTABLE_TABLE_ID", "tblnR438TK52Gr0HB")

# 각 뷰 설정
VIEWS = {
    'all': {
        'id': os.environ.get("AIRTABLE_ALL_VIEW_ID", "viwyV15T4ihMpbDbr"),
        'filename': 'all_properties.json'
    },
    'reconstruction': {
        'id': 'viwzEVzrr47fCbDNU',  # 재건축용 토지
        'filename': 'reconstruction_properties.json'
    },
    'high_yield': {
        'id': 'viwxS4dKAcQWmB0Be',  # 고수익률 건물
        'filename': 'high_yield_properties.json'
    },
    'low_cost': {
        'id': 'viwUKnawSP8SkV9Sx',  # 저가단독주택
        'filename': 'low_cost_properties.json'
    }
}

def backup_airtable_data():
    """에어테이블의 모든 뷰 데이터를 백업"""
    start_time = time.time()
    logger.info(f"====== 에어테이블 백업 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ======")
    
    backup_date = datetime.now().strftime('%Y-%m-%d')
    daily_backup_dir = os.path.join(BACKUP_DIR, backup_date)
    os.makedirs(daily_backup_dir, exist_ok=True)
    
    if not AIRTABLE_KEY:
        logger.error("AIRTABLE_API_KEY가 설정되지 않았습니다.")
        return False
    
    headers = {
        "Authorization": f"Bearer {AIRTABLE_KEY}"
    }
    
    total_records = 0
    success_count = 0
    all_records = []  # 모든 레코드 저장 (이미지 처리용)
    
    # 각 뷰별로 데이터 백업
    for view_name, view_info in VIEWS.items():
        view_id = view_info['id']
        filename = view_info['filename']
        
        logger.info(f"'{view_name}' 뷰 백업 시작 (ID: {view_id})")
        
        try:
            # 모든 레코드 가져오기 (페이지네이션 처리)
            view_records = []  # 각 뷰의 레코드를 저장할 변수
            offset = None
            page_count = 0
            
            while True:
                url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}"
                params = {'view': view_id}
                
                if offset:
                    params['offset'] = offset
                
                response = requests.get(url, headers=headers, params=params)
                
                if response.status_code != 200:
                    logger.error(f"API 요청 실패: {response.status_code} - {response.text}")
                    break
                
                data = response.json()
                records = data.get('records', [])
                view_records.extend(records)  # 각 뷰의 레코드 수집
                
                # 전체 레코드 목록에도 추가 (이미지 처리용)
                all_records.extend(records)
                
                logger.info(f"  페이지 {page_count + 1}: {len(records)}개 레코드 로드")
                page_count += 1
                
                # 다음 페이지 확인
                offset = data.get('offset')
                if not offset:
                    break
            
            # 백업 파일 저장
            backup_path = os.path.join(daily_backup_dir, filename)
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(view_records, f, ensure_ascii=False, indent=2)
            
            # 최신 데이터를 가리키는 심볼릭 링크 생성/업데이트
            latest_path = os.path.join(BACKUP_DIR, 'latest')
            os.makedirs(latest_path, exist_ok=True)
            latest_file_path = os.path.join(latest_path, filename)
            
            # 최신 파일 링크 대신 실제 복사
            with open(latest_file_path, 'w', encoding='utf-8') as f:
                json.dump(view_records, f, ensure_ascii=False, indent=2)
            
            logger.info(f"  '{view_name}' 뷰 백업 완료: {len(view_records)}개 레코드")
            logger.info(f"  백업 파일: {backup_path}")
            logger.info(f"  최신 파일: {latest_file_path}")
            
            total_records += len(view_records)
            success_count += 1
            
        except Exception as e:
            logger.error(f"'{view_name}' 뷰 백업 실패: {str(e)}")
            logger.error(traceback.format_exc())
    
    # 이미지 백업 (전체 레코드에서 이미지 추출)
    image_stats = backup_property_images(all_records, daily_backup_dir)

    # 백업 메타데이터 저장
    metadata = {
        'backup_date': backup_date,
        'total_records': total_records,
        'views_backed_up': success_count,
        'total_views': len(VIEWS),
        'timestamp': datetime.now().isoformat(),
        'image_stats': image_stats
    }
    
    metadata_path = os.path.join(daily_backup_dir, 'metadata.json')
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    # 최신 메타데이터 업데이트
    latest_metadata_path = os.path.join(BACKUP_DIR, 'latest', 'metadata.json')
    with open(latest_metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    elapsed_time = time.time() - start_time
    logger.info(f"====== 에어테이블 백업 완료: 총 {total_records}개 레코드, {elapsed_time:.2f}초 소요 ======")
    
    # 오래된 백업 정리 (옵션)
    cleanup_old_backups(30)  # 30일 이상 된 백업 삭제
    
    return success_count == len(VIEWS)

def backup_property_images(records, backup_dir):
    """매물 이미지를 백업하는 함수"""
    # 이미지 저장 디렉토리
    image_dir = os.path.join(backup_dir, 'images')
    os.makedirs(image_dir, exist_ok=True)
    
    # 이미지 메타데이터 파일 경로
    metadata_path = os.path.join(image_dir, 'image_metadata.json')
    
    # 기존 이미지 메타데이터 로드
    image_metadata = {}
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                image_metadata = json.load(f)
        except:
            logger.error("이미지 메타데이터 로드 실패, 새로 생성합니다.")
    
    new_images = 0
    updated_images = 0
    skipped_images = 0
    
    for record in records:
        record_id = record.get('id')
        fields = record.get('fields', {})
        
        # 이미지 URL 목록 수집
        image_urls = []
        
        # 대표사진 필드 처리
        if isinstance(fields.get('대표사진'), list) and fields['대표사진']:
            for attachment in fields['대표사진']:
                if attachment.get('url'):
                    image_urls.append({
                        'url': attachment['url'],
                        'filename': attachment.get('filename', ''),
                        'type': 'representative'
                    })
        
        # 사진링크 필드 처리
        if fields.get('사진링크'):
            photo_links = fields['사진링크'].split(',')
            for i, link in enumerate(photo_links):
                link = link.strip()
                if link:
                    image_urls.append({
                        'url': link,
                        'filename': f'photo_{i+1}',
                        'type': 'link'
                    })
        
        # 레코드에 이미지가 없으면 다음으로
        if not image_urls:
            continue
        
        # 레코드별 이미지 디렉토리
        record_image_dir = os.path.join(image_dir, record_id)
        os.makedirs(record_image_dir, exist_ok=True)
        
        # 이미지 다운로드 및 처리
        for img_info in image_urls:
            url = img_info['url']
            img_type = img_info['type']
            
            # URL에서 파일명 추출 또는 생성
            parsed_url = urlparse(url)
            path_parts = Path(parsed_url.path).parts
            filename = img_info['filename'] or path_parts[-1]
            
            # 확장자 확인 및 수정
            if '.' not in filename:
                filename += '.jpg'  # 기본 확장자
            
            # 이미지 파일 경로
            image_path = os.path.join(record_image_dir, filename)
            
            # 이미지 URL 해시 생성 (변경 감지용)
            url_hash = hashlib.md5(url.encode()).hexdigest()
            
            # 메타데이터에서 이전 해시 확인
            prev_hash = image_metadata.get(f"{record_id}_{filename}")
            
            # 이미지가 이미 존재하고 해시가 같으면 스킵
            if os.path.exists(image_path) and prev_hash == url_hash:
                skipped_images += 1
                continue
            
            try:
                # 이미지 다운로드
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    with open(image_path, 'wb') as f:
                        f.write(response.content)
                    
                    # 메타데이터 업데이트
                    image_metadata[f"{record_id}_{filename}"] = url_hash
                    
                    if prev_hash:
                        updated_images += 1
                    else:
                        new_images += 1
                    
                    logger.info(f"이미지 저장 완료: {filename} ({img_type})")
                else:
                    logger.warning(f"이미지 다운로드 실패: {url}, 상태 코드: {response.status_code}")
            except Exception as e:
                logger.error(f"이미지 다운로드 중 오류: {url}, 오류: {str(e)}")
    
    # 메타데이터 저장
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(image_metadata, f, ensure_ascii=False, indent=2)
    
    logger.info(f"이미지 백업 완료: 새 이미지 {new_images}개, 업데이트 {updated_images}개, 스킵 {skipped_images}개")
    
    return {
        'new_images': new_images,
        'updated_images': updated_images,
        'skipped_images': skipped_images,
        'total_processed': new_images + updated_images + skipped_images
    }

def cleanup_old_backups(days_to_keep):
    """오래된 백업 파일 정리"""
    try:
        import shutil
        from datetime import datetime, timedelta
        
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        
        for folder_name in os.listdir(BACKUP_DIR):
            # 'latest' 폴더와 메타데이터 파일은 건너뜀
            if folder_name == 'latest' or not os.path.isdir(os.path.join(BACKUP_DIR, folder_name)):
                continue
            
            try:
                # 폴더명이 날짜 형식(YYYY-MM-DD)인지 확인
                folder_date = datetime.strptime(folder_name, '%Y-%m-%d')
                
                # 기준일보다 오래된 경우 삭제
                if folder_date < cutoff_date:
                    folder_path = os.path.join(BACKUP_DIR, folder_name)
                    shutil.rmtree(folder_path)
                    logger.info(f"오래된 백업 삭제: {folder_name}")
            except ValueError:
                # 날짜 형식이 아닌 폴더는 무시
                continue
    except Exception as e:
        logger.error(f"백업 정리 중 오류 발생: {str(e)}")

"""
def run_scheduler():
    schedule.every().day.at("03:00").do(backup_airtable_data)
    
    logger.info("스케줄러 시작됨 - 매일 03:00에 백업 실행")
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # 1분마다 스케줄 확인
"""
        
if __name__ == "__main__":
    # 시작 시 즉시 한 번 백업 실행
    backup_airtable_data()
"""    
    # 스케줄러 실행
    run_scheduler()
"""