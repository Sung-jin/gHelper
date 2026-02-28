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

# [전역 상태 관리]
pending_payload = ""
pre_warning_registry = {}  # { "location_id": timestamp }
alert_cooldowns = {}

# [상수 설정]
INTERVAL_4MIN = 240  # 5분 전 -> 1분 전 간격 (초)
INTERVAL_1MIN = 60   # 1분 전 -> 시작 간격 (초)
MARGIN = 5           # 허용 오차 범위 (초)
COOLDOWN = 60        # 동일 알림 중복 방지 (초)

def packet_callback(packet):
    global pending_payload
    global pre_warning_registry
    
    if not packet.haslayer(scapy.Raw):
        return

    try:
        current_payload = packet[scapy.Raw].load.hex()
        
        # 발전 및 디버깅을 위한 전체 로그 기록 (기존 recorder 유지)
        recorder.add_entry({"t": datetime.datetime.now().strftime("%H:%M:%S.%f"), "d": current_payload})
        
        # 1. 분절 패킷 결합 및 처리
        combined = pending_payload + current_payload
        last_header_idx = combined.rfind("1d000300")
        
        if last_header_idx != -1:
            # 마지막 헤더 이후 데이터가 너무 짧으면(80자 미만) 다음 패킷과 합치기 위해 보관
            if len(combined[last_header_idx:]) < 80:
                process_area = combined[:last_header_idx]
                pending_payload = combined[last_header_idx:]
            else:
                process_area = combined
                pending_payload = ""
        else:
            # 헤더가 없으면 노이즈 방지를 위해 최소한의 잔여분만 유지
            pending_payload = combined[-300:]
            return

        if not process_area:
            return

        # 2. 메시지 덩어리 분석 (1d000300 기준 분할)
        chunks = process_area.split("1d000300")
        for chunk in chunks[1:]:
            # 구조적 지문 검증 (cb80/cba0로 시작하는 시스템 메시지인지 확인)
            if not (chunk.startswith("cb800000") or chunk.startswith("cba00000")):
                continue
            
            actual_content = chunk.split("1d00")[0]
            
            # 3. 습격 단계 키(Key) 탐색
            detected_key = next((k for k in raid_mapping.keys() if k in actual_content), None)
            if not detected_key:
                continue
            
            known_locs = raid_mapping[detected_key].get("locations", {})
            
            # 4. [보완] 구조적 ID 탐색 (Key 발견 지점 인근 100자 이내에서만 ID 탐색)
            found_id = None
            key_pos = actual_content.find(detected_key)
            search_area = actual_content[key_pos : key_pos + 100]
            
            for loc_id in known_locs.keys():
                if loc_id in search_area:
                    found_id = loc_id
                    break
            
            if not found_id:
                continue

            # 5. [핵심] 4분-1분 연쇄 검증 로직
            current_time = time.time()
            
            # A. 5분 전 (80a0) -> 메모리에 예약만 수행
            if detected_key == "80a0":
                pre_warning_registry[found_id] = current_time
                # 오래된 예고(10분 초과) 데이터 청소
                pre_warning_registry = {k: v for k, v in pre_warning_registry.items() if current_time - v < 600}

            # B. 1분 전 (8080) -> 4분 전(240초) 예고 기록과 대조
            elif detected_key == "8080":
                last_warn_time = pre_warning_registry.get(found_id, 0)
                time_diff = current_time - last_warn_time
                
                # 정확히 240초(±5초) 주기가 일치할 때만 실제 습격으로 간주
                if (INTERVAL_4MIN - MARGIN) <= time_diff <= (INTERVAL_4MIN + MARGIN):
                    cooldown_key = (detected_key, found_id)
                    if current_time - alert_cooldowns.get(cooldown_key, 0) > COOLDOWN:
                        loc_name = known_locs.get(found_id, "미식별 장소")
                        # 검증 성공 알림 발송
                        notifier.send_discord(f"🚨 [검증성공] {loc_name} 습격 1분 전! (4분 주기 일치)")
                        alert_cooldowns[cooldown_key] = current_time
                        # 다음 단계(시작) 검증을 위해 시간 업데이트
                        pre_warning_registry[found_id] = current_time

            # C. 지금 시작 (f180) -> 1분 전(60초) 알림 기록과 대조
            elif detected_key == "f180":
                last_alert_time = pre_warning_registry.get(found_id, 0)
                time_diff = current_time - last_alert_time
                
                if (INTERVAL_1MIN - MARGIN) <= time_diff <= (INTERVAL_1MIN + MARGIN):
                    # 필요 시 "습격 시작" 알림 추가 가능
                    pass

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
