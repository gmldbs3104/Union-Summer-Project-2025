# 서버 IP: http://13.125.38.1/

# 라이브러리 불러오기
from flask import Flask, request, jsonify, render_template
from datetime import datetime
import pymysql
import logging
import requests # HTTP 요청 보내기
import pandas as pd # pandas 라이브러리 추가

# 머신러닝 모듈 임포트
from ml_model_interface import predict_wifi_quality

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

    if level == "ERROR":
        color = "#ff0000"
    elif level == "WARNING":
        color = "#ffbf00"
    elif level == "INFO":
        color = "#36a64f"
    else:
        color = "#cccccc"

    message_text = f"🚨 [WiFi 진단 시스템 알림 - {level}] 🚨\n" \
                   f"• 센서 ID: `{sensor_id}`\n" \
                   f"• 센서 위치: `{location}`\n" \
                   f"• 장애 원인: `{problem_reason}`\n" \
                   f"• 발생 시각: `{occurred_at}`"

    slack_payload = {
        "text": message_text, 
        "attachments": [ 
            {
                "color": color, 
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
                        "short": False 
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
        response.raise_for_status()
        logging.info(f"Slack 알림 전송 성공 (Level: {level}, Sensor ID: {sensor_id})")
    except requests.exceptions.RequestException as e:
        logging.error(f"Slack 알림 전송 실패: {e}")
        logging.error(f"Slack Payload: {slack_payload}")

# 데이터 베이스 연결 함수
def get_db_connection():
    return pymysql.connect(
        host='localhost', 
        user='union2025', 
        password='Union2025@', 
        database='wifi_diagnosis_system', 
        charset='utf8mb4', 
        cursorclass=pymysql.cursors.DictCursor
    )

# Flask 애플리케이션 초기화
app = Flask(__name__)

# --- 기본 라우트 ---
@app.route('/')
def index():
    return "<h1>Welcome to My Flask App!</h1>"

# --- 데이터 수집/업로드 API (여러 센서 데이터를 리스트로 받아 처리) ---
@app.route("/upload", methods=["POST"])
def upload():
    conn = None
    try:
        data_list = request.get_json()
        if not isinstance(data_list, list):
            logging.warning(f"잘못된 요청 형식: 데이터는 리스트 형식이어야 합니다. 수신된 데이터: {data_list}")
            return jsonify({"status": "error", "message": "데이터는 리스트 형식이어야 합니다."}), 400

        conn = get_db_connection()
        with conn.cursor() as cursor:
            inserted = 0

            for data in data_list:
                sensor_mac = data.get("sensor_mac", "알 수 없음")
                timestamp = data.get("timestamp", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                sensor_id_for_alert = "N/A"
                location_for_alert = "알 수 없음"
                
                required_keys = ["sensor_mac", "rssi", "ping", "speed", "timestamp", "ping_timeout"]
                if not all(k in data for k in required_keys):
                    logging.warning(f"필수 필드 누락: {data}")
                    send_slack_notification(sensor_mac, location_for_alert, "필수 필드 누락", timestamp, level="WARNING")
                    continue

                try:
                    rssi = float(data["rssi"])
                    ping = float(data["ping"])
                    speed = float(data["speed"])
                    datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                    ping_timeout = bool(data["ping_timeout"])
                except (ValueError, TypeError) as e:
                    logging.warning(f"데이터 형식 오류: {e} / 수신된 데이터: {data}")
                    send_slack_notification(sensor_mac, location_for_alert, "측정 데이터 형식 오류", timestamp, level="WARNING")
                    continue

                cursor.execute("SELECT sensor_id, location FROM f_sensors WHERE ap_mac_address = %s", (sensor_mac,))
                sensor = cursor.fetchone()

                if not sensor:
                    logging.warning(f"미등록 MAC 주소: {sensor_mac}")
                    send_slack_notification(sensor_mac, location_for_alert, "미등록 센서 MAC 주소", timestamp, level="WARNING")
                    continue

                sensor_id = sensor["sensor_id"]
                location = sensor["location"]
                sensor_id_for_alert = sensor_id
                location_for_alert = location
                
                # --- 속도 감소율 계산 로직 ---
                speed_drop_rate = 0.0
                try:
                    # 이전 레코드의 speed 값을 가져오기
                    cursor.execute("""
                        SELECT speed
                        FROM f_sensor_readings
                        WHERE sensor_id = %s AND timestamp < %s
                        ORDER BY timestamp DESC
                        LIMIT 1
                    """, (sensor_id, timestamp))
                    prev_speed_data = cursor.fetchone()
                    
                    if prev_speed_data and prev_speed_data['speed'] > 0:
                        prev_speed = prev_speed_data['speed']
                        speed_drop_rate = (prev_speed - speed) / prev_speed
                        logging.info(f"센서 {sensor_id}의 속도 감소율 계산 완료: {speed_drop_rate}")
                    else:
                        logging.info(f"센서 {sensor_id}의 첫 데이터이거나 이전 속도가 0이므로 속도 감소율을 0.0으로 설정.")
                        speed_drop_rate = 0.0
                except Exception as e:
                    logging.error(f"속도 감소율 계산 중 오류 발생: {e}")
                    speed_drop_rate = None # 계산 실패 시 NULL로 저장

                # 6. 측정값 데이터베이스에 저장
                try:
                    insert_sql = """
                        INSERT INTO f_sensor_readings (sensor_id, timestamp, rssi, ping, speed, ping_timeout, speed_drop_rate)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(insert_sql, (sensor_id, timestamp, rssi, ping, speed, ping_timeout, speed_drop_rate))
                    inserted += 1
                    logging.info(f"센서 {sensor_mac} 데이터 저장 성공 at {timestamp}")
                except Exception as e:
                    logging.warning(f"DB 삽입 오류: {e} / 데이터: {data}")
                    send_slack_notification(sensor_id_for_alert, location_for_alert, f"데이터 저장 중 DB 오류 발생: {str(e)}", timestamp, level="ERROR")
                    continue
            
            conn.commit()
            
        return jsonify({"status": "success", "message": f"총 {inserted}개의 측정값 저장 완료.", "inserted_count": inserted})

    except Exception as e:
        logging.exception(f"/upload API 처리 중 예상치 못한 오류 발생: {e}")
        send_slack_notification("시스템", "서버", f"데이터 업로드 API 처리 중 서버 내부 오류 발생: {str(e)}", datetime.now().strftime('%Y-%m-%d %H:%M:%S'), level="ERROR")
        return jsonify({"status": "error", "message": "서버 내부 오류 발생"}), 500
    
    finally:
        if conn:
            conn.close()

# --- 데이터 조회 API ---
@app.route("/readings", methods=["GET"])
def get_recent_readings():
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT sr.reading_id, s.location, s.ap_mac_address, sr.timestamp, sr.rssi, sr.ping, sr.speed, sr.ping_timeout, sr.speed_drop_rate
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
        send_slack_notification("시스템", "서버", f"데이터 조회 중 DB 오류 발생: {str(e)}", datetime.now().strftime('%Y-%m-%d %H:%M:%S'), level="ERROR")
        return jsonify({"status": "error", "message": "DB 오류 발생"}), 500
    finally:
        if conn:
            conn.close()

# --- 데이터 예측 API ---
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
        send_slack_notification("시스템", "서버", "예측 요청 필수 필드 누락", timestamp_for_alert, level="WARNING")
        return jsonify({"status": "error", "message": "예측에 필요한 'reading_id' 필드가 누락되었습니다."}), 400

    try:
        reading_id = int(data["reading_id"])
        reading_id_for_alert = reading_id
    except (ValueError, TypeError):
        logging.warning(f"reading_id 타입 오류: {data['reading_id']}")
        send_slack_notification("시스템", "서버", f"예측 요청 Reading ID 형식 오류: {data.get('reading_id', '없음')}", timestamp_for_alert, level="WARNING")
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
                send_slack_notification("시스템", "서버", f"예측 대상 측정값 없음 (Reading ID: {reading_id})", timestamp_for_alert, level="ERROR")
                return jsonify({"status": "error", "message": f"reading_id {reading_id}에 해당하는 측정값을 찾을 수 없습니다."}), 404

            sensor_id_for_alert = reading_data['sensor_id']
            location_for_alert = reading_data['location']
            timestamp_for_alert = reading_data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')

            predicted_problem_type = predict_wifi_quality(
                reading_data['rssi'],
                reading_data['ping'],
                reading_data['speed'],
                location=reading_data['location'],
                ap_mac_address=reading_data['ap_mac_address'],
                timestamp=reading_data['timestamp']
            )

            insert_diagnosis_sql = """
                INSERT INTO f_diagnosis_results (reading_id, problem_type)
                VALUES (%s, %s)
            """
            cursor.execute(insert_diagnosis_sql, (reading_id, predicted_problem_type))
            conn.commit()

        logging.info(f"reading_id {reading_id}에 대한 예측 및 저장 성공. 결과: {predicted_problem_type}")
        send_slack_notification(sensor_id_for_alert, location_for_alert, f"예측 결과: {predicted_problem_type}", timestamp_for_alert, level="INFO")

        return jsonify({
            "status": "success",
            "message": "예측 완료 및 저장",
            "reading_id": reading_id,
            "predicted_problem_type": predicted_problem_type
        })
    except Exception as e:
        logging.exception(f"예측 API 오류 발생 /predict: {e}")
        send_slack_notification(sensor_id_for_alert, location_for_alert, f"예측 처리 중 시스템 오류 발생: {str(e)}", datetime.now().strftime('%Y-%m-%d %H:%M:%S'), level="ERROR")
        return jsonify({"status": "error", "message": "예측 처리 중 오류 발생"}), 500
    finally:
        if conn:
            conn.close()

# 서버 실행 (테스트 서버용 - Gunicorn/Nginx 사용 시 주석 처리)
# if __name__ == "__main__":
#     app.run(host="0.0.0.0", port=5000, debug=True)