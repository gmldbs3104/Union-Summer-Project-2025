# 서버

# 라이브러리 불러오기
from flask import Flask, request, jsonify, render_template
from datetime import datetime
import pymysql
import logging
import requests # HTTP 요청 보내기

# 머신러닝 모듈 임포트
from ml_model_interface import predict_wifi_quality

# Slack 알림
# config.py 파일에서 SLACK_WEBHOOK_URL 불러오기
try:
    from config import SLACK_WEBHOOK_URL
except ImportError:
    SLACK_WEBHOOK_URL = None
    logging.warning("Slack Webhook URL이 설정되지 않았습니다. Slack 알림 기능이 작동하지 않습니다.")

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Slack 알림 전송 함수
def send_slack_notification(sensor_id, location, problem_reason, occurred_at, level="ERROR"):
    if not SLACK_WEBHOOK_URL:
        logging.error("Slack Webhook URL이 설정되지 않아 알림을 보낼 수 없습니다.")
        return

    # 알림 레벨에 따른 색상 설정
    if level == "ERROR":
        color = "#ff0000" # 빨강
    elif level == "WARNING":
        color = "#ffbf00" # 주황
    elif level == "INFO":
        color = "#36a64f" # 초록 (정보성/성공 알림)
    else:
        color = "#cccccc" # 기본 회색

    # Slack 메시지 본문 구성
    message_text = f"🚨 **[WiFi 진단 시스템 알림 - {level}]** 🚨\n" \
                   f"• 센서 ID: `{sensor_id}`\n" \
                   f"• 센서 위치: `{location}`\n" \
                   f"• 장애 원인: `{problem_reason}`\n" \
                   f"• 발생 시각: `{occurred_at}`"

    # Slack 메시지 페이로드 (JSON 형식)
    slack_payload = {
        "text": message_text,
        "attachments": [
            {
                "color": color, # 동적 색상 적용
                "fields": [
                    {
                        "title": "센서 ID",
                        "value": str(sensor_id),
                        "short": True
                    },
                    {
                        "title": "센서 위치",
                        "value": location,
                        "short": True
                    },
                    {
                        "title": "장애 원인",
                        "value": problem_reason,
                        "short": False # 긴 메시지를 위해 false
                    },
                    {
                        "title": "발생 시각",
                        "value": occurred_at,
                        "short": True
                    }
                ],
                "footer": "WiFi Diagnosis System"
            }
        ]
    }

    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=slack_payload)
        response.raise_for_status() # HTTP 오류가 발생하면 예외 발생
        logging.info(f"Slack 알림 전송 성공 (Level: {level}, Sensor ID: {sensor_id})")
    except requests.exceptions.RequestException as e:
        logging.error(f"Slack 알림 전송 실패: {e}")
        logging.error(f"Slack Payload: {slack_payload}") # 어떤 페이로드를 보냈는지 확인용

# 데이터 베이스 연결
def get_db_connection():
    return pymysql.connect(
        host='localhost',
        user='union2025',
        password='Union2025@',
        database='wifi_diagnosis_system',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

# EC2 서버
app = Flask(__name__)

# Case 1: 루트 경로가 정의되어 있고, HTML을 반환하는 경우
@app.route('/')
def index():
    return "<h1>Welcome to My Flask App!</h1>"

# Case 2: 다른 경로만 정의되어 있는 경우
@app.route('/hello')
def hello_world():
    return "Hello, World!"

# Case 3: 변수 경로가 있는 경우
@app.route('/user/<username>')
def show_user_profile(username):
    return f'User {username}'

# 데이터 수집/업로드 API
@app.route("/upload", methods=["POST"])
def upload():
    data = request.get_json()

    # 알림에 사용할 기본 정보 (가능한 경우 먼저 추출)
    sensor_mac = data.get("sensor_mac", "알 수 없음")
    timestamp = data.get("timestamp", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    sensor_id_for_alert = "N/A" # 초기값, DB에서 조회 후 업데이트
    location_for_alert = "알 수 없음" # 초기값, DB에서 조회 후 업데이트

    # 필드 포함 여부 확인
    required_keys = ["sensor_mac", "rssi", "ping", "speed", "timestamp", "ping_timeout"]
    if not all(k in data for k in required_keys):
        logging.warning(f"필드 누락: {data}")
        send_slack_notification(
            sensor_mac,
            location_for_alert,
            f"필수 필드 누락: {', '.join([k for k in required_keys if k not in data])}", # 메시지 명확화
            timestamp,
            level="WARNING"
        )
        return jsonify({"status": "error", "message": "필드 누락"}), 400

    # 데이터 형식 검사
    try:
        rssi = float(data["rssi"])
        ping = float(data["ping"])
        speed = float(data["speed"])
    except (ValueError, TypeError):
        logging.warning(f"데이터 타입 오류: {data}")
        send_slack_notification(
            sensor_mac,
            location_for_alert,
            "측정 데이터 형식 오류 (rssi, ping, speed는 숫자여야 함)", # 메시지 명확화
            timestamp,
            level="WARNING"
        )
        return jsonify({"status": "error", "message": "rssi, ping, speed는 숫자여야 합니다."}), 400

    try:
        datetime.strptime(data["timestamp"], '%Y-%m-%d %H:%M:%S')
    except ValueError:
        logging.warning(f"timestamp 형식 오류: {data['timestamp']}")
        send_slack_notification(
            sensor_mac,
            location_for_alert,
            f"타임스탬프 형식 오류: {data['timestamp']}", # 메시지 명확화
            timestamp,
            level="WARNING"
        )
        return jsonify({"status": "error", "message": "timestamp 형식이 올바르지 않습니다."}), 400

    try:
        ping_timeout = bool(data["ping_timeout"])
    except (ValueError, TypeError):
        logging.warning(f"ping_timeout 타입 오류: {data}")
        send_slack_notification(
            sensor_mac,
            location_for_alert,
            "핑 타임아웃 형식 오류 (boolean 값이어야 함)", # 메시지 명확화
            timestamp,
            level="WARNING"
        )
        return jsonify({"status": "error", "message": "ping_timeout은 boolean 값이어야 합니다."}), 400

    # DB 연결 및 처리
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:

            # MAC 주소로 센서 ID 찾기
            cursor.execute("SELECT sensor_id, location FROM f_sensors WHERE ap_mac_address = %s", (sensor_mac,))
            sensor = cursor.fetchone()

            if not sensor:
                logging.error(f"미등록 MAC 주소: {sensor_mac}")
                send_slack_notification(
                    sensor_mac,
                    location_for_alert,
                    "미등록 센서 MAC 주소로 인한 데이터 수집 실패", # 메시지 명확화
                    timestamp,
                    level="ERROR"
                )
                return jsonify({"status": "error", "message": "해당 MAC 주소의 센서가 등록되어 있지 않습니다."}), 404

            sensor_id = sensor["sensor_id"]
            location = sensor["location"] # <--- DB에서 location 정보 가져옴

            # 알림 정보 업데이트
            sensor_id_for_alert = sensor_id
            location_for_alert = location

            # 측정값 저장
            insert_sql = """
                INSERT INTO f_sensor_readings (sensor_id, timestamp, rssi, ping, speed, ping_timeout)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_sql, (sensor_id, timestamp, rssi, ping, speed, ping_timeout))
            conn.commit()

        logging.info(f"센서 {sensor_mac} 데이터 저장 성공 at {timestamp}")
        return jsonify({"status": "success", "message": "측정값 저장 완료"})

    except Exception as e:
        logging.exception(f"DB 오류 발생 /upload: {e}")
        send_slack_notification(
            sensor_id_for_alert,
            location_for_alert,
            f"데이터 저장 중 DB 오류 발생: {str(e)}", # 메시지 명확화
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            level="ERROR"
        )
        return jsonify({"status": "error", "message": "DB 오류 발생"}), 500

    finally:
        if conn:
            conn.close()

# 데이터 조회 API
@app.route("/readings", methods=["GET"])
def get_recent_readings():
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT sr.reading_id, s.location, s.ap_mac_address, sr.timestamp, sr.rssi, sr.ping, sr.speed, sr.ping_timeout
                FROM f_sensor_readings sr
                JOIN f_sensors s ON sr.sensor_id = s.sensor_id
                ORDER BY sr.timestamp DESC
                LIMIT 10
            """)
            results = cursor.fetchall()
        logging.info("최근 10개 데이터 조회 성공")
        return jsonify({"status": "success", "data": results})

    except Exception as e:
        logging.exception(f"DB 오류 발생 /readings: {e}")
        send_slack_notification(
            "시스템",
            "서버",
            f"데이터 조회 중 DB 오류 발생: {str(e)}", # 메시지 명확화
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            level="ERROR"
        )
        return jsonify({"status": "error", "message": "DB 오류 발생"}), 500

    finally:
        if conn:
            conn.close()

# 데이터 예측 API
@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json()

    reading_id_for_alert = data.get("reading_id", "N/A")
    sensor_id_for_alert = "N/A"
    location_for_alert = "알 수 없음"
    timestamp_for_alert = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    required_keys = ["reading_id"]
    if not all(k in data for k in required_keys):
        logging.warning(f"예측 요청 필드 누락: {data}")
        send_slack_notification(
            "시스템",
            "서버",
            "예측 요청 필수 필드 누락", # 메시지 명확화
            timestamp_for_alert,
            level="WARNING"
        )
        return jsonify({"status": "error", "message": "예측에 필요한 'reading_id' 필드가 누락되었습니다."}), 400

    try:
        reading_id = int(data["reading_id"])
        reading_id_for_alert = reading_id
    except (ValueError, TypeError):
        logging.warning(f"reading_id 타입 오류: {data['reading_id']}")
        send_slack_notification(
            "시스템",
            "서버",
            f"예측 요청 Reading ID 형식 오류: {data.get('reading_id', '없음')}", # 메시지 명확화
            timestamp_for_alert,
            level="WARNING"
        )
        return jsonify({"status": "error", "message": "reading_id는 정수여야 합니다."}), 400

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT sr.rssi, sr.ping, sr.speed, s.location, s.ap_mac_address, sr.timestamp, s.sensor_id
                FROM f_sensor_readings sr
                JOIN f_sensors s ON sr.sensor_id = s.sensor_id
                WHERE sr.reading_id = %s
            """, (reading_id,))
            reading_data = cursor.fetchone()

            if not reading_data:
                logging.error(f"reading_id {reading_id}에 해당하는 데이터 없음.")
                send_slack_notification(
                    "시스템",
                    "서버",
                    f"예측 대상 측정값 없음 (Reading ID: {reading_id})", # 메시지 명확화
                    timestamp_for_alert,
                    level="ERROR"
                )
                return jsonify({"status": "error", "message": f"reading_id {reading_id}에 해당하는 측정값을 찾을 수 없습니다."}), 404

            sensor_id_for_alert = reading_data['sensor_id']
            location_for_alert = reading_data['location']
            timestamp_for_alert = reading_data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')

            # 모델을 사용하여 예측 수행
            predicted_problem_type = predict_wifi_quality(
                reading_data['rssi'],
                reading_data['ping'],
                reading_data['speed'],
                location=reading_data['location'],
                ap_mac_address=reading_data['ap_mac_address'],
                timestamp=reading_data['timestamp']
            )

            # 예측 결과 f_diagnosis_results 테이블에 저장
            insert_diagnosis_sql = """
                INSERT INTO f_diagnosis_results (reading_id, problem_type)
                VALUES (%s, %s)
            """
            cursor.execute(insert_diagnosis_sql, (reading_id, predicted_problem_type))
            conn.commit()

        logging.info(f"reading_id {reading_id}에 대한 예측 및 저장 성공. 결과: {predicted_problem_type}")

        # --- 성공적인 예측에 대한 Slack 알림 추가 ---
        send_slack_notification(
            sensor_id_for_alert,
            location_for_alert,
            f"예측 결과: {predicted_problem_type}", # 장애 원인에 예측 결과 직접 표시
            timestamp_for_alert,
            level="INFO" # 정보성 알림으로 변경 (성공했으니)
        )
        # --- Slack 알림 추가 끝 ---

        return jsonify({
            "status": "success",
            "message": "예측 완료 및 저장",
            "reading_id": reading_id,
            "predicted_problem_type": predicted_problem_type
        })

    except Exception as e:
        logging.exception(f"예측 API 오류 발생 /predict: {e}")
        send_slack_notification(
            sensor_id_for_alert,
            location_for_alert,
            f"예측 처리 중 시스템 오류 발생: {str(e)}", # 메시지 명확화
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            level="ERROR"
        )
        return jsonify({"status": "error", "message": "예측 처리 중 오류 발생"}), 500
    finally:
        if conn:
            conn.close()

# 서버 실행(테스트 서버용)
# if __name__ == "__main__":
#     app.run(host="0.0.0.0", port=5000, debug=True)
