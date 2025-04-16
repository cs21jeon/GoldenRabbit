import folium
import requests
import os
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# 환경 변수에서 API 키 가져오기
vworld_apikey = os.environ.get('VWORLD_APIKEY', 'YOUR_DEFAULT_KEY')
airtable_api_key = os.environ.get('AIRTABLE_API_KEY', 'YOUR_DEFAULT_API_KEY')

base_id = 'appGSg5QfDNKgFf73'
table_id = 'tblnR438TK52Gr0HB'
address_field = '지번 주소'  # 주소가 저장된 필드명 - 실제 필드명으로 변경 필요
price_field = '매가(만원)'  # 매가 정보가 저장된 필드명
status_field = '현황'  # 현황 정보가 저장된 필드명

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
    """에어테이블에서 데이터를 가져오는 함수"""
    url = f'https://api.airtable.com/v0/{base_id}/{table_id}'
    
    # 문서에 나온 대로 Bearer 토큰 방식으로 인증 헤더 설정
    headers = {
        'Authorization': f'Bearer {airtable_api_key}',
        'Content-Type': 'application/json'
    }
    
    # 디버깅을 위한 정보 출력
    print(f"에어테이블 API 요청 URL: {url}")
    print(f"베이스 ID: {base_id}")
    print(f"테이블 ID: {table_id}")
    print(f"검색할 필드명: address_field='{address_field}', price_field='{price_field}', status_field='{status_field}'")

    all_records = []
    offset = None

    try:
        # 페이지네이션을 사용하여 모든 레코드 가져오기
        while True:
            # offset이 있으면 다음 페이지 요청
            params = {}
            if offset:
                params['offset'] = offset
            
            # API 요청 수행
            response = requests.get(url, headers=headers, params=params)
            
            # 응답 상세 정보 출력 (디버깅용)
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
        
# 여기서부터는 기존 코드와 동일
        address_data = []
        for record in all_records:
            fields = record.get('fields', {})
            
            # 입력한 필드명으로 데이터 찾기
            address = fields.get(address_field)
            name = address  # 주소를 이름으로도 사용
            price = fields.get(price_field)
            status = fields.get(status_field)
            
            # 추가 필드 값 가져오기
            field_values = {}
            for display_name, field_name in additional_fields.items():
                field_values[display_name] = fields.get(field_name)
            
            # 디버깅: 일부 레코드의 실제 값 출력
            if len(address_data) < 3:  # 처음 3개 레코드만 출력
                print(f"address 필드값: {address}")
                print(f"price 필드값: {price}")
                print(f"status 필드값: {status}")
                
                # 첫 번째 레코드의 추가 필드 값 출력
                for display_name, value in field_values.items():
                    print(f"{display_name} 필드값: {value}")
            
            # 필터링: 주소가 있고, 현황이 "네이버", "디스코", "당근", "비공개" 중 하나라도 포함된 경우에만 처리
            valid_status = ["네이버", "디스코", "당근", "비공개"]
            
            # 현황 필드가 None이 아니고, 리스트 형태이며, 유효한 상태 중 하나라도 포함하고 있는지 확인
            is_valid_status = False
            if address is not None and status is not None:
                if isinstance(status, list):
                    # 리스트에서 유효한 상태 중 하나라도 포함되어 있는지 확인
                    is_valid_status = any(s in valid_status for s in status)
                elif isinstance(status, str):
                    # 문자열인 경우 직접 확인
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
        
        # 여기서 for 루프가 끝나고 데이터를 반환해야 함
        print(f"필터링 후 사용할 레코드 수: {len(address_data)}")
        return address_data
    
    except Exception as e:
        print(f"API 요청 중 예외 발생: {str(e)}")
        return []

def create_map():
    """지도를 생성하고 저장하는 함수"""
    # 지도 생성 - 동작구 중심으로 설정
    folium_map = folium.Map(
        location=[37.483, 126.974],  # 동작구 중심 좌표
        zoom_start=14,  # 동작구 정도의 면적이 보이는 확대 레벨
    )
    
    # 기본 타일 레이어 추가 - API 키 노출 방지를 위해 프록시 URL 사용
    folium.TileLayer(
        tiles='http://goldenrabbit21.cafe24.com:8000/api/vtile?z={z}&y={y}&x={x}',
        attr='공간정보 오픈플랫폼(브이월드)',
        name='브이월드 배경지도',
    ).add_to(folium_map)
    
    # WMS 타일 레이어 추가 - API 키 노출 방지를 위해 프록시 URL 사용
    folium.WmsTileLayer(
        url='http://goldenrabbit21.cafe24.com:8000/api/wms?',
        layers='lt_c_landinfobasemap',
        request='GetMap',
        version='1.3.0',
        height=256,
        width=256,
        # key 파라미터 제거 (프록시에서 처리)
        fmt='image/png',
        transparent=True,
        name='LX맵(편집지적도)',
    ).add_to(folium_map)
    
    # 레이어 컨트롤 추가
    folium.LayerControl().add_to(folium_map)
    
    # 에어테이블에서 주소 데이터 가져오기
    address_data = get_airtable_data()
    
    if not address_data:
        print("에어테이블에서 가져온 주소 데이터가 없습니다.")
        return folium_map
    
    # address_data를 JSON 형식으로 변환하여 HTML에 삽입
    import json
    address_data_json = json.dumps(address_data)

    # 외부 JavaScript 파일 생성 (map is not defined 문제 해결)
    external_js_path = '/home/sftpuser/www/map_script.js'
    with open(external_js_path, 'w', encoding='utf-8') as f:
        f.write(f"""
// 주소 데이터 (Python에서 전달)
const addressData = {address_data_json};

// 맵 객체 참조 변수
let mapObj = null;

// 페이지 로드 완료 시 실행
document.addEventListener('DOMContentLoaded', function() {{
    console.log('DOM 로드 완료');
    
    // 맵 요소 찾기
    const mapElements = document.querySelectorAll('div[id^="map_"]');
    if (mapElements.length > 0) {{
        const mapId = mapElements[0].id;
        console.log('맵 요소 ID:', mapId);
        
        // 맵 객체 찾기 시도 함수
        function findMapObject() {{
            // window[mapId]로 맵 객체 찾기 시도
            if (window[mapId]) {{
                console.log('맵 객체 찾음:', mapId);
                return window[mapId];
            }}
            
            // window 객체에서 map_으로 시작하는 모든 속성 검색
            const mapKeys = Object.keys(window).filter(key => key.startsWith('map_'));
            console.log('가능한 맵 객체 키:', mapKeys);
            
            // 첫 번째 발견된 맵 객체 반환
            for (const key of mapKeys) {{
                if (window[key] && typeof window[key].setView === 'function') {{
                    console.log('맵 객체를 다른 키로 찾음:', key);
                    return window[key];
                }}
            }}
            
            return null;
        }}
        
        // 맵 객체 찾기 및 주소 처리
        function initializeMap() {{
            mapObj = findMapObject();
            
            if (mapObj) {{
                console.log('맵 초기화 성공, 주소 처리 시작');
                processAddresses();
            }} else {{
                console.error('맵 객체를 찾을 수 없음');
            }}
        }}
        
        // 1초 후에 초기화 시도 (맵이 로드될 시간 제공)
        setTimeout(initializeMap, 1000);
    }} else {{
        console.error('맵 요소를 찾을 수 없음');
    }}
}});

// 주소 처리 함수
async function processAddresses() {{
    console.log('주소 처리 시작, 데이터 수:', addressData.length);
    
    // 모든 주소 처리
    for (const addr of addressData) {{
        try {{
            // API 호출 URL
            const apiUrl = `http://goldenrabbit21.cafe24.com:8000/api/vworld?address=${{encodeURIComponent(addr[1])}}`;
            console.log(`좌표 요청: ${{addr[1]}}`);
            
            const response = await fetch(apiUrl);
            const data = await response.json();
            
            if (data.response && data.response.status === 'OK') {{
                const point = data.response.result.point;
                
                if (point && point.x && point.y) {{
                    // 마커 추가 로직
                    addMarker(point, addr);
                    console.log(`마커 추가 완료: ${{addr[1]}}`);
                }}
            }} else {{
                console.warn(`좌표 변환 실패: ${{addr[1]}}`);
            }}
        }} catch (error) {{
            console.error(`주소 처리 오류: ${{addr[1]}}`, error);
        }}
    }}
}}

// 마커 추가 함수
function addMarker(point, addr) {{
    // 가격 포맷팅
    let priceDisplay = formatPrice(addr[2]);
    
    // 주소 추출
    let dongBunji = addr[1];
    if (addr[1].includes(' ')) {{
        dongBunji = addr[1].substring(addr[1].indexOf(' ') + 1);
    }}
    
    // 팝업 내용 생성
    let popupContent = '<div style="font-size: 14px;">';
    popupContent += `<b>지번: ${{dongBunji}}</b>`;
    popupContent += `<br><b>매가: ${{priceDisplay}}</b>`;
    
    // 추가 필드 처리
    const fieldValues = addr[4];
    
    // 대지 정보 추가
    if (fieldValues['토지면적(㎡)']) {{
        try {{
            const landAreaSqm = parseFloat(fieldValues['토지면적(㎡)']);
            const landAreaPyeong = Math.round(landAreaSqm / 3.3058);
            popupContent += `<br><b>대지:</b> ${{landAreaPyeong}}평 (${{landAreaSqm}}㎡)`;
        }} catch (e) {{}}
    }}
    
    // 연식 정보 추가
    if (fieldValues['사용승인일']) {{
        try {{
            const approvalDate = String(fieldValues['사용승인일']);
            if (approvalDate.includes('-') || approvalDate.includes('/')) {{
                const year = approvalDate.includes('-') ? 
                    approvalDate.split('-')[0] : approvalDate.split('/')[0];
                popupContent += `<br>연식: ${{year}}년`;
            }} else if (approvalDate.length >= 4) {{
                popupContent += `<br>연식: ${{approvalDate.substring(0, 4)}}년`;
            }}
        }} catch (e) {{}}
    }}
    
    // 주용도 정보 추가
    if (fieldValues['주용도']) {{
        popupContent += `<br>용도: ${{fieldValues['주용도']}}`;
    }}
    
    // 층수 정보 추가
    if (fieldValues['층수']) {{
        popupContent += `<br>층수: ${{fieldValues['층수']}}`;
    }}
    
    popupContent += '</div>';
    
    // 툴팁 내용
    const tooltipContent = `${{dongBunji}} | ${{priceDisplay}}`;
    
    // 맵 객체가 유효한지 확인
    if (!mapObj) {{
        console.error('마커 추가 실패: 맵 객체가 없음');
        return;
    }}
    
    // 마커 생성 및 지도에 추가
    try {{
        L.marker([point.y, point.x], {{
            icon: L.AwesomeMarkers.icon({{
                markerColor: 'red',
                iconColor: 'white',
                icon: 'bookmark',
                prefix: 'glyphicon'
            }})
        }})
        .bindPopup(L.popup({{ maxWidth: 250 }}).setContent(popupContent))
        .bindTooltip(tooltipContent, {{ sticky: true }})
        .addTo(mapObj);
    }} catch (e) {{
        console.error('마커 생성 오류:', e);
    }}
}}

// 가격 포맷팅 함수
function formatPrice(price) {{
    if (typeof price === 'number' && price >= 10000) {{
        // 10000만원(1억) 이상인 경우
        const priceInBillions = price / 10000;
        if (priceInBillions % 1 === 0) {{
            return `${{Math.floor(priceInBillions)}}억원`;
        }} else {{
            return `${{priceInBillions.toFixed(1).replace('.0', '')}}억원`;
        }}
    }} else {{
        // 1억 미만인 경우
        if (typeof price === 'number') {{
            return `${{price.toLocaleString()}}만원`;
        }} else {{
            return `${{price || '정보없음'}}`;
        }}
    }}
}}
        """)
    print(f"JavaScript 파일 생성: {external_js_path}")
    
    # 외부 JavaScript 파일을 로드하는 태그 추가
    folium_map.get_root().html.add_child(folium.Element("""
    <script src="/map_script.js"></script>
    """))
    # 디버그 스크립트 생성
    debug_js_path = '/home/sftpuser/www/debug.js'
    with open(debug_js_path, 'w', encoding='utf-8') as f:
        f.write("""
    // 디버그 정보를 기록할 요소 생성
    function createDebugPanel() {
    const debugPanel = document.createElement('div');
    debugPanel.id = 'debug-panel';
    debugPanel.style.cssText = `
        position: fixed;
        top: 10px;
        right: 10px;
        width: 300px;
        max-height: 400px;
        overflow: auto;
        background: rgba(0, 0, 0, 0.8);
        color: #00ff00;
        font-family: monospace;
        font-size: 12px;
        padding: 10px;
        border-radius: 5px;
        z-index: 9999;
    `;
    document.body.appendChild(debugPanel);
    return debugPanel;
    }

    // 디버그 정보 기록 함수
    function logDebug(message, data = null) {
    let panel = document.getElementById('debug-panel');
    if (!panel) {
        panel = createDebugPanel();
    }
    
    const timestamp = new Date().toLocaleTimeString();
    const logItem = document.createElement('div');
    logItem.style.borderBottom = '1px solid #333';
    logItem.style.paddingBottom = '5px';
    logItem.style.marginBottom = '5px';
    
    let logText = `[${timestamp}] ${message}`;
    logItem.textContent = logText;
    
    if (data) {
        try {
        const dataStr = typeof data === 'object' ? JSON.stringify(data) : data.toString();
        const dataElement = document.createElement('pre');
        dataElement.style.marginTop = '5px';
        dataElement.style.overflow = 'auto';
        dataElement.style.maxHeight = '100px';
        dataElement.style.background = '#111';
        dataElement.style.padding = '4px';
        dataElement.style.fontSize = '10px';
        dataElement.textContent = dataStr;
        logItem.appendChild(dataElement);
        } catch (e) {
        const errorElement = document.createElement('div');
        errorElement.style.color = 'red';
        errorElement.textContent = `[데이터 출력 오류: ${e.message}]`;
        logItem.appendChild(errorElement);
        }
    }
    
    panel.appendChild(logItem);
    panel.scrollTop = panel.scrollHeight;
    
    // 콘솔에도 로그 출력
    console.log(`DEBUG: ${message}`, data || '');
    }

    // 전역 객체 검사 및 상세 정보 출력
    function inspectGlobalObjects() {
    logDebug('전역 객체 검사 시작');
    
    // 모든 전역 변수 목록
    const allGlobals = Object.keys(window);
    logDebug(`전역 변수 총 개수: ${allGlobals.length}`);
    
    // 맵 관련 전역 변수 찾기
    const mapVars = allGlobals.filter(key => key.startsWith('map_'));
    logDebug(`맵 관련 전역 변수(map_ 접두사): ${mapVars.length}개`, mapVars);
    
    // div 요소 중 map_ 접두사를 가진 요소 찾기
    const mapElements = Array.from(document.querySelectorAll('div[id^="map_"]'));
    logDebug(`맵 관련 DOM 요소: ${mapElements.length}개`, mapElements.map(el => el.id));
    
    // Leaflet 관련 객체 확인
    if (typeof L !== 'undefined') {
        logDebug('Leaflet 객체 사용 가능', { version: L.version });
        
        // Leaflet 맵 인스턴스 검색 시도
        const leafletMaps = [];
        mapVars.forEach(key => {
        try {
            const obj = window[key];
            if (obj && typeof obj.getContainer === 'function') {
            leafletMaps.push({
                key: key,
                isMap: true,
                container: obj.getContainer().id
            });
            }
        } catch (e) {
            logDebug(`${key} 검사 중 오류: ${e.message}`);
        }
        });
        
        logDebug(`Leaflet 맵 인스턴스: ${leafletMaps.length}개`, leafletMaps);
    } else {
        logDebug('Leaflet 객체를 찾을 수 없음 (L is undefined)');
    }
    
    // 스크립트 태그 검사
    const scripts = Array.from(document.querySelectorAll('script'));
    logDebug(`스크립트 태그: ${scripts.length}개`, scripts.map(s => s.src || '인라인 스크립트'));
    
    // 맵 객체가 될 수 있는 모든 후보 확인
    try {
        const potentialMapObjects = [];
        allGlobals.forEach(key => {
        const obj = window[key];
        if (obj && typeof obj === 'object') {
            try {
            const hasMapMethods = typeof obj.setView === 'function' || 
                                typeof obj.addLayer === 'function' || 
                                typeof obj.getContainer === 'function';
            
            if (hasMapMethods) {
                potentialMapObjects.push(key);
            }
            } catch (e) {}
        }
        });
        
        logDebug(`지도 객체 가능성이 있는 변수: ${potentialMapObjects.length}개`, potentialMapObjects);
    } catch (e) {
        logDebug(`맵 객체 후보 검색 오류: ${e.message}`);
    }
    }

    // 오류 모니터링
    function setupErrorMonitoring() {
    window.onerror = function(message, source, lineno, colno, error) {
        logDebug(`오류 발생: ${message}`, {
        source: source,
        line: lineno,
        column: colno,
        error: error ? error.stack : 'No stack trace'
        });
        return false; // 오류를 콘솔에도 표시
    };
    
    // 모든 unhandled promise rejection 캡처
    window.addEventListener('unhandledrejection', function(event) {
        logDebug('Unhandled Promise Rejection', {
        reason: event.reason,
        stack: event.reason.stack
        });
    });
    
    logDebug('오류 모니터링 설정 완료');
    }

    // 페이지 로드 시 디버깅 시작
    document.addEventListener('DOMContentLoaded', function() {
    logDebug('DOM 로드 완료, 디버깅 시작');
    setupErrorMonitoring();
    
    // 첫 번째 검사
    inspectGlobalObjects();
    
    // 3초 후 다시 검사 (지연 로딩된 객체 확인)
    setTimeout(function() {
        logDebug('3초 후 재검사');
        inspectGlobalObjects();
    }, 3000);
    });

    logDebug('디버그 스크립트 로드 완료');
        """)

    print(f"디버그 스크립트 생성: {debug_js_path}")

    # 디버그 스크립트를 먼저 로드
    folium_map.get_root().header.add_child(folium.Element(f"""
    <script src="/debug.js"></script>
    """))

    # map_script.js 파일의 첫 부분에 디버깅 코드 추가
    with open('/home/sftpuser/www/map_script.js', 'r', encoding='utf-8') as f:
        existing_code = f.read()

    with open('/home/sftpuser/www/map_script.js', 'w', encoding='utf-8') as f:
        f.write("""
    // 디버깅 함수들 - debug.js가 로드되지 않았을 경우를 대비
    if (typeof logDebug !== 'function') {
    window.logDebug = function(msg, data) {
        console.log('DEBUG:', msg, data || '');
    };
    }

    // 맵 스크립트 초기화 시작 기록
    logDebug('맵 스크립트 초기화 시작');

    // 스코프에서 map 변수가 존재하는지 확인
    try {
    logDebug('현재 스코프의 map 변수:', map);
    } catch (e) {
    logDebug('현재 스코프에 map 변수 없음:', e.message);
    }

    // window 객체에 map 변수가 존재하는지 확인
    logDebug('window.map 존재 여부:', window.map !== undefined);

    // map으로 시작하는 모든 전역 변수 확인
    const mapVarsAtStart = Object.keys(window).filter(k => k.startsWith('map'));
    logDebug('맵 관련 전역 변수 (스크립트 시작):', mapVarsAtStart);

    """ + existing_code)

    # 외부 JavaScript 파일을 로드하는 태그 추가
    folium_map.get_root().html.add_child(folium.Element("""
    <script src="/map_script.js"></script>
    """))

    # 페이지 로드 시 실행될 디버그 코드 추가
    folium_map.get_root().html.add_child(folium.Element("""
    <script>
    // 페이지 로드 후 map 변수 확인
    document.addEventListener('DOMContentLoaded', function() {
    setTimeout(function() {
        try {
        console.log('map 변수 확인:', map); // 일부러 오류를 발생시켜 stack trace 확인
        } catch (e) {
        console.error('map 변수 접근 오류:', e);
        
        // 오류 위치 확인
        const stackLines = e.stack.split('\\n');
        console.log('오류 스택:', stackLines);
        
        // 오류 발생 소스 파일 확인
        if (stackLines.length > 1) {
            const sourceMatch = stackLines[1].match(/at (.+)$/);
            if (sourceMatch) {
            console.log('오류 발생 위치:', sourceMatch[1]);
            }
        }
        
        // 디버그 패널에 표시 (debug.js 로드된 경우)
        if (typeof logDebug === 'function') {
            logDebug('map 변수 접근 시 오류 발생', {
            message: e.message,
            stack: e.stack
            });
            
            // 모든 스크립트 태그 검사
            const scripts = Array.from(document.querySelectorAll('script'));
            logDebug('모든 스크립트 태그:', scripts.map(s => s.src || '인라인 스크립트'));
        }
        }
    }, 2000); // 페이지 로드 후 2초 후 실행
    });
    </script>
    """))
    
    return folium_map

if __name__ == "__main__":
    # 지도 생성 및 저장
    folium_map = create_map()
    folium_map.save('/home/sftpuser/www/airtable_map.html')
    print("지도가 airtable_map.html 파일로 저장되었습니다.")