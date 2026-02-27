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
pending_payload = ""

def packet_callback(packet):
    global pending_payload
    if not packet.haslayer(scapy.Raw):
        return

    try:
        current_payload = packet[scapy.Raw].load.hex()
        # 원본 로그 기록
        recorder.add_entry({"t": datetime.datetime.now().strftime("%H:%M:%S.%f"), "d": current_payload})
        # 1. 이전 패킷의 잔여분과 합치기
        combined_payload = pending_payload + current_payload
        
        # 2. 분석 후 다음 패킷을 위해 현재 패킷의 뒷부분 저장
        pending_payload = current_payload[-300:] 

        # 3. '1d000300' 단위 분할
        chunks = combined_payload.split("1d000300")
        for chunk in chunks[1:]:
            if not (chunk.startswith("cb80") or chunk.startswith("cba0")):
                continue
            
            actual_content = chunk.split("1d00")[0]
            
            # 4. Key(단계) 탐색
            detected_key = next((k for k in raid_mapping.keys() if k in actual_content), None)
            if detected_key:
                known_locs = raid_mapping[detected_key].get("locations", {})
                
                # ID 찾기 및 이름 정의
                found_id = next((id for id in known_locs if id in actual_content), None)
                found_name = known_locs.get(found_id) if found_id else "미식별 장소"
                
                # 미식별 시 후보군 추출
                if not found_id:
                    candidates = [actual_content[i:i+6] for i in range(0, len(actual_content)-6, 2)
                                 if actual_content[i:i+6] != "000000" and not actual_content[i:i+6].startswith("00")]
                    if candidates:
                        found_id = candidates[0]

                # 5. 알림 로직
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

    except Exception as e:
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
