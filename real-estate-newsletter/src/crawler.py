import requests
import time
import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Optional
from .config import Config
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger(__name__)

class NaverRealEstateNewsCrawler:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': Config.NAVER_USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })

    def _get_dynamic_content(self, url: str) -> Optional[str]:
        """JavaScript 렌더링된 페이지 가져오기"""
        options = Options()
        options.add_argument('--headless')  # 브라우저 창 숨김
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--user-agent=' + Config.NAVER_USER_AGENT)
        
        driver = None
        try:
            driver = webdriver.Chrome(options=options)
            logger.info("Selenium 브라우저 시작")
            
            driver.get(url)
            logger.info("페이지 로딩 완료, JavaScript 실행 대기 중...")
            
            # 뉴스 리스트가 로딩될 때까지 최대 15초 대기
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".land_news_list li.news_item"))
            )
            
            logger.info("뉴스 리스트 로딩 완료")
            
            # 추가로 2초 대기 (완전 로딩 보장)
            time.sleep(2)
            
            html = driver.page_source
            return html
            
        except Exception as e:
            logger.warning(f"Selenium 페이지 로딩 실패: {e}")
            # 실패해도 현재 페이지 소스 반환 시도
            if driver:
                try:
                    return driver.page_source
                except:
                    pass
            return None
            
        finally:
            if driver:
                driver.quit()
                logger.info("Selenium 브라우저 종료")

    def get_top_news_list(self, limit: int = 5) -> List[Dict[str, str]]:
        """네이버 부동산 뉴스 상위 기사 리스트 가져오기"""
        try:
            logger.info(f"네이버 부동산 뉴스 페이지 접근: {Config.NAVER_NEWS_URL}")
            
            # 먼저 일반 요청 시도
            response = self._make_request(Config.NAVER_NEWS_URL)
            if response:
                soup = BeautifulSoup(response.text, 'html.parser')
                # 뉴스 리스트가 있는지 확인
                if soup.select('.land_news_list li.news_item'):
                    logger.info("일반 요청으로 뉴스 발견")
                    html_content = response.text
                else:
                    logger.info("일반 요청으로 뉴스 없음, Selenium 사용")
                    html_content = self._get_dynamic_content(Config.NAVER_NEWS_URL)
            else:
                logger.info("일반 요청 실패, Selenium 사용")
                html_content = self._get_dynamic_content(Config.NAVER_NEWS_URL)
            
            if not html_content:
                logger.error("페이지 내용을 가져올 수 없습니다")
                return []
            
            soup = BeautifulSoup(html_content, 'html.parser')
            news_items = []

            # 디버깅: 페이지 정보 확인
            logger.info(f"페이지 제목: {soup.title.string if soup.title else 'No title'}")

            logger.info("=== 선택자 테스트 ===")
            test_selectors = ['.spot_headline', '.land_news_list', '.land_news_list li.news_item']
            for test_sel in test_selectors:
                found = soup.select(test_sel)
                logger.info(f"'{test_sel}': {len(found)}개 발견")

            # 디버깅: land_news_list 내부 확인
            land_news_element = soup.select_one('.land_news_list')
            if land_news_element:
                logger.info(f"land_news_list 내부 HTML: {str(land_news_element)[:500]}")
                
                all_links_in_land = land_news_element.find_all('a')
                logger.info(f"land_news_list 내부 링크 수: {len(all_links_in_land)}")
                
                for i, link in enumerate(all_links_in_land[:3]):
                    logger.info(f"링크 {i+1}: 제목='{link.get_text(strip=True)}', href='{link.get('href')}'")

            # 새로운 선택자들
            selectors = [
                # land_news_list에서 직접 뉴스 아이템 가져오기 (가장 우선)
                'ul.land_news_list li.news_item a.link',
                '.land_news_list .news_item a.link',
                'ul#land_news_list li.news_item a',
                '.land_news_list .news_item a',
                '.news_item a.link',
                '.land_news_list a'  # 더 간단한 선택자 추가
            ]

            # 각 선택자를 순차적으로 시도
            for selector in selectors:
                try:
                    found_links = soup.select(selector)
                    logger.info(f"선택자 '{selector}': {len(found_links)}개 링크 발견")  # 항상 출력되도록 수정
                    
                    if found_links:
                        logger.info(f"선택자 '{selector}'로 {len(found_links)}개 링크 발견")

                        for link in found_links[:limit]:
                            # 제목을 더 정확하게 추출
                            title_element = link.select_one('.title')
                            if title_element:
                                title = title_element.get_text(strip=True)
                            else:
                                # .title이 없으면 링크 텍스트에서 첫 번째 줄만 추출
                                full_text = link.get_text(strip=True)
                                title = full_text.split('\n')[0] if full_text else ""
                                
                                # 제목이 너무 길면 자르기
                                if len(title) > 80:
                                    title = title[:80] + "..."
                            
                            href = link.get('href')
                            
                            logger.info(f"DEBUG - 정제된 제목: '{title}', 길이: {len(title)}")
                            logger.info(f"DEBUG - 링크: {href}")

                            if title and href and len(title) > 10:
                                # 상대 경로를 절대 경로로 변환
                                if href.startswith('/'):
                                    if 'news.naver.com' in href:
                                        full_url = f"https:{href}"
                                    else:
                                        full_url = urljoin('https://land.naver.com', href)
                                elif href.startswith('http'):
                                    full_url = href
                                else:
                                    full_url = urljoin(Config.NAVER_NEWS_URL, href)

                                news_item = {
                                    'title': title,
                                    'url': full_url,
                                    'content': ''
                                }
                                news_items.append(news_item)
                                logger.info(f"뉴스 수집: {title[:50]}...")

                        if news_items:
                            break

                except Exception as e:
                    logger.warning(f"선택자 '{selector}' 처리 중 오류: {e}")
                    continue

            # 선택자로 찾지 못한 경우 모든 링크에서 뉴스 관련 링크 검색
            if not news_items:
                logger.info("선택자로 뉴스를 찾지 못함. 전체 링크 검색 중...")
                all_links = soup.find_all('a', href=True)

                for link in all_links:
                    href = link.get('href', '')
                    title = link.get_text(strip=True)

                    # 뉴스 관련 URL 패턴 확인
                    if (('/news/' in href or 'news.naver.com' in href) and
                        title and len(title) > 10 and len(title) < 100):

                        # URL 정규화
                        if href.startswith('/'):
                            if 'news.naver.com' in href:
                                full_url = f"https:{href}"
                            else:
                                full_url = urljoin('https://land.naver.com', href)
                        elif href.startswith('http'):
                            full_url = href
                        else:
                            continue

                        news_item = {
                            'title': title,
                            'url': full_url,
                            'content': ''
                        }
                        news_items.append(news_item)
                        logger.info(f"일반 링크에서 뉴스 발견: {title[:50]}...")

                        if len(news_items) >= limit:
                            break

            # 중복 제거 (제목 기준)
            seen_titles = set()
            unique_news = []
            for news in news_items:
                if news['title'] not in seen_titles:
                    seen_titles.add(news['title'])
                    unique_news.append(news)

            logger.info(f"총 {len(unique_news)}개 뉴스 수집 완료")
            return unique_news[:limit]

        except Exception as e:
            logger.error(f"뉴스 리스트 수집 실패: {e}")
            return []

    def get_news_content(self, news_url: str) -> Optional[str]:
        """개별 뉴스 기사 내용 가져오기"""
        try:
            logger.info(f"뉴스 내용 수집: {news_url}")

            # 지연 시간 추가
            time.sleep(Config.REQUEST_DELAY)

            response = self._make_request(news_url)
            if not response:
                return None

            soup = BeautifulSoup(response.text, 'html.parser')

            # 다양한 뉴스 사이트의 본문 선택자들
            content_selectors = [
                # 네이버 뉴스
                '#articleBodyContents',
                '.news_article .article_body',
                '.article_body',
                '.news_content',
                '#newsEndContents',
                '.article_txt',

                # 일반적인 뉴스 사이트
                '.article_content',
                '.news_text',
                '.content_area',
                '.article_wrap .content',
                '.news_wrap .content',
                '.view_content',
                '.post_content',

                # 백업 선택자
                '.content',
                'article',
                '.main_content'
            ]

            content = ""
            for selector in content_selectors:
                content_element = soup.select_one(selector)
                if content_element:
                    # 스크립트, 광고, 스타일 등 제거
                    for unwanted in content_element.select('script, style, .ad, .advertisement, .banner, .recommend'):
                        unwanted.decompose()

                    content = content_element.get_text(strip=True)
                    if len(content) > 100:  # 의미있는 길이의 콘텐츠
                        logger.info(f"본문 추출 성공: {selector} 선택자, {len(content)}자")
                        break

            # 본문을 찾지 못한 경우 전체 텍스트에서 추출
            if len(content) < 100:
                logger.warning("본문 선택자로 내용을 찾지 못함. 전체 텍스트에서 추출 시도...")

                # 불필요한 요소들 제거
                for unwanted in soup.select('script, style, nav, header, footer, .menu, .navigation, .sidebar'):
                    unwanted.decompose()

                # 본문으로 보이는 텍스트 추출
                all_text = soup.get_text()
                paragraphs = [p.strip() for p in all_text.split('\n') if len(p.strip()) > 30]

                # 뉴스 본문으로 보이는 문단들만 선택 (길이와 내용 기준)
                content_paragraphs = []
                for p in paragraphs:
                    if (len(p) > 30 and len(p) < 500 and
                        not any(skip_word in p for skip_word in ['로그인', '회원가입', '댓글', '광고', '구독', '팔로우'])):
                        content_paragraphs.append(p)

                    if len(content_paragraphs) >= 10:  # 최대 10개 문단
                        break

                content = '\n'.join(content_paragraphs)

            # 내용이 너무 길면 자르기
            if len(content) > 2000:
                content = content[:2000] + "..."

            logger.info(f"뉴스 내용 수집 완료: {len(content)}자")
            return content if len(content) > 50 else None

        except Exception as e:
            logger.error(f"뉴스 내용 수집 실패 ({news_url}): {e}")
            return None

    def get_complete_news_data(self, limit: int = 5) -> List[Dict[str, str]]:
        """제목과 내용이 포함된 완전한 뉴스 데이터 가져오기"""
        news_list = self.get_top_news_list(limit)

        if not news_list:
            logger.error("뉴스 리스트를 가져올 수 없습니다.")
            return []

        for i, news_item in enumerate(news_list, 1):
            logger.info(f"뉴스 내용 수집 {i}/{len(news_list)}: {news_item['title'][:30]}...")

            content = self.get_news_content(news_item['url'])
            if content:
                news_item['content'] = content
            else:
                # 내용을 가져올 수 없으면 제목을 기본 내용으로 사용
                news_item['content'] = f"제목: {news_item['title']}\n\n상세 내용을 확인하려면 링크를 방문하세요."
                logger.warning(f"뉴스 {i} 내용 수집 실패, 제목으로 대체")

        logger.info(f"완전한 뉴스 데이터 {len(news_list)}개 수집 완료")
        return news_list

    def _make_request(self, url: str, retries: int = 0) -> Optional[requests.Response]:
        """HTTP 요청 수행 (재시도 로직 포함)"""
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            return response

        except requests.RequestException as e:
            if retries < Config.MAX_RETRIES:
                wait_time = 2 ** retries  # 지수 백오프
                logger.warning(f"요청 실패 ({retries + 1}/{Config.MAX_RETRIES}), {wait_time}초 후 재시도: {e}")
                time.sleep(wait_time)
                return self._make_request(url, retries + 1)
            else:
                logger.error(f"최대 재시도 횟수 초과: {e}")
                return None

def test_crawler():
    """크롤러 테스트 함수"""
    try:
        crawler = NaverRealEstateNewsCrawler()

        # 뉴스 리스트만 테스트
        logger.info("=== 뉴스 리스트 수집 테스트 ===")
        news_list = crawler.get_top_news_list(3)

        if news_list:
            print(f"\n수집된 뉴스 {len(news_list)}개:")
            for i, news in enumerate(news_list, 1):
                print(f"{i}. {news['title']}")
                print(f"   URL: {news['url']}")
                print()
        else:
            print("뉴스를 수집하지 못했습니다.")
            return

        # 첫 번째 뉴스 내용 수집 테스트
        logger.info("=== 뉴스 내용 수집 테스트 ===")
        if news_list:
            content = crawler.get_news_content(news_list[0]['url'])
            if content:
                print(f"첫 번째 뉴스 내용 ({len(content)}자):")
                print(content[:200] + "..." if len(content) > 200 else content)
            else:
                print("뉴스 내용 수집 실패")

    except Exception as e:
        logger.error(f"크롤러 테스트 실패: {e}")
        print(f"테스트 실패: {e}")

if __name__ == "__main__":
    test_crawler()
