from flask import Flask, request, jsonify, make_response
import requests
import os
import re
import json
import asyncio
import threading
import time
from pathlib import Path
from dotenv import load_dotenv
from flask_cors import CORS
import logging
import traceback
from functools import lru_cache
import anthropic  # Claude API를 위한 패키지 추가
import feedparser  # 네이버 블로그 RSS를 파싱하기 위해 필요
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import undetected_chrome as uc  # 더 안정적인 Chrome 드라이버

# 글로벌 브라우저 인스턴스
browser_instance = None
browser_lock = threading.Lock()

# 이메일 설정 - 환경 변수에서 읽기
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS")  # 발송용 이메일 주소
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")  # 앱 비밀번호
ADMIN_EMAIL = "cs21.jeon@gmail.com"  # 관리자 이메일

# 버전 파일 경로 설정 - 절대 경로 사용
VERSION_FILE_PATH = '/home/sftpuser/www/version.json'

# 환경 변수 로드
load_dotenv()

# Flask 앱 설정
app = Flask(__name__)
CORS(app)  # CORS 지원 추가
vworld_key = os.environ.get("VWORLD_APIKEY")

# 로깅 설정
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# 블로그 캐시 저장 변수
blog_cache = {
    "timestamp": None,
    "posts": []
}

thumbnail_dir = "/home/sftpuser/www/blog_thumbs"
os.makedirs(thumbnail_dir, exist_ok=True)

# logNo 추출용 함수 추가
def extract_log_no(link):
    match = re.search(r'/(\d+)', link)
    return match.group(1) if match else None

def extract_image(summary):
    soup = BeautifulSoup(summary, 'html.parser')
    img_tag = soup.find('img')
    return img_tag['src'] if img_tag and 'src' in img_tag.attrs else None

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

# Flask 앱의 submit-inquiry 엔드포인트에서 매물종류 매핑 수정
@app.route('/api/submit-inquiry', methods=['POST'])
def submit_inquiry():
    logger.info("=== 상담 문의 접수 시작 ===")
    
    data = request.json
    logger.info(f"받은 데이터: {data}")

    # 매물 종류 매핑 - 에어테이블에 실제 존재하는 옵션으로 변환 (수정됨)
    property_type_map = {
        'house': '단독/다가구',
        'mixed': '상가주택', 
        'commercial': '상업용건물',  # '상업용빌딩'에서 '상업용건물'로 수정
        'land': '재건축/토지',
        'sell': '매물접수'
    }

    # 받은 propertyType을 에어테이블에 있는 값으로 매핑
    property_type = property_type_map.get(data.get("propertyType"), "기타")
    
    # 디버깅 로그 추가
    logger.info(f"Original propertyType: {data.get('propertyType')}")
    logger.info(f"Mapped propertyType: {property_type}")
    
    # 구분된 Airtable API 설정
    airtable_inquiry_key = os.environ.get("AIRTABLE_INQUIRY_KEY")
    base_id = os.environ.get("AIRTABLE_INQUIRY_BASE_ID", "appBm845MhVkkaBD1")
    table_id = os.environ.get("AIRTABLE_INQUIRY_TABLE_ID", "tblgik4xDNNPb8WUE")

    if not airtable_inquiry_key:
        logger.error("AIRTABLE_INQUIRY_KEY not set")
        return jsonify({"error": "Inquiry API key not set"}), 500

    # 필드명이 실제 Airtable 필드명과 일치하는지 확인
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
        logger.info(f"Sending to Airtable: {url}")
        logger.info(f"Payload: {payload}")
        
        response = requests.post(url, json=payload, headers=headers)

        # 응답 디버깅
        logger.info(f"Airtable response status: {response.status_code}")
        logger.info(f"Airtable response: {response.text}")
        
        if response.status_code in [200, 201]:
            # Airtable 저장 성공 시 이메일 발송 시도
            try:
                email_sent = send_consultation_email(data)
                if email_sent:
                    logger.info("✅ 상담 문의 이메일 발송 완료")
                else:
                    logger.warning("⚠️ 상담 문의 이메일 발송 실패")
            except Exception as email_error:
                logger.error(f"❌ 이메일 발송 중 오류: {str(email_error)}")
                logger.error(f"오류 상세: {traceback.format_exc()}")
            
            return jsonify({"status": "success"}), 200
        else:
            logger.error(f"Airtable 저장 실패: {response.text}")
            return jsonify({
                "error": "Airtable submission failed",
                "details": response.text
            }), response.status_code
            
    except Exception as e:
        logger.error(f"상담 접수 전체 오류: {str(e)}")
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
        search_conditions = request.json  # 변수명 변경
        logger.info(f"Search conditions: {search_conditions}")
        
        # Airtable에서 데이터 가져오기 (환경 변수에서 읽기)
        airtable_key = os.environ.get("AIRTABLE_API_KEY")
        base_id = os.environ.get("AIRTABLE_BASE_ID", "appGSg5QfDNKgFf73")
        table_id = os.environ.get("AIRTABLE_TABLE_ID", "tblnR438TK52Gr0HB")
        view_id = os.environ.get("AIRTABLE_ALL_VIEW_ID", "viwyV15T4ihMpbDbr")
        
        logger.info(f"Using view ID: {view_id}")
        
        if not airtable_key:
            logger.error("AIRTABLE_API_KEY not set")
            return jsonify({"error": "Airtable API key not set"}), 500
            
        headers = {
            "Authorization": f"Bearer {airtable_key}"
        }
        
        # 뷰 ID를 URL 파라미터로 추가
        base_url = f"https://api.airtable.com/v0/{base_id}/{table_id}"
        
        # 모든 레코드 가져오기 (페이지네이션 처리)
        all_records = []
        offset = None
        page_count = 0
        
        while True:
            url = base_url
            params = {}
            
            if view_id:
                params['view'] = view_id
            
            if offset:
                params['offset'] = offset
                
            logger.info(f"Fetching page {page_count + 1}, offset: {offset}")
            
            try:
                response = requests.get(url, headers=headers, params=params)
                
                if response.status_code != 200:
                    logger.error(f"Airtable API error: {response.status_code}")
                    return jsonify({
                        "error": "Airtable data fetch failed",
                        "details": response.text
                    }), response.status_code
                    
                airtable_data = response.json()  # 변수명 변경
                records = airtable_data.get('records', [])
                all_records.extend(records)
                
                logger.info(f"Page {page_count + 1}: {len(records)} records fetched")
                page_count += 1
                
                # 다음 페이지가 있는지 확인
                offset = airtable_data.get('offset')
                if not offset:
                    break
                    
            except Exception as e:
                logger.error(f"Request error: {str(e)}")
                return jsonify({"error": f"Request error: {str(e)}"}), 500
        
        logger.info(f"Total records from Airtable: {len(all_records)} (in {page_count} pages)")
        
        filtered_records = []
        status_filtered_count = 0
        condition_filtered_count = 0
        geocoding_failed_count = 0
        
        # 검색 조건 디버깅
        active_filters = []
        if search_conditions.get('price_value', '').strip():
            active_filters.append(f"가격 {search_conditions['price_condition']} {search_conditions['price_value']}")
        if search_conditions.get('yield_value', '').strip():
            active_filters.append(f"수익률 {search_conditions['yield_condition']} {search_conditions['yield_value']}")
        
        logger.info(f"Active filters: {', '.join(active_filters) if active_filters else 'None'}")
        
        for i, record in enumerate(all_records):
            fields = record.get('fields', {})
            
            # 처음 5개 레코드의 필드값 로깅
            if i < 5:
                logger.debug(f"Record {i} - 주소: {fields.get('지번 주소', '')}")
                logger.debug(f"  매가: {fields.get('매가(만원)', '')}")
                logger.debug(f"  수익률: {fields.get('융자제외수익률(%)', '')}")
            
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
            if search_conditions.get('price_value', '').strip() and search_conditions.get('price_condition') != 'all':
                price_raw = fields.get('매가(만원)', 0)
                try:
                    # price가 문자열인 경우 숫자로 변환
                    if isinstance(price_raw, str):
                        price = float(price_raw.replace(',', ''))
                    else:
                        price = float(price_raw) if price_raw else 0
                    
                    price_val = float(search_conditions['price_value'])
                    
                    if i < 5:  # 디버깅
                        logger.debug(f"  가격 필터링: {price} {search_conditions['price_condition']} {price_val}")
                    
                    if search_conditions['price_condition'] == 'above' and price < price_val:
                        should_include = False
                        filter_reasons.append(f"가격 {price} < {price_val}")
                    elif search_conditions['price_condition'] == 'below' and price > price_val:
                        should_include = False
                        filter_reasons.append(f"가격 {price} > {price_val}")
                except Exception as e:
                    logger.warning(f"Price parsing error for record {i}: {e}, raw value: {price_raw}")
            
            # 수익률 조건
            if should_include and search_conditions.get('yield_value', '').strip() and search_conditions.get('yield_condition') != 'all':
                yield_raw = fields.get('융자제외수익률(%)', 0)
                try:
                    # yield_rate가 문자열인 경우 숫자로 변환
                    if isinstance(yield_raw, str):
                        yield_rate = float(yield_raw.replace(',', '').replace('%', ''))
                    else:
                        yield_rate = float(yield_raw) if yield_raw else 0
                    
                    yield_val = float(search_conditions['yield_value'])
                    
                    if i < 5:  # 디버깅
                        logger.debug(f"  수익률 필터링: {yield_rate} {search_conditions['yield_condition']} {yield_val}")
                    
                    if search_conditions['yield_condition'] == 'above' and yield_rate < yield_val:
                        should_include = False
                        filter_reasons.append(f"수익률 {yield_rate} < {yield_val}")
                    elif search_conditions['yield_condition'] == 'below' and yield_rate > yield_val:
                        should_include = False
                        filter_reasons.append(f"수익률 {yield_rate} > {yield_val}")
                except Exception as e:
                    logger.warning(f"Yield parsing error for record {i}: {e}, raw value: {yield_raw}")
            
            # 실투자금 조건
            if should_include and search_conditions.get('investment_value', '').strip() and search_conditions.get('investment_condition') != 'all':
                investment_raw = fields.get('실투자금', 0)
                try:
                    if isinstance(investment_raw, str):
                        investment = float(investment_raw.replace(',', ''))
                    else:
                        investment = float(investment_raw) if investment_raw else 0
                    
                    investment_val = float(search_conditions['investment_value'])
                    
                    if search_conditions['investment_condition'] == 'above' and investment < investment_val:
                        should_include = False
                        filter_reasons.append(f"실투자금 {investment} < {investment_val}")
                    elif search_conditions['investment_condition'] == 'below' and investment > investment_val:
                        should_include = False
                        filter_reasons.append(f"실투자금 {investment} > {investment_val}")
                except Exception as e:
                    logger.warning(f"Investment parsing error: {e}")
            
            # 토지면적 조건
            if should_include and search_conditions.get('area_value', '').strip() and search_conditions.get('area_condition') != 'all':
                area_raw = fields.get('토지면적(㎡)', 0)
                try:
                    if isinstance(area_raw, str):
                        area = float(area_raw.replace(',', ''))
                    else:
                        area = float(area_raw) if area_raw else 0
                    
                    area_val = float(search_conditions['area_value'])
                    
                    if search_conditions['area_condition'] == 'above' and area < area_val:
                        should_include = False
                        filter_reasons.append(f"토지면적 {area} < {area_val}")
                    elif search_conditions['area_condition'] == 'below' and area > area_val:
                        should_include = False
                        filter_reasons.append(f"토지면적 {area} > {area_val}")
                except Exception as e:
                    logger.warning(f"Area parsing error: {e}")
            
            # 사용승인일 조건
            if should_include and search_conditions.get('approval_date', '').strip() and search_conditions.get('approval_condition') != 'all':
                approval = fields.get('사용승인일', '')
                try:
                    if approval and approval.strip():
                        approval_datetime = datetime.strptime(approval.strip(), '%Y-%m-%d')
                        target_datetime = datetime.strptime(search_conditions['approval_date'], '%Y-%m-%d')
                        
                        if search_conditions['approval_condition'] == 'before' and approval_datetime >= target_datetime:
                            should_include = False
                            filter_reasons.append(f"사용승인일 {approval} >= {search_conditions['approval_date']}")
                        elif search_conditions['approval_condition'] == 'after' and approval_datetime <= target_datetime:
                            should_include = False
                            filter_reasons.append(f"사용승인일 {approval} <= {search_conditions['approval_date']}")
                except Exception as e:
                    logger.warning(f"Date parsing error: {e}, approval date: {approval}")
            
            if not should_include:
                condition_filtered_count += 1
                if i < 10:  # 처음 10개만 로그
                    logger.info(f"Record {i} filtered out: {fields.get('지번 주소', 'Unknown')} - Reasons: {filter_reasons}")
            else:
                filtered_records.append(record)
        
        logger.info(f"Filtering summary:")
        logger.info(f"  - Total records: {len(all_records)}")
        logger.info(f"  - Status filtered: {status_filtered_count}")
        logger.info(f"  - Condition filtered: {condition_filtered_count}")
        logger.info(f"  - Passed filter: {len(filtered_records)}")
        
        # 나머지 코드는 동일...
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
                else:
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
        
        # 모든 레코드 가져오기 (페이지네이션 처리)
        all_records = []
        offset = None
        page_count = 0
        
        base_url = f"https://api.airtable.com/v0/{base_id}/{table_id}"
        
        try:
            while True:
                params = {}
                
                if view_id:
                    params['view'] = view_id
                
                if offset:
                    params['offset'] = offset
                
                logger.info(f"Fetching page {page_count + 1}, offset: {offset}")
                
                response = requests.get(base_url, headers=headers, params=params)
                
                if response.status_code != 200:
                    logger.error(f"Failed to fetch properties: {response.text}")
                    return jsonify({"error": "Failed to fetch property data"}), 500
                
                data = response.json()
                records = data.get('records', [])
                all_records.extend(records)
                
                logger.info(f"Page {page_count + 1}: {len(records)} records fetched")
                page_count += 1
                
                # 다음 페이지가 있는지 확인
                offset = data.get('offset')
                if not offset:
                    break
                    
        except Exception as e:
            logger.error(f"Request error: {str(e)}")
            return jsonify({"error": f"Request error: {str(e)}"}), 500
        
        # 레코드 수 로깅
        total_record_count = len(all_records)
        logger.info(f"Total records received from Airtable: {total_record_count} (in {page_count} pages)")

        # 첫 번째 레코드의 필드명 로깅
        if total_record_count > 0:
            first_record = all_records[0]
            logger.info(f"Sample record ID: {first_record.get('id')}")
            logger.info(f"Available fields: {', '.join(first_record.get('fields', {}).keys())}")
        
        properties = []
        
        # 현황 필드 필터링 추가
        valid_status = ["네이버", "디스코", "당근", "비공개"]
        valid_record_count = 0

        # 매물 정보 구조화 부분 수정
        for record in all_records:
            fields = record.get('fields', {})
            
            # 현황 필드 확인
            status = fields.get('현황')
            is_valid_status = False
            
            if status:
                if isinstance(status, list):
                    is_valid_status = any(s in valid_status for s in status)
                elif isinstance(status, str):
                    is_valid_status = status in valid_status
            
            # 유효한 상태가 아니면 건너뛰기
            if not is_valid_status:
                continue
                
            valid_record_count += 1
            
            # 가격 필드 처리 - 만원 단위를 억원으로 변환
            price_raw = fields.get('매가(만원)', 0)
            try:
                price_in_man = float(price_raw) if price_raw else 0
                # 억원으로 변환
                price_in_eok = price_in_man / 10000 if price_in_man >= 10000 else price_in_man / 10000
                price_display = f"{price_in_eok:.1f}억원" if price_in_man >= 10000 else f"{int(price_in_man)}만원"
            except:
                price_in_man = 0
                price_display = "가격정보없음"
            
            # 수익률 처리
            yield_rate = fields.get('융자제외수익률(%)', '')
            try:
                yield_rate = float(yield_rate) if yield_rate else 0
                yield_display = f"{yield_rate}%"
            except:
                yield_display = "정보없음"
            
            # 실투자금 처리 - 만원 단위를 억원으로 변환
            investment_raw = fields.get('실투자금', 0)
            try:
                investment_in_man = float(investment_raw) if investment_raw else 0
                # 억원으로 변환
                investment_in_eok = investment_in_man / 10000 if investment_in_man >= 10000 else investment_in_man / 10000
                investment_display = f"{investment_in_eok:.1f}억원" if investment_in_man >= 10000 else f"{int(investment_in_man)}만원"
            except:
                investment_in_man = 0
                investment_display = "정보없음"
            
            # 매물 정보 구조화 (AI가 이해하기 쉽게 변환)
            property_info = {
                "id": record.get('레코드id', ''),
                "address": fields.get('지번 주소', ''),
                "price": price_display,  # 이미 변환된 가격
                "price_raw": price_in_man,  # 원본 만원 단위 값
                "actual_investment": investment_display,  # 이미 변환된 실투자금
                "investment_raw": investment_in_man,  # 원본 만원 단위 값
                "monthly_income": fields.get('월세(만원)', ''),
                "yield": yield_display,  # 이미 변환된 수익률
                "property_type": fields.get('주용도', ''),
                "area": fields.get('토지면적(㎡)', '')
            }
            properties.append(property_info)
        
        # 처리된 데이터 로깅
        logger.info(f"Processed {len(properties)} properties out of {total_record_count} total records")
        logger.info(f"Valid status records: {valid_record_count}")
        
        # 첫 번째 처리된 매물 정보 로깅
        if properties:
            logger.info(f"Sample processed property: {json.dumps(properties[0], ensure_ascii=False)}")
        else:
            logger.warning("No properties were processed successfully")

        # 데이터 양이 너무 많으면 제한
        properties_for_ai = properties[:15] if len(properties) > 15 else properties
        if len(properties) > 15:
            logger.info(f"Limiting properties for AI from {len(properties)} to 15")
        
        # Claude에 전송할 프롬프트 수정
        prompt = f"""
        다음은 부동산 매물 목록입니다 (전체 {len(properties)}개 중 {len(properties_for_ai)}개):
        {json.dumps(properties_for_ai, ensure_ascii=False, indent=2)}
        
        사용자의 검색 조건:
        - 지역: {location}
        - 희망매매가: {price_range}
        - 실투자금: {investment}
        - 희망투자수익률: {expected_yield}
        
        위 조건에 가장 적합한 매물 2-3개를 추천해주세요. 
        
        주의사항:
        - 'price' 필드는 이미 한글로 표시된 가격입니다 (예: "25.0억원", "8000만원")
        - 'actual_investment' 필드도 이미 한글로 표시된 금액입니다 (예: "10.0억원", "5000만원")
        - 'yield' 필드도 이미 "%"가 포함되어 있습니다
        - 모든 값을 변환 없이 그대로 사용하세요
        
        각 매물에 대해 다음 형식으로 답변해주세요. 깔끔한 형식을 위해 제목 앞에는 ##을 사용하세요:
        
        ## 매물 1:
        위치: [주소]
        가격: [price 필드 값 그대로]
        주용도: [주용도]
        수익률: [yield 필드 값 그대로]
        추천 이유: [이 사용자에게 왜 이 매물이 적합한지 간단히 설명] 
        실투자금: [actual_investment 필드 값 그대로]로 매물가격 대비 주목할만한 적은 투자금입니다.
        
        
        ## 매물 2:
        위치: [주소]
        가격: [price 필드 값 그대로]
        주용도: [주용도]
        수익률: [yield 필드 값 그대로]
        추천 이유: [이 사용자에게 왜 이 매물이 적합한지 간단히 설명]
        실투자금: [actual_investment 필드 값 그대로]로 부담이 적습니다.
        
        
        ## 매물 3:
        위치: [주소]
        가격: [price 필드 값 그대로]
        주용도: [주용도]
        수익률: [yield 필드 값 그대로]
        추천 이유: [이 사용자에게 왜 이 매물이 적합한지 간단히 설명]
        실투자금: [actual_investment 필드 값 그대로]로 효율적인 투자가 가능합니다.
        
        
        조건에 맞는 매물이 없으면 '조건에 맞는 매물이 없습니다'라고 답변해주세요.

        더 많은 매물이 궁금하시다면 아래 '상담문의'를 남겨주세요.
        빠른 시일 내에 답변드리겠습니다.
        """
        
        # Claude API 호출
        logger.info("Calling Claude API for property recommendations")
        response = claude_client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=1000,
            system="당신은 부동산 투자 전문가입니다. 사용자의 조건에 맞는 최적의 매물을 추천해주세요. 제공된 데이터의 가격, 실투자금, 수익률은 이미 올바른 형식으로 변환되어 있으므로, 추가 계산이나 변환 없이 그대로 사용하세요. 깔끔한 형식을 위해 각 매물 제목 앞에 ##을 사용하고, 각 항목 사이에 적절한 줄바꿈을 넣어주세요.",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        recommendations = response.content[0].text
        logger.info(f"Claude API response received: {len(recommendations)} characters")
        
        return jsonify({
            "recommendations": recommendations,
            "total_properties": len(properties),
            "searched_properties": total_record_count,
            "valid_properties": valid_record_count,
            "ai_analyzed": len(properties_for_ai)
        })
        
    except Exception as e:
        logger.error(f"AI property search error: {str(e)}")
        return jsonify({"error": f"Error processing request: {str(e)}"}), 500

def send_consultation_email(customer_data):
    """
    상담 문의 접수 시 이메일 발송 함수
    customer_data: dict - 고객이 입력한 상담 데이터
    """
    logger.info("=== 이메일 발송 함수 시작 ===")
    logger.info(f"고객 데이터: {customer_data}")

    try:
        # 환경 변수 확인
        EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS")
        EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
        SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
        SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
        ADMIN_EMAIL = "cs21.jeon@gmail.com"
        
        logger.info(f"EMAIL_ADDRESS: {EMAIL_ADDRESS}")
        logger.info(f"EMAIL_PASSWORD: {'설정됨' if EMAIL_PASSWORD else '설정되지 않음'}")
        logger.info(f"SMTP_SERVER: {SMTP_SERVER}")
        logger.info(f"SMTP_PORT: {SMTP_PORT}")
        logger.info(f"ADMIN_EMAIL: {ADMIN_EMAIL}")

        # 이메일 설정 확인
        if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
            logger.error("이메일 설정이 완료되지 않았습니다.")
            logger.error(f"EMAIL_ADDRESS 존재: {bool(EMAIL_ADDRESS)}")
            logger.error(f"EMAIL_PASSWORD 존재: {bool(EMAIL_PASSWORD)}")
            return False
        
        customer_email = customer_data.get('email', '').strip()
        customer_phone = customer_data.get('phone', '')
        property_type = customer_data.get('propertyType', '')
        message = customer_data.get('message', '')
        
        logger.info(f"처리할 데이터:")
        logger.info(f"  - 고객 이메일: {customer_email}")
        logger.info(f"  - 고객 전화: {customer_phone}")
        logger.info(f"  - 매물 타입: {property_type}")
        logger.info(f"  - 메시지: {message[:50]}..." if len(message) > 50 else f"  - 메시지: {message}")
        
        # 매물 종류 매핑
        property_type_map = {
            'house': '단독/다가구',
            'mixed': '상가주택', 
            'commercial': '상업용빌딩',
            'land': '재건축/토지',
            'sell': '매물접수'
        }
        property_type_korean = property_type_map.get(property_type, property_type)
        
        # 고객 이름 추출 (이메일이 있는 경우)
        customer_name = ""
        if customer_email:
            customer_name = customer_email.split('@')[0]
        else:
            customer_name = "고객"

        logger.info(f"고객 이름: {customer_name}")
        logger.info(f"매물 종류 (한글): {property_type_korean}")
        
        # HTML 이메일 템플릿
        html_template = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>금토끼부동산 문의 접수 안내</title>
    <style>
        body {{
            font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', '맑은 고딕', sans-serif;
            line-height: 1.6;
            color: #333333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .email-container {{
            border: 1px solid #dddddd;
            border-radius: 8px;
            padding: 25px;
            background-color: #ffffff;
        }}
        .header {{
            text-align: center;
            margin-bottom: 25px;
        }}
        .header img {{
            max-width: 150px;
            height: auto;
        }}
        .greeting {{
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 15px;
        }}
        .content {{
            margin-bottom: 25px;
        }}
        .inquiry-details {{
            background-color: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
        }}
        .detail-row {{
            margin-bottom: 10px;
        }}
        .detail-label {{
            font-weight: bold;
            color: #555;
        }}
        .button-container {{
            text-align: center;
            margin: 30px 0;
        }}
        .button {{
            display: inline-block;
            background-color: #FFC000;
            color: #000000;
            text-decoration: none;
            padding: 12px 24px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 16px;
        }}
        .footer {{
            text-align: center;
            font-size: 12px;
            color: #777777;
            margin-top: 30px;
            border-top: 1px solid #eeeeee;
            padding-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <h2>금토끼부동산</h2>
        </div>
        
        <div class="greeting">
            안녕하세요. {customer_name}님
        </div>
        
        <div class="content">
            <p>금토끼부동산입니다.</p>
            <p>저희 부동산 페이지를 방문해주셔서 감사합니다.</p>
            <p>문의주신 내용 잘 접수되었습니다.</p>
            <p>보내주신 문의사항 확인하여 24시간 이내 답변드리겠습니다.</p>
            <p>감사합니다.</p>
        </div>
        
        <div class="inquiry-details">
            <h3>접수된 문의 내용</h3>
            <div class="detail-row">
                <span class="detail-label">매물종류:</span> {property_type_korean}
            </div>
            <div class="detail-row">
                <span class="detail-label">연락처:</span> {customer_phone}
            </div>
            <div class="detail-row">
                <span class="detail-label">문의사항:</span><br>
                {message.replace(chr(10), '<br>')}
            </div>
        </div>
        
        <div class="button-container">
            <a href="https://www.disco.re/hvzt1qow?share" class="button">금토끼부동산 보유 매물 전체 보기(디스코)</a>
        </div>
        
        <div class="footer">
            <p>본 메일은 자동발송되었습니다. 추가 문의사항은 회신해주시기 바랍니다.</p>
            <p>© 2025 금토끼부동산. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
        """
        
        # 관리자용 이메일 템플릿
        admin_html_template = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>[금토끼부동산] 새로운 상담 문의 접수</title>
    <style>
        body {{
            font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', '맑은 고딕', sans-serif;
            line-height: 1.6;
            color: #333333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .email-container {{
            border: 1px solid #dddddd;
            border-radius: 8px;
            padding: 25px;
            background-color: #ffffff;
        }}
        .header {{
            background-color: #e38000;
            color: white;
            padding: 15px;
            text-align: center;
            border-radius: 8px 8px 0 0;
            margin: -25px -25px 20px -25px;
        }}
        .inquiry-details {{
            background-color: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
        }}
        .detail-row {{
            margin-bottom: 15px;
            padding: 8px 0;
            border-bottom: 1px solid #eeeeee;
        }}
        .detail-label {{
            font-weight: bold;
            color: #555;
            display: inline-block;
            min-width: 80px;
        }}
        .urgent {{
            background-color: #fff3cd;
            border: 1px solid #ffeaa7;
            padding: 10px;
            border-radius: 4px;
            margin-bottom: 20px;
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <h2>금토끼부동산 새로운 상담 문의</h2>
        </div>
        
        <div class="urgent">
            <strong>⚠️ 새로운 상담 문의가 접수되었습니다!</strong><br>
            빠른 시일 내에 고객에게 연락을 드려 주세요.
        </div>
        
        <div class="inquiry-details">
            <h3>📋 문의 상세 정보</h3>
            <div class="detail-row">
                <span class="detail-label">매물종류:</span> {property_type_korean}
            </div>
            <div class="detail-row">
                <span class="detail-label">연락처:</span> {customer_phone}
            </div>
            <div class="detail-row">
                <span class="detail-label">이메일:</span> {customer_email if customer_email else '제공되지 않음'}
            </div>
            <div class="detail-row">
                <span class="detail-label">문의사항:</span><br>
                <div style="margin-top: 8px; padding: 10px; background-color: white; border-radius: 4px;">
                    {message.replace(chr(10), '<br>')}
                </div>
            </div>
        </div>
        
        <div style="text-align: center; margin-top: 30px;">
            <p><strong>📞 고객 연락처: {customer_phone}</strong></p>
            <p style="font-size: 14px; color: #666;">
                접수 시간: {datetime.now().strftime('%Y년 %m월 %d일 %H시 %M분')}
            </p>
        </div>
    </div>
</body>
</html>
        """
        
        # SMTP 연결 테스트
        logger.info("=== SMTP 서버 연결 시도 ===")
        try:
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            logger.info("SMTP 서버 연결 성공")
            
            server.starttls()
            logger.info("TLS 연결 성공")
            
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            logger.info("SMTP 로그인 성공")
            
        except smtplib.SMTPAuthenticationError as auth_error:
            logger.error(f"SMTP 인증 실패: {auth_error}")
            logger.error("Gmail 앱 비밀번호가 올바르지 않거나 2단계 인증이 설정되지 않았을 수 있습니다.")
            return False
        except smtplib.SMTPConnectError as conn_error:
            logger.error(f"SMTP 연결 실패: {conn_error}")
            return False
        except Exception as smtp_error:
            logger.error(f"SMTP 오류: {smtp_error}")
            return False
        
        # 이메일 발송 시도
        emails_sent = 0
        
        # 1. 고객에게 확인 이메일 발송 (이메일이 있는 경우에만)
        if customer_email:
            logger.info(f"=== 고객 확인 이메일 발송 시도: {customer_email} ===")
            try:
                # 간단한 HTML 템플릿 (테스트용)
                simple_html = f"""
                <html>
                <body>
                    <h2>금토끼부동산</h2>
                    <p>안녕하세요. {customer_name}님</p>
                    <p>상담 문의가 정상적으로 접수되었습니다.</p>
                    <p>24시간 이내에 연락드리겠습니다.</p>
                    <hr>
                    <p><strong>접수 내용:</strong></p>
                    <p>매물종류: {property_type_korean}</p>
                    <p>연락처: {customer_phone}</p>
                    <p>문의사항: {message}</p>
                </body>
                </html>
                """
                
                customer_msg = MIMEMultipart('alternative')
                customer_msg['From'] = EMAIL_ADDRESS
                customer_msg['To'] = customer_email
                customer_msg['Subject'] = "금토끼 부동산에 상담문의가 접수되었습니다."
                
                customer_html_part = MIMEText(simple_html, 'html', 'utf-8')
                customer_msg.attach(customer_html_part)
                
                server.send_message(customer_msg)
                logger.info(f"고객 확인 이메일 발송 완료: {customer_email}")
                emails_sent += 1
                
            except Exception as customer_email_error:
                logger.error(f"고객 이메일 발송 실패: {customer_email_error}")
        
        # 2. 관리자에게 알림 이메일 발송
        logger.info(f"=== 관리자 알림 이메일 발송 시도: {ADMIN_EMAIL} ===")
        try:
            # 간단한 관리자용 HTML 템플릿
            admin_html = f"""
            <html>
            <body>
                <h2>🔔 금토끼부동산 새로운 상담 문의</h2>
                <p><strong>새로운 상담 문의가 접수되었습니다!</strong></p>
                <hr>
                <p><strong>📋 문의 정보:</strong></p>
                <p>매물종류: {property_type_korean}</p>
                <p>연락처: {customer_phone}</p>
                <p>이메일: {customer_email if customer_email else '제공되지 않음'}</p>
                <p>문의사항: {message}</p>
                <hr>
                <p>접수 시간: {datetime.now().strftime('%Y년 %m월 %d일 %H시 %M분')}</p>
            </body>
            </html>
            """
            
            admin_msg = MIMEMultipart('alternative')
            admin_msg['From'] = EMAIL_ADDRESS
            admin_msg['To'] = ADMIN_EMAIL
            admin_msg['Subject'] = f"[금토끼부동산] 새로운 {property_type_korean} 상담 문의 - {customer_phone}"
            
            admin_html_part = MIMEText(admin_html, 'html', 'utf-8')
            admin_msg.attach(admin_html_part)
            
            server.send_message(admin_msg)
            logger.info(f"관리자 알림 이메일 발송 완료: {ADMIN_EMAIL}")
            emails_sent += 1
            
        except Exception as admin_email_error:
            logger.error(f"관리자 이메일 발송 실패: {admin_email_error}")
        
        server.quit()
        logger.info("SMTP 연결 종료")
        
        logger.info(f"=== 이메일 발송 완료: 총 {emails_sent}개 발송 ===")
        return emails_sent > 0
        
    except Exception as e:
        logger.error(f"이메일 발송 함수 전체 오류: {str(e)}")
        logger.error(f"오류 타입: {type(e).__name__}")
        import traceback
        logger.error(f"오류 상세: {traceback.format_exc()}")
        return False

class GoogleMessagesAutomation:
    def __init__(self):
        self.driver = None
        self.is_logged_in = False
        self.last_check_time = datetime.now()
        
    def setup_browser(self):
        """Chrome 브라우저 설정 및 시작"""
        try:
            options = uc.ChromeOptions()
            
            # 헤드리스 모드 (서버 환경용)
            # options.add_argument('--headless')  # 개발 중에는 주석 처리
            
            # 브라우저 옵션 설정
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            
            # 사용자 데이터 디렉토리 (로그인 상태 유지용)
            options.add_argument('--user-data-dir=/tmp/chrome-user-data')
            
            # 알림 비활성화
            prefs = {
                "profile.default_content_setting_values.notifications": 2
            }
            options.add_experimental_option("prefs", prefs)
            
            self.driver = uc.Chrome(options=options)
            logger.info("Chrome 브라우저가 시작되었습니다.")
            return True
            
        except Exception as e:
            logger.error(f"브라우저 설정 실패: {str(e)}")
            return False
    
    def login_to_google_messages(self):
        """구글 메시지 웹에 로그인"""
        try:
            if not self.driver:
                if not self.setup_browser():
                    return False
            
            # 구글 메시지 웹 접속
            self.driver.get('https://messages.google.com/web')
            
            # QR 코드 스캔 대기 또는 이미 로그인된 상태 확인
            wait = WebDriverWait(self.driver, 60)  # 60초 대기
            
            try:
                # 이미 로그인된 경우 새 대화 버튼이 있는지 확인
                start_chat_button = wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-e2e-start-chat], [aria-label="Start chat"]'))
                )
                self.is_logged_in = True
                logger.info("구글 메시지에 이미 로그인되어 있습니다.")
                return True
                
            except TimeoutException:
                # QR 코드 스캔 필요
                logger.info("QR 코드를 스캔하여 로그인해주세요. 60초 대기 중...")
                
                # QR 코드 스캔 완료 대기
                try:
                    start_chat_button = wait.until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-e2e-start-chat], [aria-label="Start chat"]'))
                    )
                    self.is_logged_in = True
                    logger.info("QR 코드 스캔이 완료되고 로그인되었습니다.")
                    return True
                    
                except TimeoutException:
                    logger.error("로그인 시간이 초과되었습니다.")
                    return False
                    
        except Exception as e:
            logger.error(f"구글 메시지 로그인 실패: {str(e)}")
            return False
    
    def send_message(self, phone_number, message):
        """메시지 전송"""
        try:
            if not self.is_logged_in:
                if not self.login_to_google_messages():
                    return False
            
            wait = WebDriverWait(self.driver, 30)
            
            # 새 대화 시작 버튼 클릭
            start_chat = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-e2e-start-chat], [aria-label="Start chat"]'))
            )
            start_chat.click()
            
            # 전화번호 입력 필드 찾기 및 입력
            phone_input = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="tel"], input[placeholder*="phone"], input[placeholder*="전화"]'))
            )
            phone_input.clear()
            phone_input.send_keys(phone_number)
            
            # 잠시 대기 (자동완성 등을 위해)
            time.sleep(2)
            
            # 메시지 입력 필드 찾기
            message_input = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div[contenteditable="true"], textarea[placeholder*="메시지"], textarea[placeholder*="Message"]'))
            )
            message_input.clear()
            message_input.send_keys(message)
            
            # 전송 버튼 클릭
            send_button = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-e2e-send-message], [aria-label="Send"], button[type="submit"]'))
            )
            send_button.click()
            
            logger.info(f"메시지 전송 완료: {phone_number}")
            return True
            
        except Exception as e:
            logger.error(f"메시지 전송 실패 ({phone_number}): {str(e)}")
            return False
    
    def close_browser(self):
        """브라우저 종료"""
        try:
            if self.driver:
                self.driver.quit()
                self.driver = None
                self.is_logged_in = False
                logger.info("브라우저가 종료되었습니다.")
        except Exception as e:
            logger.error(f"브라우저 종료 실패: {str(e)}")

# 글로벌 인스턴스
google_messages = GoogleMessagesAutomation()

def monitor_airtable_for_new_contacts():
    """에어테이블 모니터링 함수 (1분마다 실행)"""
    logger.info("에어테이블 모니터링을 시작합니다.")
    
    # 에어테이블 설정
    airtable_key = os.environ.get("AIRTABLE_INQUIRY_KEY")
    base_id = os.environ.get("AIRTABLE_INQUIRY_BASE_ID")
    table_id = os.environ.get("AIRTABLE_INQUIRY_TABLE_ID")
    
    if not all([airtable_key, base_id, table_id]):
        logger.error("에어테이블 설정이 완료되지 않았습니다.")
        return
    
    headers = {
        "Authorization": f"Bearer {airtable_key}",
        "Content-Type": "application/json"
    }
    
    while True:
        try:
            # 전송되지 않은 레코드 조회
            url = f"https://api.airtable.com/v0/{base_id}/{table_id}"
            params = {
                'filterByFormula': 'AND({연락처} != "", {SMS전송여부} != "완료")',
                'maxRecords': 10,
                'sort[0][field]': '생성일시',
                'sort[0][direction]': 'desc'
            }
            
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                records = data.get('records', [])
                
                logger.info(f"새로운 레코드 {len(records)}개 발견")
                
                for record in records:
                    fields = record.get('fields', {})
                    record_id = record.get('id')
                    
                    phone_number = fields.get('연락처', '').strip()
                    property_type = fields.get('매물종류', '')
                    message_content = fields.get('문의사항', '')
                    
                    if not phone_number:
                        continue
                    
                    # SMS 메시지 템플릿 생성
                    sms_message = create_sms_template(property_type, message_content)
                    
                    # 메시지 전송
                    with browser_lock:
                        success = google_messages.send_message(phone_number, sms_message)
                    
                    if success:
                        # 에어테이블 레코드 업데이트 (전송 완료 표시)
                        update_url = f"https://api.airtable.com/v0/{base_id}/{table_id}/{record_id}"
                        update_data = {
                            "fields": {
                                "SMS전송여부": "완료",
                                "SMS전송일시": datetime.now().isoformat()
                            }
                        }
                        
                        update_response = requests.patch(update_url, json=update_data, headers=headers)
                        
                        if update_response.status_code == 200:
                            logger.info(f"SMS 전송 및 업데이트 완료: {phone_number}")
                        else:
                            logger.error(f"에어테이블 업데이트 실패: {update_response.text}")
                    else:
                        logger.error(f"SMS 전송 실패: {phone_number}")
                        
                        # 실패 시에도 상태 업데이트
                        update_url = f"https://api.airtable.com/v0/{base_id}/{table_id}/{record_id}"
                        update_data = {
                            "fields": {
                                "SMS전송여부": "실패",
                                "SMS전송일시": datetime.now().isoformat()
                            }
                        }
                        requests.patch(update_url, json=update_data, headers=headers)
            
            else:
                logger.error(f"에어테이블 조회 실패: {response.text}")
        
        except Exception as e:
            logger.error(f"모니터링 오류: {str(e)}")
        
        # 1분 대기
        time.sleep(60)

def create_sms_template(property_type, customer_message):
    """SMS 메시지 템플릿 생성"""
    template = f"""안녕하세요! 금토끼부동산입니다.

{property_type} 관련 문의 주셔서 감사합니다.

고객님 문의내용:
{customer_message[:100]}{'...' if len(customer_message) > 100 else ''}

빠른 시일 내에 상세한 매물 정보를 안내해드리겠습니다.

추가 문의: 02-3471-7377
📱 010-4019-6509

금토끼부동산 드림"""
    
    return template

# Flask 앱에 추가할 엔드포인트들

@app.route('/api/sms/start-monitoring', methods=['POST'])
def start_sms_monitoring():
    """SMS 모니터링 시작"""
    try:
        # 브라우저 초기화 및 로그인
        with browser_lock:
            if google_messages.login_to_google_messages():
                # 백그라운드 모니터링 스레드 시작
                monitoring_thread = threading.Thread(target=monitor_airtable_for_new_contacts, daemon=True)
                monitoring_thread.start()
                
                logger.info("SMS 모니터링이 시작되었습니다.")
                return jsonify({"status": "success", "message": "SMS monitoring started"}), 200
            else:
                return jsonify({"status": "error", "message": "Google Messages login failed"}), 500
                
    except Exception as e:
        logger.error(f"SMS 모니터링 시작 실패: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/sms/send-test', methods=['POST'])
def send_test_sms():
    """테스트 SMS 전송"""
    try:
        data = request.json
        phone_number = data.get('phone_number')
        message = data.get('message', '테스트 메시지입니다.')
        
        if not phone_number:
            return jsonify({"status": "error", "message": "Phone number required"}), 400
        
        with browser_lock:
            success = google_messages.send_message(phone_number, message)
        
        if success:
            return jsonify({"status": "success", "message": "Test SMS sent successfully"}), 200
        else:
            return jsonify({"status": "error", "message": "Failed to send test SMS"}), 500
            
    except Exception as e:
        logger.error(f"테스트 SMS 전송 실패: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/sms/status', methods=['GET'])
def get_sms_status():
    """SMS 시스템 상태 확인"""
    try:
        status = {
            "browser_active": google_messages.driver is not None,
            "logged_in": google_messages.is_logged_in,
            "last_check": google_messages.last_check_time.isoformat() if google_messages.last_check_time else None
        }
        return jsonify(status), 200
        
    except Exception as e:
        logger.error(f"SMS 상태 확인 실패: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

# 애플리케이션 종료 시 브라우저 정리
import atexit

def cleanup_browser():
    """애플리케이션 종료 시 브라우저 정리"""
    with browser_lock:
        google_messages.close_browser()

atexit.register(cleanup_browser)

@app.route('/api/blog-feed')
def blog_feed():
    now = datetime.now()
    cache_duration = timedelta(hours=24)

    if blog_cache["timestamp"] and now - blog_cache["timestamp"] < cache_duration:
        return jsonify(blog_cache["posts"])

    feed_url = "https://rss.blog.naver.com/goldenrabbit7377.xml"
    feed = feedparser.parse(feed_url)

    posts = []
    for entry in feed.entries[:10]:
        log_no = extract_log_no(entry.link)
        if not log_no:
            continue

        # 로컬 이미지 파일 존재 여부 확인
        local_image_path = f'/home/sftpuser/www/blog_thumbs/{log_no}.jpg'
        has_thumbnail = os.path.exists(local_image_path)
        
        # HTML 태그에서 이미지 제거 및 텍스트 추출
        clean_summary = clean_html_content(entry.summary)
        
        posts.append({
            "id": log_no,
            "title": entry.title,
            "link": entry.link,
            "summary": clean_summary,  # 이미지 태그가 제거된 요약 사용
            "published": entry.published,
            "has_thumbnail": has_thumbnail  # 썸네일 존재 여부 추가
        })

    blog_cache["timestamp"] = now
    blog_cache["posts"] = posts
    return jsonify(posts)

# HTML 콘텐츠에서 이미지 태그를 제거하고 텍스트만 추출하는 함수
def clean_html_content(html_content):
    # BeautifulSoup을 사용하여 HTML 파싱
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 모든 img 태그 제거
    for img in soup.find_all('img'):
        img.decompose()
    
    # HTML에서 텍스트만 추출 (태그 제거)
    text = soup.get_text(strip=True)
    
    # 텍스트 길이 제한 (150자)
    if len(text) > 150:
        text = text[:147] + '...'
    
    return text

# 이미지 URL 추출 함수 (나중에 이미지 다운로드에 사용할 수 있음)
def extract_image(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    img_tag = soup.find('img')
    return img_tag['src'] if img_tag and 'src' in img_tag.attrs else None

@app.route('/health')
def health_check():
    """서버 상태 확인용 엔드포인트"""
    return jsonify({"status": "healthy"})

if __name__ == '__main__':
    logger.info(f"Starting server on port 8000")
    # 개발 환경에서는 debug=True 사용 가능, 프로덕션에서는 False로 설정
    app.run(host="0.0.0.0", port=8000, debug=False)