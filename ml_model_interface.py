import joblib
import pandas as pd
import os
import logging
from functools import lru_cache

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class MLModelInterface:
    def __init__(self):
        # 🔽 경로 설정 (상대경로 → 절대경로로 수정 가능)
        model_dir = "models"
        model_path = os.path.join(model_dir, 'random_forest_model.joblib')
        feature_cols_path = os.path.join(model_dir, 'feature_columns.joblib')

        if not os.path.exists(model_path) or not os.path.exists(feature_cols_path):
            raise FileNotFoundError("❌ 모델 파일을 찾을 수 없습니다. train_and_save_model.py를 먼저 실행하세요.")

        self.model = joblib.load(model_path)
        self.feature_columns = joblib.load(feature_cols_path)
        logging.info(f"✅ 머신러닝 모델이 성공적으로 로드되었습니다. 예상 피처: {self.feature_columns}")

    def predict(self, new_data_dict):
        new_data_df = pd.DataFrame([new_data_dict])

        # 누락된 피처 확인
        missing_cols = set(self.feature_columns) - set(new_data_df.columns)
        if missing_cols:
            raise ValueError(f"입력 데이터에 필수 피처가 누락되었습니다: {list(missing_cols)}")

        # 피처 순서 정렬
        preprocessed_data = new_data_df[self.feature_columns]
        prediction = self.model.predict(preprocessed_data)

        return prediction[0]

# 모델 인스턴스 싱글톤 캐싱
try:
    _model_interface = MLModelInterface()
except FileNotFoundError as e:
    logging.error(e)
    _model_interface = None

@lru_cache(maxsize=1)
def get_model_interface():
    return _model_interface

def predict_wifi_quality(rssi, speed, ping, timeout, **kwargs):
    model_interface = get_model_interface()

    if model_interface is None:
        logging.error("예측 모델이 로드되지 않았습니다. 더미 예측을 사용합니다.")
        if rssi < -80 and ping > 100:
            return "트래픽증가"
        elif speed < 5 and ping > 50:
            return "통신사백홀문제"
        elif rssi > -50 and ping < 20 and speed > 10:
            return "정상"
        else:
            return "공유기문제"

    features = {
        'rssi': rssi,
        'speed': speed,
        'ping': ping,
        'timeout': timeout
    }

    try:
        prediction = model_interface.predict(features)
        return prediction
    except Exception as e:
        logging.error(f"예측 중 오류 발생: {e}")
        return "예측_오류"

get_model_interface()