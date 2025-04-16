from flask import Flask, request
import hmac
import hashlib
import subprocess

app = Flask(__name__)

# GitHub Webhook 설정 시 입력한 Secret 값과 반드시 일치해야 함
GITHUB_SECRET = b'goldenrabbit_secret_9402'  # 👈 이 부분은 필요시 수정하세요

@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Hub-Signature-256")
    if signature is None:
        return "Signature missing", 400

    payload = request.get_data()
    mac = hmac.new(GITHUB_SECRET, msg=payload, digestmod=hashlib.sha256)
    expected_signature = "sha256=" + mac.hexdigest()

    if not hmac.compare_digest(expected_signature, signature):
        return "Invalid signature", 403

    # 인증 성공 시 배포 실행
    try:
        subprocess.run(["git", "-C", "/root/goldenrabbit", "pull"], check=True)
        subprocess.run(["systemctl", "restart", "vworld"], check=True)
        return "Deployed successfully", 200
    except subprocess.CalledProcessError as e:
        return f"Deployment failed: {e}", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9000)
