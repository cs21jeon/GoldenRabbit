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
import shutil
import schedule

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

# 로깅 설정
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    filename='/home/sftpuser/logs/airtable_backup.log')
logger = logging.getLogger('airtable_backup')

# 백업 디렉토리 설정 - 단일 폴더 사용
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

# 🆕 완전 새로고침 모드 설정
FULL_REFRESH_MODE = True  # True로 설정하면 매번 완전 새로고침

def save_backup_data(data, filename):
    """백업 데이터 저장"""
    file_path = os.path.join(BACKUP_DIR, filename)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"데이터 저장 완료: {filename} ({len(data)}개 레코드)")

def cleanup_image_directory():
    """이미지 디렉토리 완전 정리 (새로고침 모드에서만)"""
    if not FULL_REFRESH_MODE:
        return
    
    image_dir = os.path.join(BACKUP_DIR, 'images')
    
    if os.path.exists(image_dir):
        try:
            # 기존 이미지 폴더 완전 삭제
            shutil.rmtree(image_dir)
            logger.info("🗑️ 기존 이미지 폴더 완전 삭제")
        except Exception as e:
            logger.error(f"이미지 폴더 삭제 실패: {e}")
    
    # 새 이미지 폴더 생성
    os.makedirs(image_dir, exist_ok=True)
    logger.info("📁 새 이미지 폴더 생성")

def backup_airtable_data():
    """에어테이블의 모든 뷰 데이터를 백업 (완전 새로고침 방식)"""
    start_time = time.time()
    
    backup_mode = "완전 새로고침" if FULL_REFRESH_MODE else "증분 업데이트"
    logger.info(f"====== 에어테이블 백업 시작 ({backup_mode}): {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ======")
    
    if not AIRTABLE_KEY:
        logger.error("AIRTABLE_API_KEY가 설정되지 않았습니다.")
        return False
    
    headers = {
        "Authorization": f"Bearer {AIRTABLE_KEY}"
    }
    
    total_records = 0
    success_count = 0
    all_records = []  # 모든 레코드 저장 (이미지 처리용)
    
    # 🆕 완전 새로고침 모드에서 이미지 폴더 정리
    if FULL_REFRESH_MODE:
        cleanup_image_directory()
    
    # 각 뷰별로 데이터 백업
    for view_name, view_info in VIEWS.items():
        view_id = view_info['id']
        filename = view_info['filename']
        
        logger.info(f"'{view_name}' 뷰 백업 시작 (ID: {view_id})")
        
        try:
            # 모든 레코드 가져오기 (페이지네이션 처리)
            view_records = []
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
                view_records.extend(records)
                
                # 전체 레코드 목록에도 추가 (이미지 처리용, all 뷰에서만)
                if view_name == 'all':
                    all_records.extend(records)
                
                logger.info(f"  페이지 {page_count + 1}: {len(records)}개 레코드 로드")
                page_count += 1
                
                # 다음 페이지 확인
                offset = data.get('offset')
                if not offset:
                    break
            
            # 🆕 완전 새로고침 모드: 항상 저장
            if FULL_REFRESH_MODE:
                save_backup_data(view_records, filename)
                logger.info(f"✅ '{view_name}' 뷰 완전 새로고침 완료: {len(view_records)}개 레코드")
            else:
                # 기존 증분 업데이트 로직은 여기에 그대로 유지
                # (필요시 기존 compare_and_update_data 함수 사용)
                save_backup_data(view_records, filename)
            
            total_records += len(view_records)
            success_count += 1
            
        except Exception as e:
            logger.error(f"'{view_name}' 뷰 백업 실패: {str(e)}")
            logger.error(traceback.format_exc())
    
    # 🆕 이미지 백업 (완전 새로고침 모드에서는 항상 실행)
    image_stats = {"new_images": 0, "updated_images": 0, "skipped_images": 0, "total_processed": 0}
    if all_records:  # FULL_REFRESH_MODE에서는 updated_views 조건 제거
        logger.info("이미지 백업 시작")
        image_stats = backup_property_images_full_refresh(all_records)
    else:
        logger.info("백업할 레코드가 없습니다.")

    # 백업 메타데이터 저장
    metadata = {
        'last_backup_date': datetime.now().strftime('%Y-%m-%d'),
        'last_backup_time': datetime.now().isoformat(),
        'backup_mode': backup_mode,
        'full_refresh_enabled': FULL_REFRESH_MODE,
        'total_records': total_records,
        'views_processed': success_count,
        'total_views': len(VIEWS),
        'image_stats': image_stats,
        'backup_type': 'full_refresh' if FULL_REFRESH_MODE else 'incremental'
    }
    
    metadata_path = os.path.join(BACKUP_DIR, 'metadata.json')
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    elapsed_time = time.time() - start_time
    
    logger.info(f"====== 백업 완료 ({backup_mode}): 총 {total_records}개 레코드, {elapsed_time:.2f}초 소요 ======")
    
    return success_count == len(VIEWS)

def backup_property_images_full_refresh(records):
    """매물 이미지를 백업하는 함수 (완전 새로고침 버전)"""
    # 이미지 저장 디렉토리
    image_dir = os.path.join(BACKUP_DIR, 'images')
    os.makedirs(image_dir, exist_ok=True)
    
    # 이미지 메타데이터 파일 경로
    metadata_path = os.path.join(image_dir, 'image_metadata.json')
    
    # 🆕 완전 새로고침 모드에서는 메타데이터도 새로 시작
    image_metadata = {
        'backup_mode': 'full_refresh',
        'backup_date': datetime.now().isoformat(),
        'total_records_processed': 0
    }
    
    new_images = 0
    error_images = 0
    
    def get_best_image_from_record(record):
        """레코드에서 가장 좋은 이미지 1개 선택"""
        fields = record.get('fields', {})
        
        # 우선순위 1: 대표사진 필드 (첫 번째 이미지)
        if isinstance(fields.get('대표사진'), list) and fields['대표사진']:
            attachment = fields['대표사진'][0]  # 첫 번째만
            if attachment.get('url'):
                return {
                    'url': attachment['url'],
                    'filename': attachment.get('filename', 'representative.jpg'),
                    'type': 'representative'
                }
        
        # 우선순위 2: 사진링크 필드 (첫 번째 링크)
        if fields.get('사진링크'):
            photo_links = fields['사진링크'].split(',')
            for link in photo_links:
                link = link.strip()
                if link and link.startswith('http'):
                    return {
                        'url': link,
                        'filename': 'photo_link.jpg',
                        'type': 'link'
                    }
        
        return None
    
    for record in records:
        record_id = record.get('id')
        
        if not record_id:
            continue
        
        # 레코드별 이미지 디렉토리
        record_image_dir = os.path.join(image_dir, record_id)
        os.makedirs(record_image_dir, exist_ok=True)
        
        # 가장 좋은 이미지 1개 선택
        best_image = get_best_image_from_record(record)
        
        if not best_image:
            continue
        
        url = best_image['url']
        img_type = best_image['type']
        
        try:
            # 파일명 처리
            original_filename = best_image['filename']
            
            # 확장자 확인
            if '.' not in original_filename:
                original_filename += '.jpg'
            
            # 파일명 정리 (특수문자 제거)
            filename = "".join(c for c in original_filename if c.isalnum() or c in '.-_').strip()
            if not filename or filename == '.jpg':
                filename = f"image_{int(time.time())}.jpg"
            
            # 이미지 파일 경로
            image_path = os.path.join(record_image_dir, filename)
            
            # 🆕 항상 새로 다운로드 (완전 새로고침)
            logger.info(f"이미지 다운로드: {record_id} -> {filename}")
            response = requests.get(url, timeout=30, stream=True)
            
            if response.status_code == 200:
                # 임시 파일로 먼저 다운로드
                temp_path = image_path + '.tmp'
                
                with open(temp_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                # 파일 크기 확인 (최소 1KB)
                if os.path.getsize(temp_path) > 1000:
                    # 성공적으로 다운로드되면 정식 파일로 이동
                    os.rename(temp_path, image_path)
                    
                    # 메타데이터 업데이트
                    image_metadata[f"{record_id}_filename"] = filename
                    image_metadata[f"{record_id}_type"] = img_type
                    image_metadata[f"{record_id}_url"] = url
                    
                    new_images += 1
                    logger.info(f"✅ 이미지 저장: {filename} ({img_type})")
                else:
                    # 파일이 너무 작으면 삭제
                    os.remove(temp_path)
                    logger.warning(f"파일 크기가 너무 작음: {url}")
                    error_images += 1
            else:
                logger.warning(f"이미지 다운로드 실패: {url}, 상태 코드: {response.status_code}")
                error_images += 1
                
        except Exception as e:
            logger.error(f"이미지 처리 중 오류: {url}, 오류: {str(e)}")
            error_images += 1
    
    # 메타데이터 저장
    try:
        image_metadata['total_records_processed'] = len(records)
        image_metadata['stats'] = {
            'new_images': new_images,
            'error_images': error_images,
            'success_rate': f"{(new_images / (new_images + error_images) * 100):.1f}%" if (new_images + error_images) > 0 else "0%"
        }
        
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(image_metadata, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"이미지 메타데이터 저장 실패: {str(e)}")
    
    logger.info(f"🎉 이미지 백업 완료 (완전 새로고침)!")
    logger.info(f"   - 새 이미지: {new_images}개")
    logger.info(f"   - 오류: {error_images}개")
    logger.info(f"   - 성공률: {(new_images / (new_images + error_images) * 100):.1f}%" if (new_images + error_images) > 0 else "0%")
    
    return {
        'new_images': new_images,
        'updated_images': 0,  # 완전 새로고침에서는 모두 새 이미지
        'skipped_images': 0,
        'error_images': error_images,
        'total_processed': new_images + error_images,
        'full_refresh_mode': True
    }

def cleanup_old_backups():
    """오래된 백업 폴더 정리 (날짜 형식 폴더들만)"""
    try:
        removed_count = 0
        for folder_name in os.listdir(BACKUP_DIR):
            folder_path = os.path.join(BACKUP_DIR, folder_name)
            
            # 날짜 형식(YYYY-MM-DD) 폴더만 삭제 대상
            if os.path.isdir(folder_path) and len(folder_name) == 10 and folder_name.count('-') == 2:
                try:
                    # 폴더명이 날짜 형식인지 확인
                    datetime.strptime(folder_name, '%Y-%m-%d')
                    # 날짜 형식이면 삭제
                    shutil.rmtree(folder_path)
                    logger.info(f"오래된 백업 폴더 삭제: {folder_name}")
                    removed_count += 1
                except ValueError:
                    # 날짜 형식이 아닌 폴더는 무시
                    continue
                except Exception as e:
                    logger.error(f"폴더 삭제 실패 {folder_name}: {e}")
        
        if removed_count > 0:
            logger.info(f"총 {removed_count}개의 오래된 백업 폴더를 정리했습니다.")
        else:
            logger.info("정리할 오래된 백업 폴더가 없습니다.")
            
    except Exception as e:
        logger.error(f"백업 정리 중 오류 발생: {str(e)}")

def run_scheduler():
    """스케줄러 실행"""
    # 처음 실행 시 오래된 백업 폴더 정리
    cleanup_old_backups()
    
    # 매일 03:00에 백업 실행
    schedule.every().day.at("03:00").do(backup_airtable_data)
    
    backup_mode = "완전 새로고침" if FULL_REFRESH_MODE else "증분 업데이트"
    logger.info(f"스케줄러 시작됨 ({backup_mode}) - 매일 03:00에 백업 실행")
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # 1분마다 스케줄 확인
        
if __name__ == "__main__":
    # 시작 시 오래된 백업 폴더 정리
    cleanup_old_backups()
    
    # 백업 실행
    backup_airtable_data()
    
    # 스케줄러 실행 (주석 해제하면 활성화)
    # run_scheduler()