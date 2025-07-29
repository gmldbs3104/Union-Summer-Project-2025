# 센서 개발 완료되면 없어도 되는 파일 

import requests
import datetime
import time 

# /upload 엔드포인트 테스트 데이터
upload_data = {
    "sensor_mac": "AA:BB:CC:DD:EE:FF", # DB에 등록된 MAC 주소를 사용
    "rssi": -68.2,
    "ping": 30.5,
    "speed": 22.4,
    "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "ping_timeout": False
}

# /upload 테스트
upload_response = requests.post("http://127.0.0.1:5000/upload", json=upload_data)
print("--- /upload 테스트 결과 ---")
print("Status Code:", upload_response.status_code)
print("Response Text:", upload_response.text)

# upload가 성공하고 reading_id를 얻어야 predict를 테스트할 수 있음
# 실제로는 DB에서 가장 최근에 추가된 reading_id를 조회하는 로직이 필요할 수 있습니다.
# 여기서는 간단하게 가정하고 수동으로 reading_id를 입력하거나,
# /upload가 성공적으로 데이터를 저장했음을 확인한 후 /readings에서 최근 reading_id를 가져오는 방식으로 진행합니다.

if upload_response.status_code == 200:
    print("\n--- /predict 테스트 준비 ---")
    # 실제 시스템에서는 /readings 엔드포인트를 호출하여 가장 최근 reading_id를 가져오거나
    # /upload 응답에 reading_id를 포함하도록 수정하는 것이 효율적입니다.
    # 여기서는 임시로 DB에서 직접 확인한 후 입력하는 것을 가정합니다.
    # 또는 테스트를 위해 임의의 reading_id를 사용합니다.

    # 예시: 가장 최근에 저장된 reading_id를 가져오는 간단한 방법 (실제 운영에서는 권장되지 않음)
    try:
        readings_response = requests.get("http://127.0.0.1:5000/readings")
        if readings_response.status_code == 200:
            recent_readings = readings_response.json().get('data')
            if recent_readings:
                latest_reading_id = recent_readings[0]['reading_id']
                print(f"가장 최근 reading_id: {latest_reading_id}")

                # /predict 엔드포인트 테스트 데이터
                predict_data = {
                    "reading_id": latest_reading_id
                }

                # /predict 테스트
                print("\n--- /predict 테스트 결과 ---")
                predict_response = requests.post("http://127.0.0.1:5000/predict", json=predict_data)
                print("Status Code:", predict_response.status_code)
                print("Response Text:", predict_response.text)
            else:
                print("조회된 데이터가 없어 /predict 테스트를 할 수 없습니다.")
        else:
            print(f"/readings 조회 실패: {readings_response.status_code}, {readings_response.text}")
    except Exception as e:
        print(f"/readings 또는 /predict 테스트 중 오류 발생: {e}")
