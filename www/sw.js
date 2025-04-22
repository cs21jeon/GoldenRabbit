// 캐시 이름 정의
const CACHE_NAME = 'goldenrabbit-v4';

// 캐시할 파일 목록
const urlsToCache = [
  '/',
  '/index.html',
  '/js/inquiry-form.js',
  '/js/property-api.js',
  '/images/favicon_goldenrabbit.png',
  '/manifest.json',
  '/images/icon-192x192.png',
  '/images/icon-512x512.png'
];

// 서비스 워커 설치 시 캐시 저장
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('캐시 생성 완료');
        return cache.addAll(urlsToCache);
      })
  );
  self.skipWaiting(); //대기 단계 건너뛰기
});

// 네트워크 요청 가로채기
self.addEventListener('fetch', event => {
  // HTML 또는 JS 파일인 경우 네트워크 우선 전략 사용
  if (event.request.url.includes('.html') || event.request.url.includes('.js')) {
    event.respondWith(
      fetch(event.request)
        .then(response => {
          // 네트워크 요청 성공 시 캐시 업데이트
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then(cache => {
            cache.put(event.request, responseClone);
          });
          return response;
        })
        .catch(() => {
          // 네트워크 요청 실패 시 캐시에서 반환
          return caches.match(event.request);
        })
    );
  } else {
    // 기타 리소스는 캐시 우선 전략 사용
    event.respondWith(
      caches.match(event.request)
        .then(response => {
          // 캐시에서 찾으면 캐시된 응답 반환
          if (response) {
            return response;
          }
          
          // 캐시에 없으면 네트워크에서 가져오기
          return fetch(event.request)
            .then(response => {
              // 유효한 응답이 아니면 그냥 반환
              if (!response || response.status !== 200 || response.type !== 'basic') {
                return response;
              }
              
              // 응답 복제 (스트림은 한 번만 사용 가능하므로)
              const responseToCache = response.clone();
              
              // 응답을 캐시에 저장
              caches.open(CACHE_NAME)
                .then(cache => {
                  cache.put(event.request, responseToCache);
                });
                
              return response;
            });
        })
    );
  }
});

// 새 버전의 서비스 워커가 활성화될 때 이전 캐시 삭제
self.addEventListener('activate', event => {
  const cacheWhitelist = [CACHE_NAME];
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheWhitelist.indexOf(cacheName) === -1) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  event.waitUntil(clients.claim()); // 모든 클라이언트에 즉시 제어권 획득
});
