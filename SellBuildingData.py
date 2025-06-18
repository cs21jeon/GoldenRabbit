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
    '상세설명': '상세설명',
    '실투자금': '실투자금',
    '융자제외수익률(%)': '융자제외수익률(%)'
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
            record_id = record.get('id')
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
                address_data.append([name, address, price, status, field_values, record_id])
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

def safe_string_for_js(text):
    """JavaScript에서 안전하게 사용할 수 있도록 문자열 처리"""
    if not text:
        return ""
    
    # 위험한 문자들을 안전하게 변환
    text = str(text)
    text = text.replace('\\', '\\\\')  # 백슬래시
    text = text.replace("'", "\\'")    # 작은따옴표
    text = text.replace('"', '\\"')    # 큰따옴표
    text = text.replace('\n', '\\n')   # 줄바꿈
    text = text.replace('\r', '\\r')   # 캐리지 리턴
    text = text.replace('\t', '\\t')   # 탭
    
    return text

def create_safe_popup_html(name, address, price_display, field_values, record_id):
    """안전한 팝업 HTML 생성"""
    
    # 문자열을 안전하게 처리
    safe_name = safe_string_for_js(name)
    safe_address = safe_string_for_js(address)
    safe_record_id = safe_string_for_js(record_id)
    
    popup_html = f"""
<div class="popup-content">
    <div class="popup-title">{safe_name}</div>
    <div class="popup-info">매가: {price_display}</div>
"""
    
    # 토지면적 정보
    if field_values.get('토지면적(㎡)'):
        try:
            sqm = float(field_values['토지면적(㎡)'])
            pyeong = round(sqm / 3.3058)
            popup_html += f'    <div class="popup-info">대지: {pyeong}평 ({sqm}㎡)</div>\n'
        except:
            pass
    
    # 층수 정보        
    if field_values.get('층수'):
        popup_html += f'    <div class="popup-info">층수: {field_values["층수"]}</div>\n'
    
    # 주용도 정보
    if field_values.get('주용도'):
        popup_html += f'    <div class="popup-info">용도: {field_values["주용도"]}</div>\n'

    # 상세내역 보기 링크 (안전한 방식)
    popup_html += f'''    <a href="javascript:void(0);" 
       onclick="handlePropertyDetail('{safe_record_id}')"
       class="detail-link">
       상세내역보기-클릭
    </a>
'''

    # 문의하기 링크 (안전한 방식)
    popup_html += f'''    <a href="javascript:void(0);" 
       onclick="handleConsultModal('{safe_address}')"
       class="detail-link" 
       style="background-color:#2962FF; color:white; margin-top:5px;">
       이 매물 문의하기
    </a>
'''

    popup_html += "</div>"
    
    return popup_html

def create_map():
    folium_map = folium.Map(location=[37.4834458778777, 126.970207234818], zoom_start=15)
    folium_map._name = 'leafletMap'  # 변수명 변경
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

    # CSS 스타일 추가
    folium_map.get_root().header.add_child(folium.Element("""
    <style>
    /* 가격 말풍선 스타일 */
    .price-bubble {
        background-color: #fff;
        border: 2px solid #e38000;
        border-radius: 6px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.2);
        padding: 3px 6px;
        font-size: 13px;
        font-weight: bold;
        color: #e38000;
        white-space: nowrap;
        text-align: center;
        position: absolute;
        left: 50%;
        transform: translateX(-50%);
        width: 70px;
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
    
    /* 팝업창 스타일 */
    .leaflet-popup-content-wrapper {
        border-radius: 8px;
        box-shadow: 0 3px 8px rgba(0,0,0,0.2);
        padding: 0;
    }
    .leaflet-popup-content {
        margin: 8px 10px;
        font-size: 14px;
        line-height: 1.5;
    }
    .leaflet-popup-tip {
        box-shadow: 0 3px 8px rgba(0,0,0,0.2);
    }
    .popup-content {
        font-family: 'Noto Sans KR', sans-serif;
    }
    .popup-title {
        font-size: 16px;
        font-weight: bold;
        margin-bottom: 6px;
        color: #333;
    }
    .popup-info {
        margin-top: 2px;
        color: #444;
    }
    /* 상세내역 보기 링크 스타일 */
    .detail-link {
        display: block;
        margin-top: 10px;
        padding: 5px;
        background-color: #f5f5f5;
        border-top: 1px solid #e0e0e0;
        text-align: center;
        font-weight: bold;
        color: #e38000;
        cursor: pointer;
        text-decoration: none;
        border-radius: 0 0 6px 6px;
    }
    .detail-link:hover {
        background-color: #e6e6e6;
    }
    </style>
    
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap" rel="stylesheet">
    """))

    address_data = get_airtable_data()
    if not address_data:
        print("에어테이블에서 가져온 주소 데이터가 없습니다.")
        return folium_map

    # JavaScript 데이터 수집
    javascript_data = []
    marker_index = 0

    for addr in address_data:
        name, address, price, status, field_values, record_id = addr
        lat, lon = geocode_address(address)
        if lat is None or lon is None:
            continue

        # JavaScript 데이터에 추가 (가격 필드 수정)
        property_price = price if price else field_values.get('매가(만원)', 0)
        try:
            property_price = float(property_price) if property_price else 0
        except:
            property_price = 0
            
        # 안전한 데이터 처리
        safe_data = {
            'index': marker_index,
            'lat': lat,
            'lon': lon,
            'name': safe_string_for_js(name),
            'address': safe_string_for_js(address),
            'price': property_price,
            'investment': float(field_values.get('실투자금', 0)) if field_values.get('실투자금') else 0,
            'yield': float(field_values.get('융자제외수익률(%)', 0)) if field_values.get('융자제외수익률(%)') else 0,
            'area': float(field_values.get('토지면적(㎡)', 0)) if field_values.get('토지면적(㎡)') else 0,
            'approval_date': safe_string_for_js(field_values.get('사용승인일', '')),
            'record_id': safe_string_for_js(record_id),
            'layers': safe_string_for_js(field_values.get('층수', '')),
            'usage': safe_string_for_js(field_values.get('주용도', '')),
            'land_area': field_values.get('토지면적(㎡)', 0)
        }
        
        javascript_data.append(safe_data)

        price_display = f"{price:,}만원" if isinstance(price, int) and price < 10000 else f"{price / 10000:.1f}억원".rstrip('0').rstrip('.') if isinstance(price, int) else (price or "가격정보 없음")

        # 안전한 팝업 HTML 생성
        popup_html = create_safe_popup_html(name, address, price_display, field_values, record_id)

        bubble_html = f'<div class="price-bubble">{price_display}</div>'
        icon = folium.DivIcon(
            html=bubble_html,
            icon_size=(100, 40),
            icon_anchor=(50, 40),
            class_name="empty"
        )

        marker = folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_html, max_width=250),
            icon=icon
        )
        marker._name = f"marker_{marker_index}"
        marker.add_to(folium_map)
        marker_index += 1

    # 안전한 JavaScript 코드 생성
    javascript_code = f"""
<script>
console.log('🔍 JavaScript 시작');

try {{
    // 데이터 로드
    var allProperties = {json.dumps(javascript_data, ensure_ascii=False, indent=2)};
    console.log('✅ 데이터 로드 완료:', allProperties.length, '개');

    // 마커 참조 저장
    var markers = {{}};

    // 안전한 매물 상세 핸들러
    function handlePropertyDetail(recordId) {{
        console.log('매물 상세 요청'); // 콘솔 데이터 가림 , recordId
        
        try {{
            // 부모 창에서 전체화면 상태 확인
            var isFullscreen = false;
            try {{
                isFullscreen = !!parent.document.querySelector('.map-container.fullscreen');
            }} catch(e) {{
                console.log('전체화면 상태 확인 실패:', e);
            }}
            
            console.log('전체화면 상태:', isFullscreen);
            
            // 다양한 방법으로 매물 상세 모달 열기 시도
            if (parent.openPropertyDetailGlobal) {{
                parent.openPropertyDetailGlobal(recordId);
            }} else if (parent.openPropertyDetailModal) {{
                parent.openPropertyDetailModal(recordId);
            }} else {{
                // 메시지로 전달
                parent.postMessage({{
                    action: 'openPropertyDetail',
                    recordId: recordId,
                    isFullscreen: isFullscreen
                }}, '*');
            }}
            
            // 전체화면 상태에서는 포커스 이동
            if (isFullscreen) {{
                parent.focus();
            }}
            
        }} catch(error) {{
            console.error('매물 상세 열기 실패:', error);
            // 폴백: 메시지 전달
            try {{
                parent.postMessage({{
                    action: 'openPropertyDetail',
                    recordId: recordId,
                    isFullscreen: false
                }}, '*');
            }} catch(e) {{
                console.error('메시지 전달도 실패:', e);
            }}
        }}
    }}

    // 안전한 상담 모달 핸들러
    function handleConsultModal(address) {{
        console.log('상담 모달 요청:', address);
        
        try {{
            if (parent.openConsultModalGlobal) {{
                parent.openConsultModalGlobal(address);
            }} else if (parent.openConsultModal) {{
                parent.openConsultModal(address);
            }} else {{
                parent.postMessage({{
                    action: 'openConsultModal',
                    address: address
                }}, '*');
            }}
        }} catch(error) {{
            console.error('상담 모달 열기 실패:', error);
            try {{
                parent.postMessage({{
                    action: 'openConsultModal',
                    address: address
                }}, '*');
            }} catch(e) {{
                console.error('메시지 전달도 실패:', e);
            }}
        }}
    }}

    // Leaflet 맵이 로드된 후 실행
    document.addEventListener('DOMContentLoaded', function() {{
        console.log('지도 초기화 시작');
        
        // 실제 leaflet 맵 변수를 자동으로 찾기
        var actualMap = null;
        for (var key in window) {{
            if (key.startsWith('leaflet_map_') && window[key] && window[key].eachLayer) {{
                actualMap = window[key];
                window.leafletMap = actualMap; // 별칭 생성
                console.log('지도 변수 찾음:', key);
                break;
            }}
        }}
        
        if (actualMap) {{
            console.log('지도 변수 설정 완료');
            
            // 마커 설정
            actualMap.eachLayer(function(layer) {{
                if (layer instanceof L.Marker) {{
                    var markerName = layer._myName;
                    if (markerName && markerName.startsWith('marker_')) {{
                        var index = parseInt(markerName.split('_')[1]);
                        markers[index] = layer;
                    }}
                }}
            }});
            
            console.log('마커 설정 완료:', Object.keys(markers).length, '개');
        }} else {{
            console.error('지도 변수를 찾을 수 없습니다!');
        }}
    }});
    
    function filterProperties(conditions) {{
        console.log('filterProperties 호출됨', conditions);
        var filteredProperties = [];
        var totalCount = allProperties.length;
        var filteredCount = 0;
        
        // 실제 맵 참조 가져오기
        var actualMap = window.leafletMap;
        if (!actualMap) {{
            for (var key in window) {{
                if (key.startsWith('leaflet_map_') && window[key] && window[key].eachLayer) {{
                    actualMap = window[key];
                    break;
                }}
            }}
        }}
        
        allProperties.forEach(function(property, index) {{
            var shouldShow = true;
            
            // 매가 조건
            if (conditions.price_value && conditions.price_condition !== 'all') {{
                var price = parseFloat(property.price) || 0;
                var priceVal = parseFloat(conditions.price_value);
                if (conditions.price_condition === 'above' && price < priceVal) shouldShow = false;
                if (conditions.price_condition === 'below' && price > priceVal) shouldShow = false;
            }}
            
            // 실투자금 조건
            if (conditions.investment_value && conditions.investment_condition !== 'all') {{
                var investment = parseFloat(property.investment) || 0;
                var investmentVal = parseFloat(conditions.investment_value);
                if (conditions.investment_condition === 'above' && investment < investmentVal) shouldShow = false;
                if (conditions.investment_condition === 'below' && investment > investmentVal) shouldShow = false;
            }}
            
            // 수익률 조건
            if (conditions.yield_value && conditions.yield_condition !== 'all') {{
                var yieldRate = parseFloat(property.yield) || 0;
                var yieldVal = parseFloat(conditions.yield_value);
                if (conditions.yield_condition === 'above' && yieldRate < yieldVal) shouldShow = false;
                if (conditions.yield_condition === 'below' && yieldRate > yieldVal) shouldShow = false;
            }}
            
            // 토지면적 조건
            if (conditions.area_value && conditions.area_condition !== 'all') {{
                var area = parseFloat(property.area) || 0;
                var areaVal = parseFloat(conditions.area_value);
                if (conditions.area_condition === 'above' && area < areaVal) shouldShow = false;
                if (conditions.area_condition === 'below' && area > areaVal) shouldShow = false;
            }}
            
            // 사용승인일 조건
            if (conditions.approval_date && conditions.approval_condition !== 'all') {{
                var approval = property.approval_date;
                if (approval) {{
                    var approvalDate = new Date(approval);
                    var targetDate = new Date(conditions.approval_date);
                    if (conditions.approval_condition === 'before' && approvalDate >= targetDate) shouldShow = false;
                    if (conditions.approval_condition === 'after' && approvalDate <= targetDate) shouldShow = false;
                }}
            }}
            
            if (shouldShow) {{
                filteredProperties.push(property);
                filteredCount++;
            }}
            
            // 마커 표시/숨김
            var marker = markers[index];
            if (marker && actualMap) {{
                if (shouldShow) {{
                    marker.addTo(actualMap);
                }} else {{
                    actualMap.removeLayer(marker);
                }}
            }}
        }});
        
        console.log('필터링 결과: ' + filteredCount + '/' + totalCount);
        return filteredProperties;
    }}
    
    // 전체 마커 표시
    function showAllMarkers() {{
        var actualMap = window.leafletMap;
        if (!actualMap) {{
            for (var key in window) {{
                if (key.startsWith('leaflet_map_') && window[key] && window[key].eachLayer) {{
                    actualMap = window[key];
                    break;
                }}
            }}
        }}
        
        if (actualMap) {{
            Object.values(markers).forEach(function(marker) {{
                marker.addTo(actualMap);
            }});
        }}
    }}
    
    // 부모 창과 통신
    window.addEventListener('message', function(event) {{
        if (event.data.type === 'filter') {{
            var filtered = filterProperties(event.data.conditions);
            parent.postMessage({{
                type: 'filterResult',
                count: filtered.length
            }}, '*');
        }} else if (event.data.type === 'reset') {{
            showAllMarkers();
            parent.postMessage({{
                type: 'filterResult',
                count: allProperties.length
            }}, '*');
        }}
    }});
    
    console.log('✅ JavaScript 초기화 완료');
    
}} catch(error) {{
    console.error('❌ JavaScript 오류:', error);
}}
</script>
"""
    
    folium_map.get_root().header.add_child(folium.Element(javascript_code))

    return folium_map

if __name__ == "__main__":
    cache_file = '/home/sftpuser/www/airtable_map.html'
    cache_time = 86400
    current_time = time.time()

    KST = timezone(timedelta(hours=9))
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