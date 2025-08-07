# File 1: train_and_save_model.py
# 이 스크립트는 모델을 학습하고 정확도를 계산한 후, 모델을 저장합니다.
# 이 파일을 한 번 실행하여 'models' 디렉터리 내에 모델 파일을 생성해야 합니다.
#
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split # 데이터 분할을 위해 추가
from sklearn.metrics import accuracy_score          # 정확도 계산을 위해 추가
from sklearn.preprocessing import OrdinalEncoder
import joblib
import os

print("모델 학습 및 저장 프로세스를 시작합니다...")

# --- 1. 엑셀 파일에서 데이터 불러오기 ---
# TODO: 아래 변수 값을 실제 엑셀 파일 경로로 수정하세요.
excel_file_path = 'C:/Users/kimze/OneDrive/동국대학교/동아리/FarmSystem/Union-Summer-Project-2025/wifi_classification_dummy_data_with_rssi.xlsx' # 사용자 경로로 업데이트

try:
    # pandas를 사용하여 엑셀 파일 불러오기
    df_train = pd.read_excel(excel_file_path)
    print(f"✅ 엑셀 파일 '{excel_file_path}'에서 데이터 로드 성공.")

    # 모델 학습에 사용할 실제 컬럼명 리스트
    # 엑셀 파일의 컬럼명에 맞춰 'issue_type'을 라벨로,
    # 'rssi', 'avg_d_kbps', 'avg_lat_ms', 'timeout'을 피처로 사용합니다.
    expected_columns = ['rssi', 'avg_d_kbps', 'avg_lat_ms', 'timeout', 'issue_type']

    if not all(col in df_train.columns for col in expected_columns):
        print("⚠️ 경고: 엑셀 파일의 컬럼명에 모델 학습에 필요한 컬럼 중 누락된 것이 있습니다.")
        print(f"필요한 컬럼: {expected_columns}")
        print(f"파일의 실제 컬럼: {df_train.columns.tolist()}")
        print("코드가 정상적으로 작동하려면 엑셀 파일의 컬럼명이 일치해야 합니다.")
        # 누락된 컬럼이 있으면 강제로 오류 발생시켜 사용자에게 알림
        raise ValueError("필수 엑셀 컬럼이 누락되었습니다. 엑셀 파일을 확인하세요.")

except FileNotFoundError:
    print(f"❌ 오류: 지정된 엑셀 파일 '{excel_file_path}'을(를) 찾을 수 없습니다.")
    print("파일 경로를 올바르게 설정했는지 확인하고 다시 시도하세요.")
    # 파일이 없는 경우 더미 데이터를 사용하여 계속 진행
    print("⚠️ 오류를 방지하기 위해 더미 데이터를 사용하여 학습을 진행합니다.")
    n_samples = 5000
    data = {
        'rssi': np.random.randint(-100, -30, size=n_samples),
        'avg_d_kbps': np.random.uniform(1, 100, size=n_samples), # 'speed' 대신
        'avg_lat_ms': np.random.randint(5, 500, size=n_samples),  # 'ping' 대신
        'timeout': np.random.choice([True, False], size=n_samples), # 'ping_timeout' 대신
        'issue_type': np.random.choice(['정상', '트래픽증가', '통신사백홀문제', '공유기문제'], size=n_samples) # 'problem_type' 대신
    }
    df_train = pd.DataFrame(data)
except ValueError as e:
    print(f"❌ 오류: {e}")
    print("모델 학습을 중단합니다.")
    exit() # 필수 컬럼 누락 시 스크립트 종료

# --- 2. 피처/라벨 분리 및 데이터 분할 ---
# 라벨 컬럼을 'issue_type'으로 변경
y = df_train['issue_type']
# 라벨 컬럼을 제외한 모든 피처를 사용하거나, 특정 피처만 선택할 수 있습니다.
# 여기서는 엑셀 파일에 있는 피처 중 모델 학습에 사용할 피처를 명시적으로 선택합니다.
model_features = ['rssi', 'avg_d_kbps', 'avg_lat_ms', 'timeout']
X_encoded = df_train[model_features].copy()

# 데이터를 훈련 세트와 테스트 세트로 분할 (80% 훈련, 20% 테스트)
X_train, X_test, y_train, y_test = train_test_split(X_encoded, y, test_size=0.2, random_state=42)

print("✅ 데이터 준비 완료. 훈련 데이터: {}, 테스트 데이터: {}".format(X_train.shape, X_test.shape))

# --- 3. 모델 학습 및 평가 ---
clf = RandomForestClassifier(random_state=42)
clf.fit(X_train, y_train)

print("✅ 모델 학습 완료.")

# 테스트 데이터로 예측
y_pred = clf.predict(X_test)

# 정확도 계산 및 출력
accuracy = accuracy_score(y_test, y_pred)
print(f"✅ 모델 정확도: {accuracy:.4f}")

# --- 4. 학습된 모델 저장 ---
# 모델용 디렉터리가 없으면 생성
model_dir = "models"
if not os.path.exists(model_dir):
    os.makedirs(model_dir)

model_path = os.path.join(model_dir, 'random_forest_model.joblib')
feature_cols_path = os.path.join(model_dir, 'feature_columns.joblib')

joblib.dump(clf, model_path)
# 모델이 학습된 피처 컬럼 이름을 저장하여 예측 시 일관성을 유지합니다.
joblib.dump(model_features, feature_cols_path) # X_encoded.columns.tolist() 대신 model_features 사용

print(f"✅ 모델이 다음 경로에 저장되었습니다: {model_path}")
print(f"✅ 피처 열이 다음 경로에 저장되었습니다: {feature_cols_path}")

print("--------------------------------------------------")
print("이제 app.py를 실행하여 Flask 서버를 시작하세요.")
print("--------------------------------------------------")
