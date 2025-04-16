from flask import Flask, request, jsonify, make_response
import requests
import os
from dotenv import load_dotenv
from flask_cors import CORS
import logging
from functools import lru_cache

# 환경 변수 로드
load_dotenv()

# Flask 앱 설정
app = Flask(__name__)
CORS(app)  # CORS 지원 추가
vworld_key = os.environ.get("VWORLD_APIKEY")

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 캐싱 적용 (최근 100개 요청 캐싱)
@lru_cache(maxsize=100)
def get_geocode(address):
    url = "https://api.vworld.kr/req/address"  # HTTPS 사용
    params = {
        "service": "address",
        "request": "getcoord",
        "format": "json",
        "crs": "EPSG:4326",
        "type": "PARCEL",  # 지번 주소 검색 유형 추가
        "address": address,
        "key": vworld_key
    }
    
    response = requests.get(url, params=params)
    return response.json(), response.status_code

@app.route('/api/vworld')
def vworld_geocode():
    address = request.args.get('address')
    if not address:
        return jsonify({"error": "Missing address parameter"}), 400
    
    logger.info(f"Geocoding request for address: {address}")
    
    try:
        # API 키 확인
        if not vworld_key:
            logger.error("VWORLD_APIKEY environment variable is not set")
            return jsonify({"error": "API key not configured"}), 500
        
        # 캐싱된 함수 호출
        data, status_code = get_geocode(address)
        
        # API 응답 확인
        if status_code != 200:
            logger.error(f"V-World API returned status code {status_code}")
            return jsonify({"error": f"External API error: {status_code}"}), status_code
        
        # 응답 데이터에 오류가 있는지 확인
        response_status = data.get("response", {}).get("status")
        if response_status != "OK":
            logger.warning(f"V-World API returned non-OK status: {response_status}")
            error_message = data.get("response", {}).get("error", {}).get("text", "Unknown error")
            return jsonify({"error": error_message, "data": data}), 400
        
        return jsonify(data)
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {str(e)}")
        return jsonify({"error": f"Connection error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

# V-World 타일 프록시 엔드포인트 추가
@app.route('/api/vtile')
def vworld_tile():
    """V-World 타일을 프록시하는 엔드포인트"""
    try:
        z = request.args.get('z')
        y = request.args.get('y')
        x = request.args.get('x')
        
        if not all([z, y, x]):
            return jsonify({"error": "Missing parameters"}), 400
            
        url = f"https://api.vworld.kr/req/wmts/1.0.0/{vworld_key}/Base/{z}/{y}/{x}.png"
        response = requests.get(url)
        
        # Response 객체 대신 make_response 사용
        return make_response(
            response.content, 
            response.status_code,
            {'Content-Type': response.headers.get('Content-Type', 'image/png')}
        )
    except Exception as e:
        logger.error(f"Tile proxy error: {str(e)}")
        return jsonify({"error": str(e)}), 500

# V-World WMS 프록시 엔드포인트 추가
@app.route('/api/wms')
def vworld_wms():
    """V-World WMS를 프록시하는 엔드포인트"""
    try:
        # WMS 파라미터 전달
        params = {k: v for k, v in request.args.items()}
        params['key'] = vworld_key  # API 키 추가
        
        url = "https://api.vworld.kr/req/wms"
        response = requests.get(url, params=params)
        
        # Response 객체 대신 make_response 사용
        return make_response(
            response.content, 
            response.status_code,
            {'Content-Type': response.headers.get('Content-Type', 'image/png')}
        )
    except Exception as e:
        logger.error(f"WMS proxy error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health_check():
    """서버 상태 확인용 엔드포인트"""
    return jsonify({"status": "healthy"})

if __name__ == '__main__':
    logger.info(f"Starting server on port 8000")
    # 개발 환경에서는 debug=True 사용 가능, 프로덕션에서는 False로 설정
    app.run(host="0.0.0.0", port=8000, debug=False)