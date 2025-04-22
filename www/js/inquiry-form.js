// 상담 문의 폼 제출 처리 스크립트
document.addEventListener('DOMContentLoaded', function() {
    const consultForm = document.getElementById('consultForm');
    const formStatus = document.getElementById('formStatus');
    
    // 개인정보 동의 모달 요소 생성 및 추가
    const modalHTML = `
    <div id="privacyModal" class="modal" style="display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.4); overflow: auto;">
        <div class="modal-content" style="background-color: white; margin: 15% auto; padding: 20px; border: 1px solid #888; width: 80%; max-width: 500px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">
            <h3 style="margin-top: 0;">개인정보 수집 및 이용 동의</h3>
            <div style="margin-bottom: 20px; height: 150px; overflow-y: auto; padding: 10px; border: 1px solid #ddd; background-color: #f9f9f9;">
                <p>1. 수집항목: 연락처, 이메일, 문의내용</p>
                <p>2. 수집목적: 부동산 상담 및 답변 제공</p>
                <p>3. 보유기간: 상담 완료 후 6개월</p>
                <p>귀하는 개인정보 수집 및 이용에 대한 동의를 거부할 권리가 있으나, 동의 거부 시 상담 서비스 이용이 제한됩니다.</p>
            </div>
            <div style="display: flex; align-items: center; margin-bottom: 20px;">
                <input type="checkbox" id="privacyCheck" style="margin-right: 8px;">
                <label for="privacyCheck">개인정보 수집 및 이용에 동의합니다.</label>
            </div>
            <div style="text-align: center;">
                <button id="agreeBtn" disabled style="padding: 8px 16px; background-color: #ccc; color: white; border: none; border-radius: 4px; cursor: not-allowed; margin-right: 10px;">동의하기</button>
                <button id="cancelBtn" style="padding: 8px 16px; background-color: #f44336; color: white; border: none; border-radius: 4px; cursor: pointer;">취소</button>
            </div>
        </div>
    </div>
    
    <div id="completionModal" class="modal" style="display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.4); overflow: auto;">
        <div class="modal-content" style="background-color: white; margin: 15% auto; padding: 20px; border: 1px solid #888; width: 80%; max-width: 500px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); text-align: center;">
            <h3 style="margin-top: 0; color: green;">상담접수가 완료되었습니다</h3>
            <p>빠른시일 내에 회신드리겠습니다.</p>
            <button id="closeBtn" style="padding: 8px 16px; background-color: #4CAF50; color: white; border: none; border-radius: 4px; cursor: pointer; margin-top: 15px;">닫기</button>
        </div>
    </div>`;
    
    // 모달 HTML을 body에 추가
    document.body.insertAdjacentHTML('beforeend', modalHTML);
    
    // 모달 및 관련 요소
    const privacyModal = document.getElementById('privacyModal');
    const completionModal = document.getElementById('completionModal');
    const privacyCheck = document.getElementById('privacyCheck');
    const agreeBtn = document.getElementById('agreeBtn');
    const cancelBtn = document.getElementById('cancelBtn');
    const closeBtn = document.getElementById('closeBtn');
    
    // 체크박스 상태에 따라 동의하기 버튼 활성화/비활성화
    privacyCheck.addEventListener('change', function() {
        if (this.checked) {
            agreeBtn.disabled = false;
            agreeBtn.style.backgroundColor = '#4CAF50';
            agreeBtn.style.cursor = 'pointer';
        } else {
            agreeBtn.disabled = true;
            agreeBtn.style.backgroundColor = '#ccc';
            agreeBtn.style.cursor = 'not-allowed';
        }
    });
    
    // 취소 버튼 클릭 시 모달 닫기 및 상태 메시지 초기화
    cancelBtn.addEventListener('click', function() {
        privacyModal.style.display = 'none';
        // 상태 메시지 숨기기
        formStatus.style.display = 'none';
    });
    
    // 완료 모달의 닫기 버튼 클릭 시 모달 닫기 및 성공 메시지 표시
    closeBtn.addEventListener('click', function() {
        completionModal.style.display = 'none';
        // 성공 메시지 표시
        formStatus.style.display = 'block';
        formStatus.textContent = '상담신청이 정상적으로 처리되었습니다.';
        formStatus.style.color = 'green';
    });
    
    if (consultForm) {
        // 폼 제출 시 개인정보 동의 모달 표시
        consultForm.addEventListener('submit', function(e) {
            e.preventDefault();
            // 상태 메시지 초기화
            formStatus.style.display = 'none';
            privacyModal.style.display = 'block';
        });
        
        // 동의하기 버튼 클릭 시 실제 폼 제출 처리
        agreeBtn.addEventListener('click', async function() {
            privacyModal.style.display = 'none'; // 동의 모달 닫기
            
            // 로딩 표시
            const submitButton = consultForm.querySelector('button[type="submit"]');
            const originalButtonText = submitButton.textContent;
            submitButton.disabled = true;
            submitButton.textContent = '접수 중...';
            
            // 상태 메시지 표시
            formStatus.style.display = 'block';
            formStatus.textContent = '상담 문의를 접수 중입니다...';
            formStatus.style.color = '#666';
            
            // 폼 데이터 수집
            const propertyType = document.getElementById('propertyType').value;
            const phone = document.getElementById('phone').value;
            const email = document.getElementById('email').value || '';
            const message = document.getElementById('message').value;
            
            // 서버에 보낼 데이터
            const data = {
                propertyType: propertyType,
                phone: phone,
                email: email,
                message: message
            };
            
            try {
                // 서버리스 함수 호출
                const response = await fetch('/api/submit-inquiry', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(data)
                });
                
                // 응답 로깅 (디버깅용)
                console.log('서버 응답 상태:', response.status);
                const responseData = await response.json();
                console.log('서버 응답 데이터:', responseData);
                
                if (!response.ok) {
                    throw new Error(`서버 요청 실패: ${response.status}`);
                }
                
                // 폼 초기화
                consultForm.reset();
                
                // 상태 메시지 숨기기 (팝업으로 대체)
                formStatus.style.display = 'none';
                
                // 완료 모달 표시
                completionModal.style.display = 'block';
                
            } catch (error) {
                console.error('상담 접수 실패:', error);
                // 오류 메시지
                formStatus.textContent = '상담 접수 중 오류가 발생했습니다. 전화로 문의해 주세요.';
                formStatus.style.color = 'red';
            } finally {
                // 버튼 상태 복원
                submitButton.disabled = false;
                submitButton.textContent = originalButtonText;
            }
        });
    }
});
