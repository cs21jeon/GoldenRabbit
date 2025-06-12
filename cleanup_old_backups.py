#!/usr/bin/env python3
"""
기존 날짜별 백업 폴더를 정리하고 단일 백업 시스템으로 마이그레이션하는 스크립트. 일시적 사용.
"""

import os
import shutil
import json
import logging
from datetime import datetime
from pathlib import Path

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 백업 디렉토리 경로
BACKUP_DIR = '/home/sftpuser/www/airtable_backup'

def cleanup_old_backup_folders():
    """기존 날짜별 백업 폴더들을 정리"""
    logger.info("=== 기존 백업 폴더 정리 시작 ===")
    
    if not os.path.exists(BACKUP_DIR):
        logger.error(f"백업 디렉토리가 존재하지 않습니다: {BACKUP_DIR}")
        return False
    
    # 백업 디렉토리 내용 확인
    logger.info(f"백업 디렉토리 내용 확인: {BACKUP_DIR}")
    try:
        items = os.listdir(BACKUP_DIR)
        logger.info(f"발견된 항목들: {items}")
    except Exception as e:
        logger.error(f"디렉토리 읽기 실패: {e}")
        return False
    
    # 날짜 형식 폴더 찾기 및 정리
    date_folders = []
    other_items = []
    
    for item in items:
        item_path = os.path.join(BACKUP_DIR, item)
        
        # 디렉토리인지 확인
        if os.path.isdir(item_path):
            # 날짜 형식(YYYY-MM-DD) 폴더인지 확인
            if len(item) == 10 and item.count('-') == 2:
                try:
                    # 날짜 형식인지 검증
                    datetime.strptime(item, '%Y-%m-%d')
                    date_folders.append(item)
                except ValueError:
                    # 날짜 형식이 아님
                    other_items.append(item)
            else:
                other_items.append(item)
        else:
            other_items.append(item)
    
    logger.info(f"날짜 폴더: {date_folders}")
    logger.info(f"기타 항목: {other_items}")
    
    # 최신 날짜 폴더에서 데이터 마이그레이션
    if date_folders:
        # 날짜순 정렬 (최신이 마지막)
        date_folders.sort()
        latest_folder = date_folders[-1]
        latest_folder_path = os.path.join(BACKUP_DIR, latest_folder)
        
        logger.info(f"최신 날짜 폴더에서 데이터 마이그레이션: {latest_folder}")
        
        # 최신 폴더의 JSON 파일들을 루트로 이동
        try:
            json_files = [
                'all_properties.json',
                'reconstruction_properties.json', 
                'high_yield_properties.json',
                'low_cost_properties.json',
                'metadata.json'
            ]
            
            for json_file in json_files:
                src_path = os.path.join(latest_folder_path, json_file)
                dst_path = os.path.join(BACKUP_DIR, json_file)
                
                if os.path.exists(src_path):
                    logger.info(f"파일 이동: {src_path} -> {dst_path}")
                    shutil.copy2(src_path, dst_path)
                else:
                    logger.warning(f"파일이 존재하지 않음: {src_path}")
            
            # 이미지 폴더도 이동
            src_images = os.path.join(latest_folder_path, 'images')
            dst_images = os.path.join(BACKUP_DIR, 'images')
            
            if os.path.exists(src_images):
                if os.path.exists(dst_images):
                    logger.info("기존 이미지 폴더 삭제 후 이동")
                    shutil.rmtree(dst_images)
                
                logger.info(f"이미지 폴더 이동: {src_images} -> {dst_images}")
                shutil.move(src_images, dst_images)
            else:
                logger.warning("이미지 폴더가 존재하지 않음")
                
        except Exception as e:
            logger.error(f"데이터 마이그레이션 실패: {e}")
            return False
    
    # 모든 날짜 폴더 삭제
    removed_count = 0
    for date_folder in date_folders:
        folder_path = os.path.join(BACKUP_DIR, date_folder)
        try:
            logger.info(f"날짜 폴더 삭제: {date_folder}")
            shutil.rmtree(folder_path)
            removed_count += 1
        except Exception as e:
            logger.error(f"폴더 삭제 실패 {date_folder}: {e}")
    
    # latest 폴더도 정리 (이제 필요없음)
    latest_path = os.path.join(BACKUP_DIR, 'latest')
    if os.path.exists(latest_path):
        try:
            logger.info("latest 폴더 삭제")
            shutil.rmtree(latest_path)
        except Exception as e:
            logger.error(f"latest 폴더 삭제 실패: {e}")
    
    # 메타데이터 업데이트
    update_metadata_for_new_system()
    
    logger.info(f"=== 정리 완료: {removed_count}개 날짜 폴더 삭제됨 ===")
    return True

def update_metadata_for_new_system():
    """새로운 백업 시스템용 메타데이터 생성"""
    metadata = {
        'migration_date': datetime.now().strftime('%Y-%m-%d'),
        'migration_time': datetime.now().isoformat(),
        'backup_type': 'single_folder_incremental',
        'system_version': '2.0',
        'note': '날짜별 폴더 시스템에서 단일 폴더 시스템으로 마이그레이션됨'
    }
    
    metadata_path = os.path.join(BACKUP_DIR, 'migration_metadata.json')
    try:
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        logger.info(f"마이그레이션 메타데이터 생성: {metadata_path}")
    except Exception as e:
        logger.error(f"메타데이터 생성 실패: {e}")

def verify_backup_structure():
    """백업 구조 검증"""
    logger.info("=== 백업 구조 검증 ===")
    
    required_files = [
        'all_properties.json',
        'reconstruction_properties.json',
        'high_yield_properties.json', 
        'low_cost_properties.json'
    ]
    
    missing_files = []
    for file_name in required_files:
        file_path = os.path.join(BACKUP_DIR, file_name)
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            logger.info(f"✓ {file_name}: {file_size:,} bytes")
        else:
            logger.warning(f"✗ {file_name}: 파일 없음")
            missing_files.append(file_name)
    
    # 이미지 폴더 확인
    images_path = os.path.join(BACKUP_DIR, 'images')
    if os.path.exists(images_path):
        try:
            image_count = sum(len(files) for _, _, files in os.walk(images_path))
            logger.info(f"✓ 이미지 폴더: {image_count}개 파일")
        except Exception as e:
            logger.warning(f"이미지 폴더 확인 실패: {e}")
    else:
        logger.warning("✗ 이미지 폴더 없음")
    
    if missing_files:
        logger.error(f"누락된 파일들: {missing_files}")
        return False
    else:
        logger.info("✓ 모든 필수 파일이 존재합니다")
        return True

def show_disk_usage():
    """디스크 사용량 확인"""
    logger.info("=== 디스크 사용량 확인 ===")
    
    try:
        # 백업 디렉토리 전체 크기
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(BACKUP_DIR):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                except OSError:
                    pass
        
        # 크기를 읽기 쉬운 형식으로 변환
        if total_size < 1024:
            size_str = f"{total_size} B"
        elif total_size < 1024 * 1024:
            size_str = f"{total_size / 1024:.1f} KB"
        elif total_size < 1024 * 1024 * 1024:
            size_str = f"{total_size / (1024 * 1024):.1f} MB"
        else:
            size_str = f"{total_size / (1024 * 1024 * 1024):.1f} GB"
        
        logger.info(f"백업 디렉토리 총 크기: {size_str}")
        
    except Exception as e:
        logger.error(f"디스크 사용량 확인 실패: {e}")

def main():
    """메인 실행 함수"""
    print("=== 에어테이블 백업 시스템 마이그레이션 ===")
    print(f"백업 디렉토리: {BACKUP_DIR}")
    print()
    
    # 현재 상태 확인
    show_disk_usage()
    print()
    
    # 사용자 확인
    response = input("기존 날짜별 백업 폴더들을 정리하시겠습니까? (y/N): ")
    if response.lower() != 'y':
        print("작업이 취소되었습니다.")
        return
    
    # 정리 실행
    success = cleanup_old_backup_folders()
    
    if success:
        print("\n=== 마이그레이션 완료 ===")
        verify_backup_structure()
        print()
        show_disk_usage()
        print("\n새로운 백업 시스템이 준비되었습니다!")
        print("이제 매일 3시에 변경사항만 업데이트됩니다.")
    else:
        print("\n마이그레이션 중 오류가 발생했습니다.")
        print("로그를 확인해주세요.")

if __name__ == "__main__":
    main()