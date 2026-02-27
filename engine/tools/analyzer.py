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
# { "location_id": [time1, time2, ...] } 형태로 여러 예고 시간 저장
pre_warning_registry = {} 

def packet_callback(packet):
    global pending_payload
    if not packet.haslayer(scapy.Raw): return

    try:
        current_payload = packet[scapy.Raw].load.hex()
        # 로그 기록
        recorder.add_entry({"t": datetime.datetime.now().strftime("%H:%M:%S.%f"), "d": current_payload})
        
        combined = pending_payload + current_payload
        last_header_idx = combined.rfind("1d000300")
        
        if last_header_idx != -1:
            process_area = combined[:last_header_idx]
            pending_payload = combined[last_header_idx:]
        else:
            pending_payload = combined[-300:]
            return

        chunks = process_area.split("1d000300")
        for chunk in chunks[1:]:
            if len(chunk) < 20 or not (chunk.startswith("cb80") or chunk.startswith("cba0")):
                continue
            
            actual_content = chunk.split("1d00")[0]
            detected_key = next((k for k in raid_mapping.keys() if k in actual_content), None)
            
            if not detected_key: continue
            
            known_locs = raid_mapping[detected_key].get("locations", {})
            found_id = next((id for id in known_locs if id in actual_content), None)
            
            if found_id:
                current_time = time.time()
                
                # --- 교차 검증 로직 시작 ---
                
                # 1. 5분 전(80a0) 발생 시: 시간 리스트에 추가 (덮어쓰기 방지)
                if detected_key == "80a0":
                    if found_id not in pre_warning_registry:
                        pre_warning_registry[found_id] = []
                    pre_warning_registry[found_id].append(current_time)
                    # 리스트가 너무 커지지 않게 최근 5개만 유지
                    pre_warning_registry[found_id] = pre_warning_registry[found_id][-5:]

                # 2. 1분 전(8080) 발생 시: 리스트 내 시간들과 대조
                elif detected_key == "8080":
                    warning_times = pre_warning_registry.get(found_id, [])
                    is_validated = False
                    
                    for t in warning_times:
                        # 3분(180초) ~ 6분(360초) 사이의 예고가 있는지 확인
                        if 180 <= (current_time - t) <= 360:
                            is_validated = True
                            break
                    
                    if is_validated:
                        # 검증 성공 시에만 알림 발송 및 쿨타임 체크
                        cooldown_key = (detected_key, found_id)
                        if current_time - alert_cooldowns.get(cooldown_key, 0) > COOLDOWN_SECONDS:
                            loc_name = known_locs.get(found_id, "미식별")
                            msg = f"🚨 [검증완료] {loc_name} 습격 1분 전!"
                            notifier.send_discord(msg)
                            alert_cooldowns[cooldown_key] = current_time
                            # 사용된 예고 데이터 삭제
                            pre_warning_registry[found_id] = [] 

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
