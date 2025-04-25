import os
import requests
from flask import Flask, request, jsonify
import anthropic
from airtable import Airtable

app = Flask(__name__)

# API 키 설정
vworld_apikey = os.environ.get('VWORLD_APIKEY', 'YOUR_DEFAULT_KEY')
airtable_api_key = os.environ.get('AIRTABLE_API_KEY', 'YOUR_DEFAULT_API_KEY')
anthropic_api_key = os.environ.get('ANTHROPIC_API_KEY', 'YOUR_DEFAULT_ANTHROPIC_KEY')

# Airtable 설정
base_id = 'appGSg5QfDNKgFf73'
table_name = 'tblnR438TK52Gr0HB'
airtable = Airtable(base_id, table_name, airtable_api_key)

# Claude 클라이언트 설정
claude_client = anthropic.Anthropic(api_key=anthropic_api_key)

@app.route('/api/property-search', methods=['POST'])
def property_search():
    # 사용자 입력 받기
    data = request.json
    location = data.get('location', '')
    price_range = data.get('price_range', '')
    investment = data.get('investment', '')
    expected_yield = data.get('expected_yield', '')
    
    # Airtable에서 매물 데이터 가져오기
    properties = airtable.get_all()
    
    # Claude에 전송할 프롬프트 구성
    prompt = f"""
    다음은 부동산 매물 목록입니다:
    {properties}
    
    사용자의 검색 조건:
    - 지역: {location}
    - 희망매매가: {price_range}
    - 실투자금: {investment}
    - 희망투자수익률: {expected_yield}
    
    위 조건에 가장 적합한 매물 3개를 추천해주세요. 각 매물에 대해 왜 이 사용자에게 적합한지 짧게 설명해주세요.
    """
    
    # Claude API 호출
    response = claude_client.messages.create(
        model="claude-3-7-sonnet-20250219",
        max_tokens=1000,
        system="당신은 부동산 투자 전문가입니다. 사용자의 조건에 맞는 최적의 매물을 추천해주세요.",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    
    return jsonify({
        "recommendations": response.content[0].text
    })

if __name__ == '__main__':
    app.run(debug=True)