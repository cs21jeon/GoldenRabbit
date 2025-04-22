document.addEventListener('DOMContentLoaded', function() {
  // PWA 설치 관련 변수
  let deferredPrompt;
  
  // 설치 안내 배너 생성
  const installBanner = document.createElement('div');
  installBanner.style.display = 'none';
  // 배너 스타일 코드...
  
  // 브라우저 및 OS 확인
  const ua = navigator.userAgent;
  const isAndroid = /Android/i.test(ua);
  const isChrome = /Chrome/i.test(ua) && /Google Inc/.test(navigator.vendor);
  
  // 앱이 이미 설치되어 있는지 확인
  const isStandalone = window.matchMedia('(display-mode: standalone)').matches || 
                       window.navigator.standalone || document.referrer.includes('android-app://');
  
  // 이미 설치된 경우 배너를 표시하지 않음
  if (isStandalone) {
    console.log('앱이 이미 설치되어 있습니다');
    return;
  }
  
  // 배너 내용 설정
  // 배너 HTML 코드...
  
  // 배너를 문서에 추가
  document.body.appendChild(installBanner);
  
  // 닫기 버튼 이벤트
  const closeButton = document.getElementById('closeBanner');
  if (closeButton) {
    closeButton.addEventListener('click', function () {
      installBanner.style.display = 'none';
      localStorage.setItem('pwaInstallBannerClosed', Date.now());
    });
  }
  // 설치 버튼 이벤트 (크롬인 경우에만)
  if (isChrome) {
    const installBtn = document.getElementById('pwaInstallButton');
    if (installBtn) {
      installBtn.addEventListener('click', async () => {
        // 설치 버튼 클릭 시 처리...
      });
    }
  }
    
  // PWA 설치 가능할 때 이벤트 발생
  window.addEventListener('beforeinstallprompt', (e) => {
    // 이미 설치된 경우 무시
    if (isStandalone) return;
    
    // 브라우저 기본 설치 프롬프트 방지
    e.preventDefault();
    // 이벤트 저장
    deferredPrompt = e;
    // 설치 배너 표시
    installBanner.style.display = 'block';
  });
  
  // 앱이 설치되었을 때 이벤트
  window.addEventListener('appinstalled', () => {
    console.log('앱이 설치되었습니다');
    installBanner.style.display = 'none';
    // 설치 완료를 로컬 스토리지에 저장
    localStorage.setItem('pwaInstalled', 'true');
  });
  
  // 페이지가 PWA 모드로 로드되었는지 확인하는 추가 방법
  window.matchMedia('(display-mode: standalone)').addEventListener('change', (e) => {
    if (e.matches) {
      // standalone 모드로 변경됨 = 앱으로 실행 중
      console.log('앱으로 실행 중입니다');
      installBanner.style.display = 'none';
    }
  });
  
  // 이미 배너를 닫은 적이 있는지 확인
  const lastClosed = localStorage.getItem('pwaInstallBannerClosed');
  if (lastClosed) {
    const daysSinceClosed = (Date.now() - parseInt(lastClosed)) / (1000 * 60 * 60 * 24);
    if (daysSinceClosed < 30) {
      installBanner.style.display = 'none';
    } else {
      localStorage.removeItem('pwaInstallBannerClosed');
    }
  }
  
  // 크롬이 아닌 안드로이드 기기에서는 설치 배너를 바로 표시
  if (isAndroid && !isChrome && !isStandalone) {
    // 이미 배너를 닫은 적이 없으면 표시
    if (!lastClosed) {
      installBanner.style.display = 'block';
    }
  }
});
