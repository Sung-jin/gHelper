import scapy.all as scapy
import datetime
import sys
import os
import time
import re
from utils import ConfigManager, Notifier
from recording import PacketRecorder

# 초기 설정
DEFAULT_WEBHOOK_URL = "YOUR_DISCORD_WEBHOOK_URL"
ConfigManager.init_app_config("mapping.json", DEFAULT_WEBHOOK_URL)

recorder = PacketRecorder(
    start_hour=0,
    end_hour=24,
    interval_min=10,
    log_dir=os.path.join(ConfigManager.get_base_path(), "logs")
)
notifier = Notifier()
raid_mapping = ConfigManager.get_global("raid_mapping", {})

# [전역 상태 관리]
pending_payload = ""
alert_cooldowns = {}  # { (detected_key, found_id): timestamp }

# [상수 설정]
COOLDOWN = 180               # 동일 장소/동일 단계 알림 중복 방지 (3분)
MIN_RAID_PACKET_SIZE = 100   # 습격 패킷 최소 길이 기준
EVENT_PREFIX = "01000000"    # 전역 이벤트 선언 접두어

def process_complete_block(block_hex):
    global alert_cooldowns

    # 1. 습격 단계 키 탐색 (80a0, 8080, f180)
    detected_key = next((k for k in raid_mapping.keys() if k in block_hex), None)
    if not detected_key:
        return

    # 2. 이벤트 선언 접두어 패턴 검증 (접두어와 키 사이 가변 바이트 허용)
    pattern = f"{EVENT_PREFIX}.{{2,64}}{detected_key}"
    if not re.search(pattern, block_hex):
        return

    # 3. 장소 ID 탐색 (키 근처 오프셋 범위 내 검색)
    known_locs = raid_mapping[detected_key].get("locations", {})
    key_index = block_hex.find(detected_key)
    search_area = block_hex[key_index:key_index + 100] # 키 이후 50바이트 내 조사

    found_id = next((loc_id for loc_id in known_locs.keys() if loc_id in search_area), None)
    if not found_id:
        return

    # 4. 조합형 쿨다운 검증 (멀티 클라이언트 중복 방지)
    current_time = time.time()
    cooldown_key = (detected_key, found_id)

    if current_time - alert_cooldowns.get(cooldown_key, 0) > COOLDOWN:
        loc_name = known_locs.get(found_id)
        type_name = raid_mapping[detected_key].get("type", "알 수 없는 단계")

        # 디스코드 즉시 알림 발송
        notifier.send_discord(f"🚨 [{type_name}] {loc_name}")

        alert_cooldowns[cooldown_key] = current_time

def packet_callback(packet):
    global pending_payload

    if not packet.haslayer(scapy.Raw):
        return

    try:
        current_payload = packet[scapy.Raw].load.hex()
        pending_payload += current_payload

        # 데이터 기록
        recorder.add_entry({"t": datetime.datetime.now().strftime("%H:%M:%S.%f"), "d": current_payload})

        while len(pending_payload) >= 8:
            # 1d00 헤더 탐색
            start_idx = pending_payload.find("1d00")
            if start_idx == -1:
                pending_payload = ""
                break

            pending_payload = pending_payload[start_idx:]
            if len(pending_payload) < 8: break

            # 길이 정보 추출 (Little-endian)
            len_hex = pending_payload[4:8]
            payload_len = int(len_hex[2:4] + len_hex[0:2], 16)

            # 전처리: 습격 가능성이 없는 짧은 길이는 즉시 스킵
            if payload_len < MIN_RAID_PACKET_SIZE:
                pending_payload = pending_payload[4:] # 헤더 이후부터 다시 탐색
                continue

            total_block_chars = (4 + payload_len) * 2

            if len(pending_payload) >= total_block_chars:
                complete_block = pending_payload[:total_block_chars]
                process_complete_block(complete_block)
                pending_payload = pending_payload[total_block_chars:]
            else:
                break

    except Exception:
        pass

if __name__ == "__main__":
    print("="*50)
    print("  Raid Analytics System v4.0")
    print(f"  Monitoring 24H: {recorder.start_hour} - {recorder.end_hour}")
    print("="*50)

    recorder.start_monitoring_thread()

    try:
        scapy.sniff(filter="tcp", prn=packet_callback, store=0)
    except KeyboardInterrupt:
        recorder.save_to_file()
        sys.exit(0)