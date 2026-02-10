import scapy.all as scapy
import json
import time
import datetime
import os
import sys
import requests

# 설정 값
DISCORD_WEBHOOK_URL = "YOUR_DISCORD_WEBHOOK_URL"
CONFIG_PATH = "engine/tools/mapping.json"
LOG_DIR = "logs"
DUPE_WINDOW = 30  # 중복 알림 방지 (초)

# 폴더 생성
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

last_sent_raids = {}
raid_mapping = {}
captured_packets = []
last_save_time = time.time()

def load_mapping():
    global raid_mapping
    # 실행 파일 옆의 mapping.json 확인
    if not os.path.exists(CONFIG_PATH):
        print(f"\n[Error] {CONFIG_PATH} 파일이 없습니다.")
        print("프로그램 실행을 위해 mapping.json 파일이 필요합니다.")
        print("3초 뒤 프로그램을 종료합니다...")
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
    """10분 단위로 수집된 모든 패킷 데이터를 파일로 저장"""
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

    segments = payload_hex.split("1d000300")
    
    for seg in segments[1:]:
        if len(seg) > 30: continue 

        # [변경] 단순히 포함 여부가 아니라, 정확한 위치(앞 4자)의 Opcode를 확인
        opcode = seg[0:4] 
        
        found_type = None
        if opcode == "80a0": found_type = "a0"   # 5분 전
        elif opcode == "8080": found_type = "80" # 1분 전
        elif opcode == "f180": found_type = "f1" # 시작
        
        # 만약 위 조건에 해당하지 않으면 (예: 0840, 0880 등) 무시됨
        if found_type:
            data_part = seg[4:]
            if data_part.startswith("0000"):
                potential_id = data_part[4:10]
            else:
                potential_id = data_part[:6]

            if not potential_id: continue

            full_key = f"{found_type}{potential_id}"
            now = time.time()

            if full_key in last_sent_raids and now - last_sent_raids[full_key] < DUPE_WINDOW:
                continue

            timing_info = raid_mapping.get(found_type, {"type": "미등록 단계", "locations": {}})
            location_name = timing_info.get("locations", {}).get(potential_id, f"신규({potential_id})")

            message = (
                f"📢 **[습격 탐지]** {location_name} {timing_info['type']}\n"
                f"- 코드: {found_type} / ID: {potential_id}\n"
                f"- 원본: `1d000300{seg[:20]}`"
            )
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {location_name} 감지")
            send_discord(message)
            last_sent_raids[full_key] = now

        else:
            # 30자 미만의 미식별 시스템 패킷 디버깅용
            debug_msg = (
                f"🔍 **[미확인 소형 패킷]**\n"
                f"- 데이터: `1d000300{seg}`\n"
                f"- 분석: 새로운 패턴일 수 있음"
            )
            print(f"[DEBUG] {debug_msg}")
            send_discord(debug_msg)

def packet_callback(packet):
    global captured_packets, last_save_time

    if packet.haslayer(scapy.Raw):
        payload = packet[scapy.Raw].load
        payload_hex = payload.hex()

        # 1. 파일 저장을 위한 데이터 수집
        pkt_info = {
            "time": datetime.datetime.now().strftime("%H:%M:%S.%f"),
            "src": packet[scapy.IP].src if packet.haslayer(scapy.IP) else "unknown",
            "dst": packet[scapy.IP].dst if packet.haslayer(scapy.IP) else "unknown",
            "size": len(payload),
            "data": payload_hex
        }
        captured_packets.append(pkt_info)

        # 2. 실시간 습격 탐지 로직 실행
        check_raid_notification(payload_hex)

        # 3. 10분(600초)마다 자동 저장
        if time.time() - last_save_time > 600:
            save_to_file()

print("🚀 패킷 분석기 및 데이터 녹화 시작...")
send_discord("🚀 패킷 분석 모니터링 및 녹화 시스템이 시작되었습니다.")
scapy.sniff(filter="tcp", prn=packet_callback, store=0)
