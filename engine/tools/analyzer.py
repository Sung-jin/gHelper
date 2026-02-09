import datetime
import json
import os
import threading
import time
import requests
import sys
from scapy.all import sniff, Raw, IP

# --- [설정 영역] ---
LOG_DIR = "packet_logs"
START_HOUR = 19
END_HOUR = 2
SAVE_INTERVAL_MIN = 10
DISCORD_WEBHOOK_URL = "YOUR_DISCORD_WEBHOOK_URL"
DUPE_WINDOW = 5

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# 전역 변수 초기화
last_sent_raids = {}
raid_mapping = {}
current_log_data = []
current_file_label = ""

def send_startup_notification():
    """앱 시작 시 URL 유효성 확인용 알림"""
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    msg = f"🚀 **패킷 분석기 모니터링 시작!**\n- 시작 시간: {now_str}\n- 대상 대역: 119.205.203.x"

    if "YOUR_DISCORD_WEBHOOK_URL" in DISCORD_WEBHOOK_URL:
        print("\n[Warning] Webhook URL이 치환되지 않았습니다. 빌드 설정을 확인하세요.")
    else:
        send_discord(msg)
        print("\n[*] 시작 알림을 디스코드로 전송했습니다.")

def get_mapping_path(filename="mapping.json"):
    """경로 우선순위: 1. EXE 외부, 2. EXE 내부(_MEIPASS), 3. 현재 디렉토리"""
    if getattr(sys, 'frozen', False):
        ext_path = os.path.join(os.path.dirname(sys.executable), filename)
        if os.path.isfile(ext_path): return ext_path
    if hasattr(sys, '_MEIPASS'):
        int_path = os.path.join(sys._MEIPASS, filename)
        if os.path.isfile(int_path): return int_path
    return os.path.join(os.getcwd(), filename)

MAPPING_FILE = get_mapping_path("mapping.json")

def load_mapping():
    global raid_mapping
    try:
        if os.path.exists(MAPPING_FILE):
            with open(MAPPING_FILE, "r", encoding="utf-8") as f:
                raid_mapping = json.load(f)
        return raid_mapping
    except Exception as e:
        return {}

def send_discord(content):
    if "YOUR_DISCORD_WEBHOOK_URL" in DISCORD_WEBHOOK_URL: return
    try:
        payload = {"content": content}
        # 전송 결과 확인을 위해 response 로그 추가
        resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
        if resp.status_code != 204:
            print(f"\n[Error] Discord 전송 실패 (Status: {resp.status_code})")
    except Exception as e:
        print(f"\n[Error] 디스코드 발송 예외 발생: {e}")

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

        load_mapping()

        # 2. [개선] JSON 파일에 존재하는 Opcode인 경우에만 로직 수행
        # 하드코딩된 리스트 대신 raid_mapping의 키값을 직접 확인합니다.
        if opcode_type in raid_mapping:
            now = time.time()
            # 중복 방지 체크
            if full_key in last_sent_raids and now - last_sent_raids[full_key] < DUPE_WINDOW:
                return

            timing_info = raid_mapping[opcode_type]
            location_name = timing_info["locations"].get(location_id, f"미식별({location_id})")

            # 알림 발송
            message = f"📢 **[습격 알림]** {location_name} {timing_info['type']}"
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

    # [수정] 실행 직후 디스코드 알림 테스트
    send_startup_notification()

    threading.Thread(target=monitor_status, daemon=True).start()
    try:
        sniff(prn=packet_callback, store=0)
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")
