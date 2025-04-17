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

@app.route('/api/submit-inquiry', methods=['POST'])
def submit_inquiry():
    data = request.json

    # 구분된 Airtable API 설정
    airtable_inquiry_key = os.environ.get("AIRTABLE_INQUIRY_KEY")
    base_id = os.environ.get("AIRTABLE_BASE_ID", "appBm845MhVkkaBD1")
    table_id = os.environ.get("AIRTABLE_TABLE_ID", "tblgik4xDNNPb8WUE")

    if not airtable_inquiry_key:
        return jsonify({"error": "Inquiry API key not set"}), 500

    payload = {
        "fields": {
            "매물종류": data.get("propertyType"),
            "연락처": data.get("phone"),
            "이메일": data.get("email"),
            "문의사항": data.get("message")
        }
    }

    headers = {
        "Authorization": f"Bearer {airtable_inquiry_key}",
        "Content-Type": "application/json"
    }

    url = f"https://api.airtable.com/v0/{base_id}/{table_id}"
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code in [200, 201]:
            return jsonify({"status": "success"}), 200
        else:
            return jsonify({
                "error": "Airtable submission failed",
                "details": response.text
            }), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/property-list', methods=['GET'])
def get_property_list():
    airtable_key = os.environ.get("AIRTABLE_API_KEY")
    base_id = os.environ.get("AIRTABLE_BASE_ID") 
    table_id = os.environ.get("AIRTABLE_TABLE_ID")
    view_id = os.environ.get("AIRTABLE_VIEW_ID")
    
    if not airtable_key:
        return jsonify({"error": "Airtable API key not set"}), 500
        
    headers = {
        "Authorization": f"Bearer {airtable_key}"
    }
    
    # 뷰 ID를 URL 파라미터로 추가
    url = f"https://api.airtable.com/v0/{base_id}/{table_id}?view={view_id}"
    
    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            return jsonify({
                "error": "Airtable data fetch failed",
                "details": response.text
            }), response.status_code
            
        return jsonify(response.json()), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health_check():
    """서버 상태 확인용 엔드포인트"""
    return jsonify({"status": "healthy"})

if __name__ == '__main__':
    logger.info(f"Starting server on port 8000")
    # 개발 환경에서는 debug=True 사용 가능, 프로덕션에서는 False로 설정
    app.run(host="0.0.0.0", port=8000, debug=False)
