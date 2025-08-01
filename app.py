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

    # 알림 레벨에 따른 색상 설정
    if level == "ERROR":
        color = "#ff0000" # 빨강
    elif level == "WARNING":
        color = "#ffbf00" # 주황
    elif level == "INFO":
        color = "#36a64f" # 초록 (정보성/성공 알림)
    else:
        color = "#cccccc" # 기본 회색

    # 메시지 본문
    message_text = f"🚨 [WiFi 진단 시스템 알림 - {level}] 🚨\n" \
                   f"• 센서 ID: `{sensor_id}`\n" \
                   f"• 센서 위치: `{location}`\n" \
                   f"• 장애 원인: `{problem_reason}`\n" \
                   f"• 발생 시각: `{occurred_at}`"

    # 메시지 페이로드 (JSON 형식)
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
        # Slack Webhook URL로 POST 요청 전송
        response = requests.post(SLACK_WEBHOOK_URL, json=slack_payload)
        response.raise_for_status() # HTTP 오류가 발생하면 예외 발생 (4xx, 5xx 응답)
        logging.info(f"Slack 알림 전송 성공 (Level: {level}, Sensor ID: {sensor_id})")
    except requests.exceptions.RequestException as e:
        # Slack 알림 전송 실패 시 로깅
        logging.error(f"Slack 알림 전송 실패: {e}")
        logging.error(f"Slack Payload: {slack_payload}") # 어떤 페이로드를 보냈는지 확인용

# 데이터 베이스 연결 함수
def get_db_connection():
    return pymysql.connect(
        host='localhost', 
        user='union2025', 
        password='Union2025@', 
        database='wifi_diagnosis_system', 
        charset='utf8mb4', 
        cursorclass=pymysql.cursors.DictCursor # 딕셔너리 형태로 결과를 반환
    )

# Flask 애플리케이션 초기화
app = Flask(__name__)

# --- 기본 라우트 ---
@app.route('/')
def index():
    """루트 경로 요청 처리: 환영 메시지 반환."""
    return "<h1>Welcome to My Flask App!</h1>"

# --- 데이터 수집/업로드 API (여러 센서 데이터를 리스트로 받아 처리) ---
@app.route("/upload", methods=["POST"])
def upload():
    try:
        # 1. 요청 본문이 JSON 리스트인지 확인
        data_list = request.get_json()
        if not isinstance(data_list, list):
            logging.warning(f"잘못된 요청 형식: 데이터는 리스트 형식이어야 합니다. 수신된 데이터: {data_list}")
            return jsonify({"status": "error", "message": "데이터는 리스트 형식이어야 합니다."}), 400

        conn = get_db_connection()
        with conn.cursor() as cursor:
            inserted = 0 # 성공적으로 삽입된 레코드 수를 추적하는 카운터

            # 2. 리스트의 각 데이터 레코드를 반복하여 처리
            for data in data_list:
                # 알림에 사용할 기본 정보 (가능한 경우 먼저 추출)
                sensor_mac = data.get("sensor_mac", "알 수 없음")
                timestamp = data.get("timestamp", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                sensor_id_for_alert = "N/A"
                location_for_alert = "알 수 없음"

                # 3. 필수 필드 포함 여부 확인
                required_keys = ["sensor_mac", "rssi", "ping", "speed", "timestamp", "ping_timeout"]
                if not all(k in data for k in required_keys):
                    logging.warning(f"필수 필드 누락: {data}")
                    send_slack_notification(
                        sensor_mac,
                        location_for_alert,
                        f"필수 필드 누락: {', '.join([k for k in required_keys if k not in data])}",
                        timestamp,
                        level="WARNING"
                    )
                    continue 

                # 4. 데이터 형식 검사 
                try:
                    rssi = float(data["rssi"])
                    ping = float(data["ping"])
                    speed = float(data["speed"])
                    datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                    ping_timeout = bool(data["ping_timeout"])
                except (ValueError, TypeError) as e:
                    logging.warning(f"데이터 형식 오류: {e} / 수신된 데이터: {data}")
                    send_slack_notification(
                        sensor_mac,
                        location_for_alert,
                        f"측정 데이터 형식 오류: {e}",
                        timestamp,
                        level="WARNING"
                    )
                    continue 

                # 5. DB에서 MAC 주소로 센서 ID 및 위치 조회
                cursor.execute("SELECT sensor_id, location FROM f_sensors WHERE ap_mac_address = %s", (sensor_mac,))
                sensor = cursor.fetchone()

                if not sensor:
                    logging.warning(f"미등록 MAC 주소: {sensor_mac}")
                    send_slack_notification(
                        sensor_mac,
                        location_for_alert,
                        "미등록 센서 MAC 주소로 인한 데이터 수집 실패",
                        timestamp,
                        level="WARNING" 
                    )
                    continue 

                sensor_id = sensor["sensor_id"]
                location = sensor["location"] 

                # 알림 정보 업데이트 
                sensor_id_for_alert = sensor_id
                location_for_alert = location

                # 6. 측정값 데이터베이스에 저장
                try:
                    insert_sql = """
                        INSERT INTO f_sensor_readings (sensor_id, timestamp, rssi, ping, speed, ping_timeout)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(insert_sql, (sensor_id, timestamp, rssi, ping, speed, ping_timeout))
                    inserted += 1 # 성공적으로 삽입된 경우 카운터 증가
                    logging.info(f"센서 {sensor_mac} 데이터 저장 성공 at {timestamp}")
                except Exception as e:
                    logging.warning(f"DB 삽입 오류: {e} / 데이터: {data}")
                    send_slack_notification(
                        sensor_id_for_alert,
                        location_for_alert,
                        f"데이터 저장 중 DB 오류 발생: {str(e)}",
                        timestamp,
                        level="ERROR"
                    )
                    continue 

            conn.commit()

        # 7. 최종 성공 응답 반환
        return jsonify({"status": "success", "message": f"총 {inserted}개의 측정값 저장 완료.", "inserted_count": inserted})

    except Exception as e:
        logging.exception(f"/upload API 처리 중 예상치 못한 오류 발생: {e}")
        send_slack_notification(
            "시스템", 
            "서버",
            f"데이터 업로드 API 처리 중 서버 내부 오류 발생: {str(e)}",
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            level="ERROR"
        )
        return jsonify({"status": "error", "message": "서버 내부 오류 발생"}), 500
    
    finally:
        if 'conn' in locals() and conn:
            conn.close()

# --- 데이터 조회 API ---
@app.route("/readings", methods=["GET"])
def get_recent_readings():
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # f_sensor_readings와 f_sensors 테이블을 조인 -> 필요한 정보 조회
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
        send_slack_notification(
            "시스템",
            "서버",
            f"데이터 조회 중 DB 오류 발생: {str(e)}",
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            level="ERROR"
        )
        return jsonify({"status": "error", "message": "DB 오류 발생"}), 500

    finally:
        if conn:
            conn.close()

# --- 데이터 예측 API ---
@app.route("/predict", methods=["POST"])
def predict():
    """
    주어진 reading_id에 해당하는 센서 데이터를 조회하여 머신러닝 모델로 WiFi 품질을 예측하고,
    그 결과를 데이터베이스에 저장합니다.
    """
    data = request.get_json()

    # 알림에 사용할 기본 정보 초기화
    reading_id_for_alert = data.get("reading_id", "N/A")
    sensor_id_for_alert = "N/A"
    location_for_alert = "알 수 없음"
    timestamp_for_alert = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 필수 필드 확인
    required_keys = ["reading_id"]
    if not all(k in data for k in required_keys):
        logging.warning(f"예측 요청 필드 누락: {data}")
        send_slack_notification(
            "시스템",
            "서버",
            "예측 요청 필수 필드 누락",
            timestamp_for_alert,
            level="WARNING"
        )
        return jsonify({"status": "error", "message": "예측에 필요한 'reading_id' 필드가 누락되었습니다."}), 400

    # reading_id의 데이터 타입 검사
    try:
        reading_id = int(data["reading_id"])
        reading_id_for_alert = reading_id # 알림용 ID 업데이트
    except (ValueError, TypeError):
        logging.warning(f"reading_id 타입 오류: {data['reading_id']}")
        send_slack_notification(
            "시스템",
            "서버",
            f"예측 요청 Reading ID 형식 오류: {data.get('reading_id', '없음')}",
            timestamp_for_alert,
            level="WARNING"
        )
        return jsonify({"status": "error", "message": "reading_id는 정수여야 합니다."}), 400

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # reading_id에 해당하는 센서 데이터 조회
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
                    f"예측 대상 측정값 없음 (Reading ID: {reading_id})",
                    timestamp_for_alert,
                    level="ERROR"
                )
                return jsonify({"status": "error", "message": f"reading_id {reading_id}에 해당하는 측정값을 찾을 수 없습니다."}), 404

            # 알림에 사용할 센서 정보 업데이트
            sensor_id_for_alert = reading_data['sensor_id']
            location_for_alert = reading_data['location']
            timestamp_for_alert = reading_data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')

            # 머신러닝 모델을 사용하여 예측 수행
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

        # 성공적인 예측에 대한 Slack 알림 전송 (INFO 레벨)
        send_slack_notification(
            sensor_id_for_alert,
            location_for_alert,
            f"예측 결과: {predicted_problem_type}", # 장애 원인에 예측 결과 직접 표시
            timestamp_for_alert,
            level="INFO" # 정보성 알림으로 변경 (성공했으니)
        )

        # 예측 결과 반환
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
            f"예측 처리 중 시스템 오류 발생: {str(e)}",
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            level="ERROR"
        )
        return jsonify({"status": "error", "message": "예측 처리 중 오류 발생"}), 500
    finally:
        if conn:
            conn.close()

# --- 속도 감소율 계산 및 업데이트 API (수정된 코드) ---
@app.route("/calculate_speed_drop_rates", methods=["POST"])
def calculate_speed_drop_rates():
    conn = None
    try:
        conn = get_db_connection()
        logging.info("데이터베이스 연결 성공.")

        # 1. 속도 감소율 계산이 필요한 데이터만 가져오기
        # `speed_drop_rate`가 NULL인 레코드와 그 직전 레코드를 가져오는 복합 쿼리를 사용
        df = pd.read_sql("""
            WITH latest_readings AS (
                SELECT
                    reading_id,
                    sensor_id,
                    timestamp,
                    speed,
                    ROW_NUMBER() OVER(PARTITION BY sensor_id ORDER BY timestamp DESC) as rn
                FROM f_sensor_readings
                WHERE speed_drop_rate IS NULL
            ),
            previous_readings AS (
                SELECT
                    sensor_id,
                    speed,
                    timestamp
                FROM f_sensor_readings
                WHERE timestamp < (SELECT MIN(timestamp) FROM latest_readings)
                ORDER BY timestamp DESC
                LIMIT 100
            )
            SELECT * FROM latest_readings
            UNION ALL
            SELECT * FROM previous_readings
        """, conn)

        logging.info(f"계산 필요한 데이터 {len(df)}개 불러오기 완료.")

        if df.empty:
            logging.info("계산할 데이터가 없어 속도 감소율을 계산할 내용이 없습니다.")
            return jsonify({"status": "success", "message": "계산할 데이터가 없습니다."})

        # 2. 센서별로 그룹화하여 이전 speed와 비교한 속도 감소율 계산
        df["prev_speed"] = df.groupby("sensor_id")["speed"].shift(1)
        df["speed_drop_rate"] = (df["prev_speed"] - df["speed"]) / df["prev_speed"]
        
        # 3. 계산된 결과만 필터링하고, NaN 제거 (첫 행은 비교 불가)
        df = df[df['rn'] == 1].dropna(subset=["speed_drop_rate"])
        logging.info(f"계산 가능한 {len(df)}개의 측정값에 대한 속도 감소율 계산 완료.")

        if df.empty:
            logging.info("계산 가능한 속도 감소율 데이터가 없어 업데이트할 내용이 없습니다.")
            return jsonify({"status": "success", "message": "계산 가능한 속도 감소율 데이터가 없어 업데이트할 내용이 없습니다."})

        # 4. DB 업데이트 실행
        update_count = 0
        with conn.cursor() as cursor:
            for _, row in df.iterrows():
                try:
                    cursor.execute("""
                        UPDATE f_sensor_readings
                        SET speed_drop_rate = %s
                        WHERE reading_id = %s
                    """, (row["speed_drop_rate"], int(row["reading_id"])))
                    update_count += 1
                except Exception as update_e:
                    logging.error(f"reading_id {row['reading_id']}의 speed_drop_rate 업데이트 실패: {update_e}")
            
            conn.commit() # 모든 업데이트를 한 번에 커밋
        
        logging.info(f"총 {update_count}개의 측정값에 대한 speed_drop_rate 업데이트 성공.")
        
        return jsonify({"status": "success", "message": f"총 {update_count}개의 측정값에 대한 속도 감소율 업데이트 완료."})

    except pymysql.Error as db_err:
        logging.exception(f"데이터베이스 오류 발생 /calculate_speed_drop_rates: {db_err}")
        send_slack_notification(
            "시스템",
            "서버",
            f"속도 감소율 계산 중 DB 오류 발생: {str(db_err)}",
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            level="ERROR"
        )
        return jsonify({"status": "error", "message": "DB 오류 발생"}), 500
    except Exception as e:
        logging.exception(f"속도 감소율 계산 및 업데이트 중 예상치 못한 오류 발생: {e}")
        send_slack_notification(
            "시스템",
            "서버",
            f"속도 감소율 계산 중 시스템 오류 발생: {str(e)}",
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            level="ERROR"
        )
        return jsonify({"status": "error", "message": "예측 처리 중 오류 발생"}), 500
    finally:
        if conn:
            conn.close()

# 서버 실행 (테스트 서버용 - Gunicorn/Nginx 사용 시 주석 처리)
# if __name__ == "__main__":
#     app.run(host="0.0.0.0", port=5000, debug=True)