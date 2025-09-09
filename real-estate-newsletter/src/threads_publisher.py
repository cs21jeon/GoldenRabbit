import logging
import requests
import time
from typing import Optional, Dict, Any, List
from .config import Config

logger = logging.getLogger(__name__)

class ThreadsPublisher:
    def __init__(self):
        required_config = [
            'THREADS_ACCESS_TOKEN',
            'THREADS_USER_ID'
        ]

        for config_key in required_config:
            if not getattr(Config, config_key):
                raise ValueError(f"{config_key}가 설정되지 않았습니다.")

        self.access_token = Config.THREADS_ACCESS_TOKEN
        self.user_id = Config.THREADS_USER_ID
        self.api_base = Config.THREADS_API_BASE

    def create_threaded_post(self, main_content: str, reply_contents: List[str]) -> Optional[str]:
        """메인 게시물과 댓글들을 연결해서 게시"""
        try:
            # 1. 메인 게시물 작성
            logger.info("메인 게시물 작성 중...")
            container_id = self._create_media_container(main_content)
            if not container_id:
                logger.error("메인 게시물 컨테이너 생성 실패")
                return None
            
            main_post_id = self._publish_media_container(container_id)
            if not main_post_id:
                logger.error("메인 게시물 발행 실패")
                return None
            
            logger.info(f"메인 게시물 작성 성공: {main_post_id}")
            
            # 메인 게시물 완전 처리 대기 (중요!)
            logger.info("메인 게시물 완전 처리 대기 중...")
            time.sleep(10)  # 10초 대기
            
            # 2. 각 댓글을 메인 게시물에 연결
            reply_ids = []
            for i, reply_content in enumerate(reply_contents, 1):
                logger.info(f"댓글 {i}/{len(reply_contents)} 작성 중...")
                
                # 댓글 작성 전 추가 대기
                if i > 1:
                    time.sleep(5)  # 댓글 간 5초 간격
                
                reply_id = self.create_reply_post(reply_content, main_post_id)
                if reply_id:
                    reply_ids.append(reply_id)
                    logger.info(f"댓글 {i} 작성 성공: {reply_id}")
                else:
                    logger.warning(f"댓글 {i} 작성 실패, 재시도...")
                    # 한 번 더 시도
                    time.sleep(3)
                    retry_id = self.create_reply_post(reply_content, main_post_id)
                    if retry_id:
                        reply_ids.append(retry_id)
                        logger.info(f"댓글 {i} 재시도 성공: {retry_id}")
            
            logger.info(f"전체 스레드 작성 완료 - 메인: {main_post_id}, 댓글: {len(reply_ids)}개")
            return main_post_id
            
        except Exception as e:
            logger.error(f"스레드 게시 실패: {e}")
            return None

    def create_reply_post(self, text: str, parent_id: str) -> Optional[str]:
        """댓글 게시물 생성"""
        try:
            # 1단계: 댓글 컨테이너 생성
            container_id = self._create_reply_container(text, parent_id)
            if not container_id:
                return None
            
            # 2단계: 댓글 발행
            reply_id = self._publish_media_container(container_id)
            return reply_id
            
        except Exception as e:
            logger.error(f"댓글 작성 실패: {e}")
            return None

    def _create_reply_container(self, text: str, parent_id: str) -> Optional[str]:
        """댓글 컨테이너 생성"""
        try:
            url = f"{self.api_base}/{self.user_id}/threads"
            
            data = {
                'media_type': 'TEXT',
                'text': text,
                'reply_to_id': parent_id,  # 부모 게시물 ID
                'access_token': self.access_token
            }
            
            logger.info(f"댓글 컨테이너 생성 요청: {len(text)}자")
            
            response = requests.post(url, data=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                container_id = result.get('id')
                
                if container_id:
                    logger.info(f"댓글 컨테이너 생성 성공: {container_id}")
                    return container_id
                else:
                    logger.error(f"댓글 컨테이너 ID 없음: {result}")
                    return None
            else:
                logger.error(f"댓글 컨테이너 생성 실패: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"댓글 컨테이너 생성 중 오류: {e}")
            return None

    def _create_media_container(self, text: str, link_attachment: Optional[str] = None) -> Optional[str]:
        """1단계: 미디어 컨테이너 생성"""
        try:
            url = f"{self.api_base}/{self.user_id}/threads"

            data = {
                'media_type': 'TEXT',
                'text': text,
                'access_token': self.access_token
            }

            # 링크 첨부가 있는 경우
            if link_attachment:
                data['link_attachment'] = link_attachment

            logger.info(f"Threads 컨테이너 생성 요청: {len(text)}자")

            response = requests.post(url, data=data, timeout=30)

            if response.status_code == 200:
                result = response.json()
                container_id = result.get('id')

                if container_id:
                    logger.info(f"컨테이너 생성 성공: {container_id}")
                    return container_id
                else:
                    logger.error(f"컨테이너 ID를 받지 못함: {result}")
                    return None
            else:
                logger.error(f"컨테이너 생성 실패: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"컨테이너 생성 중 오류: {e}")
            return None

    def _publish_media_container(self, container_id: str) -> Optional[str]:
        """2단계: 미디어 컨테이너 발행"""
        try:
            url = f"{self.api_base}/{self.user_id}/threads_publish"

            data = {
                'creation_id': container_id,
                'access_token': self.access_token
            }

            logger.info(f"Threads 게시물 발행 요청: {container_id}")

            response = requests.post(url, data=data, timeout=30)

            if response.status_code == 200:
                result = response.json()
                post_id = result.get('id')

                if post_id:
                    logger.info(f"게시물 발행 성공: {post_id}")
                    return post_id
                else:
                    logger.error(f"Post ID를 받지 못함: {result}")
                    return None
            else:
                logger.error(f"게시물 발행 실패: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"게시물 발행 중 오류: {e}")
            return None

    def get_user_profile(self) -> Optional[Dict[str, Any]]:
        """사용자 프로필 정보 가져오기 (연결 테스트용)"""
        try:
            url = f"{self.api_base}/{self.user_id}"
            params = {
                'fields': 'id,username,name,threads_profile_picture_url,threads_biography',
                'access_token': self.access_token
            }

            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                profile = response.json()
                logger.info(f"프로필 조회 성공: {profile.get('username', 'Unknown')}")
                return profile
            else:
                logger.error(f"프로필 조회 실패: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"프로필 조회 중 오류: {e}")
            return None

    def get_user_threads(self, limit: int = 10) -> Optional[list]:
        """사용자가 작성한 최근 게시물 가져오기"""
        try:
            url = f"{self.api_base}/{self.user_id}/threads"
            params = {
                'fields': 'id,media_type,text,timestamp,permalink',
                'limit': limit,
                'access_token': self.access_token
            }

            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                result = response.json()
                threads = result.get('data', [])
                logger.info(f"게시물 조회 성공: {len(threads)}개")
                return threads
            else:
                logger.error(f"게시물 조회 실패: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"게시물 조회 중 오류: {e}")
            return None

    def test_connection(self) -> bool:
        """Threads API 연결 테스트"""
        try:
            logger.info("Threads API 연결 테스트 시작...")

            # 프로필 정보 가져오기로 연결 테스트
            profile = self.get_user_profile()

            if profile:
                username = profile.get('username', 'Unknown')
                user_id = profile.get('id', 'Unknown')
                logger.info(f"연결 테스트 성공 - 사용자: {username} (ID: {user_id})")
                return True
            else:
                logger.error("연결 테스트 실패 - 프로필 정보를 가져올 수 없음")
                return False

        except Exception as e:
            logger.error(f"연결 테스트 중 오류: {e}")
            return False

def test_threads_publisher():
    """Threads 발행기 테스트"""
    try:
        publisher = ThreadsPublisher()

        # 연결 테스트
        if not publisher.test_connection():
            print("Threads API 연결 실패")
            return

        # 테스트 게시물 작성
        test_text = """🏠 테스트 게시물

부동산 뉴스레터 자동화 시스템 테스트 중입니다.

📊 #부동산뉴스 #골든래빗 #테스트"""

        print("테스트 게시물 작성 중...")
        post_id = publisher.create_threads_post(test_text)

        if post_id:
            print(f"테스트 게시 성공! Post ID: {post_id}")
        else:
            print("테스트 게시 실패")

        # 최근 게시물 조회
        print("\n최근 게시물 조회 중...")
        threads = publisher.get_user_threads(5)

        if threads:
            print(f"최근 게시물 {len(threads)}개:")
            for i, thread in enumerate(threads[:3], 1):
                text = thread.get('text', '')[:50]
                timestamp = thread.get('timestamp', '')
                print(f"{i}. {text}... ({timestamp})")
        else:
            print("게시물 조회 실패")

    except Exception as e:
        print(f"테스트 실패: {e}")

if __name__ == "__main__":
    test_threads_publisher()
