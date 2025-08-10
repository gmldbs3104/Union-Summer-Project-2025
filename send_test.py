# local_test_client.py (수정된 버전)
import requests
import json
from datetime import datetime

# 로컬 Flask 서버 주소 (app.py가 실행될 곳)
SERVER_URL = "http://127.0.0.1:5000/upload"

# 1. 테스트용 더미 데이터 생성
# app.py는 리스트 형태로 데이터를 받으므로, 리스트 안에 데이터를 넣어야 합니다.
dummy_data = [  # ◀◀◀ ❗️가장 중요한 수정사항: 리스트로 감싸기
    {
        "sensor_mac": "AA:BB:CC:DD:EE:FF", # DB f_sensors 테이블에 미리 등록한 MAC 주소
        "rssi": -68.2,
        "ping": 30.5,
        "speed": 22.4,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ping_timeout": False
    }
]

print(f"📡 로컬 서버({SERVER_URL})로 테스트 데이터 전송...")
print("보내는 데이터:")
print(json.dumps(dummy_data, indent=2))

try:
    # 2. 서버의 /upload 경로로 POST 요청 보내기
    # 이 요청 하나로 f_sensor_readings 와 f_diagnosis_results 에 모두 데이터가 저장되어야 정상입니다.
    response = requests.post(SERVER_URL, json=dummy_data, timeout=10)

    # 3. 서버 응답 결과 출력
    print("\n✅ 서버 응답 코드:", response.status_code)
    try:
        print("✅ 서버 응답 내용:", response.json())
    except json.JSONDecodeError:
        print("⚠️ JSON 파싱 실패. 텍스트 응답:\n", response.text)

except requests.exceptions.RequestException as e:
    print(f"❌ 전송 실패: {e}")