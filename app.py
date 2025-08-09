# 라이브러리 불러오기
from flask import Flask, request, jsonify, render_template
from datetime import datetime
import pymysql
import logging
import requests

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
                    {"title": "센서 ID", "value": str(sensor_id), "short": True},
                    {"title": "센서 위치", "value": location, "short": True},
                    {"title": "장애 원인", "value": problem_reason, "short": False},
                    {"title": "발생 시각", "value": occurred_at, "short": True}
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
    return "<h1>WiFi Diagnosis System is Running</h1>"

# --- 데이터 수집, 저장, 예측을 한 번에 처리하는 API ---
@app.route("/upload", methods=["POST"])
def upload_and_predict():
    conn = None
    try:
        data_list = request.get_json()
        if not isinstance(data_list, list):
            return jsonify({"status": "error", "message": "데이터는 리스트 형식이어야 합니다."}), 400

        conn = get_db_connection()
        with conn.cursor() as cursor:
            processed_count = 0
            for data in data_list:
                # 1. 데이터 검증 및 전처리
                sensor_mac = data.get("sensor_mac", "알 수 없음")
                timestamp_str = data.get("timestamp", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                try:
                    rssi = float(data["rssi"])
                    ping = float(data["ping"])
                    speed = float(data["speed"])
                    ping_timeout = bool(data["ping_timeout"])
                except (ValueError, TypeError, KeyError) as e:
                    logging.warning(f"데이터 형식/필드 오류: {e} / 수신 데이터: {data}")
                    continue

                cursor.execute("SELECT sensor_id, location FROM f_sensors WHERE ap_mac_address = %s", (sensor_mac,))
                sensor = cursor.fetchone()
                if not sensor:
                    logging.warning(f"미등록 MAC 주소: {sensor_mac}")
                    continue
                
                sensor_id = sensor["sensor_id"]
                location = sensor["location"]
                
                # 2. 속도 감소율 계산
                speed_drop_rate = 0.0
                try:
                    cursor.execute("SELECT speed FROM f_sensor_readings WHERE sensor_id = %s AND timestamp < %s ORDER BY timestamp DESC LIMIT 1", (sensor_id, timestamp_str))
                    prev_speed_data = cursor.fetchone()
                    if prev_speed_data and prev_speed_data['speed'] > 0:
                        speed_drop_rate = (prev_speed_data['speed'] - speed) / prev_speed_data['speed']
                except Exception as e:
                    logging.error(f"속도 감소율 계산 중 오류: {e}")
                    speed_drop_rate = 0.0 # 오류 시 0으로 처리

                # 3. 측정값 DB 저장
                insert_sql = "INSERT INTO f_sensor_readings (sensor_id, timestamp, rssi, ping, speed, ping_timeout, speed_drop_rate) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                cursor.execute(insert_sql, (sensor_id, timestamp_str, rssi, ping, speed, ping_timeout, speed_drop_rate))
                reading_id = cursor.lastrowid
                conn.commit()
                logging.info(f"ID {reading_id}: 데이터 저장 성공.")

                # 4. 저장된 데이터로 "바로" 예측 실행
                predicted_problem_type = predict_wifi_quality(
                    rssi=rssi,
                    speed=speed,
                    ping=ping,
                    timeout=ping_timeout,
                    speed_drop_rate=speed_drop_rate or 0.0
                )
                logging.info(f"ID {reading_id}: 예측 완료. 결과: {predicted_problem_type}")

                # 5. 예측 결과를 DB에 저장
                insert_diagnosis_sql = "INSERT INTO f_diagnosis_results (reading_id, problem_type) VALUES (%s, %s)"
                cursor.execute(insert_diagnosis_sql, (reading_id, predicted_problem_type))
                conn.commit()
                logging.info(f"ID {reading_id}: 예측 결과 저장 성공.")

                # 6. Slack 알림 전송
                send_slack_notification(sensor_id, location, f"예측 결과: {predicted_problem_type}", timestamp_str, level="INFO")
                processed_count += 1

            return jsonify({"status": "success", "message": f"총 {processed_count}개의 데이터 처리 및 예측 완료."})

    except Exception as e:
        logging.exception(f"/upload API 처리 중 예상치 못한 오류 발생: {e}")
        if conn:
            conn.rollback() # 오류 발생 시 DB 변경사항 되돌리기
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
        return jsonify({"status": "success", "data": results})
    except Exception as e:
        logging.exception(f"DB 오류 발생 /readings: {e}")
        return jsonify({"status": "error", "message": "DB 오류 발생"}), 500
    finally:
        if conn:
            conn.close()

# --- 참고용: 수동으로 재분석할 때 사용하는 API ---
@app.route("/predict", methods=["POST"])
def predict():
    conn = None
    try:
        data = request.get_json()
        reading_id = int(data["reading_id"])
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT sr.*, s.location, s.ap_mac_address FROM f_sensor_readings sr JOIN f_sensors s ON sr.sensor_id = s.sensor_id WHERE sr.reading_id = %s", (reading_id,))
            reading_data = cursor.fetchone()
            if not reading_data:
                return jsonify({"status": "error", "message": "해당 reading_id를 찾을 수 없습니다."}), 404
            
            predicted_problem_type = predict_wifi_quality(
                rssi=reading_data['rssi'],
                speed=reading_data['speed'],
                ping=reading_data['ping'],
                timeout=reading_data['ping_timeout'],
                speed_drop_rate=reading_data['speed_drop_rate'] or 0.0
            )
            
            # 예측 결과가 이미 있으면 업데이트, 없으면 새로 삽입
            cursor.execute("INSERT INTO f_diagnosis_results (reading_id, problem_type) VALUES (%s, %s) ON DUPLICATE KEY UPDATE problem_type = VALUES(problem_type)", (reading_id, predicted_problem_type))
            conn.commit()
            
        return jsonify({"status": "success", "reading_id": reading_id, "predicted_problem_type": predicted_problem_type})
    except Exception as e:
        logging.exception(f"예측 API 오류 발생 /predict: {e}")
        return jsonify({"status": "error", "message": "예측 처리 중 오류 발생"}), 500
    finally:
        if conn:
            conn.close()

# 서버 실행 (로컬 테스트용)
# if __name__ == "__main__":
#     app.run(host="0.0.0.0", port=5000, debug=True)
