#!/usr/bin/env python3
import feedparser
import os
import re
import requests
from bs4 import BeautifulSoup
import logging
from datetime import datetime
import time

# 로깅 설정
log_dir = '/home/sftpuser/logs/'
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"{log_dir}/blog_thumbnail_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

# 저장 디렉토리 설정
save_dir = '/home/sftpuser/www/blog_thumbs/'
os.makedirs(save_dir, exist_ok=True)

# 네이버 블로그 RSS URL
feed_url = 'https://rss.blog.naver.com/goldenrabbit7377.xml'

# 네이버 이미지 다운로드를 위한 헤더 설정
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Referer': 'https://blog.naver.com/'
}

def download_thumbnail():
    """블로그 썸네일 다운로드 메인 함수"""
    logger.info("블로그 썸네일 다운로드 작업 시작")
    
    try:
        # RSS 피드 파싱
        feed = feedparser.parse(feed_url)
        
        if not feed.entries:
            logger.warning("피드에 항목이 없습니다")
            return
        
        logger.info(f"총 {len(feed.entries[:10])} 개의 포스트 처리 시작")
        
        # 다운로드된 이미지 카운터
        downloaded_count = 0
        skipped_count = 0
        failed_count = 0
        
        for entry in feed.entries[:10]:
            # 로그넘버 추출
            match = re.search(r'/(\d+)', entry.link)
            if not match:
                logger.error(f"로그넘버 추출 실패: {entry.link}")
                continue
            
            log_no = match.group(1)
            image_filename = f"{log_no}.jpg"
            save_path = os.path.join(save_dir, image_filename)
            
            # 이미 존재하는 경우 스킵
            if os.path.exists(save_path):
                logger.info(f"이미 존재하는 이미지 스킵: {image_filename}")
                skipped_count += 1
                continue
            
            # HTML에서 이미지 태그 추출
            soup = BeautifulSoup(entry.summary, 'html.parser')
            img_tag = soup.find('img')
            
            if img_tag and 'src' in img_tag.attrs:
                img_url = img_tag['src']
                logger.info(f"이미지 다운로드 시도: {image_filename}")
                
                # 최대 3번 재시도
                for attempt in range(3):
                    try:
                        # 이미지 다운로드
                        img_data = requests.get(img_url, headers=headers, timeout=10)
                        
                        if img_data.status_code == 200:
                            # 이미지 저장
                            with open(save_path, 'wb') as f:
                                f.write(img_data.content)
                            logger.info(f"이미지 저장 성공: {image_filename}")
                            downloaded_count += 1
                            break
                        else:
                            logger.warning(f"다운로드 실패 ({img_data.status_code}): {img_url}, 시도 {attempt+1}/3")
                            if attempt == 2:  # 마지막 시도 후에도 실패
                                failed_count += 1
                    
                    except Exception as e:
                        logger.error(f"다운로드 중 예외 발생: {e}, 시도 {attempt+1}/3")
                        if attempt == 2:  # 마지막 시도 후에도 실패
                            failed_count += 1
                    
                    # 재시도 전 잠시 대기
                    if attempt < 2:  # 마지막 시도가 아니면 대기
                        time.sleep(2)
            else:
                logger.warning(f"이미지 태그를 찾을 수 없음: {entry.title}")
                failed_count += 1
            
            # 네이버 서버에 부담을 주지 않기 위해 요청 사이에 잠시 대기
            time.sleep(1)
        
        logger.info(f"작업 완료. 다운로드: {downloaded_count}, 스킵: {skipped_count}, 실패: {failed_count}")
    
    except Exception as e:
        logger.error(f"작업 중 예외 발생: {str(e)}")

if __name__ == "__main__":
    download_thumbnail()