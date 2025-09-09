#!/bin/bash
# setup_token_auto_refresh.sh
# Threads 토큰 자동 갱신 시스템 설정 스크립트

set -e

echo "=== Threads 토큰 자동 갱신 시스템 설정 ==="

# 필요한 디렉토리 생성
echo "디렉토리 생성 중..."
mkdir -p /root/goldenrabbit/logs
mkdir -p /root/goldenrabbit/backups

# token_manager.py 파일 권한 설정
chmod +x /root/goldenrabbit/token_manager.py

# 로그 파일 초기화
touch /root/goldenrabbit/logs/token_manager.log
touch /root/goldenrabbit/logs/token_notifications.log

echo "기본 설정 완료!"

# Cron 작업 설정
echo "Cron 작업 설정 중..."

# 현재 crontab 백업
crontab -l > /tmp/crontab_backup_$(date +%Y%m%d_%H%M%S) 2>/dev/null || echo "기존 crontab 없음"

# 새로운 cron 작업 추가
(crontab -l 2>/dev/null; echo "# Threads 토큰 자동 갱신 (매월 1일 오전 3시)") | crontab -
(crontab -l 2>/dev/null; echo "0 3 1 * * /usr/bin/python3 /root/goldenrabbit/token_manager.py >> /root/goldenrabbit/logs/token_cron.log 2>&1") | crontab -

echo "Cron 작업 추가 완료!"

# 설정된 cron 작업 확인
echo ""
echo "=== 설정된 Cron 작업 ==="
crontab -l | grep -A1 -B1 "token_manager"

echo ""
echo "=== 설정 완료 ==="
echo "1. 자동 갱신: 매월 1일 오전 3시에 자동 실행"
echo "2. 수동 실행: python3 /root/goldenrabbit/token_manager.py"
echo "3. 로그 확인: tail -f /root/goldenrabbit/logs/token_manager.log"
echo "4. 알림 확인: tail -f /root/goldenrabbit/logs/token_notifications.log"

# 테스트 실행 여부 묻기
echo ""
read -p "지금 토큰 갱신을 테스트하시겠습니까? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "토큰 갱신 테스트 실행 중..."
    python3 /root/goldenrabbit/token_manager.py
else
    echo "설정이 완료되었습니다. 수동으로 테스트하려면 다음 명령을 실행하세요:"
    echo "python3 /root/goldenrabbit/token_manager.py"
fi
