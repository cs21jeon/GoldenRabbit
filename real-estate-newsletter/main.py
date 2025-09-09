#!/usr/bin/env python3
"""
부동산 뉴스레터 자동화 시스템
네이버 부동산 뉴스 → Claude 요약 → Threads 게시 + 웹사이트 업데이트
"""

import sys
import os
import logging
import json
from datetime import datetime
from typing import List, Dict

# 현재 디렉토리를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.config import Config, setup_logging
from src.crawler import NaverRealEstateNewsCrawler
from src.summarizer import ClaudeNewsSummarizer
from src.threads_publisher import ThreadsPublisher

class NewsletterService:
    def __init__(self):
        """뉴스레터 서비스 초기화"""
        # 로깅 설정
        self.logger = setup_logging()

        # 설정 검증
        try:
            Config.validate_config()
            self.logger.info("설정 검증 완료")
        except ValueError as e:
            self.logger.error(f"설정 오류: {e}")
            raise

        # 각 모듈 초기화
        try:
            self.crawler = NaverRealEstateNewsCrawler()
            self.summarizer = ClaudeNewsSummarizer()
            self.publisher = ThreadsPublisher()
            self.logger.info("모든 모듈 초기화 완료")
        except Exception as e:
            self.logger.error(f"모듈 초기화 실패: {e}")
            raise

    def save_news_for_web(self, summarized_news: List[Dict[str, str]]):
        """웹사이트용 뉴스 데이터 저장 - 오전에만 실행, 5개 뉴스"""
        try:
            current_hour = datetime.now().hour
            
            # 오전 시간대(6시~12시)에만 웹사이트 업데이트
            if not (6 <= current_hour < 12):
                self.logger.info(f"현재 시간({current_hour}시)은 웹사이트 업데이트 시간이 아닙니다. (오전 6-12시만 업데이트)")
                return
            
            web_news_data = {
                'update_time': datetime.now().isoformat(),
                'news': []
            }
            
            # 상위 5개 뉴스만 저장
            for news in summarized_news[:5]:
                thumbnail_url = self._extract_thumbnail(news.get('url', '')) or '/images/default_news.jpg'
                
                web_news_data['news'].append({
                    'title': news['title'],
                    'summary': self._clean_summary_for_web(news['summary']),
                    'url': news['url'],
                    'thumbnail': thumbnail_url,
                    'published': datetime.now().strftime('%Y-%m-%d %H:%M')
                })
            
            # 웹사이트 디렉토리에 저장 (이전 파일 완전 덮어쓰기)
            web_data_dir = '/home/sftpuser/www/data'
            os.makedirs(web_data_dir, exist_ok=True)
            
            with open(f'{web_data_dir}/latest_news.json', 'w', encoding='utf-8') as f:
                json.dump(web_news_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"웹사이트용 뉴스 데이터 저장 완료: {len(web_news_data['news'])}개 (오전 업데이트)")
            
        except Exception as e:
            self.logger.error(f"웹사이트용 뉴스 저장 실패: {e}")

    def _extract_thumbnail(self, news_url: str) -> str:
        """뉴스 URL에서 썸네일 이미지 추출"""
        try:
            import requests
            from bs4 import BeautifulSoup
            
            response = requests.get(news_url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Open Graph 이미지 찾기
            og_image = soup.find('meta', property='og:image')
            if og_image and og_image.get('content'):
                return og_image['content']
            
            # 첫 번째 이미지 찾기
            img_tag = soup.find('img')
            if img_tag and img_tag.get('src'):
                img_src = img_tag['src']
                if img_src.startswith('http'):
                    return img_src
                elif img_src.startswith('//'):
                    return f"https:{img_src}"
            
            return None
            
        except Exception as e:
            self.logger.warning(f"썸네일 추출 실패 ({news_url}): {e}")
            return None

    def _clean_summary_for_web(self, summary: str) -> str:
        """웹 표시용으로 요약 텍스트 정리"""
        lines = summary.split('\n')
        clean_lines = []
        
        for line in lines:
            line = line.strip()
            if line:
                # 앞의 숫자나 기호 제거
                line = line.lstrip('1234567890.- •')
                clean_lines.append(line)
        
        # 최대 100자로 제한
        clean_summary = ' '.join(clean_lines)
        if len(clean_summary) > 100:
            clean_summary = clean_summary[:97] + '...'
            
        return clean_summary

    def run_daily_newsletter(self, news_count: int = 5) -> bool:
        """일일 뉴스레터 실행"""
        try:
            self.logger.info("=== 부동산 뉴스레터 자동화 시작 ===")
            start_time = datetime.now()

            # 1단계: 뉴스 크롤링
            self.logger.info(f"1단계: 네이버 부동산 뉴스 상위 {news_count}개 수집 중...")
            news_list = self.crawler.get_complete_news_data(news_count)

            if not news_list:
                self.logger.error("수집된 뉴스가 없습니다.")
                return False

            self.logger.info(f"뉴스 수집 완료: {len(news_list)}개")

            # 2단계: Claude 요약
            self.logger.info("2단계: Claude를 이용한 뉴스 요약 중...")
            summarized_news = self.summarizer.summarize_news_batch(news_list)

            if not summarized_news:
                self.logger.error("요약된 뉴스가 없습니다.")
                return False

            self.logger.info(f"뉴스 요약 완료: {len(summarized_news)}개")

            # 2.5단계: 웹사이트용 뉴스 데이터 저장 (오전에만)
            self.logger.info("2.5단계: 웹사이트용 뉴스 데이터 저장 중...")
            self.save_news_for_web(summarized_news)

            # 3단계: Threads 게시글 생성
            self.logger.info("3단계: Threads 게시글 생성 중...")
            main_content = self.summarizer.create_threads_post(summarized_news)
            reply_contents = self.summarizer.create_reply_posts(summarized_news)

            if not main_content:
                self.logger.error("메인 게시글 생성 실패")
                return False

            self.logger.info(f"메인 게시글 생성 완료: {len(main_content)}자")
            self.logger.info(f"댓글 {len(reply_contents)}개 생성 완료")

            # 4단계: Threads 스레드 게시
            self.logger.info("4단계: Threads 스레드에 게시 중...")
            post_id = self.publisher.create_threaded_post(main_content, reply_contents)

            if post_id:
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                
                self.logger.info(f"Threads 스레드 게시 성공! 메인 Post ID: {post_id}")
                self.logger.info(f"전체 소요시간: {duration:.2f}초")
                self.logger.info("=== 뉴스레터 자동화 완료 ===")
                
                # 실행 결과 요약
                self._log_execution_summary(news_list, summarized_news, post_id, duration)
                return True
            else:
                self.logger.error("Threads 스레드 게시 실패")
                return False

        except Exception as e:
            self.logger.error(f"뉴스레터 실행 중 오류: {e}")
            return False

    def _log_execution_summary(self, news_list: List[Dict], summarized_news: List[Dict],
                             post_id: str, duration: float):
        """실행 결과 요약 로깅"""
        current_hour = datetime.now().hour
        web_updated = "예" if 6 <= current_hour < 12 else "아니오 (오전 시간대 아님)"
        
        summary = f"""
==========================================
뉴스레터 실행 결과 요약
==========================================
실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
소요 시간: {duration:.2f}초
수집 뉴스: {len(news_list)}개
요약 완료: {len(summarized_news)}개
웹사이트 업데이트: {web_updated}
Threads Post ID: {post_id}

수집된 뉴스 제목:
"""

        for i, news in enumerate(news_list, 1):
            summary += f"{i}. {news['title']}\n"

        summary += "=========================================="

        self.logger.info(summary)

    def test_all_components(self) -> bool:
        """모든 구성요소 테스트"""
        self.logger.info("=== 전체 시스템 테스트 시작 ===")

        # 1. 크롤러 테스트
        self.logger.info("1. 크롤러 테스트...")
        try:
            test_news = self.crawler.get_complete_news_data(2)
            if test_news:
                self.logger.info(f"크롤러 테스트 성공: {len(test_news)}개 뉴스 수집")
            else:
                self.logger.error("크롤러 테스트 실패")
                return False
        except Exception as e:
            self.logger.error(f"크롤러 테스트 실패: {e}")
            return False

        # 2. Claude 요약 테스트
        self.logger.info("2. Claude 요약 테스트...")
        try:
            test_summary = self.summarizer.summarize_single_news(test_news[0])
            if test_summary:
                self.logger.info("Claude 요약 테스트 성공")
                
                # 웹사이트 저장 테스트
                self.logger.info("2.5. 웹사이트 저장 테스트...")
                summarized_test = [{
                    'title': test_news[0]['title'],
                    'url': test_news[0]['url'],
                    'summary': test_summary
                }]
                self.save_news_for_web(summarized_test)
                
            else:
                self.logger.error("Claude 요약 테스트 실패")
                return False
        except Exception as e:
            self.logger.error(f"Claude 요약 테스트 실패: {e}")
            return False

        # 3. Threads 연결 테스트
        self.logger.info("3. Threads API 연결 테스트...")
        try:
            if self.publisher.test_connection():
                self.logger.info("Threads 연결 테스트 성공")
            else:
                self.logger.error("Threads 연결 테스트 실패")
                return False
        except Exception as e:
            self.logger.error(f"Threads 연결 테스트 실패: {e}")
            return False

        self.logger.info("=== 전체 시스템 테스트 완료 ===")
        return True

def main():
    """메인 실행 함수"""
    try:
        service = NewsletterService()

        # 명령행 인수 처리
        if len(sys.argv) > 1:
            command = sys.argv[1].lower()

            if command == 'test':
                # 테스트 모드
                print("테스트 모드 실행 중...")
                if service.test_all_components():
                    print("모든 테스트 통과!")
                    sys.exit(0)
                else:
                    print("테스트 실패!")
                    sys.exit(1)

            elif command == 'run':
                # 실제 실행 모드
                print("뉴스레터 자동화 실행 중...")
                if service.run_daily_newsletter():
                    print("뉴스레터 발행 성공!")
                    sys.exit(0)
                else:
                    print("뉴스레터 발행 실패!")
                    sys.exit(1)

            elif command == 'help':
                print("""
부동산 뉴스레터 자동화 시스템

사용법:
  python main.py test    - 전체 시스템 테스트
  python main.py run     - 뉴스레터 실행 (실제 게시)
  python main.py help    - 도움말 표시

동작 방식:
  - Threads 게시: 하루 2번 (기존 방식 유지)
  - 웹사이트 업데이트: 오전(6-12시)에만 5개 뉴스 저장

설정 파일:
  .env - 환경변수 설정 (API 키 등)

로그 파일:
  logs/newsletter.log - 실행 로그

웹사이트 연동:
  /home/sftpuser/www/data/latest_news.json - 웹사이트용 뉴스 데이터
                """)
                sys.exit(0)

            else:
                print(f"알 수 없는 명령: {command}")
                print("python main.py help 를 실행하여 도움말을 확인하세요.")
                sys.exit(1)

        else:
            # 기본 실행 (테스트 모드)
            print("기본 모드: 테스트 실행")
            if service.test_all_components():
                print("테스트 완료! 실제 실행하려면 'python main.py run'을 사용하세요.")
            else:
                print("테스트 실패! 설정을 확인해주세요.")

    except KeyboardInterrupt:
        print("\n사용자에 의해 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        print(f"치명적 오류: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()