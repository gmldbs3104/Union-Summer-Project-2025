import logging

# 로깅 설정 (app.py와 동일하게 설정)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 전역 변수로 모델을 저장할 변수 선언
_model = None 

def load_model():
    """
    모델을 로드하는 함수.
    현재는 더미 모델 로딩을 흉내내지만, 실제 모델 파일 (.pkl, .joblib 등)을 로드하도록 수정됩니다.
    """
    global _model
    if _model is None:
        try:
            # TODO: 실제 모델 로딩 코드 추가 (예: joblib.load('your_model.pkl'))
            # 현재는 단순히 "더미 모델 로드됨"을 흉내냅니다.
            _model = "dummy_random_forest_model" 
            logging.info("더미 예측 모델을 로드했습니다.")
        except Exception as e:
            logging.error(f"모델 로드 중 오류 발생: {e}")
            _model = None # 모델 로드 실패 시 None으로 설정
    return _model

def predict_wifi_quality(rssi, ping, speed, location=None, ap_mac_address=None, timestamp=None):
    """
    주어진 데이터를 바탕으로 와이파이 품질 문제를 예측하는 함수.
    실제 모델이 통합되면 이 함수는 로드된 모델을 사용하여 예측을 수행합니다.
    """
    model = load_model()
    if model is None:
        logging.error("예측 모델이 로드되지 않았습니다. 더미 예측을 사용합니다.")
        return dummy_predict_logic(rssi, ping, speed) # 모델 로드 실패 시 더미 로직 사용
    
    # TODO: 실제 모델을 사용하여 예측하는 코드 구현
    # 예시:
    # features = [[rssi, ping, speed, ...]] # 모델 입력에 맞게 특성 배열 생성
    # prediction = model.predict(features)[0] 
    # return map_prediction_to_problem_type(prediction) # 모델 출력값을 문제 유형으로 매핑
    
    # 현재는 모델이 없으므로 더미 로직을 반환
    logging.info(f"모델({model})을 사용하여 예측 중 (더미): RSSI={rssi}, Ping={ping}, Speed={speed}")
    return dummy_predict_logic(rssi, ping, speed)


def dummy_predict_logic(rssi, ping, speed):
    """
    모델이 없을 때 예측을 흉내내는 더미 로직.
    실제 모델이 준비되면 이 함수는 삭제되거나, 실제 모델의 예측 로직으로 대체됩니다.
    """
    if rssi < -80 and ping > 100:
        return "전파간섭"
    elif speed < 5 and ping > 50:
        return "통신사백홀문제"
    elif rssi > -50 and ping < 20 and speed > 10:
        return "정상"
    else:
        return "공유기문제" # 임의의 기본값

# 이 파일이 임포트될 때 모델을 미리 로드하도록 호출
# 앱이 시작될 때 한 번만 로드되도록 합니다.
load_model()