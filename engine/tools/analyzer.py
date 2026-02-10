import scapy.all as scapy
import json
import time
import datetime
import os
import sys
import requests

# ==========================================
# 설정 값
# ==========================================
DISCORD_WEBHOOK_URL = "YOUR_DISCORD_WEBHOOK_URL"
CONFIG_PATH = "engine/tools/mapping.json"
LOG_DIR = "logs"
DUPE_WINDOW = 30  # 중복 알림 방지 (초)

# 녹화 및 탐지 활성화 시간 (19시 ~ 익일 02시)
START_HOUR = 19
END_HOUR = 2

# 폴더 생성
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

last_sent_raids = {}
raid_mapping = {}
captured_packets = []
last_save_time = time.time()

def is_active_time():
    """현재 시간이 분석 활성화 시간대인지 확인"""
    now = datetime.datetime.now().hour
    if START_HOUR <= now or now < END_HOUR:
        return True
    return False

def load_mapping():
    global raid_mapping
    if not os.path.exists(CONFIG_PATH):
        print(f"\n[Error] {CONFIG_PATH} 파일이 없습니다. 3초 뒤 종료...")
        time.sleep(3)
        sys.exit(1)
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            raid_mapping = json.load(f)
    except Exception as e:
        print(f"[Error] mapping.json 읽기 실패: {e}")
        sys.exit(1)

def send_discord(message):
    if DISCORD_WEBHOOK_URL.startswith("http"):
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": message})
        except Exception as e:
            print(f"디스코드 전송 실패: {e}")

def save_to_file():
    global captured_packets, last_save_time
    if not captured_packets:
        last_save_time = time.time()
        return

    label = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"recon_{label}.json"
    filepath = os.path.join(LOG_DIR, filename)

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(captured_packets, f, ensure_ascii=False, indent=2)
        print(f"\n[{datetime.datetime.now()}] 전체 로그 저장 완료: {filename}")
    except Exception as e:
        print(f"파일 저장 에러: {e}")

    captured_packets = []
    last_save_time = time.time()

def check_raid_notification(payload_hex):
    global last_sent_raids, raid_mapping
    load_mapping()

    # 시스템 코드(1d000300) 단위로 분할
    segments = payload_hex.split("1d000300")
    
    for seg in segments[1:]:
        # [Strict] 습격 패킷은 보통 22자(11바이트). 
        # 오늘 확인된 노이즈들과 차별화하기 위해 길이를 더 타이트하게 제한 가능.
        if len(seg) > 26: continue 

        opcode = seg[0:4]
        found_type = None
        
        # [Strict] 오늘 노이즈로 판명된 80a0, 8080은 제외하고 
        # 과거에 실제 습격으로 의심되었던 83계열이나 f1계열만 필터링
        if opcode == "83a0": found_type = "a0"
        elif opcode == "8380": found_type = "80"
        elif opcode == "f180": found_type = "f1"
        
        if found_type:
            data_part = seg[4:]
            if data_part.startswith("0000"):
                potential_id = data_part[4:10]
            else:
                potential_id = data_part[:6]

            full_key = f"{found_type}{potential_id}"
            now = time.time()

            if full_key in last_sent_raids and now - last_sent_raids[full_key] < DUPE_WINDOW:
                continue

            timing_info = raid_mapping.get(found_type, {"type": "미등록 단계", "locations": {}})
            location_name = timing_info.get("locations", {}).get(potential_id, f"신규({potential_id})")

            message = (
                f"📢 **[습격 탐지]** {location_name} {timing_info['type']}\n"
                f"- 코드: {found_type} / ID: {potential_id}\n"
                f"- 원본: `1d000300{seg[:22]}`"
            )
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {location_name} 감지!")
            send_discord(message)
            last_sent_raids[full_key] = now
        else:
            # 30자 미만인데 우리가 정한 엄격한 opcode(83a0 등)에 안 걸리는 패킷들
            # 오늘처럼 노이즈가 많을 때는 디스코드 대신 터미널에만 출력하여 모니터링
            if len(seg) <= 22:
                print(f"[Skip] 노이즈 혹은 미식별: 1d000300{seg}")

def packet_callback(packet):
    global captured_packets, last_save_time

    if not is_active_time():
        # 활성화 시간대가 아니면 아무것도 하지 않음 (리소스 절약)
        return

    if packet.haslayer(scapy.Raw):
        payload = packet[scapy.Raw].load
        payload_hex = payload.hex()

        # 1. 파일 저장을 위한 데이터 수집
        pkt_info = {
            "time": datetime.datetime.now().strftime("%H:%M:%S.%f"),
            "data": payload_hex
        }
        captured_packets.append(pkt_info)

        # 2. 실시간 탐지 실행
        check_raid_notification(payload_hex)

        # 3. 10분마다 혹은 데이터가 많이 쌓이면 저장
        if time.time() - last_save_time > 600 or len(captured_packets) > 5000:
            save_to_file()

print(f"🚀 분석기 시작 (활성 시간: {START_HOUR}시~{END_HOUR}시)")
send_discord(f"🚀 패킷 분석 및 {START_HOUR}시~{END_HOUR}시 녹화 시스템 시작")

try:
    scapy.sniff(filter="tcp", prn=packet_callback, store=0)
except KeyboardInterrupt:
    print("\n정지 요청 감지. 남은 데이터를 저장합니다...")
    save_to_file()
    sys.exit(0)
