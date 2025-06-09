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

def calculate_data_hash(data):
    """데이터의 해시값을 계산하여 변경사항 감지"""
    data_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(data_str.encode('utf-8')).hexdigest()

def load_previous_data(filename):
    """이전 백업 데이터 로드"""
    file_path = os.path.join(BACKUP_DIR, filename)
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"이전 데이터 로드 실패 ({filename}): {e}")
    return None

def save_backup_data(data, filename):
    """백업 데이터 저장"""
    file_path = os.path.join(BACKUP_DIR, filename)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"데이터 저장 완료: {filename}")

def compare_and_update_data(new_data, view_name, filename):
    """데이터 비교 후 변경사항이 있을 때만 업데이트"""
    previous_data = load_previous_data(filename)
    
    # 새 데이터 해시 계산
    new_hash = calculate_data_hash(new_data)
    
    # 이전 데이터가 없으면 새로 저장
    if previous_data is None:
        logger.info(f"'{view_name}' - 이전 데이터 없음, 새로 저장")
        save_backup_data(new_data, filename)
        return True, len(new_data), 0, len(new_data)
    
    # 이전 데이터 해시 계산
    previous_hash = calculate_data_hash(previous_data)
    
    # 데이터가 동일하면 업데이트 하지 않음
    if new_hash == previous_hash:
        logger.info(f"'{view_name}' - 데이터 변경사항 없음, 업데이트 건너뜀")
        return False, len(new_data), 0, 0
    
    # 변경사항이 있으면 업데이트
    logger.info(f"'{view_name}' - 데이터 변경 감지, 업데이트 진행")
    
    # 레코드별 변경사항 분석
    previous_records = {record.get('id'): record for record in previous_data}
    new_records = {record.get('id'): record for record in new_data}
    
    added_count = len(set(new_records.keys()) - set(previous_records.keys()))
    removed_count = len(set(previous_records.keys()) - set(new_records.keys()))
    
    modified_count = 0
    for record_id in set(new_records.keys()) & set(previous_records.keys()):
        if calculate_data_hash(new_records[record_id]) != calculate_data_hash(previous_records[record_id]):
            modified_count += 1
    
    logger.info(f"'{view_name}' 변경사항 - 추가: {added_count}, 삭제: {removed_count}, 수정: {modified_count}")
    
    # 새 데이터 저장
    save_backup_data(new_data, filename)
    
    return True, len(new_data), added_count + removed_count + modified_count, len(new_data)

def backup_airtable_data():
    """에어테이블의 모든 뷰 데이터를 백업 (변경사항만 업데이트)"""
    start_time = time.time()
    logger.info(f"====== 에어테이블 백업 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ======")
    
    if not AIRTABLE_KEY:
        logger.error("AIRTABLE_API_KEY가 설정되지 않았습니다.")
        return False
    
    headers = {
        "Authorization": f"Bearer {AIRTABLE_KEY}"
    }
    
    total_records = 0
    success_count = 0
    total_changes = 0
    updated_views = []
    all_records = []  # 모든 레코드 저장 (이미지 처리용)
    
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
            
            # 데이터 비교 및 업데이트
            was_updated, record_count, changes, final_count = compare_and_update_data(
                view_records, view_name, filename
            )
            
            if was_updated:
                updated_views.append(view_name)
                total_changes += changes
            
            total_records += record_count
            success_count += 1
            
        except Exception as e:
            logger.error(f"'{view_name}' 뷰 백업 실패: {str(e)}")
            logger.error(traceback.format_exc())
    
    # 이미지 백업 (전체 레코드에서 이미지 추출, all 뷰가 업데이트된 경우에만)
    image_stats = {"new_images": 0, "updated_images": 0, "skipped_images": 0, "total_processed": 0}
    if 'all' in updated_views and all_records:
        logger.info("이미지 백업 시작")
        image_stats = backup_property_images(all_records)
    else:
        logger.info("데이터 변경사항이 없어 이미지 백업 건너뜀")

    # 백업 메타데이터 저장
    metadata = {
        'last_backup_date': datetime.now().strftime('%Y-%m-%d'),
        'last_backup_time': datetime.now().isoformat(),
        'total_records': total_records,
        'views_processed': success_count,
        'total_views': len(VIEWS),
        'updated_views': updated_views,
        'total_changes': total_changes,
        'image_stats': image_stats,
        'backup_type': 'incremental'
    }
    
    metadata_path = os.path.join(BACKUP_DIR, 'metadata.json')
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    elapsed_time = time.time() - start_time
    
    if updated_views:
        logger.info(f"====== 백업 완료: {len(updated_views)}개 뷰 업데이트 ({', '.join(updated_views)}), 총 {total_changes}개 변경사항, {elapsed_time:.2f}초 소요 ======")
    else:
        logger.info(f"====== 백업 완료: 변경사항 없음, {elapsed_time:.2f}초 소요 ======")
    
    return success_count == len(VIEWS)

def backup_property_images(records):
    """매물 이미지를 백업하는 함수 (중복 제거 및 최적화 버전)"""
    # 이미지 저장 디렉토리
    image_dir = os.path.join(BACKUP_DIR, 'images')
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
    error_images = 0
    cleaned_duplicates = 0
    
    def get_image_priority(filename):
        """이미지 파일 우선순위 결정"""
        filename_lower = filename.lower()
        
        # 1순위: 원본 파일명 (날짜, 카카오톡 등)
        if any(keyword in filename_lower for keyword in ['202', 'kakao', 'img_', 'dsc_', 'photo_202']):
            return (1, len(filename))
        
        # 2순위: representative 파일
        elif 'representative' in filename_lower:
            return (2, len(filename))
        
        # 3순위: 의미있는 파일명
        elif not filename_lower.startswith('photo_') or len(filename) > 15:
            return (3, len(filename))
        
        # 4순위: photo_ 로 시작하는 생성된 파일명
        else:
            return (4, len(filename))
    
    def clean_existing_duplicates(record_image_dir, record_id):
        """기존 중복 파일들 정리"""
        if not os.path.exists(record_image_dir):
            return None, 0
        
        # 기존 이미지 파일들 찾기
        existing_files = []
        for f in os.listdir(record_image_dir):
            file_path = os.path.join(record_image_dir, f)
            if (os.path.isfile(file_path) and 
                f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')) and
                os.path.getsize(file_path) > 1000):  # 1KB 이상만
                existing_files.append({
                    'filename': f,
                    'path': file_path,
                    'size': os.path.getsize(file_path),
                    'priority': get_image_priority(f)
                })
        
        if not existing_files:
            return None, 0
        
        # 우선순위 순으로 정렬
        existing_files.sort(key=lambda x: (x['priority'][0], -x['size']))
        
        # 가장 좋은 파일 선택
        best_file = existing_files[0]
        files_to_delete = existing_files[1:]  # 나머지는 삭제 대상
        
        deleted_count = 0
        for file_info in files_to_delete:
            try:
                os.remove(file_info['path'])
                logger.info(f"중복 파일 삭제: {record_id}/{file_info['filename']} (우선순위: {file_info['priority'][0]})")
                deleted_count += 1
            except Exception as e:
                logger.warning(f"파일 삭제 실패: {file_info['filename']} - {e}")
        
        return best_file['filename'], deleted_count
    
    for record in records:
        record_id = record.get('id')
        fields = record.get('fields', {})
        
        if not record_id:
            continue
        
        # 레코드별 이미지 디렉토리
        record_image_dir = os.path.join(image_dir, record_id)
        os.makedirs(record_image_dir, exist_ok=True)
        
        # 🔧 기존 중복 파일들 정리
        existing_best_file, deleted_count = clean_existing_duplicates(record_image_dir, record_id)
        cleaned_duplicates += deleted_count
        
        # 기존에 좋은 파일이 있으면 새로 다운로드하지 않음
        if existing_best_file:
            # 메타데이터 업데이트
            image_metadata[f"{record_id}_optimized"] = True
            image_metadata[f"{record_id}_filename"] = existing_best_file
            skipped_images += 1
            continue
        
        # 🆕 새로운 이미지 다운로드 로직
        image_urls = []
        processed_urls = set()  # 중복 URL 방지
        
        # 우선순위 1: 대표사진 필드 (원본 파일명 유지)
        if isinstance(fields.get('대표사진'), list) and fields['대표사진']:
            for i, attachment in enumerate(fields['대표사진']):
                if attachment.get('url') and attachment['url'] not in processed_urls:
                    original_filename = attachment.get('filename', f'representative_{i+1}.jpg')
                    image_urls.append({
                        'url': attachment['url'],
                        'filename': original_filename,
                        'type': 'representative',
                        'priority': 1
                    })
                    processed_urls.add(attachment['url'])
        
        # 우선순위 2: 사진링크 필드 (대표사진에 없는 URL만)
        if fields.get('사진링크'):
            photo_links = fields['사진링크'].split(',')
            for i, link in enumerate(photo_links):
                link = link.strip()
                if link and link.startswith('http') and link not in processed_urls:
                    image_urls.append({
                        'url': link,
                        'filename': f'photo_link_{i+1}.jpg',
                        'type': 'link',
                        'priority': 2
                    })
                    processed_urls.add(link)
        
        # 레코드에 이미지가 없으면 다음으로
        if not image_urls:
            continue
        
        # 우선순위 순으로 정렬 후 첫 번째만 다운로드
        image_urls.sort(key=lambda x: x['priority'])
        img_info = image_urls[0]  # 가장 우선순위 높은 이미지만
        
        url = img_info['url']
        img_type = img_info['type']
        
        try:
            # 파일명 처리
            parsed_url = urlparse(url)
            path_parts = Path(parsed_url.path).parts
            original_filename = img_info['filename'] or path_parts[-1]
            
            # 확장자 확인
            if '.' not in original_filename:
                original_filename += '.jpg'
            
            # 파일명 정리 (특수문자 제거)
            filename = "".join(c for c in original_filename if c.isalnum() or c in '.-_').strip()
            if not filename or filename == '.jpg':
                filename = f"image_{int(time.time())}.jpg"
            
            # 이미지 파일 경로
            image_path = os.path.join(record_image_dir, filename)
            
            # 이미지 URL 해시 생성 (변경 감지용)
            url_hash = hashlib.md5(url.encode()).hexdigest()
            
            # 메타데이터에서 이전 해시 확인
            prev_hash = image_metadata.get(f"{record_id}_hash")
            
            # 이미지가 이미 존재하고 해시가 같으면 스킵
            if os.path.exists(image_path) and prev_hash == url_hash:
                skipped_images += 1
                continue
            
            # 이미지 다운로드
            logger.info(f"이미지 다운로드 시작: {record_id} -> {filename}")
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
                    image_metadata[f"{record_id}_hash"] = url_hash
                    image_metadata[f"{record_id}_filename"] = filename
                    image_metadata[f"{record_id}_type"] = img_type
                    image_metadata[f"{record_id}_optimized"] = True
                    
                    if prev_hash:
                        updated_images += 1
                        logger.info(f"✅ 이미지 업데이트: {filename} ({img_type})")
                    else:
                        new_images += 1
                        logger.info(f"✅ 새 이미지 저장: {filename} ({img_type})")
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
        image_metadata['last_optimization'] = datetime.now().isoformat()
        image_metadata['optimization_stats'] = {
            'duplicates_cleaned': cleaned_duplicates,
            'new_images': new_images,
            'updated_images': updated_images
        }
        
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(image_metadata, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"이미지 메타데이터 저장 실패: {str(e)}")
    
    logger.info(f"🎉 이미지 백업 최적화 완료!")
    logger.info(f"   - 새 이미지: {new_images}개")
    logger.info(f"   - 업데이트: {updated_images}개") 
    logger.info(f"   - 스킵: {skipped_images}개")
    logger.info(f"   - 오류: {error_images}개")
    logger.info(f"   - 중복 파일 정리: {cleaned_duplicates}개")
    
    return {
        'new_images': new_images,
        'updated_images': updated_images,
        'skipped_images': skipped_images,
        'error_images': error_images,
        'duplicates_cleaned': cleaned_duplicates,
        'total_processed': new_images + updated_images + skipped_images + error_images,
        'optimization_enabled': True
    }

def cleanup_old_backups():
    """오래된 백업 폴더 정리 (날짜 형식 폴더들만)"""
    try:
        import shutil
        from datetime import datetime
        
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

"""
def run_scheduler():
    # 처음 실행 시 오래된 백업 폴더 정리
    cleanup_old_backups()
    
    # 매일 03:00에 백업 실행
    schedule.every().day.at("03:00").do(backup_airtable_data)
    
    logger.info("스케줄러 시작됨 - 매일 03:00에 백업 실행")
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # 1분마다 스케줄 확인
"""
        
if __name__ == "__main__":
    # 시작 시 오래된 백업 폴더 정리
    cleanup_old_backups()
    
    # 백업 실행
    backup_airtable_data()
    
"""    
    # 스케줄러 실행
    run_scheduler()
"""