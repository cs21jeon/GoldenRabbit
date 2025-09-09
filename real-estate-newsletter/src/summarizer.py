import logging
from typing import List, Dict, Optional
import anthropic
from .config import Config

logger = logging.getLogger(__name__)

class ClaudeNewsSummarizer:
    def __init__(self):
        if not Config.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")

        self.client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)

    def create_summary_prompt(self, news_item: Dict[str, str]) -> str:
        """뉴스 요약을 위한 프롬프트 생성"""
        return f"""
    다음 부동산 뉴스를 3-4줄로 핵심만 간단히 요약해주세요.

    제목: {news_item['title']}
    내용: {news_item['content']}

    요약 조건:
    - 최대 3-4줄, 각 줄은 한 문장
    - 핵심 내용만 포함 (수치, 지역, 정책 등)
    - 불필요한 수사나 반복 제거
    - 각 줄은 40자 이내로 작성

    예시 형식:
    1. 핵심 내용 첫 번째
    2. 핵심 내용 두 번째
    3. 핵심 내용 세 번째
    """

    def summarize_single_news(self, news_item: Dict[str, str]) -> Optional[str]:
        """개별 뉴스 기사 요약"""
        try:
            if not news_item.get('title') or not news_item.get('content'):
                logger.warning("뉴스 제목 또는 내용이 없어 요약을 건너뜁니다.")
                return None

            prompt = self.create_summary_prompt(news_item)

            logger.info(f"뉴스 요약 시작: {news_item['title'][:50]}...")

            response = self.client.messages.create(
                model=Config.CLAUDE_MODEL,
                max_tokens=500,
                temperature=0.3,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            summary = response.content[0].text.strip()
            logger.info(f"요약 완료: {len(summary)}자")

            return summary

        except Exception as e:
            logger.error(f"뉴스 요약 실패 ({news_item.get('title', 'Unknown')}): {e}")
            return None

    def summarize_news_batch(self, news_list: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """여러 뉴스 기사 배치 요약"""
        summarized_news = []

        for i, news_item in enumerate(news_list, 1):
            logger.info(f"뉴스 {i}/{len(news_list)} 요약 중...")

            summary = self.summarize_single_news(news_item)

            if summary:
                summarized_item = {
                    'title': news_item['title'],
                    'url': news_item['url'],
                    'original_content': news_item['content'],
                    'summary': summary
                }
                summarized_news.append(summarized_item)
                logger.info(f"뉴스 {i} 요약 성공")
            else:
                logger.warning(f"뉴스 {i} 요약 실패")

        logger.info(f"총 {len(summarized_news)}개 뉴스 요약 완료")
        return summarized_news

    def create_threads_post(self, summarized_news: List[Dict[str, str]]) -> str:
        """요약된 뉴스들을 Threads 게시용 3단 구조로 변환"""
        try:
            if not summarized_news:
                return "오늘의 부동산 뉴스가 없습니다."
            
            from datetime import datetime
            today = datetime.now().strftime('%Y년 %m월 %d일')
            
            # 첫 번째 뉴스만 메인 게시물로 사용
            first_news = summarized_news[0]
            
            # 헤더 (날짜 + 제목)
            post_content = f"📅 {today} 부동산 주요뉴스\n\n"
            
            # 3단 구조: 제목 + 요약 + 링크
            post_content += f"📰 {first_news['title']}\n\n"
            
            # 요약을 • 포인트로 정리
            summary_lines = first_news['summary'].split('\n')
            clean_points = []
            
            for line in summary_lines:
                line = line.strip()
                if line and len(line) > 10:
                    # 숫자나 • 제거하고 깔끔하게
                    line = line.lstrip('1234567890.- •')
                    clean_points.append(f"• {line}")
                if len(clean_points) >= 3:  # 최대 3개 포인트
                    break
            
            for point in clean_points:
                post_content += f"{point}\n"
            
            post_content += f"\n🔗 {first_news['url']}\n\n"
            
            # 출처 및 해시태그
            post_content += "📰 출처: 네이버부동산뉴스\n"
            post_content += "#부동산뉴스 #골든래빗 #금토끼부동산"
            
            # 글자 수 제한 확인 (500자)
            if len(post_content) > 500:
                # 포인트 개수 줄이기
                shorter_content = f"📅 {today} 부동산 주요뉴스\n\n"
                shorter_content += f"📰 {first_news['title']}\n\n"
                for point in clean_points[:2]:  # 2개만
                    shorter_content += f"{point}\n"
                shorter_content += f"\n🔗 {first_news['url']}\n\n"
                shorter_content += "📰 출처: 네이버부동산뉴스\n#부동산뉴스 #골든래빗 #금토끼부동산"
                post_content = shorter_content
            
            logger.info(f"메인 게시글 생성 완료: {len(post_content)}자")
            return post_content
            
        except Exception as e:
            logger.error(f"메인 게시글 생성 실패: {e}")
            return f"부동산 뉴스 ({datetime.now().strftime('%Y-%m-%d')})"

    def create_reply_posts(self, summarized_news: List[Dict[str, str]]) -> List[str]:
        """나머지 뉴스들을 댓글용 텍스트로 변환"""
        try:
            reply_posts = []
            
            # 두 번째 뉴스부터 댓글로 사용
            for news in summarized_news[1:5]:  # 최대 4개 댓글
                # 댓글용 3단 구조 (해시태그 없음)
                reply_content = f"📰 {news['title']}\n\n"
                
                # 요약 포인트 (댓글은 더 간단하게)
                summary_lines = news['summary'].split('\n')
                clean_points = []
                
                for line in summary_lines:
                    line = line.strip()
                    if line and len(line) > 10:
                        line = line.lstrip('1234567890.- •')
                        clean_points.append(f"• {line}")
                    if len(clean_points) >= 2:  # 댓글은 최대 2개 포인트
                        break
                
                for point in clean_points:
                    reply_content += f"{point}\n"
                
                reply_content += f"\n🔗 {news['url']}"
                
                # 댓글 글자 수 제한 (400자)
                if len(reply_content) > 400:
                    # 1개 포인트만 사용
                    reply_content = f"📰 {news['title']}\n\n• {clean_points[0]}\n\n🔗 {news['url']}"
                
                reply_posts.append(reply_content)
                logger.info(f"댓글 {len(reply_posts)} 생성: {len(reply_content)}자")
            
            return reply_posts
            
        except Exception as e:
            logger.error(f"댓글 생성 실패: {e}")
            return []

    def _truncate_post_content(self, content: str, news_list: List[Dict[str, str]]) -> str:
        """게시글 내용을 Threads 제한에 맞게 축약"""
        from datetime import datetime
        today = datetime.now().strftime('%Y년 %m월 %d일')

        # 기본 헤더와 푸터
        header = f"🏠 {today} 부동산 뉴스 요약\n\n"
        footer = "\n📊 #부동산뉴스 #골든래빗"

        available_length = 450 - len(header) - len(footer)  # 여유분 50자

        truncated_content = header

        for i, news in enumerate(news_list[:3], 1):  # 최대 3개만
            news_summary = f"📰 {i}. {news['title'][:30]}...\n"

            # 요약을 2-3줄로 축약
            summary_lines = news['summary'].split('\n')[:3]
            short_summary = ' '.join(summary_lines).strip()
            if len(short_summary) > 80:
                short_summary = short_summary[:80] + "..."

            news_content = news_summary + short_summary + "\n\n"

            if len(truncated_content + news_content + footer) <= 500:
                truncated_content += news_content
            else:
                break

        truncated_content += footer
        return truncated_content

def test_summarizer():
    """요약기 테스트 함수"""
    # 테스트용 가짜 뉴스 데이터
    test_news = [
        {
            'title': '정부, 부동산 정책 발표',
            'url': 'https://example.com/news1',
            'content': '정부가 오늘 새로운 부동산 정책을 발표했습니다. 주요 내용으로는 대출 규제 완화와 공급 확대 방안이 포함되어 있습니다...'
        }
    ]

    try:
        summarizer = ClaudeNewsSummarizer()
        summarized = summarizer.summarize_news_batch(test_news)

        if summarized:
            threads_post = summarizer.create_threads_post(summarized)
            print("=== Threads 게시글 ===")
            print(threads_post)
        else:
            print("요약 실패")

    except Exception as e:
        print(f"테스트 실패: {e}")

if __name__ == "__main__":
    test_summarizer()
