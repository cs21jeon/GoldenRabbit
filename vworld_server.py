from flask import Flask, request, jsonify, make_response
import requests
import os
import json
from dotenv import load_dotenv
from flask_cors import CORS
import logging
from functools import lru_cache
import anthropic  # Claude API를 위한 패키지 추가
import feedparser  # 네이버 블로그 RSS를 파싱하기 위해 필요
from datetime import datetime, timedelta

# 환경 변수 로드
load_dotenv()

# Flask 앱 설정
app = Flask(__name__)
CORS(app)  # CORS 지원 추가
vworld_key = os.environ.get("VWORLD_APIKEY")

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 블로그 캐시 저장 변수
blog_cache = {
    "timestamp": None,
    "posts": []
}

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

@app.route('/api/search-map', methods=['POST'])
def search_map():
    """검색 조건에 따른 동적 지도 생성"""
    try:
        import folium
        from datetime import datetime
        
        # 검색 조건 받기
        data = request.json
        logger.info(f"Search conditions: {data}")
        
        # Airtable에서 데이터 가져오기 (환경 변수에서 읽기)
        airtable_key = os.environ.get("AIRTABLE_API_KEY")
        base_id = os.environ.get("AIRTABLE_BASE_ID", "appGSg5QfDNKgFf73")
        table_id = os.environ.get("AIRTABLE_TABLE_ID", "tblnR438TK52Gr0HB")
        view_id = os.environ.get("AIRTABLE_ALL_VIEW_ID", "viwyV15T4ihMpbDbr")
        
        if not airtable_key:
            logger.error("AIRTABLE_API_KEY not set")
            return jsonify({"error": "Airtable API key not set"}), 500
            
        headers = {
            "Authorization": f"Bearer {airtable_key}"
        }
        
        # 뷰 ID를 URL 파라미터로 추가
        url = f"https://api.airtable.com/v0/{base_id}/{table_id}"
        if view_id:
            url += f"?view={view_id}"
        
        logger.info(f"Fetching data from: {url}")
        
        try:
            response = requests.get(url, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"Airtable API error: {response.status_code}")
                return jsonify({
                    "error": "Airtable data fetch failed",
                    "details": response.text
                }), response.status_code
                
        except Exception as e:
            logger.error(f"Request error: {str(e)}")
            return jsonify({"error": f"Request error: {str(e)}"}), 500
        
        # 데이터 처리
        airtable_data = response.json()
        all_records = airtable_data.get('records', [])
        logger.info(f"Total records from Airtable: {len(all_records)}")
        
        filtered_records = []
        status_filtered_count = 0
        condition_filtered_count = 0
        geocoding_failed_count = 0
        
        for record in all_records:
            fields = record.get('fields', {})
            
            # 현황 필드 확인
            status = fields.get('현황')
            valid_status = ["네이버", "디스코", "당근", "비공개"]
            is_valid_status = False
            
            if status:
                if isinstance(status, list):
                    is_valid_status = any(s in valid_status for s in status)
                elif isinstance(status, str):
                    is_valid_status = status in valid_status
            
            # 유효한 상태가 아니면 건너뛰기
            if not is_valid_status:
                status_filtered_count += 1
                continue
            
            # 각 조건 확인
            should_include = True
            filter_reasons = []
            
            # 매가 조건
            if data.get('price_value') and data.get('price_condition') != 'all':
                price = fields.get('매가(만원)', 0)
                try:
                    price = float(price) if price else 0
                    price_val = float(data['price_value'])
                    if data['price_condition'] == 'above' and price < price_val:
                        should_include = False
                        filter_reasons.append(f"가격 {price} < {price_val}")
                    elif data['price_condition'] == 'below' and price > price_val:
                        should_include = False
                        filter_reasons.append(f"가격 {price} > {price_val}")
                except Exception as e:
                    logger.warning(f"Price parsing error: {e}")
                    should_include = False
                    filter_reasons.append(f"가격 파싱 오류")
            
            # 실투자금 조건
            if should_include and data.get('investment_value') and data.get('investment_condition') != 'all':
                investment = fields.get('실투자금', 0)
                try:
                    investment = float(investment) if investment else 0
                    investment_val = float(data['investment_value'])
                    if data['investment_condition'] == 'above' and investment < investment_val:
                        should_include = False
                        filter_reasons.append(f"실투자금 {investment} < {investment_val}")
                    elif data['investment_condition'] == 'below' and investment > investment_val:
                        should_include = False
                        filter_reasons.append(f"실투자금 {investment} > {investment_val}")
                except:
                    should_include = False
                    filter_reasons.append("실투자금 파싱 오류")
            
            # 수익률 조건
            if should_include and data.get('yield_value') and data.get('yield_condition') != 'all':
                yield_rate = fields.get('융자제외수익률(%)', 0)
                try:
                    yield_rate = float(yield_rate) if yield_rate else 0
                    yield_val = float(data['yield_value'])
                    if data['yield_condition'] == 'above' and yield_rate < yield_val:
                        should_include = False
                        filter_reasons.append(f"수익률 {yield_rate} < {yield_val}")
                    elif data['yield_condition'] == 'below' and yield_rate > yield_val:
                        should_include = False
                        filter_reasons.append(f"수익률 {yield_rate} > {yield_val}")
                except:
                    should_include = False
                    filter_reasons.append("수익률 파싱 오류")
            
            # 토지면적 조건
            if should_include and data.get('area_value') and data.get('area_condition') != 'all':
                area = fields.get('토지면적(㎡)', 0)
                try:
                    area = float(area) if area else 0
                    area_val = float(data['area_value'])
                    if data['area_condition'] == 'above' and area < area_val:
                        should_include = False
                        filter_reasons.append(f"토지면적 {area} < {area_val}")
                    elif data['area_condition'] == 'below' and area > area_val:
                        should_include = False
                        filter_reasons.append(f"토지면적 {area} > {area_val}")
                except:
                    should_include = False
                    filter_reasons.append("토지면적 파싱 오류")
            
            # 사용승인일 조건
            if should_include and data.get('approval_date') and data.get('approval_condition') != 'all':
                approval = fields.get('사용승인일', '')
                try:
                    if approval:
                        approval_datetime = datetime.strptime(approval, '%Y-%m-%d')
                        target_datetime = datetime.strptime(data['approval_date'], '%Y-%m-%d')
                        
                        if data['approval_condition'] == 'before' and approval_datetime >= target_datetime:
                            should_include = False
                            filter_reasons.append(f"사용승인일 {approval} >= {data['approval_date']}")
                        elif data['approval_condition'] == 'after' and approval_datetime <= target_datetime:
                            should_include = False
                            filter_reasons.append(f"사용승인일 {approval} <= {data['approval_date']}")
                except Exception as e:
                    logger.warning(f"Date parsing error: {e}")
                    should_include = False
                    filter_reasons.append("날짜 파싱 오류")
            
            if not should_include:
                condition_filtered_count += 1
                logger.debug(f"Record filtered out: {fields.get('지번 주소', 'Unknown')} - Reasons: {filter_reasons}")
            else:
                filtered_records.append(record)
        
        logger.info(f"Filtering summary:")
        logger.info(f"  - Total records: {len(all_records)}")
        logger.info(f"  - Status filtered: {status_filtered_count}")
        logger.info(f"  - Condition filtered: {condition_filtered_count}")
        logger.info(f"  - Passed filter: {len(filtered_records)}")
        
        # 지도 생성
        folium_map = folium.Map(location=[37.4834458778777, 126.970207234818], zoom_start=15)
        
        # 타일 레이어 추가
        folium.TileLayer(
            tiles='https://goldenrabbit.biz/api/vtile?z={z}&y={y}&x={x}',
            attr='공간정보 오픈플랫폼(브이월드)',
            name='브이월드 배경지도',
        ).add_to(folium_map)
        
        # 마커 추가
        added_markers = 0
        for record in filtered_records:
            fields = record.get('fields', {})
            address = fields.get('지번 주소')
            price = fields.get('매가(만원)')
            record_id = record.get('id')
            
            if not address:
                logger.warning("No address found in record")
                continue
                
            # 주소 지오코딩
            try:
                geo_data, _ = get_geocode(address)
                if geo_data.get("response", {}).get("status") == "OK":
                    result = geo_data["response"]["result"]
                    lat = float(result["point"]["y"])
                    lon = float(result["point"]["x"])
                    logger.debug(f"Geocoding success for {address}: {lat}, {lon}")
                else:
                    logger.warning(f"Geocoding failed for {address}: {geo_data}")
                    geocoding_failed_count += 1
                    continue
            except Exception as e:
                logger.warning(f"Geocoding error for {address}: {e}")
                geocoding_failed_count += 1
                continue
            
            # 가격 표시 형식
            try:
                if isinstance(price, (int, float)):
                    price_display = f"{int(price):,}만원" if price < 10000 else f"{price / 10000:.1f}억원".rstrip('0').rstrip('.')
                else:
                    price_display = "가격정보 없음"
            except:
                price_display = "가격정보 없음"
            
            # 팝업 HTML
            popup_html = f"""
            <div style="font-family: 'Noto Sans KR', sans-serif;">
                <div style="font-size: 16px; font-weight: bold; margin-bottom: 6px;">{address}</div>
                <div style="color: #444;">매가: {price_display}</div>
            """
            
            if fields.get('토지면적(㎡)'):
                try:
                    sqm = float(fields['토지면적(㎡)'])
                    pyeong = round(sqm / 3.3058)
                    popup_html += f'<div style="color: #444;">대지: {pyeong}평 ({sqm}㎡)</div>'
                except:
                    pass
            
            if fields.get('층수'):
                popup_html += f'<div style="color: #444;">층수: {fields["층수"]}</div>'
            
            if fields.get('주용도'):
                popup_html += f'<div style="color: #444;">용도: {fields["주용도"]}</div>'
            
            # 에어테이블 링크
            airtable_url = f"https://airtable.com/{base_id}/{table_id}/viwyV15T4ihMpbDbr/{record_id}?blocks=hide"
            popup_html += f'<a href="{airtable_url}" target="_blank" style="display: block; margin-top: 10px; padding: 5px; background-color: #f5f5f5; text-align: center; color: #e38000; text-decoration: none;">상세내역보기</a>'
            popup_html += f'<a href="javascript:void(0);" onclick="parent.openConsultModal(\'{address}\')" style="display: block; margin-top: 5px; padding: 5px; background-color: #2962FF; color: white; text-align: center; text-decoration: none;">이 매물 문의하기</a>'
            popup_html += "</div>"
            
            # 가격 말풍선 아이콘
            bubble_html = f"""
            <div style="background-color: #fff; border: 2px solid #e38000; border-radius: 6px; 
                       box-shadow: 0 2px 5px rgba(0,0,0,0.2); padding: 3px 6px; font-size: 13px; 
                       font-weight: bold; color: #e38000; white-space: nowrap; text-align: center;">
                {price_display}
            </div>
            """
            
            icon = folium.DivIcon(
                html=bubble_html,
                icon_size=(100, 40),
                icon_anchor=(50, 40)
            )
            
            folium.Marker(
                location=[lat, lon],
                popup=folium.Popup(popup_html, max_width=250),
                icon=icon
            ).add_to(folium_map)
            
            added_markers += 1
        
        logger.info(f"Added {added_markers} markers to the map")
        logger.info(f"Geocoding failed for {geocoding_failed_count} addresses")
        
        # HTML 문자열로 반환
        map_html = folium_map._repr_html_()
        
        return jsonify({
            "map_html": map_html,
            "count": len(filtered_records),
            "statistics": {
                "total_records": len(all_records),
                "status_filtered": status_filtered_count,
                "condition_filtered": condition_filtered_count,
                "passed_filter": len(filtered_records),
                "geocoding_failed": geocoding_failed_count,
                "markers_added": added_markers
            }
        })
        
    except Exception as e:
        logger.error(f"Search map error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e), "details": traceback.format_exc()}), 500

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
        view_id = os.environ.get("AIRTABLE_ALL_VIEW_ID", "viwyV15T4ihMpbDbr")
        
        if not airtable_key:
            return jsonify({"error": "Airtable API key not set"}), 500
            
        headers = {
            "Authorization": f"Bearer {airtable_key}"
        }
        
        # 뷰 ID를 URL 파라미터로 추가
        url = f"https://api.airtable.com/v0/{base_id}/{table_id}"
        if view_id:
            url += f"?view={view_id}"
        
        # API 요청 로깅
        logger.info(f"Requesting Airtable data from: {url}")

        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            logger.error(f"Failed to fetch properties: {response.text}")
            return jsonify({"error": "Failed to fetch property data"}), 500
        
        # 응답 로깅
        logger.info(f"Airtable response status: {response.status_code}")
        logger.info(f"Airtable response length: {len(response.text)} characters")

        # 에어테이블 데이터 처리
        properties_data = response.json()
        
        # 레코드 수 로깅
        record_count = len(properties_data.get('records', []))
        logger.info(f"Received {record_count} records from Airtable")

        # 첫 번째 레코드의 필드명 로깅
        if record_count > 0:
            first_record = properties_data['records'][0]
            logger.info(f"Sample record ID: {first_record.get('id')}")
            logger.info(f"Available fields: {', '.join(first_record.get('fields', {}).keys())}")
        
        properties = []

        for record in properties_data.get('records', []):
            fields = record.get('fields', {})
            
            # 매물 정보 구조화 (필요한 필드만 추출)
            property_info = {
                "id": record.get('레코드id', ''),
                "address": fields.get('지번 주소', ''),
                "price": fields.get('매가(만원)', ''),
                "actual_investment": fields.get('실투자금', ''),
                "monthly_income": fields.get('월세(만원)', ''),
                "yield": fields.get('융자제외수익률(%)', ''),
                "property_type": fields.get('주용도', ''),
                "area": fields.get('토지면적(㎡)', '')
            }
            properties.append(property_info)
        
        # 처리된 데이터 로깅
        logger.info(f"Processed {len(properties)} properties")
        
        # 첫 번째 처리된 매물 정보 로깅
        if properties:
            logger.info(f"Sample processed property: {json.dumps(properties[0], ensure_ascii=False)}")
        else:
            logger.warning("No properties were processed successfully")

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
        
        위치: [주소]
        가격: [매매가]
        주용도: [주용도]
        수익률: [수익률]
        추천 이유: [이 사용자에게 왜 이 매물이 적합한지 간단히 설명]
        
        매물 2: ...
        
        조건에 맞는 매물이 없으면 '조건에 맞는 매물이 없습니다'라고 답변해주세요.

        결과 출력하는 맨 아래에는 "더 많은 매물이 궁금하시다면 아래 '상담문의'를 남겨주세요.
        빠른 시일 내에 답변드리겠습니다."라는 문구를 출력해 주세요.
        """
        
        # Claude API 호출
        logger.info("Calling Claude API for property recommendations")
        response = claude_client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=1000,
            system="당신은 부동산 투자 전문가입니다. 사용자의 조건에 맞는 최적의 매물을 추천해주세요. 만일 딱 맞는 조건이 없다면 가장 근접한 조건으로 선택해 주세요. 참고로 자료에 나타난 단위는 모두 만원 단위야. 예를들어 150000은 15억원과 같이",
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

@app.route('/api/blog-feed')
def blog_feed():
    now = datetime.now()
    cache_duration = timedelta(hours=24)

    # 캐시가 있고, 24시간 이내이면 재사용
    if blog_cache["timestamp"] and now - blog_cache["timestamp"] < cache_duration:
        return jsonify(blog_cache["posts"])

    feed_url = "https://rss.blog.naver.com/goldenrabbit7377.xml"  
    feed = feedparser.parse(feed_url)

    posts = []
    for entry in feed.entries[:10]:  # ✨ 최신 10개까지 가져오기
        posts.append({
            "title": entry.title,
            "link": entry.link,
            "summary": entry.summary,
            "published": entry.published
        })

    # 캐시 저장
    blog_cache["timestamp"] = now
    blog_cache["posts"] = posts

    return jsonify(posts)

@app.route('/health')
def health_check():
    """서버 상태 확인용 엔드포인트"""
    return jsonify({"status": "healthy"})

if __name__ == '__main__':
    logger.info(f"Starting server on port 8000")
    # 개발 환경에서는 debug=True 사용 가능, 프로덕션에서는 False로 설정
    app.run(host="0.0.0.0", port=8000, debug=False)