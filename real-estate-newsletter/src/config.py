import os
import logging
from dotenv import load_dotenv

# .env 파일 로드 (절대 경로 지정)
load_dotenv('/root/goldenrabbit/.env')

class Config:
    # 네이버 크롤링 설정
    NAVER_USER_AGENT = os.getenv('NAVER_USER_AGENT', 
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
    NAVER_NEWS_URL = 'https://land.naver.com/news/headline.naver'
    
    # Claude API 설정
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
    CLAUDE_MODEL = 'claude-3-haiku-20240307'  # 비용 효율적인 모델
    
    # Threads API 설정
    THREADS_APP_ID = os.getenv('THREADS_APP_ID')
    THREADS_APP_SECRET = os.getenv('THREADS_APP_SECRET')
    THREADS_ACCESS_TOKEN = os.getenv('THREADS_ACCESS_TOKEN')
    THREADS_USER_ID = os.getenv('THREADS_USER_ID')
    THREADS_API_BASE = 'https://graph.threads.net/v1.0'
    
    # 로깅 설정
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', 'logs/newsletter.log')
    
    # 스케줄링 설정
    SCHEDULE_TIMES = os.getenv('SCHEDULE_TIMES', '08:00,18:00').split(',')
    
    # 크롤링 설정
    REQUEST_DELAY = 2  # 요청 간 대기시간 (초)
    MAX_RETRIES = 3    # 최대 재시도 횟수
    
    @classmethod
    def validate_config(cls):
        """필수 설정값들이 있는지 확인"""
        required_vars = [
            'ANTHROPIC_API_KEY',
            'THREADS_APP_ID', 
            'THREADS_APP_SECRET',
            'THREADS_ACCESS_TOKEN',
            'THREADS_USER_ID'
        ]
        
        missing_vars = []
        for var in required_vars:
            if not getattr(cls, var):
                missing_vars.append(var)
        
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        return True

def setup_logging():
    """로깅 설정"""
    # logs 디렉토리 생성
    os.makedirs('logs', exist_ok=True)
    
    # 로깅 레벨 설정
    level = getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO)
    
    # 로깅 포맷 설정
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 파일 핸들러
    file_handler = logging.FileHandler(Config.LOG_FILE, encoding='utf-8')
    file_handler.setFormatter(formatter)
    
    # 콘솔 핸들러
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # 루트 로거 설정
    logger = logging.getLogger()
    logger.setLevel(level)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger
