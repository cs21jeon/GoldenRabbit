import requests
import os
import json
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# API 키 설정 - 하드코딩된 값 제거
NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET')
AIRTABLE_API_KEY = os.environ.get('AIRTABLE_API_KEY')

# API 키 확인
if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
    print("경고: 네이버 API 키가 설정되지 않았습니다. 환경 변수를 확인하세요.")
    # 개발 환경에서만 사용할 임시 값 (실제 배포 시 제거 필요)
    if not NAVER_CLIENT_ID:
        print("NAVER_CLIENT_ID 환경 변수가 필요합니다")
    if not NAVER_CLIENT_SECRET:
        print("NAVER_CLIENT_SECRET 환경 변수가 필요합니다")

if not AIRTABLE_API_KEY:
    print("경고: AIRTABLE_API_KEY가 설정되지 않았습니다. 환경 변수를 확인하세요.")

# 에어테이블 설정
BASE_ID = 'appGSg5QfDNKgFf73'
TABLE_ID = 'tblnR438TK52Gr0HB'
ADDRESS_FIELD = '지번 주소'
PRICE_FIELD = '매가(만원)'
STATUS_FIELD = '현황'

# 팝업에 표시할 추가 필드
ADDITIONAL_FIELDS = {
    '토지면적(㎡)': '토지면적(㎡)',
    '연면적(㎡)': '연면적(㎡)',
    '건폐율(%)': '건폐율(%)',
    '용적률(%)': '용적률(%)',
    '용도지역': '용도지역',
    '주용도': '주용도',
    '층수': '층수',
    '사용승인일': '사용승인일',
    '보증금(만원)': '보증금(만원)',
    '월세(만원)': '월세(만원)',
    '인접역': '인접역',
    '거리(m)': '거리(m)',
    '상세설명': '상세설명'
}

def get_airtable_data():
    """에어테이블에서 데이터를 가져오는 함수"""
    url = f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}'
    
    headers = {
        'Authorization': f'Bearer {AIRTABLE_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    print(f"에어테이블 API 요청 URL: {url}")
    print(f"베이스 ID: {BASE_ID}")
    print(f"테이블 ID: {TABLE_ID}")
    print(f"검색할 필드명: address_field='{ADDRESS_FIELD}', price_field='{PRICE_FIELD}', status_field='{STATUS_FIELD}'")

    all_records = []
    offset = None

    try:
        # 페이지네이션을 사용하여 모든 레코드 가져오기
        while True:
            params = {}
            if offset:
                params['offset'] = offset
            
            response = requests.get(url, headers=headers, params=params)
            
            print(f"API 응답 상태 코드: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                records = data.get('records', [])
                all_records.extend(records)
                
                print(f"현재까지 가져온 레코드 수: {len(all_records)}")
                
                # 첫 페이지일 경우 필드 정보 디버깅
                if len(all_records) <= len(records) and len(records) > 0:
                    fields = records[0].get('fields', {})
                    print(f"첫 번째 레코드의 필드 키: {list(fields.keys())}")
                    
                    # 필드명 공백 문제 확인
                    possible_address_fields = [k for k in fields.keys() if '주소' in k or 'address' in k.lower()]
                    possible_price_fields = [k for k in fields.keys() if '매가' in k or 'price' in k.lower() or '금액' in k]
                    possible_status_fields = [k for k in fields.keys() if '현황' in k or 'status' in k.lower()]
                    
                    print(f"가능한 주소 필드: {possible_address_fields}")
                    print(f"가능한 가격 필드: {possible_price_fields}")
                    print(f"가능한 현황 필드: {possible_status_fields}")
                
                # 다음 페이지가 있는지 확인
                offset = data.get('offset')
                if not offset:
                    break  # 더 이상 페이지가 없으면 종료
            else:
                print(f"에어테이블 API 오류: {response.status_code}")
                print(response.text)
                break
        
        # 데이터 처리
        address_data = []
        for record in all_records:
            fields = record.get('fields', {})
            
            # 필드 값 가져오기
            address = fields.get(ADDRESS_FIELD)
            name = address  # 주소를 이름으로도 사용
            price = fields.get(PRICE_FIELD)
            status = fields.get(STATUS_FIELD)
            
            # 추가 필드 값 가져오기
            field_values = {}
            for display_name, field_name in ADDITIONAL_FIELDS.items():
                field_values[display_name] = fields.get(field_name)
            
            # 디버깅: 일부 레코드의 실제 값 출력
            if len(address_data) < 3:  # 처음 3개 레코드만 출력
                print(f"address 필드값: {address}")
                print(f"price 필드값: {price}")
                print(f"status 필드값: {status}")
                
                # 첫 번째 레코드의 추가 필드 값 출력
                for display_name, value in field_values.items():
                    print(f"{display_name} 필드값: {value}")
            
            # 필터링: 주소가 있고, 현황이 특정 값 중 하나인 경우에만 처리
            valid_status = ["네이버", "디스코", "당근", "비공개"]
            
            # 현황 필드 확인
            is_valid_status = False
            if address is not None and status is not None:
                if isinstance(status, list):
                    is_valid_status = any(s in valid_status for s in status)
                elif isinstance(status, str):
                    is_valid_status = status in valid_status
            
            if address is not None and is_valid_status:
                # 숫자 형식의 가격인 경우 숫자로 변환
                try:
                    if isinstance(price, str) and price.isdigit():
                        price = int(price)
                    elif isinstance(price, (int, float)):
                        price = int(price)
                except (ValueError, TypeError):
                    pass
                
                address_data.append([name, address, price, status, field_values])
        
        print(f"필터링 후 사용할 레코드 수: {len(address_data)}")
        return address_data
    
    except Exception as e:
        print(f"API 요청 중 예외 발생: {str(e)}")
        return []

def geocode_address(address):
    """네이버 지도 API를 사용하여 주소를 좌표로 변환하는 함수"""
    url = "https://naveropenapi.apigw.ntruss.com/map-geocode/v2/geocode"
    params = {
        "query": address
    }
    headers = {
        "X-NCP-APIGW-API-KEY-ID": NAVER_CLIENT_ID,
        "X-NCP-APIGW-API-KEY": NAVER_CLIENT_SECRET
    }
    
    try:
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "OK" and len(data.get("addresses", [])) > 0:
                # 첫 번째 결과 반환
                coords = data["addresses"][0]
                return {
                    "x": float(coords["x"]),  # 경도
                    "y": float(coords["y"])   # 위도
                }
            else:
                print(f"주소 검색 결과 없음: {address}")
                return None
        else:
            print(f"네이버 지도 API 오류: {response.status_code}")
            print(response.text)
            return None
    except Exception as e:
        print(f"좌표 변환 중 오류 발생: {str(e)}")
        return None

def create_map():
    """네이버 지도 기반의 HTML 파일을 생성하는 함수"""
    # API 키 확인
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        print("오류: 네이버 API 키가 설정되지 않았습니다. 환경 변수를 확인하세요.")
        return
    
    if not AIRTABLE_API_KEY:
        print("오류: AIRTABLE_API_KEY가 설정되지 않았습니다. 환경 변수를 확인하세요.")
        return

    # 에어테이블에서 주소 데이터 가져오기
    address_data = get_airtable_data()
    
    if not address_data:
        print("에어테이블에서 가져온 주소 데이터가 없습니다.")
        return
    
    # 모든 주소의 좌표 가져오기
    print("주소 좌표 변환 시작...")
    locations = []
    for addr in address_data:
        address = addr[1]
        coords = geocode_address(address)
        if coords:
            # 데이터 포맷 조정
            location = {
                "address": address,
                "name": addr[0],
                "price": addr[2],
                "status": addr[3],
                "fields": addr[4],
                "lat": coords["y"],
                "lng": coords["x"]
            }
            locations.append(location)
            print(f"좌표 변환 성공: {address} -> {coords}")
        else:
            print(f"좌표 변환 실패: {address}")
    
    print(f"좌표 변환 완료, 총 위치 수: {len(locations)}")
    
    # 중심 좌표 계산 (모든 위치의 평균)
    if locations:
        center_lat = sum(loc["lat"] for loc in locations) / len(locations)
        center_lng = sum(loc["lng"] for loc in locations) / len(locations)
    else:
        # 기본 중심 좌표 (서울)
        center_lat = 37.5665
        center_lng = 126.9780
    
    # HTML 파일 생성
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>부동산 지도</title>
    <script type="text/javascript" src="https://openapi.map.naver.com/openapi/v3/maps.js?ncpClientId={NAVER_CLIENT_ID}"></script>
    <style>
        #map {{
            width: 100%;
            height: 800px;
        }}
        .marker-info {{
            padding: 10px;
            font-family: 'Malgun Gothic', '맑은 고딕', sans-serif;
            font-size: 14px;
            line-height: 1.5;
        }}
        .marker-info h3 {{
            margin: 0 0 5px 0;
            font-size: 16px;
        }}
        .marker-info b {{
            font-weight: 600;
        }}
        .marker-info hr {{
            margin: 8px 0;
            border: 0;
            border-top: 1px solid #eee;
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    <script>
        // 지도 데이터
        const locations = {json.dumps(locations)};
        
        // 지도 생성
        const map = new naver.maps.Map('map', {{
            center: new naver.maps.LatLng({center_lat}, {center_lng}),
            zoom: 14,
            mapTypeId: naver.maps.MapTypeId.NORMAL
        }});
        
        // 정보창 생성
        const infoWindow = new naver.maps.InfoWindow({{
            anchorSkew: true,
            backgroundColor: "white",
            borderWidth: 1,
            borderColor: "#ccc",
            pixelOffset: new naver.maps.Point(20, -20),
            disableAutoPan: false
        }});
        
        // 가격 포맷팅 함수
        function formatPrice(price) {{
            if (typeof price === 'number') {{
                if (price >= 10000) {{
                    const billion = price / 10000;
                    if (billion % 1 === 0) {{
                        return `${{Math.floor(billion)}}억원`;
                    }} else {{
                        return `${{billion.toFixed(1).replace('.0', '')}}억원`;
                    }}
                }} else {{
                    return `${{price.toLocaleString()}}만원`;
                }}
            }}
            return price ? `${{price}}만원` : '가격정보 없음';
        }}
        
        // 마커 생성 및 추가
        locations.forEach(loc => {{
            const marker = new naver.maps.Marker({{
                position: new naver.maps.LatLng(loc.lat, loc.lng),
                map: map,
                icon: {{
                    content: `<div style="width: 12px; height: 12px; background-color: red; border-radius: 50%;"></div>`,
                    size: new naver.maps.Size(12, 12),
                    anchor: new naver.maps.Point(6, 6)
                }},
                title: loc.address
            }});
            
            // 주소에서 동명과 번지만 추출
            let shortAddress = loc.address;
            if (loc.address.includes(' ')) {{
                shortAddress = loc.address.substring(loc.address.indexOf(' ') + 1);
            }}
            
            // 현황 정보 표시
            let statusInfo = "";
            if (loc.status) {{
                if (Array.isArray(loc.status)) {{
                    statusInfo = loc.status.join(', ');
                }} else {{
                    statusInfo = loc.status;
                }}
            }}
            
            // 팝업 내용 생성
            let popupContent = `<div class="marker-info">`;
            popupContent += `<h3>${{shortAddress}}</h3>`;
            popupContent += `<b>매가:</b> ${{formatPrice(loc.price)}}<br>`;
            
            // 추가 필드 표시
            const fields = loc.fields;
            
            // 대지 정보 추가
            if (fields['토지면적(㎡)']) {{
                try {{
                    const landAreaSqm = parseFloat(fields['토지면적(㎡)']);
                    const landAreaPyeong = Math.round(landAreaSqm / 3.3058);
                    popupContent += `<b>대지:</b> ${{landAreaPyeong}}평 (${{landAreaSqm}}㎡)<br>`;
                }} catch (e) {{}}
            }}
            
            // 연식 정보 추가
            if (fields['사용승인일']) {{
                try {{
                    const approvalDate = String(fields['사용승인일']);
                    if (approvalDate.includes('-') || approvalDate.includes('/')) {{
                        const year = approvalDate.includes('-') ? 
                            approvalDate.split('-')[0] : approvalDate.split('/')[0];
                        popupContent += `<b>연식:</b> ${{year}}년<br>`;
                    }} else if (approvalDate.length >= 4) {{
                        popupContent += `<b>연식:</b> ${{approvalDate.substring(0, 4)}}년<br>`;
                    }}
                }} catch (e) {{}}
            }}
            
            // 주용도 정보 추가
            if (fields['주용도']) {{
                popupContent += `<b>용도:</b> ${{fields['주용도']}}<br>`;
            }}
            
            // 층수 정보 추가
            if (fields['층수']) {{
                popupContent += `<b>층수:</b> ${{fields['층수']}}<br>`;
            }}
            
            // 현황 정보 추가
            if (statusInfo) {{
                popupContent += `<hr><b>현황:</b> ${{statusInfo}}`;
            }}
            
            popupContent += `</div>`;
            
            // 마커 클릭 이벤트 리스너 추가
            naver.maps.Event.addListener(marker, 'click', function() {{
                if (infoWindow.getMap()) {{
                    infoWindow.close();
                }}
                infoWindow.setContent(popupContent);
                infoWindow.open(map, marker);
            }});
        }});
        
        // 로드 완료 메시지
        console.log("지도가 성공적으로 로드되었습니다.");
    </script>
</body>
</html>
    """
    
    # HTML 파일 저장
    output_path = '/home/sftpuser/www/airtable_map_v2.html'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"지도가 {output_path} 파일로 저장되었습니다.")

if __name__ == "__main__":
    create_map()