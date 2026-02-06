import datetime
import json
import os
import threading
import time
import requests
import sys  # 추가: sys 모듈 누락 수정
from scapy.all import sniff, Raw, IP

# --- [설정 영역] ---
LOG_DIR = "packet_logs"
START_HOUR = 19
END_HOUR = 2
SAVE_INTERVAL_MIN = 10
DISCORD_WEBHOOK_URL = "YOUR_DISCORD_WEBHOOK_URL"
DUPE_WINDOW = 5  # 중복 방지 (5초)

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# 전역 변수 초기화
last_sent_raids = {}
raid_mapping = {}
current_log_data = []
current_file_label = ""

def get_mapping_path(filename="mapping.json"):
    """경로 우선순위: 1. EXE 외부, 2. EXE 내부(_MEIPASS), 3. 현재 디렉토리"""
    if getattr(sys, 'frozen', False):
        ext_dir = os.path.dirname(sys.executable)
        ext_path = os.path.join(ext_dir, filename)
        if os.path.isfile(ext_path):
            return ext_path

    if hasattr(sys, '_MEIPASS'):
        int_path = os.path.join(sys._MEIPASS, filename)
        if os.path.isfile(int_path):
            return int_path

    return os.path.join(os.getcwd(), filename)

MAPPING_FILE = get_mapping_path("mapping.json")

def load_mapping():
    """매핑 데이터 로드"""
    global raid_mapping
    target_path = MAPPING_FILE if os.path.isfile(MAPPING_FILE) else get_mapping_path("mapping.json")
    try:
        if os.path.exists(target_path):
            with open(target_path, "r", encoding="utf-8") as f:
                raid_mapping = json.load(f)
        return raid_mapping
    except Exception as e:
        print(f"\n[Error] 매핑 파일 읽기 오류: {e}")
        return {}

def send_discord(content):
    if DISCORD_WEBHOOK_URL == "YOUR_DISCORD_WEBHOOK_URL":
        return
    try:
        payload = {"content": f"📢 **[습격 알림]** {content}"}
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
    except Exception as e:
        print(f"\n[Error] 디스코드 발송 실패: {e}")

def is_recording_time():
    now = datetime.datetime.now()
    current_hour = now.hour
    if current_hour >= START_HOUR or current_hour < END_HOUR:
        return True
    return False

def check_raid_notification(payload_hex):
    global last_sent_raids
    
    if "1d000300" in payload_hex:
        idx = payload_hex.find("1d000300")
        opcode_type = payload_hex[idx+8:idx+12]
        location_id = payload_hex[idx+12:idx+18]
        full_key = f"{opcode_type}{location_id}"
        
        # 중복 확인 (full_id -> full_key 변수명 수정)
        now = time.time()
        if full_key in last_sent_raids and now - last_sent_raids[full_key] < DUPE_WINDOW:
            return

        load_mapping() # 실시간 업데이트 반영
        
        timing_info = raid_mapping.get(opcode_type, {"type": "미식별 타이밍", "locations": {}})
        location_name = timing_info["locations"].get(location_id, f"미식별({location_id})")
        
        message = f"{location_name} {timing_info['type']}"
        print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] {message}")
        send_discord(message)
        
        last_sent_raids[full_key] = now

def save_to_file(data_to_save, label):
    if not data_to_save: return
    filename = f"recon_{label}.json"
    filepath = os.path.join(LOG_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=2)
    print(f"\n[{datetime.datetime.now()}] 저장 완료: {filename}")

def packet_callback(packet):
    global current_log_data, current_file_label

    if packet.haslayer(Raw) and packet.haslayer(IP):
        # 1. IP 필터링 (한 번만 수행)
        if not (packet[IP].dst.startswith("119.205.203") or packet[IP].src.startswith("119.205.203")):
            return

        now = datetime.datetime.now()
        payload_hex = packet[Raw].load.hex()

        # 2. 실시간 습격 탐지 (녹화 시간 상관없이 항상 실행)
        check_raid_notification(payload_hex)
    
        # 3. 녹화 시간 체크 및 데이터 저장
        if not is_recording_time():
            if current_log_data:
                temp_data, temp_label = current_log_data[:], current_file_label
                current_log_data, current_file_label = [], ""
                threading.Thread(target=save_to_file, args=(temp_data, temp_label)).start()
            return

        # 4. 10분 단위 파일 교체 로직
        file_label = now.strftime("%Y%m%d_%H") + str((now.minute // SAVE_INTERVAL_MIN) * SAVE_INTERVAL_MIN).zfill(2)
        if current_file_label != "" and current_file_label != file_label:
            temp_data, temp_label = current_log_data[:], current_file_label
            current_log_data = []
            threading.Thread(target=save_to_file, args=(temp_data, temp_label)).start()

        current_file_label = file_label
        current_log_data.append({
            "time": now.strftime('%H:%M:%S.%f'),
            "src": packet[IP].src,
            "dst": packet[IP].dst,
            "size": len(packet[Raw].load),
            "data": payload_hex
        })

def monitor_status():
    while True:
        status = "● 녹화 중" if is_recording_time() else "○ 대기 중"
        print(f"\r현재 시간: {datetime.datetime.now().strftime('%H:%M:%S')} | 상태: {status}", end="")
        time.sleep(1)

if __name__ == "__main__":
    print(f"패킷 분석기 및 알람 시작 ({START_HOUR}:00 ~ {END_HOUR}:00)")
    threading.Thread(target=monitor_status, daemon=True).start()
    try:
        sniff(prn=packet_callback, store=0)
    except KeyboardInterrupt:
        if current_log_data:
            save_to_file(current_log_data, current_file_label)
        print("\n프로그램을 종료합니다.")
