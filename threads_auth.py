from flask import Blueprint, request, redirect, jsonify
import requests
import os
from urllib.parse import urlencode
import logging
from dotenv import load_dotenv

# .env 파일 로드 (절대 경로 지정)
load_dotenv('/root/goldenrabbit/.env')

# Blueprint 생성
threads_auth_bp = Blueprint('threads_auth', __name__)

# 환경변수에서 설정 가져오기
THREADS_APP_ID = os.getenv('THREADS_APP_ID')
THREADS_APP_SECRET = os.getenv('THREADS_APP_SECRET')
REDIRECT_URI = 'https://goldenrabbit.biz/auth/threads/callback'

logger = logging.getLogger(__name__)

@threads_auth_bp.route('/auth/threads')
def threads_auth():
    """Threads OAuth 인증 시작"""
    try:
        # OAuth 파라미터 설정
        params = {
            'client_id': THREADS_APP_ID,
            'redirect_uri': REDIRECT_URI,
            'scope': 'threads_basic,threads_content_publish',
            'response_type': 'code'
        }
        
        # Threads OAuth URL로 리디렉션
        auth_url = f"https://threads.net/oauth/authorize?{urlencode(params)}"
        logger.info(f"Threads OAuth 인증 시작: {auth_url}")
        
        return redirect(auth_url)
        
    except Exception as e:
        logger.error(f"Threads 인증 시작 실패: {e}")
        return jsonify({'error': 'Authentication failed'}), 500

@threads_auth_bp.route('/auth/threads/callback')
def threads_callback():
    """Threads OAuth 콜백 처리"""
    code = request.args.get('code')
    error = request.args.get('error')
    
    if error:
        logger.error(f"Threads 인증 오류: {error}")
        return jsonify({'error': f'Authentication error: {error}'}), 400
    
    if not code:
        logger.error("Threads 인증 코드 없음")
        return jsonify({'error': 'No authorization code'}), 400
    
    try:
        # Access Token 요청
        token_data = {
            'client_id': THREADS_APP_ID,
            'client_secret': THREADS_APP_SECRET,
            'grant_type': 'authorization_code',
            'redirect_uri': REDIRECT_URI,
            'code': code
        }
        
        logger.info("Threads Access Token 요청 중...")
        response = requests.post(
            'https://graph.threads.net/oauth/access_token',
            data=token_data,
            timeout=30
        )
        
        if response.status_code == 200:
            token_info = response.json()
            access_token = token_info.get('access_token')
            user_id = token_info.get('user_id')
            
            logger.info(f"Threads 토큰 획득 성공 - User ID: {user_id}")
            
            # 장기 토큰으로 교환
            long_lived_token = exchange_for_long_lived_token(access_token)
            
            # 성공 페이지 반환 (실제 토큰 정보 포함)
            return f'''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Threads 인증 성공</title>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }}
                    .success {{ color: green; }}
                    .token-info {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0; }}
                    .copy-btn {{ background: #007bff; color: white; padding: 5px 10px; border: none; border-radius: 3px; cursor: pointer; }}
                </style>
            </head>
            <body>
                <h1 class="success">✅ Threads 인증 성공!</h1>
                <p>아래 정보를 <code>.env</code> 파일에 저장하세요:</p>
                
                <div class="token-info">
                    <h3>환경변수 설정</h3>
                    <pre id="env-vars">THREADS_USER_ID={user_id}
THREADS_ACCESS_TOKEN={long_lived_token or access_token}</pre>
                    <button class="copy-btn" onclick="copyToClipboard()">복사</button>
                </div>
                
                <p><strong>User ID:</strong> {user_id}</p>
                <p><strong>Token Type:</strong> {'Long-lived' if long_lived_token else 'Short-lived'}</p>
                
                <script>
                function copyToClipboard() {{
                    const text = document.getElementById('env-vars').textContent;
                    navigator.clipboard.writeText(text).then(() => {{
                        alert('클립보드에 복사되었습니다!');
                    }});
                }}
                </script>
            </body>
            </html>
            '''
        else:
            logger.error(f"Threads 토큰 요청 실패: {response.text}")
            return jsonify({'error': f'Token request failed: {response.text}'}), 400
            
    except Exception as e:
        logger.error(f"Threads 콜백 처리 중 오류: {e}")
        return jsonify({'error': f'Callback processing failed: {str(e)}'}), 500

def exchange_for_long_lived_token(short_token):
    """단기 토큰을 장기 토큰으로 교환"""
    try:
        params = {
            'grant_type': 'th_exchange_token',
            'client_secret': THREADS_APP_SECRET,
            'access_token': short_token
        }
        
        logger.info("장기 토큰 교환 요청 중...")
        response = requests.get(
            'https://graph.threads.net/access_token',
            params=params,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            long_token = data.get('access_token')
            logger.info("장기 토큰 교환 성공")
            return long_token
        else:
            logger.warning(f"장기 토큰 교환 실패: {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"장기 토큰 교환 중 오류: {e}")
        return None

@threads_auth_bp.route('/webhook/threads', methods=['GET', 'POST'])
def threads_webhook():
    """Threads 웹훅 엔드포인트"""
    if request.method == 'GET':
        # 웹훅 검증
        verify_token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        
        # 검증 토큰 확인
        expected_verify_token = os.getenv('THREADS_WEBHOOK_VERIFY_TOKEN', 'goldenrabbit_threads_verify')
        
        if verify_token == expected_verify_token:
            logger.info("Threads 웹훅 검증 성공")
            return challenge
        else:
            logger.warning("Threads 웹훅 검증 실패")
            return 'Forbidden', 403
    
    elif request.method == 'POST':
        # 웹훅 데이터 처리
        try:
            data = request.get_json()
            logger.info(f"Threads 웹훅 데이터 수신: {data}")
            return 'OK', 200
        except Exception as e:
            logger.error(f"웹훅 처리 중 오류: {e}")
            return 'Error', 500

@threads_auth_bp.route('/deauth/threads', methods=['POST'])
def threads_deauth():
    """사용자 연결 해제 처리"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        
        logger.info(f"Threads 사용자 {user_id} 연결 해제 요청")
        
        # 여기서 해당 사용자의 토큰을 데이터베이스에서 삭제하는 로직 추가
        # 현재는 로깅만 수행
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"연결 해제 처리 중 오류: {e}")
        return jsonify({'error': str(e)}), 500

# 테스트용 엔드포인트
@threads_auth_bp.route('/threads/test')
def threads_test():
    """Threads API 연결 테스트"""
    return '''
    <h1>Threads API 테스트</h1>
    <p><a href="/auth/threads">Threads 계정 연결하기</a></p>
    <p>연결 후 받은 토큰으로 뉴스레터 서비스를 이용할 수 있습니다.</p>
    '''
