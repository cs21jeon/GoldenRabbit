#!/usr/bin/env python3
"""
Threads 토큰 자동 갱신 및 .env 파일 업데이트 시스템
매월 실행하여 토큰을 갱신하고 서비스를 재시작합니다.
"""

import requests
import os
import re
import subprocess
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
import shutil

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/root/goldenrabbit/logs/token_manager.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ThreadsTokenManager:
    def __init__(self):
        self.env_file_path = '/root/goldenrabbit/.env'
        self.backup_dir = '/root/goldenrabbit/backups'
        
        # .env 파일 로드
        load_dotenv(self.env_file_path)
        
        # 현재 설정 로드
        self.app_secret = os.getenv('THREADS_APP_SECRET')
        self.current_token = os.getenv('THREADS_ACCESS_TOKEN')
        self.user_id = os.getenv('THREADS_USER_ID')
        self.app_id = os.getenv('THREADS_APP_ID')
        
        # 백업 디렉토리 생성
        os.makedirs(self.backup_dir, exist_ok=True)
        os.makedirs('/root/goldenrabbit/logs', exist_ok=True)
    
    def validate_config(self):
        """필수 설정값 확인"""
        missing = []
        if not self.app_secret:
            missing.append('THREADS_APP_SECRET')
        if not self.current_token:
            missing.append('THREADS_ACCESS_TOKEN')
        if not self.user_id:
            missing.append('THREADS_USER_ID')
        if not self.app_id:
            missing.append('THREADS_APP_ID')
        
        if missing:
            logger.error(f"필수 환경변수 누락: {', '.join(missing)}")
            return False
        
        logger.info("환경변수 설정 확인 완료")
        return True
    
    def backup_env_file(self):
        """현재 .env 파일 백업"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = f"{self.backup_dir}/.env.backup_{timestamp}"
            shutil.copy2(self.env_file_path, backup_file)
            logger.info(f".env 파일 백업 완료: {backup_file}")
            return backup_file
        except Exception as e:
            logger.error(f".env 파일 백업 실패: {e}")
            return None
    
    def check_token_validity(self, token):
        """토큰 유효성 검사"""
        try:
            url = f"https://graph.threads.net/v1.0/me"
            params = {
                'fields': 'id,username',
                'access_token': token
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"토큰 유효성 확인 - 사용자 ID: {data.get('id')}")
                return True
            else:
                logger.warning(f"토큰 유효성 검사 실패: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"토큰 유효성 검사 중 오류: {e}")
            return False
    
    def exchange_for_long_lived_token(self):
        """현재 토큰을 새로운 장기 토큰으로 교환"""
        try:
            url = "https://graph.threads.net/access_token"
            params = {
                'grant_type': 'th_exchange_token',
                'client_secret': self.app_secret,
                'access_token': self.current_token
            }
            
            logger.info("새로운 장기 토큰 요청 중...")
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                new_token = data.get('access_token')
                expires_in = data.get('expires_in', 5184000)  # 기본 60일
                
                # 만료일 계산
                expiry_date = datetime.now() + timedelta(seconds=int(expires_in))
                
                logger.info(f"새 토큰 발급 성공")
                logger.info(f"만료일: {expiry_date.strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info(f"유효기간: {expires_in//86400}일")
                
                return new_token, expiry_date
            else:
                logger.error(f"토큰 교환 실패: {response.status_code} - {response.text}")
                return None, None
                
        except Exception as e:
            logger.error(f"토큰 교환 중 오류: {e}")
            return None, None
    
    def update_env_file(self, new_token):
        """새 토큰으로 .env 파일 업데이트"""
        try:
            # 현재 .env 파일 읽기
            with open(self.env_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # THREADS_ACCESS_TOKEN 라인 찾아서 교체
            pattern = r'THREADS_ACCESS_TOKEN=.*'
            new_line = f'THREADS_ACCESS_TOKEN={new_token}'
            
            if re.search(pattern, content):
                # 기존 라인 교체
                updated_content = re.sub(pattern, new_line, content)
            else:
                # 새 라인 추가
                updated_content = content + f'\n{new_line}\n'
            
            # 업데이트된 시간 주석 추가/업데이트
            timestamp_comment = f'# THREADS_TOKEN_UPDATED={datetime.now().strftime("%Y-%m-%d_%H:%M:%S")}'
            timestamp_pattern = r'# THREADS_TOKEN_UPDATED=.*'
            
            if re.search(timestamp_pattern, updated_content):
                updated_content = re.sub(timestamp_pattern, timestamp_comment, updated_content)
            else:
                updated_content += f'\n{timestamp_comment}\n'
            
            # 파일 쓰기
            with open(self.env_file_path, 'w', encoding='utf-8') as f:
                f.write(updated_content)
            
            logger.info(".env 파일 업데이트 완료")
            return True
            
        except Exception as e:
            logger.error(f".env 파일 업데이트 실패: {e}")
            return False
    
    def restart_service(self):
        """vworld.service 재시작"""
        try:
            # systemd 서비스 재시작
            result = subprocess.run(
                ['sudo', 'systemctl', 'restart', 'vworld.service'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                logger.info("vworld.service 재시작 성공")
                
                # 서비스 상태 확인
                status_result = subprocess.run(
                    ['sudo', 'systemctl', 'is-active', 'vworld.service'],
                    capture_output=True,
                    text=True
                )
                
                if status_result.stdout.strip() == 'active':
                    logger.info("서비스가 정상적으로 실행 중")
                    return True
                else:
                    logger.warning("서비스 재시작 후 상태 이상")
                    return False
            else:
                logger.error(f"서비스 재시작 실패: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"서비스 재시작 중 오류: {e}")
            return False
    
    def send_notification(self, message, success=True):
        """알림 전송 (로그 파일에 기록)"""
        level = "SUCCESS" if success else "ERROR"
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        notification = f"""
==========================================
TOKEN MANAGER NOTIFICATION - {level}
시간: {timestamp}
메시지: {message}
==========================================
"""
        
        logger.info(notification)
        
        # 별도 알림 파일에도 기록
        try:
            with open('/root/goldenrabbit/logs/token_notifications.log', 'a', encoding='utf-8') as f:
                f.write(notification + '\n')
        except Exception as e:
            logger.warning(f"알림 파일 쓰기 실패: {e}")
    
    def run_token_refresh(self):
        """토큰 갱신 전체 프로세스 실행"""
        logger.info("=== Threads 토큰 자동 갱신 시작 ===")
        
        # 1. 설정 확인
        if not self.validate_config():
            self.send_notification("필수 환경변수가 누락되어 토큰 갱신을 중단합니다.", False)
            return False
        
        # 2. 현재 토큰 유효성 확인
        if not self.check_token_validity(self.current_token):
            logger.warning("현재 토큰이 만료되었거나 유효하지 않습니다. 갱신을 시도합니다.")
        
        # 3. .env 파일 백업
        backup_file = self.backup_env_file()
        if not backup_file:
            self.send_notification("백업 생성 실패로 토큰 갱신을 중단합니다.", False)
            return False
        
        # 4. 새 토큰 발급
        new_token, expiry_date = self.exchange_for_long_lived_token()
        if not new_token:
            self.send_notification("새 토큰 발급에 실패했습니다.", False)
            return False
        
        # 5. 새 토큰 유효성 확인
        if not self.check_token_validity(new_token):
            self.send_notification("새로 발급받은 토큰이 유효하지 않습니다.", False)
            return False
        
        # 6. .env 파일 업데이트
        if not self.update_env_file(new_token):
            self.send_notification("환경변수 파일 업데이트에 실패했습니다.", False)
            return False
        
        # 7. 서비스 재시작
        if not self.restart_service():
            self.send_notification("서비스 재시작에 실패했습니다.", False)
            return False
        
        # 8. 성공 알림
        success_msg = f"토큰 갱신 완료! 새 토큰 만료일: {expiry_date.strftime('%Y-%m-%d %H:%M:%S')}"
        self.send_notification(success_msg, True)
        
        logger.info("=== 토큰 갱신 프로세스 완료 ===")
        return True

def main():
    """메인 실행 함수"""
    try:
        manager = ThreadsTokenManager()
        success = manager.run_token_refresh()
        
        if success:
            print("토큰 갱신이 성공적으로 완료되었습니다.")
            exit(0)
        else:
            print("토큰 갱신 중 오류가 발생했습니다. 로그를 확인하세요.")
            exit(1)
            
    except Exception as e:
        logger.error(f"토큰 매니저 실행 중 치명적 오류: {e}")
        print(f"치명적 오류: {e}")
        exit(1)

if __name__ == "__main__":
    main()
