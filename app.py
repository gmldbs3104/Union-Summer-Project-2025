# 서버

# 라이브러리 불러오기
from flask import Flask, request, jsonify # request: 데이터 접근 jsonify: Python 데이터를 JSON으로 응답하게 해줌
from datetime import datetime # 시간 관련 기능
import pymysql # DB 접속 정보 설정 
import logging # 콘솔 로깅 라이브러리

# 머신러닝 모듈 임포트
from ml_model_interface import predict_wifi_quality

# 로깅 설정 
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 데이터 베이스 연결
def get_db_connection():
    return pymysql.connect(
        host='localhost',
        user='union2025',                   # MySQL 사용자명
        password='Union2025@',     # MySQL 비밀번호
        database='wifi_diagnosis_system',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

app = Flask(__name__) # 서버 객체 생성

# 데이터 수집/업로드 API
@app.route("/upload", methods=["POST"])
def upload():
    data = request.get_json() # 데이터 수신

    # 필드 포함 여부 확인
    required_keys = ["sensor_mac", "rssi", "ping", "speed", "timestamp", "ping_timeout"]
    if not all(k in data for k in required_keys):
        logging.warning(f"필드 누락: {data}")
        return jsonify({"status": "error", "message": "필드 누락"}), 400

    # 데이터 형식 검사
    # rssi, ping, speed
    try:
        rssi = float(data["rssi"])
        ping = float(data["ping"])
        speed = float(data["speed"])

    except (ValueError, TypeError):
        logging.warning(f"데이터 타입 오류: {data}")
        return jsonify({"status": "error", "message": "rssi, ping, speed는 숫자여야 합니다."}), 400

    # timestamp
    try:
        datetime.strptime(data["timestamp"], '%Y-%m-%d %H:%M:%S')

    except ValueError:
        logging.warning(f"timestamp 형식 오류: {data['timestamp']}")
        return jsonify({"status": "error", "message": "timestamp 형식이 올바르지 않습니다."}), 400

    # ping_timeout
    try:
        ping_timeout = bool(data["ping_timeout"]) 

    except (ValueError, TypeError):
        logging.warning(f"ping_timeout 타입 오류: {data}")
        return jsonify({"status": "error", "message": "ping_timeout은 boolean 값이어야 합니다."}), 400
    
    sensor_mac = data["sensor_mac"]
    timestamp = data["timestamp"] 

    # DB 연결 및 처리    
    conn = None
    try:
        conn = get_db_connection() # DB 연결
        with conn.cursor() as cursor:

            # MAC 주소로 센서 ID 찾기
            cursor.execute("SELECT sensor_id FROM f_sensors WHERE ap_mac_address = %s", (sensor_mac,))
            sensor = cursor.fetchone()

            if not sensor:
                logging.error(f"미등록 MAC 주소: {sensor_mac}")
                return jsonify({"status": "error", "message": "해당 MAC 주소의 센서가 등록되어 있지 않습니다."}), 404

            sensor_id = sensor["sensor_id"]

            # 측정값 저장
            insert_sql = """
                INSERT INTO f_sensor_readings (sensor_id, timestamp, rssi, ping, speed, ping_timeout)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_sql, (sensor_id, timestamp, rssi, ping, speed, ping_timeout))
            conn.commit()

        logging.info(f"센서 {data['sensor_mac']} 데이터 저장 성공 at {data['timestamp']}")
        return jsonify({"status": "success", "message": "측정값 저장 완료"})

    except Exception as e:
        logging.exception(f"DB 오류 발생 /upload: {e}") 
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
            # 최근 10개 데이터 조회
            cursor.execute("""
                SELECT sr.reading_id, s.location, s.ap_mac_address, sr.timestamp, sr.rssi, sr.ping, sr.speed, sr.ping_timeout # <-- 컬럼 추가
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
        return jsonify({"status": "error", "message": "DB 오류 발생"}), 500
    
    finally:
        if conn:
            conn.close()

# 데이터 예측 API
# 추후 수정 예정
@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json()

    # 예측에 필요한 필드 확인 (어떤 필드가 필요한지는 모델 설계에 따라 달라짐)
    # 현재는 reading_id를 받아 해당 reading에 대한 예측을 수행하는 것으로 가정
    required_keys = ["reading_id"]
    if not all(k in data for k in required_keys):
        logging.warning(f"예측 요청 필드 누락: {data}")
        return jsonify({"status": "error", "message": "예측에 필요한 'reading_id' 필드가 누락되었습니다."}), 400

    try:
        reading_id = int(data["reading_id"])
    except (ValueError, TypeError):
        logging.warning(f"reading_id 타입 오류: {data['reading_id']}")
        return jsonify({"status": "error", "message": "reading_id는 정수여야 합니다."}), 400

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # reading_id로 해당 측정값 데이터 조회
            cursor.execute("""
                SELECT sr.rssi, sr.ping, sr.speed, s.location, s.ap_mac_address, sr.timestamp
                FROM f_sensor_readings sr
                JOIN f_sensors s ON sr.sensor_id = s.sensor_id
                WHERE sr.reading_id = %s
            """, (reading_id,))
            reading_data = cursor.fetchone()

            if not reading_data:
                logging.error(f"reading_id {reading_id}에 해당하는 데이터 없음.")
                return jsonify({"status": "error", "message": f"reading_id {reading_id}에 해당하는 측정값을 찾을 수 없습니다."}), 404

            # 모델을 사용하여 예측 수행
            # ml_model_interface.py의 함수 호출
            predicted_problem_type = predict_wifi_quality(
                reading_data['rssi'], 
                reading_data['ping'], 
                reading_data['speed'],
                location=reading_data['location'], # 모델에 더 많은 특성 필요 시 전달
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
        return jsonify({
            "status": "success",
            "message": "예측 완료 및 저장",
            "reading_id": reading_id,
            "predicted_problem_type": predicted_problem_type
        })

    except Exception as e:
        logging.exception(f"예측 API 오류 발생 /predict: {e}")
        return jsonify({"status": "error", "message": "예측 처리 중 오류 발생"}), 500
    finally:
        if conn:
            conn.close()

# 서버 실행(테스트 서버용)
if __name__ == "__main__":
    # 개발 환경에서는 디버그 모드 활성화 가능 (운영 환경에서는 비활성화)
    app.run(host="0.0.0.0", port=5000, debug=True) 
