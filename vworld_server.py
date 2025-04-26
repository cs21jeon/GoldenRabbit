from flask import Flask, request, jsonify, make_response
import requests
import os
import json
from dotenv import load_dotenv
from flask_cors import CORS
import logging
from functools import lru_cache
import anthropic  # Claude API를 위한 패키지 추가

# 환경 변수 로드
load_dotenv()

# Flask 앱 설정
app = Flask(__name__)
CORS(app)  # CORS 지원 추가
vworld_key = os.environ.get("VWORLD_APIKEY")

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Anthropic API 키 설정
anthropic_api_key = os.environ.get('ANTHROPIC_API_KEY')
claude_client = anthropic.Anthropic(api_key=anthropic_api_key)

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
    logger.info(f"Received inquiry submission: {data}")

    # 매물 종류 매핑 - 에어테이블에 실제 존재하는 옵션으로 변환
    property_type_map = {
        'house': '단독/다가구',
        'mixed': '상가주택', 
        'commercial': '상업용빌딩',
        'land': '재건축/토지',
        'sell': '매물접수'
    }

    # 받은 propertyType을 에어테이블에 있는 값으로 매핑
    property_type = property_type_map.get(data.get("propertyType"), "기타")
    
    # 구분된 Airtable API 설정
    airtable_inquiry_key = os.environ.get("AIRTABLE_INQUIRY_KEY")
    base_id = os.environ.get("AIRTABLE_INQUIRY_BASE_ID", "appBm845MhVkkaBD1")
    table_id = os.environ.get("AIRTABLE_INQUIRY_TABLE_ID", "tblgik4xDNNPb8WUE")

    if not airtable_inquiry_key:
        logger.error("AIRTABLE_INQUIRY_KEY not set")
        return jsonify({"error": "Inquiry API key not set"}), 500

    payload = {
        "records": [
            {
                "fields": {
                    "매물종류": property_type,
                    "연락처": data.get("phone"),
                    "이메일": data.get("email"),
                    "문의사항": data.get("message")
                }
            }
        ]
    }

    headers = {
        "Authorization": f"Bearer {airtable_inquiry_key}",
        "Content-Type": "application/json"
    }

    url = f"https://api.airtable.com/v0/{base_id}/{table_id}"
    try:
        # 디버깅 로그 추가
        print(f"Sending to Airtable: {url}")
        print(f"Payload: {payload}")
        
        response = requests.post(url, json=payload, headers=headers)

        # 응답 디버깅
        print(f"Airtable response status: {response.status_code}")
        print(f"Airtable response: {response.text}")
        
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

# AI 물건 검색 기능 추가
@app.route('/api/property-search', methods=['POST'])
def property_search():
    try:
        # Anthropic API 키 확인
        if not anthropic_api_key:
            logger.error("ANTHROPIC_API_KEY environment variable is not set")
            return jsonify({"error": "AI API key not configured"}), 500
            
        # 사용자 입력 받기
        data = request.json
        location = data.get('location', '')
        price_range = data.get('price_range', '')
        investment = data.get('investment', '')
        expected_yield = data.get('expected_yield', '')
        
        logger.info(f"AI property search request: location={location}, price_range={price_range}, investment={investment}, expected_yield={expected_yield}")
        
        # Airtable에서 매물 데이터 가져오기
        airtable_key = os.environ.get("AIRTABLE_API_KEY")
        base_id = os.environ.get("AIRTABLE_BASE_ID", "appGSg5QfDNKgFf73")
        table_id = os.environ.get("AIRTABLE_TABLE_ID", "tblnR438TK52Gr0HB")
        view_id = os.environ.get("AIRTABLE_VIEW_ID")
        
        if not airtable_key:
            return jsonify({"error": "Airtable API key not set"}), 500
            
        headers = {
            "Authorization": f"Bearer {airtable_key}"
        }
        
        # 뷰 ID를 URL 파라미터로 추가
        url = f"https://api.airtable.com/v0/{base_id}/{table_id}"
        if view_id:
            url += f"?view={view_id}"
        
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            logger.error(f"Failed to fetch properties: {response.text}")
            return jsonify({"error": "Failed to fetch property data"}), 500
        
        # 에어테이블 데이터 처리
        properties_data = response.json()
        properties = []
        
        for record in properties_data.get('records', []):
            fields = record.get('fields', {})
            
            # 매물 정보 구조화 (필요한 필드만 추출)
            property_info = {
                "id": record.get('id', ''),
                "name": fields.get('건물명', ''),
                "address": fields.get('주소', ''),
                "price": fields.get('매매가', ''),
                "monthly_income": fields.get('월소득', ''),
                "yield": fields.get('수익률', ''),
                "property_type": fields.get('건물종류', ''),
                "area": fields.get('대지면적', '')
            }
            properties.append(property_info)
        
        # 데이터 양이 너무 많으면 제한
        if len(properties) > 15:
            logger.info(f"Limiting properties from {len(properties)} to 15")
            properties = properties[:15]
        
        # Claude에 전송할 프롬프트 구성
        prompt = f"""
        다음은 부동산 매물 목록입니다:
        {json.dumps(properties, ensure_ascii=False, indent=2)}
        
        사용자의 검색 조건:
        - 지역: {location}
        - 희망매매가: {price_range}
        - 실투자금: {investment}
        - 희망투자수익률: {expected_yield}
        
        위 조건에 가장 적합한 매물 2-3개를 추천해주세요. 각 매물에 대해 다음 형식으로 답변해주세요:
        
        매물 1: [매물명]
        가격: [매매가]
        위치: [주소]
        수익률: [수익률]
        추천 이유: [이 사용자에게 왜 이 매물이 적합한지 간단히 설명]
        
        매물 2: ...
        
        조건에 맞는 매물이 없으면 '조건에 맞는 매물이 없습니다'라고 답변해주세요.
        """
        
        # Claude API 호출
        logger.info("Calling Claude API for property recommendations")
        response = claude_client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=1000,
            system="당신은 부동산 투자 전문가입니다. 사용자의 조건에 맞는 최적의 매물을 추천해주세요.",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        recommendations = response.content[0].text
        logger.info(f"Claude API response received: {len(recommendations)} characters")
        
        return jsonify({
            "recommendations": recommendations
        })
        
    except Exception as e:
        logger.error(f"AI property search error: {str(e)}")
        return jsonify({"error": f"Error processing request: {str(e)}"}), 500

# 임시 테스트 엔드포인트 추가 (vworld_server.py에 추가)
@app.route('/api/test-airtable-data', methods=['GET'])
def test_airtable_data():
    airtable_key = os.environ.get("AIRTABLE_API_KEY")
    base_id = os.environ.get("AIRTABLE_BASE_ID", "appGSg5QfDNKgFf73")
    table_id = os.environ.get("AIRTABLE_TABLE_ID", "tblnR438TK52Gr0HB")
    
    if not airtable_key:
        return jsonify({"error": "Airtable API key not set"}), 500
        
    headers = {
        "Authorization": f"Bearer {airtable_key}"
    }
    
    url = f"https://api.airtable.com/v0/{base_id}/{table_id}?maxRecords=3"
    
    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            return jsonify({
                "error": "Airtable API error", 
                "status_code": response.status_code,
                "details": response.text
            }), 500
            
        return jsonify({
            "success": True,
            "record_count": len(response.json().get('records', [])),
            "first_three_records": response.json().get('records', [])
        })
            
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