import folium
import requests
import os
import time
from datetime import datetime, time as dtime, timedelta, timezone
import json
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

vworld_apikey = os.environ.get('VWORLD_APIKEY', 'YOUR_DEFAULT_KEY')
airtable_api_key = os.environ.get('AIRTABLE_API_KEY', 'YOUR_DEFAULT_API_KEY')

base_id = 'appGSg5QfDNKgFf73'
table_id = 'tblnR438TK52Gr0HB'
address_field = '지번 주소'
price_field = '매가(만원)'
status_field = '현황'

def debug_airtable_data():
    """에어테이블 데이터 가져오기 디버그 함수"""
    url = f'https://api.airtable.com/v0/{base_id}/{table_id}'
    headers = {
        'Authorization': f'Bearer {airtable_api_key}',
        'Content-Type': 'application/json'
    }

    print(f"🔍 API 요청 URL: {url}")
    print(f"🔑 API 키 존재 여부: {bool(airtable_api_key and airtable_api_key != 'YOUR_DEFAULT_API_KEY')}")
    print(f"📋 Base ID: {base_id}")
    print(f"📊 Table ID: {table_id}")
    
    try:
        response = requests.get(url, headers=headers)
        print(f"📡 HTTP 응답 코드: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ API 오류: {response.status_code}")
            print(f"📄 응답 내용: {response.text}")
            return []
        
        data = response.json()
        records = data.get('records', [])
        print(f"📊 전체 레코드 수: {len(records)}")
        
        if len(records) == 0:
            print("⚠️ 레코드가 없습니다. 테이블이 비어있거나 권한 문제일 수 있습니다.")
            return []
        
        # 첫 번째 레코드 구조 확인
        if records:
            first_record = records[0]
            print(f"📝 첫 번째 레코드 ID: {first_record.get('id')}")
            print(f"📋 첫 번째 레코드 필드들:")
            fields = first_record.get('fields', {})
            for field_name, field_value in fields.items():
                print(f"   - {field_name}: {field_value}")
        
        # 필수 필드 확인
        valid_records = 0
        invalid_records = 0
        
        valid_status = ["네이버", "디스코", "당근", "비공개"]
        
        for i, record in enumerate(records):
            fields = record.get('fields', {})
            address = fields.get(address_field)
            status = fields.get(status_field)
            
            has_address = bool(address)
            has_valid_status = False
            
            if status:
                if isinstance(status, list):
                    has_valid_status = any(s in valid_status for s in status)
                elif isinstance(status, str):
                    has_valid_status = status in valid_status
            
            if has_address and has_valid_status:
                valid_records += 1
                if valid_records <= 3:  # 처음 3개만 출력
                    print(f"✅ 유효한 레코드 {valid_records}: {address} - {status}")
            else:
                invalid_records += 1
                if invalid_records <= 3:  # 처음 3개만 출력
                    print(f"❌ 무효한 레코드 {invalid_records}: 주소={address}, 상태={status}")
        
        print(f"📈 유효한 레코드: {valid_records}개")
        print(f"📉 무효한 레코드: {invalid_records}개")
        
        return records
        
    except requests.exceptions.RequestException as e:
        print(f"🌐 네트워크 오류: {str(e)}")
        return []
    except json.JSONDecodeError as e:
        print(f"📄 JSON 파싱 오류: {str(e)}")
        return []
    except Exception as e:
        print(f"❌ 예상치 못한 오류: {str(e)}")
        return []

def test_geocoding():
    """지오코딩 테스트"""
    test_address = "서울특별시 강남구 역삼동 123-45"
    print(f"\n🗺️ 지오코딩 테스트: {test_address}")
    print(f"🔑 VWorld API 키 존재 여부: {bool(vworld_apikey and vworld_apikey != 'YOUR_DEFAULT_KEY')}")
    
    url = "https://api.vworld.kr/req/address"
    params = {
        "service": "address",
        "request": "getcoord",
        "format": "json",
        "crs": "EPSG:4326",
        "type": "PARCEL",
        "address": test_address,
        "key": vworld_apikey
    }
    
    try:
        response = requests.get(url, params=params)
        print(f"📡 지오코딩 응답 코드: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"📄 지오코딩 응답: {data}")
            
            if data.get('response', {}).get('status') == 'OK':
                result = data['response']['result']
                lat = float(result['point']['y'])
                lon = float(result['point']['x'])
                print(f"✅ 좌표 변환 성공: {lat}, {lon}")
            else:
                print(f"❌ 지오코딩 실패: {data.get('response', {}).get('status')}")
        else:
            print(f"❌ 지오코딩 API 오류: {response.text}")
            
    except Exception as e:
        print(f"❌ 지오코딩 오류: {str(e)}")

def enhanced_get_airtable_data():
    """개선된 에어테이블 데이터 가져오기"""
    url = f'https://api.airtable.com/v0/{base_id}/{table_id}'
    headers = {
        'Authorization': f'Bearer {airtable_api_key}',
        'Content-Type': 'application/json'
    }

    all_records = []
    offset = None
    page_count = 0

    try:
        while True:
            page_count += 1
            params = {}
            if offset:
                params['offset'] = offset
                
            print(f"📄 페이지 {page_count} 요청 중...")
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                records = data.get('records', [])
                all_records.extend(records)
                print(f"📊 페이지 {page_count}: {len(records)}개 레코드")
                
                offset = data.get('offset')
                if not offset:
                    break
            else:
                print(f"❌ 에어테이블 API 오류: {response.status_code}")
                print(f"📄 오류 내용: {response.text}")
                break

        print(f"📈 총 {len(all_records)}개 레코드 수집 완료")

        # 데이터 처리
        address_data = []
        valid_status = ["네이버", "디스코", "당근", "비공개"]
        
        for record in all_records:
            record_id = record.get('id')
            fields = record.get('fields', {})
            address = fields.get(address_field)
            price = fields.get(price_field)
            status = fields.get(status_field)

            # 상태 검증 개선
            is_valid_status = False
            if status:
                if isinstance(status, list):
                    is_valid_status = any(s in valid_status for s in status)
                elif isinstance(status, str):
                    is_valid_status = status in valid_status

            print(f"🔍 레코드 검증: 주소='{address}', 상태='{status}', 유효={is_valid_status}")

            if address and is_valid_status:
                # 추가 필드 수집
                additional_fields = {
                    '토지면적(㎡)': fields.get('토지면적(㎡)'),
                    '연면적(㎡)': fields.get('연면적(㎡)'),
                    '건폐율(%)': fields.get('건폐율(%)'),
                    '용적률(%)': fields.get('용적률(%)'),
                    '용도지역': fields.get('용도지역'),
                    '주용도': fields.get('주용도'),
                    '층수': fields.get('층수'),
                    '사용승인일': fields.get('사용승인일'),
                    '보증금(만원)': fields.get('보증금(만원)'),
                    '월세(만원)': fields.get('월세(만원)'),
                    '인접역': fields.get('인접역'),
                    '거리(m)': fields.get('거리(m)'),
                    '상세설명': fields.get('상세설명'),
                    '실투자금': fields.get('실투자금'),
                    '융자제외수익률(%)': fields.get('융자제외수익률(%)')
                }

                # 가격 처리
                try:
                    if isinstance(price, str) and price.isdigit():
                        price = int(price)
                    elif isinstance(price, (int, float)):
                        price = int(price)
                except:
                    pass

                address_data.append([address, address, price, status, additional_fields, record_id])
                print(f"✅ 유효한 데이터 추가: {address}")

        print(f"🎯 최종 유효 데이터: {len(address_data)}개")
        return address_data
        
    except Exception as e:
        print(f"❌ API 요청 중 예외 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        return []

if __name__ == "__main__":
    print("=" * 50)
    print("🔍 Airtable 연동 디버깅 시작")
    print("=" * 50)
    
    # 1. 환경 변수 확인
    print("\n1️⃣ 환경 변수 확인")
    print(f"   - AIRTABLE_API_KEY: {'✅ 설정됨' if airtable_api_key and airtable_api_key != 'YOUR_DEFAULT_API_KEY' else '❌ 미설정'}")
    print(f"   - VWORLD_APIKEY: {'✅ 설정됨' if vworld_apikey and vworld_apikey != 'YOUR_DEFAULT_KEY' else '❌ 미설정'}")
    
    # 2. Airtable 연결 테스트
    print("\n2️⃣ Airtable 연결 테스트")
    records = debug_airtable_data()
    
    # 3. 지오코딩 테스트
    print("\n3️⃣ 지오코딩 테스트")
    test_geocoding()
    
    # 4. 실제 데이터 처리 테스트
    print("\n4️⃣ 실제 데이터 처리 테스트")
    address_data = enhanced_get_airtable_data()
    
    print("\n" + "=" * 50)
    print(f"🎯 디버깅 완료 - 최종 결과: {len(address_data)}개 매물")
    print("=" * 50)