import folium
import requests
import os
import time
from datetime import datetime
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# 환경 변수에서 API 키 가져오기
vworld_apikey = os.environ.get('VWORLD_APIKEY', 'YOUR_DEFAULT_KEY')
airtable_api_key = os.environ.get('AIRTABLE_API_KEY', 'YOUR_DEFAULT_API_KEY')

base_id = 'appGSg5QfDNKgFf73'
table_id = 'tblnR438TK52Gr0HB'
address_field = '지번 주소'
price_field = '매가(만원)'
status_field = '현황'

# 팝업에 표시할 추가 필드
additional_fields = {
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
    url = f'https://api.airtable.com/v0/{base_id}/{table_id}'
    headers = {
        'Authorization': f'Bearer {airtable_api_key}',
        'Content-Type': 'application/json'
    }

    all_records = []
    offset = None

    try:
        while True:
            params = {}
            if offset:
                params['offset'] = offset
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                records = data.get('records', [])
                all_records.extend(records)
                offset = data.get('offset')
                if not offset:
                    break
            else:
                print(f"에어테이블 API 오류: {response.status_code}")
                print(response.text)
                break

        address_data = []
        for record in all_records:
            fields = record.get('fields', {})
            address = fields.get(address_field)
            name = address
            price = fields.get(price_field)
            status = fields.get(status_field)

            field_values = {display_name: fields.get(field_name) for display_name, field_name in additional_fields.items()}

            valid_status = ["네이버", "디스코", "당근", "비공개"]
            is_valid_status = False
            if address and status:
                if isinstance(status, list):
                    is_valid_status = any(s in valid_status for s in status)
                elif isinstance(status, str):
                    is_valid_status = status in valid_status

            if address and is_valid_status:
                try:
                    if isinstance(price, str) and price.isdigit():
                        price = int(price)
                    elif isinstance(price, (int, float)):
                        price = int(price)
                except:
                    pass
                address_data.append([name, address, price, status, field_values])
        return address_data
    except Exception as e:
        print(f"API 요청 중 예외 발생: {str(e)}")
        return []

def geocode_address(address):
    url = "https://api.vworld.kr/req/address"
    params = {
        "service": "address",
        "request": "getcoord",
        "format": "json",
        "crs": "EPSG:4326",
        "type": "PARCEL",
        "address": address,
        "key": vworld_apikey
    }
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data['response']['status'] == 'OK':
            result = data['response']['result']
            return float(result['point']['y']), float(result['point']['x'])
    except Exception as e:
        print(f"주소 변환 실패: {address}, 에러: {e}")
    return None, None

def create_map():
    folium_map = folium.Map(location=[37.4834458778777, 126.970207234818], zoom_start=15)
    folium.TileLayer(
        tiles='https://goldenrabbit.biz/api/vtile?z={z}&y={y}&x={x}',
        attr='공간정보 오픈플랫폼(브이월드)',
        name='브이월드 배경지도',
    ).add_to(folium_map)
    folium.WmsTileLayer(
        url='https://goldenrabbit.biz/api/wms?',
        layers='lt_c_landinfobasemap',
        request='GetMap',
        version='1.3.0',
        height=256,
        width=256,
        fmt='image/png',
        transparent=True,
        name='LX맵(편집지적도)',
    ).add_to(folium_map)
    folium.LayerControl().add_to(folium_map)

    address_data = get_airtable_data()
    if not address_data:
        print("에어테이블에서 가져온 주소 데이터가 없습니다.")
        return folium_map

    for addr in address_data:
        name, address, price, status, field_values = addr
        lat, lon = geocode_address(address)
        if lat is None or lon is None:
            continue
    
        price_display = f"{price:,}만원" if isinstance(price, int) and price < 10000 else f"{price / 10000:.1f}억원".rstrip('0').rstrip('.') if isinstance(price, int) else (price or "가격정보 없음")
    
        popup_html = f"<b>{name}</b><br>매가: {price_display}<br>"
        if field_values.get('토지면적(㎡)'):
            try:
                sqm = float(field_values['토지면적(㎡)'])
                pyeong = round(sqm / 3.3058)
                popup_html += f"대지: {pyeong}평 ({sqm}㎡)<br>"
            except:
                pass
        if field_values.get('층수'):
            popup_html += f"층수: {field_values['층수']}<br>"
        if field_values.get('주용도'):
            popup_html += f"용도: {field_values['주용도']}<br>"
        
        # CSS를 직접 삽입하는 대신 클래스를 사용
        folium_map.get_root().header.add_child(folium.Element("""
        <style>
        .price-bubble {
            background-color: #fff;
            border: 2px solid #e38000;
            border-radius: 6px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
            padding: 3px 6px;
            font-size: 12px;
            font-weight: bold;
            color: #e38000;
            white-space: nowrap;
            text-align: center;        
            /* 위치 관련 추가 */
            position: absolute;          /* 부모가 relative여야 함 */
            left: 50%;                   /* 부모 기준 가운데 */
            transform: translateX(-50%); /* 자기 자신 너비 절반만큼 왼쪽 이동 */
            width: 70px;                /* 원하는 폭 설정 */
        }
        .price-bubble:after {
            content: '';
            position: absolute;
            bottom: -8px;
            left: 50%;
            margin-left: -8px;
            width: 0;
            height: 0;
            border-left: 8px solid transparent;
            border-right: 8px solid transparent;
            border-top: 8px solid #e38000;
        }
        </style>
        """))
        
        # 간단한 HTML 구조 사용
        bubble_html = f'<div class="price-bubble">{price_display}</div>'
        
        # DivIcon 생성
        icon = folium.DivIcon(
            html=bubble_html,
            icon_size=(100, 40),
            icon_anchor=(50, 40),
            class_name="empty"  # 기본 CSS 클래스를 사용하지 않도록 설정
        )
        
        # 마커 추가
        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_html, max_width=250),
            icon=icon,
            tooltip=name
        ).add_to(folium_map)
    
    return folium_map

if __name__ == "__main__":
    cache_file = '/home/sftpuser/www/airtable_map.html'
    cache_time = 86400
    current_time = time.time()

    from datetime import time as dtime, timedelta, timezone

    # 서울 타임존
    KST = timezone(timedelta(hours=9))

    # 오늘 새벽 3시
    now = datetime.now(KST)
    today_3am = datetime.combine(now.date(), dtime(3, 0), tzinfo=KST)
    map_mtime = datetime.fromtimestamp(os.path.getmtime(cache_file), KST) if os.path.exists(cache_file) else None

    if map_mtime and map_mtime >= today_3am:
        print(f"캐시된 지도를 사용합니다. (생성 시간: {map_mtime})")
    else:
        print("새 지도를 생성합니다...")
        folium_map = create_map()
        folium_map.save(cache_file)
        print(f"지도가 {cache_file} 파일로 저장되었습니다.")
