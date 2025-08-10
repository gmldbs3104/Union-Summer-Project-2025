# Wivue 위뷰

## 💡 프로젝트 개요
<br>
본 프로젝트는 교내 와이파이 품질 문제의 근본적인 해결을 목표로 하는 **AI 기반 와이파이 장애 진단 및 대응 지원 시스템**입니다. 


## ⚙️ 주요 기능
<br>

### AI 기반 장애 진단
- 머신러닝 모델을 통해 와이파이 속도, 신호 강도, 핑 테스트 데이터를 분석하여 장애 원인을 진단합니다.

### 실시간 알림
- 장애 발생 시 Slack 웹훅을 통해 사전에 설정된 채널로 알림을 전송합니다.
- 알림에는 센서 ID, 위치, 장애 원인, 발생 시각 등의 정보가 포함됩니다.

### 데이터 수집 및 관리
- 라즈베리파이 센서가 네트워크 데이터를 측정하고, 이 데이터는 MySQL 데이터베이스에 저장됩니다.


### 🛠️ 기술 스택
<br>
- Hardware: Raspberry Pi 5 
- Machine Learning: NumPy, Pandas, Scikit-learn 
- Database: MySQL 
- Server: Flask, Amazon EC2, Nginx, Gunicorn 
- Notification System: Slack Webhook 


### 🧑‍💻 팀원 소개
<br>
김영모: 컴퓨터공학전공, 머신러닝

박재현: 전자전기공학부, 하드웨어

박재홍: 컴퓨터공학전공, 머신러닝

주희윤: 컴퓨터공학전공, PM, 백엔드

차영준: 컴퓨터공학전공, DB, 서버
