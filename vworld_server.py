from flask import Flask, request, jsonify, make_response, send_from_directory, Blueprint
import requests
import os
import re
import json
import glob
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

# 버전 파일 경로 설정 - 절대 경로 사용
VERSION_FILE_PATH = '/home/sftpuser/www/version.json'

# 백업 데이터 관련 경로 설정 (단일 폴더 구조)
BACKUP_DIR = '/home/sftpuser/www/airtable_backup'

# 환경 변수 로드
load_dotenv()

# Flask 앱 설정
app = Flask(__name__)
CORS(app)  # CORS 지원 추가
vworld_key = os.environ.get("VWORLD_APIKEY")

# Flask 서버에 정적 파일 경로 추가
app.static_folder = 'static'
app.static_url_path = '/static'

# 로깅 설정
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   filename='/home/sftpuser/logs/api_debug.log')
logger = logging.getLogger('image_api')

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

# ===== V-World API 관련 엔드포인트 =====
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

# V-World 타일 프록시 엔드포인트
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
        
        return make_response(
            response.content, 
            response.status_code,
            {'Content-Type': response.headers.get('Content-Type', 'image/png')}
        )
    except Exception as e:
        logger.error(f"Tile proxy error: {str(e)}")
        return jsonify({"error": str(e)}), 500

# V-World WMS 프록시 엔드포인트
@app.route('/api/wms')
def vworld_wms():
    """V-World WMS를 프록시하는 엔드포인트"""
    try:
        # WMS 파라미터 전달
        params = {k: v for k, v in request.args.items()}
        params['key'] = vworld_key  # API 키 추가
        
        url = "https://api.vworld.kr/req/wms"
        response = requests.get(url, params=params)
        
        return make_response(
            response.content, 
            response.status_code,
            {'Content-Type': response.headers.get('Content-Type', 'image/png')}
        )
    except Exception as e:
        logger.error(f"WMS proxy error: {str(e)}")
        return jsonify({"error": str(e)}), 500

# ===== 백업 상태 확인 =====
@app.route('/api/backup-status')
def backup_status():
    """백업 상태 확인 엔드포인트"""
    try:
        metadata_path = os.path.join(BACKUP_DIR, 'metadata.json')
        
        if not os.path.exists(metadata_path):
            return jsonify({
                "status": "error",
                "message": "백업 메타데이터를 찾을 수 없습니다."
            }), 404
        
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        # 백업 파일들의 존재 여부 확인
        files_status = {}
        for view_name, filename in {
            'all': 'all_properties.json',
            'reconstruction': 'reconstruction_properties.json',
            'high_yield': 'high_yield_properties.json',
            'low_cost': 'low_cost_properties.json'
        }.items():
            file_path = os.path.join(BACKUP_DIR, filename)
            files_status[view_name] = os.path.exists(file_path)
        
        return jsonify({
            "status": "success",
            "metadata": metadata,
            "files": files_status
        })
        
    except Exception as e:
        logger.error(f"백업 상태 확인 오류: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"백업 상태 확인 중 오류 발생: {str(e)}"
        }), 500

# ===== 매물 관련 API (백업 우선, 에어테이블 폴백) =====
def get_property_list_from_airtable():
    """에어테이블에서 직접 매물 목록 가져오기 (폴백용)"""
    airtable_key = os.environ.get("AIRTABLE_API_KEY")
    base_id = os.environ.get("AIRTABLE_BASE_ID") 
    table_id = os.environ.get("AIRTABLE_TABLE_ID")
    view_id = os.environ.get("AIRTABLE_VIEW_ID")
    
    if not airtable_key:
        return jsonify({"error": "Airtable API key not set"}), 500
        
    headers = {
        "Authorization": f"Bearer {airtable_key}"
    }
    
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

@app.route('/api/property-list', methods=['GET'])
def get_property_list():
    """백업된 매물 목록 가져오기 (백업 우선, 에어테이블 폴백)"""
    try:
        # 백업 파일에서 데이터 로드 시도
        all_properties_path = os.path.join(BACKUP_DIR, 'all_properties.json')
        
        if not os.path.exists(all_properties_path):
            logger.warning("백업 파일을 찾을 수 없어 에어테이블 API로 폴백합니다.")
            return get_property_list_from_airtable()
        
        with open(all_properties_path, 'r', encoding='utf-8') as f:
            records = json.load(f)
        
        response_data = {
            "records": records
        }
        
        logger.info(f"백업에서 {len(records)}개 매물 반환")
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"백업 매물 목록 조회 오류: {str(e)}")
        # 오류 발생 시 에어테이블 API로 폴백
        return get_property_list_from_airtable()

def get_category_property_from_airtable(view_id):
    """에어테이블에서 직접 카테고리별 대표 매물 가져오기 (폴백용)"""
    try:
        logger.info(f"카테고리 대표 매물 요청 (에어테이블): view_id = {view_id}")
        
        airtable_key = os.environ.get("AIRTABLE_API_KEY")
        base_id = os.environ.get("AIRTABLE_BASE_ID", "appGSg5QfDNKgFf73") 
        table_id = os.environ.get("AIRTABLE_TABLE_ID", "tblnR438TK52Gr0HB")
        
        if not airtable_key:
            logger.error("AIRTABLE_API_KEY not set")
            return jsonify({"error": "Airtable API key not set"}), 500
            
        headers = {
            "Authorization": f"Bearer {airtable_key}"
        }
        
        url = f"https://api.airtable.com/v0/{base_id}/{table_id}"
        
        params = {
            'view': view_id,
            'filterByFormula': '{대표} = TRUE()',
            'maxRecords': 1,
            'sort[0][field]': '매가(만원)',
            'sort[0][direction]': 'asc'
        }
        
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code != 200:
            logger.error(f"Airtable API 오류: {response.text}")
            return jsonify({
                "error": "Airtable data fetch failed",
                "details": response.text,
                "status_code": response.status_code
            }), response.status_code
        
        data = response.json()
        records = data.get('records', [])
        
        if not records:
            logger.warning(f"뷰 {view_id}에서 대표 매물을 찾을 수 없습니다.")
            return jsonify({
                "error": "No representative property found",
                "message": "해당 카테고리에 대표로 설정된 매물이 없습니다.",
                "records": []
            }), 404
        
        response_data = {
            "records": records,
            "view_id": view_id,
            "total_count": len(records),
            "source": "airtable"
        }
        
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"에어테이블 카테고리 매물 API 오류: {str(e)}")
        return jsonify({
            "error": "Internal server error",
            "details": str(e)
        }), 500

@app.route('/api/category-property', methods=['GET'])
def get_category_property():
    """백업된 카테고리별 대표 매물 가져오기 (백업 우선, 에어테이블 폴백)"""
    try:
        view_id = request.args.get('view')
        if not view_id:
            return jsonify({"error": "View ID parameter is required"}), 400
        
        # 뷰 ID에 따른 파일 선택
        filename = None
        if view_id == 'viwzEVzrr47fCbDNU':  # 재건축용 토지
            filename = 'reconstruction_properties.json'
        elif view_id == 'viwxS4dKAcQWmB0Be':  # 고수익률 건물
            filename = 'high_yield_properties.json'
        elif view_id == 'viwUKnawSP8SkV9Sx':  # 저가단독주택
            filename = 'low_cost_properties.json'
        else:
            # 정의되지 않은 뷰 ID인 경우 에어테이블 API로 폴백
            return get_category_property_from_airtable(view_id)
        
        file_path = os.path.join(BACKUP_DIR, filename)
        
        if not os.path.exists(file_path):
            # 백업 파일이 없는 경우 에어테이블 API로 폴백
            logger.warning(f"백업 파일을 찾을 수 없어 에어테이블 API로 폴백합니다: {filename}")
            return get_category_property_from_airtable(view_id)
        
        # 파일에서 데이터 로드
        with open(file_path, 'r', encoding='utf-8') as f:
            all_records = json.load(f)
        
        # '대표' 필드가 체크된 레코드만 필터링
        representative_records = [
            r for r in all_records
            if r.get('fields', {}).get('대표') == True
        ]
        
        # 결과가 없으면 모든 레코드 중 첫 번째 사용
        if not representative_records and all_records:
            representative_records = [all_records[0]]
        
        # 응답 구조를 명확하게 정의
        response_data = {
            "records": representative_records,
            "view_id": view_id,
            "total_count": len(representative_records),
            "source": "backup",
            "success": True  # 성공 여부 명시
        }
        
        logger.info(f"백업에서 카테고리 대표 매물 반환: {len(representative_records)}개")
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"백업 카테고리 매물 API 오류: {str(e)}")
        import traceback
        logger.error(f"상세 오류: {traceback.format_exc()}")
        # 오류 발생 시 에어테이블 API로 폴백
        try:
            return get_category_property_from_airtable(view_id)
        except:
            return jsonify({
                "error": "Failed to load category property",
                "message": str(e),
                "success": False
            }), 500

@app.route('/api/debug/backup-files')
def debug_backup_files():
    """백업 파일 상태 확인 (디버깅용)"""
    try:
        files_info = {}
        
        # 백업 디렉토리 존재 확인
        if not os.path.exists(BACKUP_DIR):
            return jsonify({
                "error": f"Backup directory does not exist: {BACKUP_DIR}",
                "backup_dir": BACKUP_DIR
            }), 404
        
        # 각 파일 확인
        expected_files = [
            'all_properties.json',
            'reconstruction_properties.json', 
            'high_yield_properties.json',
            'low_cost_properties.json',
            'metadata.json'
        ]
        
        for filename in expected_files:
            file_path = os.path.join(BACKUP_DIR, filename)
            if os.path.exists(file_path):
                stat = os.stat(file_path)
                with open(file_path, 'r', encoding='utf-8') as f:
                    try:
                        data = json.load(f)
                        record_count = len(data) if isinstance(data, list) else "Not a list"
                    except:
                        record_count = "Invalid JSON"
                        
                files_info[filename] = {
                    "exists": True,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "record_count": record_count
                }
            else:
                files_info[filename] = {"exists": False}
        
        # 이미지 디렉토리 확인
        image_dir = os.path.join(BACKUP_DIR, 'images')
        if os.path.exists(image_dir):
            image_folders = [d for d in os.listdir(image_dir) if os.path.isdir(os.path.join(image_dir, d))]
            files_info["images"] = {
                "exists": True,
                "folder_count": len(image_folders),
                "sample_folders": image_folders[:5]  # 처음 5개만
            }
        else:
            files_info["images"] = {"exists": False}
            
        return jsonify({
            "backup_dir": BACKUP_DIR,
            "files": files_info,
            "total_files": len([f for f in files_info.values() if f.get("exists")])
        })
        
    except Exception as e:
        logger.error(f"백업 파일 확인 오류: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/category-properties')
def get_category_properties():
    """백업된 특정 카테고리의 모든 매물 가져오기"""
    try:
        view_id = request.args.get('view')
        if not view_id:
            return jsonify({"error": "View ID parameter is required"}), 400
        
        # 뷰 ID에 따른 파일 선택
        filename = None
        if view_id == 'viwzEVzrr47fCbDNU':  # 재건축용 토지
            filename = 'reconstruction_properties.json'
        elif view_id == 'viwxS4dKAcQWmB0Be':  # 고수익률 건물
            filename = 'high_yield_properties.json'
        elif view_id == 'viwUKnawSP8SkV9Sx':  # 저가단독주택
            filename = 'low_cost_properties.json'
        else:
            return jsonify({"error": "Invalid view ID"}), 400
        
        file_path = os.path.join(BACKUP_DIR, filename)
        
        if not os.path.exists(file_path):
            return jsonify({"error": "Backup file not found"}), 404
        
        # 파일에서 데이터 로드
        with open(file_path, 'r', encoding='utf-8') as f:
            records = json.load(f)
        
        # 유효한 상태인 레코드만 필터링
        valid_status = ["네이버", "디스코", "당근", "비공개"]
        
        filtered_records = []
        for record in records:
            fields = record.get('fields', {})
            status = fields.get('현황')
            is_valid_status = False
            
            if status:
                if isinstance(status, list):
                    is_valid_status = any(s in valid_status for s in status)
                elif isinstance(status, str):
                    is_valid_status = status in valid_status
            
            if is_valid_status:
                filtered_records.append(record)
        
        response_data = {
            "records": filtered_records,
            "view_id": view_id,
            "total_count": len(filtered_records),
            "source": "backup"
        }
        
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"카테고리 매물 목록 API 오류: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/property-detail')
def get_property_detail():
    """백업된 데이터에서 특정 매물 상세 정보 가져오기"""
    return get_property_detail_backup()  # 동일한 함수 호출로 통일

@app.route('/api/property-detail-backup')
def get_property_detail_backup():
    """백업된 데이터에서 특정 매물 상세 정보 가져오기 (HTML 호환용)"""
    try:
        property_id = request.args.get('id')
        if not property_id:
            return jsonify({'error': 'Record ID is required'}), 400
        
        # 모든 매물 데이터 파일 로드
        file_path = os.path.join(BACKUP_DIR, 'all_properties.json')
        
        if not os.path.exists(file_path):
            logger.error(f"백업 파일을 찾을 수 없음: {file_path}")
            return jsonify({"error": "Backup file not found"}), 404
        
        # 파일에서 데이터 로드
        with open(file_path, 'r', encoding='utf-8') as f:
            all_properties = json.load(f)
        
        # 요청된 ID의 매물 찾기
        property_data = next((p for p in all_properties if p.get('id') == property_id), None)
        
        if not property_data:
            return jsonify({'error': f'Property with ID {property_id} not found'}), 404
        
        response_data = {'property': property_data}
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"매물 상세 조회 중 오류 발생: {str(e)}")
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

# ===== 검색 및 지도 관련 API =====
@app.route('/api/search-map', methods=['POST'])
def search_map():
    """백업 데이터에서 검색 조건에 따른 동적 지도 생성"""
    try:
        import folium
        from datetime import datetime
        
        search_conditions = request.json
        logger.info(f"Search conditions: {search_conditions}")
        
        # 백업 파일에서 데이터 로드
        all_properties_path = os.path.join(BACKUP_DIR, 'all_properties.json')
        
        if not os.path.exists(all_properties_path):
            logger.warning("백업 파일을 찾을 수 없습니다.")
            return jsonify({"error": "Backup file not found"}), 404
        
        with open(all_properties_path, 'r', encoding='utf-8') as f:
            all_records = json.load(f)
        
        logger.info(f"백업에서 {len(all_records)}개 레코드를 로드했습니다.")
        
        # 필터링 처리
        filtered_records = []
        status_filtered_count = 0
        condition_filtered_count = 0
        geocoding_failed_count = 0
        
        for i, record in enumerate(all_records):
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
            
            if not is_valid_status:
                status_filtered_count += 1
                continue
            
            # 각 조건 확인
            should_include = True
            
            # 매가 조건
            if search_conditions.get('price_value', '').strip() and search_conditions.get('price_condition') != 'all':
                price_raw = fields.get('매가(만원)', 0)
                try:
                    if isinstance(price_raw, str):
                        price = float(price_raw.replace(',', ''))
                    else:
                        price = float(price_raw) if price_raw else 0
                    
                    price_val = float(search_conditions['price_value'])
                    
                    if search_conditions['price_condition'] == 'above' and price < price_val:
                        should_include = False
                    elif search_conditions['price_condition'] == 'below' and price > price_val:
                        should_include = False
                except Exception as e:
                    logger.warning(f"Price parsing error for record {i}: {e}")
            
            # 수익률 조건
            if should_include and search_conditions.get('yield_value', '').strip() and search_conditions.get('yield_condition') != 'all':
                yield_raw = fields.get('융자제외수익률(%)', 0)
                try:
                    if isinstance(yield_raw, str):
                        yield_rate = float(yield_raw.replace(',', '').replace('%', ''))
                    else:
                        yield_rate = float(yield_raw) if yield_raw else 0
                    
                    yield_val = float(search_conditions['yield_value'])
                    
                    if search_conditions['yield_condition'] == 'above' and yield_rate < yield_val:
                        should_include = False
                    elif search_conditions['yield_condition'] == 'below' and yield_rate > yield_val:
                        should_include = False
                except Exception as e:
                    logger.warning(f"Yield parsing error for record {i}: {e}")
            
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
                    elif search_conditions['investment_condition'] == 'below' and investment > investment_val:
                        should_include = False
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
                    elif search_conditions['area_condition'] == 'below' and area > area_val:
                        should_include = False
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
                        elif search_conditions['approval_condition'] == 'after' and approval_datetime <= target_datetime:
                            should_include = False
                except Exception as e:
                    logger.warning(f"Date parsing error: {e}")
            
            if not should_include:
                condition_filtered_count += 1
            else:
                filtered_records.append(record)
        
        logger.info(f"필터링 요약: 전체 {len(all_records)}, 필터 통과 {len(filtered_records)}")
        
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
            
            popup_html += f'''
            <a href="javascript:void(0);" 
                onclick="(function() {{ try {{ parent.openPropertyDetailGlobal('{record_id}'); }} catch(e) {{ window.parent.postMessage({{action:'openPropertyDetail',recordId:'{record_id}'}}, '*'); }} }})();"
                style="display: block; margin-top: 10px; padding: 5px; background-color: #f5f5f5; text-align: center; color: #e38000; text-decoration: none;">
                상세내역보기
            </a>
            <a href="javascript:void(0);" 
                onclick="(function() {{ try {{ parent.openConsultModalGlobal('{address}'); }} catch(e) {{ window.parent.postMessage({{action:'openConsultModal',address:'{address}'}}, '*'); }} }})();"
                style="display: block; margin-top: 5px; padding: 5px; background-color: #2962FF; color: white; text-align: center; text-decoration: none;">
                이 매물 문의하기
            </a>
            '''
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
        
        logger.info(f"백업 데이터에서 {added_markers}개의 마커를 지도에 추가했습니다.")
        
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
                "markers_added": added_markers,
                "source": "backup"
            }
        })
        
    except Exception as e:
        logger.error(f"백업 데이터 검색 오류: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ===== 이미지 관련 API =====
@app.route('/api/check-image')
def check_image():
    """특정 레코드의 이미지 존재 여부 확인 (우선순위 기반 선택)"""
    record_id = request.args.get('record_id')
    if not record_id:
        return jsonify({"error": "Record ID is required"}), 400
    
    # 백업 디렉토리의 이미지 경로
    image_dir = os.path.join(BACKUP_DIR, 'images', record_id)
    
    # 디렉토리 존재 확인
    if not os.path.exists(image_dir):
        return jsonify({"hasImage": False, "reason": "Directory not found"}), 200
    
    try:
        # 이미지 파일 찾기
        image_files = []
        for f in os.listdir(image_dir):
            file_path = os.path.join(image_dir, f)
            if (os.path.isfile(file_path) and 
                f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')) and
                os.path.getsize(file_path) > 0):  # 0바이트 파일 제외
                image_files.append(f)
        
        if not image_files:
            return jsonify({"hasImage": False, "reason": "No valid image files found"}), 200
        
        # 이미지 파일들을 우선순위에 따라 정렬
        def get_image_priority(filename):
            filename_lower = filename.lower()
            
            # 1순위: 원본 파일명 (날짜가 포함되거나 카카오톡 등)
            if any(keyword in filename_lower for keyword in ['202', 'kakao', 'img_', 'dsc_']):
                return (1, len(filename))  # 원본 파일명, 길이 순
            
            # 2순위: representative 파일
            elif 'representative' in filename_lower:
                return (2, len(filename))
            
            # 3순위: 기타 파일
            elif not filename_lower.startswith('photo_'):
                return (3, len(filename))
            
            # 4순위: photo_ 로 시작하는 생성된 파일명
            else:
                return (4, len(filename))
        
        # 우선순위에 따라 정렬 (1순위가 먼저, 같은 순위면 파일명 길이 순)
        image_files.sort(key=get_image_priority)
        
        # 가장 우선순위 높은 이미지 선택
        selected_image = image_files[0]
        
        # 파일 정보 확인
        image_path = os.path.join(image_dir, selected_image)
        file_size = os.path.getsize(image_path)
        
        logger.info(f"이미지 선택: {record_id} -> {selected_image} ({file_size} bytes, 우선순위: {get_image_priority(selected_image)[0]})")
        
        return jsonify({
            "hasImage": True,
            "filename": selected_image,
            "fileSize": file_size,
            "priority": get_image_priority(selected_image)[0],
            "allImages": image_files,
            "totalFiles": len(image_files)
        }), 200
        
    except Exception as e:
        logger.error(f"이미지 확인 중 오류: {record_id} - {str(e)}")
        return jsonify({
            "hasImage": False, 
            "error": str(e),
            "reason": "Error occurred while checking images"
        }), 500

# 디버깅용 API도 업데이트
@app.route('/api/debug/image-priority')
def debug_image_priority():
    """이미지 우선순위 확인 (디버깅용)"""
    record_id = request.args.get('record_id')
    if not record_id:
        return jsonify({"error": "Record ID is required"}), 400
    
    image_dir = os.path.join(BACKUP_DIR, 'images', record_id)
    
    if not os.path.exists(image_dir):
        return jsonify({"exists": False, "directory": image_dir})
    
    try:
        files_with_priority = []
        for filename in os.listdir(image_dir):
            file_path = os.path.join(image_dir, filename)
            if os.path.isfile(file_path):
                def get_image_priority(fname):
                    fname_lower = fname.lower()
                    if any(keyword in fname_lower for keyword in ['202', 'kakao', 'img_', 'dsc_']):
                        return 1  # 원본 파일명
                    elif 'representative' in fname_lower:
                        return 2  # representative
                    elif not fname_lower.startswith('photo_'):
                        return 3  # 기타
                    else:
                        return 4  # photo_ 생성 파일
                
                files_with_priority.append({
                    "filename": filename,
                    "size": os.path.getsize(file_path),
                    "priority": get_image_priority(filename),
                    "is_image": filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))
                })
        
        # 우선순위 순으로 정렬
        files_with_priority.sort(key=lambda x: (x['priority'], -x['size']))
        
        return jsonify({
            "exists": True,
            "directory": image_dir,
            "files": files_with_priority,
            "recommended": files_with_priority[0] if files_with_priority else None
        })
        
    except Exception as e:
        return jsonify({"exists": True, "directory": image_dir, "error": str(e)})

# 백업 이미지 디렉토리를 정적 파일로 제공
@app.route('/airtable_backup/images/<path:path>')
def serve_backup_images(path):
    """백업 이미지 제공"""
    image_dir = os.path.join(BACKUP_DIR, 'images')
    return send_from_directory(image_dir, path)

# ===== 상담 문의 API =====
@app.route('/api/submit-inquiry', methods=['POST'])
def submit_inquiry():
    logger.info("=== 상담 문의 접수 시작 ===")
    
    data = request.json
    logger.info(f"받은 데이터: {data}")

    # 매물 종류 매핑
    property_type_map = {
        'house': '단독/다가구',
        'mixed': '상가주택', 
        'commercial': '상업용건물',
        'land': '재건축/토지',
        'sell': '매물접수'
    }

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
        response = requests.post(url, json=payload, headers=headers)
        
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

# ===== AI 매물 검색 API =====
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
        
        # 백업 데이터에서 매물 정보 가져오기
        all_properties_path = os.path.join(BACKUP_DIR, 'all_properties.json')
        
        if not os.path.exists(all_properties_path):
            return jsonify({"error": "Property data not available"}), 500
            
        with open(all_properties_path, 'r', encoding='utf-8') as f:
            all_records = json.load(f)
        
        # 매물 정보 구조화
        properties = []
        valid_status = ["네이버", "디스코", "당근", "비공개"]
        
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
            
            if not is_valid_status:
                continue
            
            # 가격 처리
            price_raw = fields.get('매가(만원)', 0)
            try:
                price_in_man = float(price_raw) if price_raw else 0
                price_display = f"{price_in_man / 10000:.1f}억원" if price_in_man >= 10000 else f"{int(price_in_man)}만원"
            except:
                price_display = "가격정보없음"
            
            # 실투자금 처리
            investment_raw = fields.get('실투자금', 0)
            try:
                investment_in_man = float(investment_raw) if investment_raw else 0
                investment_display = f"{investment_in_man / 10000:.1f}억원" if investment_in_man >= 10000 else f"{int(investment_in_man)}만원"
            except:
                investment_display = "정보없음"
            
            # 수익률 처리
            yield_rate = fields.get('융자제외수익률(%)', '')
            try:
                yield_display = f"{float(yield_rate)}%" if yield_rate else "정보없음"
            except:
                yield_display = "정보없음"
            
            property_info = {
                "id": record.get('id', ''),
                "address": fields.get('지번 주소', ''),
                "price": price_display,
                "actual_investment": investment_display,
                "monthly_income": fields.get('월세(만원)', ''),
                "yield": yield_display,
                "property_type": fields.get('주용도', ''),
                "area": fields.get('토지면적(㎡)', '')
            }
            properties.append(property_info)
        
        # AI 분석을 위해 데이터 제한
        properties_for_ai = properties[:15] if len(properties) > 15 else properties
        
        # Claude API 호출
        prompt = f"""
        다음은 부동산 매물 목록입니다 (전체 {len(properties)}개 중 {len(properties_for_ai)}개):
        {json.dumps(properties_for_ai, ensure_ascii=False, indent=2)}
        
        사용자의 검색 조건:
        - 지역: {location}
        - 희망매매가: {price_range}
        - 실투자금: {investment}
        - 희망투자수익률: {expected_yield}
        
        위 조건에 가장 적합한 매물 2-3개를 추천해주세요.
        
        각 매물에 대해 다음 형식으로 답변해주세요:
        
        ## 매물 1:
        위치: [주소]
        가격: [price 필드 값 그대로]
        주용도: [주용도]
        수익률: [yield 필드 값 그대로]
        추천 이유: [이 사용자에게 왜 이 매물이 적합한지 간단히 설명]
        실투자금: [actual_investment 필드 값 그대로]로 효율적인 투자가 가능합니다.
        
        조건에 맞는 매물이 없으면 '조건에 맞는 매물이 없습니다'라고 답변해주세요.
        """
        
        response = claude_client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=1000,
            system="당신은 부동산 투자 전문가입니다. 사용자의 조건에 맞는 최적의 매물을 추천해주세요.",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        recommendations = response.content[0].text
        
        return jsonify({
            "recommendations": recommendations,
            "total_properties": len(properties),
            "ai_analyzed": len(properties_for_ai)
        })
        
    except Exception as e:
        logger.error(f"AI property search error: {str(e)}")
        return jsonify({"error": f"Error processing request: {str(e)}"}), 500

def setup_detailed_logging():
    """상세한 로깅 설정"""
    # 파일 핸들러
    file_handler = logging.FileHandler('/home/sftpuser/logs/api_detailed.log')
    file_handler.setLevel(logging.DEBUG)
    
    # 콘솔 핸들러
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 포맷터
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # 로거에 핸들러 추가
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(logging.DEBUG)

# 애플리케이션 시작 시 로깅 설정
setup_detailed_logging()

# ===== 이메일 발송 함수 =====
def send_consultation_email(customer_data):
    """상담 문의 접수 시 이메일 발송 함수"""
    logger.info("=== 이메일 발송 함수 시작 ===")
    
    try:
        EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS")
        EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
        SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
        SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
        ADMIN_EMAIL = "cs21.jeon@gmail.com"
        
        if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
            logger.error("이메일 설정이 완료되지 않았습니다.")
            return False
        
        customer_email = customer_data.get('email', '').strip()
        customer_phone = customer_data.get('phone', '')
        property_type = customer_data.get('propertyType', '')
        message = customer_data.get('message', '')
        
        property_type_map = {
            'house': '단독/다가구',
            'mixed': '상가주택', 
            'commercial': '상업용빌딩',
            'land': '재건축/토지',
            'sell': '매물접수'
        }
        property_type_korean = property_type_map.get(property_type, property_type)
        
        customer_name = customer_email.split('@')[0] if customer_email else "고객"
        
        # SMTP 연결
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        
        emails_sent = 0
        
        # 고객에게 확인 이메일 발송
        if customer_email:
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
            emails_sent += 1
        
        # 관리자에게 알림 이메일 발송
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
        emails_sent += 1
        
        server.quit()
        
        logger.info(f"=== 이메일 발송 완료: 총 {emails_sent}개 발송 ===")
        return emails_sent > 0
        
    except Exception as e:
        logger.error(f"이메일 발송 함수 전체 오류: {str(e)}")
        return False

# ===== 블로그 관련 API =====
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
            "summary": clean_summary,
            "published": entry.published,
            "has_thumbnail": has_thumbnail
        })

    blog_cache["timestamp"] = now
    blog_cache["posts"] = posts
    return jsonify(posts)

def clean_html_content(html_content):
    """HTML 콘텐츠에서 이미지 태그를 제거하고 텍스트만 추출"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 모든 img 태그 제거
    for img in soup.find_all('img'):
        img.decompose()
    
    # HTML에서 텍스트만 추출
    text = soup.get_text(strip=True)
    
    # 텍스트 길이 제한 (150자)
    if len(text) > 150:
        text = text[:147] + '...'
    
    return text

# ===== 기타 엔드포인트 =====
@app.route('/health')
def health_check():
    """서버 상태 확인용 엔드포인트"""
    return jsonify({"status": "healthy"})

if __name__ == '__main__':
    logger.info(f"Starting server on port 8000")
    app.run(host="0.0.0.0", port=8000, debug=False)