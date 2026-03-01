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
COOLDOWN = 180       # 동일 알림 중복 방지 (초)

def packet_callback(packet):
    global pending_payload
    global pre_warning_registry
    global alert_cooldowns
    
    # Raw 레이어가 없는 패킷은 무시
    if not packet.haslayer(scapy.Raw):
        return

    try:
        # 1. 페이로드 추출 및 결합
        current_payload = packet[scapy.Raw].load.hex()
        combined = pending_payload + current_payload
        
        recorder.add_entry({"t": datetime.datetime.now().strftime("%H:%M:%S.%f"), "d": current_payload})
        
        # 2. 메시지 헤더(1d000300) 기준으로 데이터 분할
        # 마지막 덩어리는 다음 패킷과 합쳐질 수 있으므로 buffer에 보관
        chunks = combined.split("1d000300")
        if len(chunks) > 1:
            process_area = chunks[:-1]  # 완성된 덩어리들
            pending_payload = "1d000300" + chunks[-1]  # 미완성 덩어리
        else:
            pending_payload = combined
            return

        for chunk in process_area:
            # 3. 습격 단계 키(Key) 탐색 (80a0: 5분전, 8080: 1분전, f180: 시작)
            detected_key = next((k for k in raid_mapping.keys() if k in chunk), None)
            if not detected_key:
                continue
            
            # 해당 키에 매핑된 장소 리스트 가져오기
            known_locs = raid_mapping[detected_key].get("locations", {})
            
            # 4. 위치 ID 탐색 (유연한 탐색: 청크 전체에서 ID 존재 여부 확인)
            found_id = next((loc_id for loc_id in known_locs.keys() if loc_id in chunk), None)
            
            if not found_id:
                # [신규 식별지 대응] 키는 발견됐는데 ID가 매핑에 없는 경우 
                # 로그에만 남기거나 별도의 '알 수 없는 ID' 처리를 할 수 있습니다.
                continue

            current_time = time.time()
            
            # 5. [사용자 정의] 4분-1분 연쇄 검증 로직
            
            # A단계: 5분 전(80a0) 포착 시 -> 시간 기록 (예약)
            if detected_key == "80a0":
                pre_warning_registry[found_id] = current_time
                # 메모리 관리를 위해 10분 이상 된 오래된 기록 삭제
                pre_warning_registry = {k: v for k, v in pre_warning_registry.items() if current_time - v < 600}

            # B단계: 1분 전(8080) 포착 시 -> 4분 전 기록과 대조
            elif detected_key == "8080":
                last_warn_time = pre_warning_registry.get(found_id, 0)
                time_diff = current_time - last_warn_time
                
                # 사용자님 지침: 5분전(A)과 1분전(B) 사이는 정확히 4분(240초)
                if (INTERVAL_4MIN - MARGIN) <= time_diff <= (INTERVAL_4MIN + MARGIN):
                    cooldown_key = (detected_key, found_id)
                    if current_time - alert_cooldowns.get(cooldown_key, 0) > COOLDOWN:
                        loc_name = known_locs.get(found_id, f"신규지역(ID:{found_id})")
                        
                        # 디스코드 알림 발송
                        notifier.send_discord(f"🚨 [검증성공] {loc_name} 습격 1분 전! (4분 주기 일치)")
                        
                        alert_cooldowns[cooldown_key] = current_time
                        # 다음 '시작' 단계 검증을 위해 시간 업데이트
                        pre_warning_registry[found_id] = current_time

            # C단계: 시작(f180) 포착 시 -> 1분 전 기록과 대조 (필요 시 알림)
            elif detected_key == "f180":
                last_alert_time = pre_warning_registry.get(found_id, 0)
                if (INTERVAL_1MIN - MARGIN) <= (current_time - last_alert_time) <= (INTERVAL_1MIN + MARGIN):
                    # 실시간 모니터링용 로그 (알림은 선택 사항)
                    pass

    except Exception as e:
        # 예기치 못한 에러 발생 시 프로그램 중단 방지 및 로그 출력
        print(f"Error processing packet: {e}")

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
