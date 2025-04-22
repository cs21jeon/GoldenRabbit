
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
        