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
    map = folium.Map(
        location=[37.5, 126.95],  # 동작구 중심 좌표
        zoom_start=14,  # 동작구 정도의 면적이 보이는 확대 레벨
    )
    
    # 기본 타일 레이어 추가
    folium.TileLayer(
        tiles=f'https://api.vworld.kr/req/wmts/1.0.0/{vworld_apikey}/Base/{{z}}/{{y}}/{{x}}.png',
        attr='공간정보 오픈플랫폼(브이월드)',
        name='브이월드 배경지도',
    ).add_to(map)
    
    # WMS 타일 레이어 추가
    folium.WmsTileLayer(
        url='https://api.vworld.kr/req/wms?',
        layers='lt_c_landinfobasemap',
        request='GetMap',
        version='1.3.0',
        height=256,
        width=256,
        key=vworld_apikey,
        fmt='image/png',
        transparent=True,
        name='LX맵(편집지적도)',
    ).add_to(map)
    
    # 레이어 컨트롤 추가
    folium.LayerControl().add_to(map)
    
    # 에어테이블에서 주소 데이터 가져오기
    address_data = get_airtable_data()
    
    if not address_data:
        print("에어테이블에서 가져온 주소 데이터가 없습니다.")
        return map
    
    # V-World API로 주소 좌표 변환 및 마커 추가 부분을 변경
    # Python에서 직접 API 호출하는 대신 클라이언트에서 처리하도록 JavaScript 코드 삽입

    # address_data를 JSON 형식으로 변환하여 HTML에 삽입
    import json
    address_data_json = json.dumps(address_data)

    # JavaScript 코드를 생성하여 HTML에 삽입
    js_code = f"""
    <script>
    // 주소 데이터를 JavaScript 변수로 저장
    const addressData = {address_data_json};

    // 페이지 로드 완료 시 실행
    document.addEventListener('DOMContentLoaded', async function() {{
        // 모든 주소에 대해 좌표 변환 및 마커 추가
        for (const addr of addressData) {{
            try {{
                // 서버리스 함수를 통해 주소 좌표 변환
                const response = await fetch(`/api/vworld?address=${{encodeURIComponent(addr[1])}}`);
                const data = await response.json();
                
                // 좌표 정보가 있는지 확인
                if (data.response && data.response.status === 'OK') {{
                    const result = data.response.result;
                    const point = result.point;
                    
                    if (point && point.x && point.y) {{
                        // 금액을 억 단위로 변환
                        let priceDisplay = addr[2];
                        if (typeof addr[2] === 'number' && addr[2] >= 10000) {{
                            // 10000만원(1억) 이상인 경우
                            const priceInBillions = addr[2] / 10000;
                            if (priceInBillions % 1 === 0) {{
                                // 정수인 경우 (예: 3억)
                                priceDisplay = `${{Math.floor(priceInBillions)}}억원`;
                            }} else {{
                                // 소수점이 있는 경우 (예: 3.5억)
                                priceDisplay = `${{priceInBillions.toFixed(1).replace('.0', '')}}억원`;
                            }}
                        }} else {{
                            // 1억 미만인 경우 (만원 단위 유지)
                            if (typeof addr[2] === 'number') {{
                                priceDisplay = `${{addr[2].toLocaleString()}}만원`;
                            }} else {{
                                priceDisplay = `${{addr[2]}}만원`;
                            }}
                        }}
                        
                        // 현황 정보 처리
                        let statusInfo = "";
                        if (addr[3]) {{
                            if (Array.isArray(addr[3])) {{
                                statusInfo = `현황: ${{addr[3].join(', ')}}`;
                            }} else {{
                                statusInfo = `현황: ${{addr[3]}}`;
                            }}
                        }}
                        
                        // 주소에서 첫 번째 공백 이후의 부분만 추출
                        let dongBunji = addr[1];
                        if (addr[1].includes(' ')) {{
                            dongBunji = addr[1].substring(addr[1].indexOf(' ') + 1);
                        }}
                        
                        // 팝업 내용 생성
                        let popupContent = '<div style="font-size: 14px;">';
                        popupContent += `<b>지번: ${{dongBunji}}</b>`;
                        popupContent += `<br><b>매가: ${{priceDisplay}}</b>`;
                        
                        // 추가 필드 값 처리
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
                        
                        // 마커 생성 및 지도에 추가
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
                        .addTo(map);
                        
                        console.log(`마커 추가: ${{dongBunji}}, 좌표: ${{point.y}}, ${{point.x}}`);
                    }}
                }}
            }} catch (error) {{
                console.error(`주소 검색 실패: ${{addr[1]}}`, error);
            }}
        }}
    }});
    </script>
    """

    # Python으로 생성한 마커 추가 코드 대신 JavaScript 코드를 HTML에 삽입
    map.get_root().html.add_child(folium.Element(js_code))
    
    return map

if __name__ == "__main__":
    # 지도 생성 및 저장
    map = create_map()
    map.save('airtable_map.html')
    print("지도가 airtable_map.html 파일로 저장되었습니다.")
