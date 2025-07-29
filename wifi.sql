-- 0. 스키마 생성 및 선택
CREATE DATABASE IF NOT EXISTS wifi_diagnosis_system
DEFAULT CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE wifi_diagnosis_system;

-- 1. 센서 정보 테이블
CREATE TABLE f_sensors (
    sensor_id INT AUTO_INCREMENT PRIMARY KEY,
    location VARCHAR(100) NOT NULL,
    ap_mac_address VARCHAR(17) NOT NULL
);

-- 2. 센서 측정값 테이블
CREATE TABLE f_sensor_readings (
    reading_id INT AUTO_INCREMENT PRIMARY KEY,
    sensor_id INT NOT NULL,
    timestamp DATETIME NOT NULL,
    rssi FLOAT,
    ping FLOAT,
    speed FLOAT,
    ping_timeout BOOLEAN,
    FOREIGN KEY (sensor_id) REFERENCES f_sensors(sensor_id)
        ON DELETE CASCADE ON UPDATE CASCADE
);

-- 3. AI 분석 결과 테이블
CREATE TABLE f_diagnosis_results (
    result_id INT AUTO_INCREMENT PRIMARY KEY,
    reading_id INT NOT NULL,
    diagnosis_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    problem_type ENUM('공유기문제', '통신사백홀문제', '트래픽증가', '정상'),
    FOREIGN KEY (reading_id) REFERENCES f_sensor_readings(reading_id)
        ON DELETE CASCADE ON UPDATE CASCADE
);

-- 4. 관리자 테이블 (이메일 기반 로그인 및 이메일 발송 시각)
CREATE TABLE f_admin_users (
    admin_id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(100) NOT NULL UNIQUE,
    email_sent_time DATETIME
);
