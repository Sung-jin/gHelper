import scapy.all as scapy
import datetime
import sys
import os
import time
from utils import ConfigManager, Notifier
from recording import PacketRecorder

# 초기 설정 (Secret 주입은 Git Actions에서 처리됨)
DEFAULT_WEBHOOK_URL = "YOUR_DISCORD_WEBHOOK_URL"
ConfigManager.init_app_config("mapping.json", DEFAULT_WEBHOOK_URL)

recorder = PacketRecorder(
    start_hour=19, 
    end_hour=2, 
    interval_min=10, 
    log_dir=os.path.join(ConfigManager.get_base_path(), "logs")
)
notifier = Notifier()
raid_mapping = ConfigManager.get_global("raid_mapping", {})

# 쿨타임 관리를 위한 딕셔너리 {(key, loc_id): last_sent_time}
alert_cooldowns = {}
COOLDOWN_SECONDS = 60

def packet_callback(packet):
    if not packet.haslayer(scapy.Raw):
        return

    try:
        payload_hex = packet[scapy.Raw].load.hex()
        recorder.add_entry({
            "t": datetime.datetime.now().strftime("%H:%M:%S.%f"),
            "d": payload_hex
        })

        # 구조적 정밀 탐색 (Header 1d000300)
        header_idx = payload_hex.find("1d000300")
        if header_idx == -1: return

        # Key(단계) 확인 (Header로부터 16자 뒤)
        key_pos = header_idx + 16
        detected_key = None
        for key in raid_mapping.keys():
            if payload_hex.startswith(key, key_pos):
                detected_key = key
                break

        if detected_key:
            # ID 추출 (Key 이후 데이터 영역에서 6자리 탐색)
            # 보통 Key 뒤에 0000 패딩 이후 위치하므로 범위를 지정하여 탐색
            search_area = payload_hex[key_pos + 4 : key_pos + 44]

            known_locations = raid_mapping[detected_key].get("locations", {})
            found_loc_id = None
            found_loc_name = "미식별 장소"

            # 등록된 ID 우선 확인
            for loc_id, loc_name in known_locations.items():
                if loc_id in search_area:
                    found_loc_id = loc_id
                    found_loc_name = loc_name
                    break

            # 등록되지 않은 경우, search_area에서 0000이 아닌 첫 6자리 후보 추출
            if not found_loc_id:
                # 0000을 제외한 유의미한 6자리 추출
                cleaned_area = search_area.replace("0000", "")
                if len(cleaned_area) >= 6:
                    found_loc_id = cleaned_area[:6]

            # 5. 쿨타임 체크 (Key + ID 조합)
            if found_loc_id:
                current_time = time.time()
                cooldown_key = (detected_key, found_loc_id)
                last_sent = alert_cooldowns.get(cooldown_key, 0)

                if current_time - last_sent > COOLDOWN_SECONDS:
                    status_type = raid_mapping[detected_key]["type"]

                    if found_loc_name != "미식별 장소":
                        msg = f"🚨 [습격 감지] {found_loc_name} ({status_type})"
                    else:
                        msg = f"❓ [미식별 습격] 새로운 ID 포착! ({status_type})\nID 후보: {found_loc_id}"

                    print(f"[*] {datetime.datetime.now()} - {msg}")
                    notifier.send_discord(msg)

                    # 쿨타임 업데이트
                    alert_cooldowns[cooldown_key] = current_time

    except Exception:
        pass

if __name__ == "__main__":
    print("="*50)
    print("  Raid Detection & Recording System v3.0")
    print(f"  Monitoring: {recorder.start_hour}:00 ~ {recorder.end_hour}:00")
    print("="*50)

    recorder.start_monitoring_thread()

    try:
        scapy.sniff(filter="tcp", prn=packet_callback, store=0)
    except KeyboardInterrupt:
        recorder.save_to_file() # 종료 전 남은 데이터 저장
        print("\n[!] 종료합니다.")
        sys.exit(0)
