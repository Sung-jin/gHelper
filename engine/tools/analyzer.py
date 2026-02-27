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
        # 원본 로그 기록
        recorder.add_entry({"t": datetime.datetime.now().strftime("%H:%M:%S.%f"), "d": payload_hex})

        # 1. '1d000300' (시스템 메시지 시작) 단위로 전체 패킷 분할
        chunks = payload_hex.split("1d000300")

        for chunk in chunks[1:]: # 첫 번째 분할물은 헤더 이전 데이터이므로 제외

            # 2. 메시지 타입 지문(Fingerprint) 검증
            if not (chunk.startswith("cb80") or chunk.startswith("cba0")):
                continue

            # 3. 메시지 유효 범위 확정
            # 1d000300 이후 다음 시스템 메시지(1d00)가 나오기 전까지만 실제 습격 데이터
            actual_content = chunk.split("1d00")[0]

            # 4. 단계(Key) 확인 (80a0, 8080, f180 등)
            detected_key = next((k for k in raid_mapping.keys() if k in actual_content), None)
            if not detected_key:
                continue

            # 5. 장소 ID 확인 (mapping.json 기반)
            known_locations = raid_mapping[detected_key].get("locations", {})
            found_id = None
            found_name = "미식별 장소"

            for loc_id, loc_name in known_locations.items():
                if loc_id in actual_content:
                    found_id = loc_id
                    found_name = loc_name
                    break

            # 6. 미식별 습격 처리
            if not found_id:
                # 0000 패딩을 제외한 유의미한 6자리 후보 추출
                candidates = [actual_content[i:i+6] for i in range(0, len(actual_content)-6, 2)
                              if actual_content[i:i+6] != "000000" and not actual_content[i:i+6].startswith("00")]
                if candidates:
                    found_id = candidates[0]

            # 7. 쿨타임 적용 및 최종 알림
            if found_id:
                current_time = time.time()
                cooldown_key = (detected_key, found_id)

                if current_time - alert_cooldowns.get(cooldown_key, 0) > COOLDOWN_SECONDS:
                    status_type = raid_mapping[detected_key]["type"]
                    if found_name != "미식별 장소":
                        msg = f"🚨 [습격 감지] {found_name} ({status_type})"
                    else:
                        msg = f"❓ [미식별 습격] 신규 ID 포착! ({status_type})\n추출 ID: {found_id}"

                    print(f"[*] {datetime.datetime.now()} - {msg}")
                    notifier.send_discord(msg)
                    alert_cooldowns[cooldown_key] = current_time

    except Exception:
        pass

if __name__ == "__main__":
    print("="*50)
    print("  Raid Detection & Recording System v3.1")
    print(f"  Monitoring: {recorder.start_hour}:00 ~ {recorder.end_hour}:00")
    print("="*50)

    recorder.start_monitoring_thread()

    try:
        scapy.sniff(filter="tcp", prn=packet_callback, store=0)
    except KeyboardInterrupt:
        recorder.save_to_file() # 종료 전 남은 데이터 저장
        print("\n[!] 종료합니다.")
        sys.exit(0)
