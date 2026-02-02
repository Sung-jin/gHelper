import datetime
import json
import os
import threading
import time
from scapy.all import sniff, Raw, IP

# --- [설정 영역] ---
LOG_DIR = "packet_logs"
START_HOUR = 19  # 오후 7시 시작
END_HOUR = 2     # 다음날 오전 2시 종료 (26시)
SAVE_INTERVAL_MIN = 10 # 10분 단위 저장

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

current_log_data = []
current_file_label = ""

def is_recording_time():
    """현재 시간이 녹화 범위 내에 있는지 확인 (19:00 ~ 02:00)"""
    now = datetime.datetime.now()
    current_hour = now.hour
    
    # 19시 이후이거나 02시 이전인 경우
    if current_hour >= START_HOUR or current_hour < END_HOUR:
        return True
    return False

def save_to_file(data_to_save, label):
    """데이터를 JSON 파일로 저장"""
    if not data_to_save:
        return
    
    filename = f"recon_{label}.json"
    filepath = os.path.join(LOG_DIR, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=2)
    
    print(f"[{datetime.datetime.now()}] 저장 완료: {filename} ({len(data_to_save)} 패킷)")

def packet_callback(packet):
    global current_log_data, current_file_label
    
    # 1. 녹화 시간대가 아니면 무시
    if not is_recording_time():
        if current_log_data: # 녹화 시간대가 끝나면 남은 데이터 저장
            temp_data = current_log_data[:]
            temp_label = current_file_label
            current_log_data = []
            threading.Thread(target=save_to_file, args=(temp_data, temp_label)).start()
        return

    # 2. 패킷 유효성 검사 (IP 대역 필터)
    if packet.haslayer(Raw) and packet.haslayer(IP):
        if not (packet[IP].dst.startswith("119.205.203") or packet[IP].src.startswith("119.205.203")):
            return

        now = datetime.datetime.now()
        # 10분 단위 레이블 생성 (예: 20260203_1910)
        file_label = now.strftime("%Y%m%d_%H") + str((now.minute // SAVE_INTERVAL_MIN) * SAVE_INTERVAL_MIN).zfill(2)

        # 3. 10분이 지나서 레이블이 바뀌면 파일 저장
        if current_file_label != "" and current_file_label != file_label:
            temp_data = current_log_data[:]
            temp_label = current_file_label
            current_log_data = []
            threading.Thread(target=save_to_file, args=(temp_data, temp_label)).start()

        current_file_label = file_label
        
        payload = packet[Raw].load
        entry = {
            "time": now.strftime('%H:%M:%S.%f'),
            "src": packet[IP].src,
            "dst": packet[IP].dst,
            "size": len(payload),
            "data": payload.hex()
        }
        current_log_data.append(entry)

def monitor_status():
    """현재 상태를 콘솔에 표시하는 모니터링 스레드"""
    while True:
        status = "● 녹화 중" if is_recording_time() else "○ 대기 중 (19:00 시작)"
        print(f"\r현재 시간: {datetime.datetime.now().strftime('%H:%M:%S')} | 상태: {status}", end="")
        time.sleep(1)

if __name__ == "__main__":
    print(f"패킷 자동 예약 로거 시작 ({START_HOUR}:00 ~ {END_HOUR}:00)")
    threading.Thread(target=monitor_status, daemon=True).start()
    
    try:
        # sniff 실행 (필터 없이 모든 패킷 감시)
        sniff(prn=packet_callback, store=0)
    except KeyboardInterrupt:
        if current_log_data:
            save_to_file(current_log_data, current_file_label)
        print("\n프로그램을 종료합니다.")
