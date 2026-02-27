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
    # 전역 상태를 유지하기 위해 global 선언
    global pending_payload
    global pre_warning_registry
    
    if not packet.haslayer(scapy.Raw):
        return

    try:
        current_payload = packet[scapy.Raw].load.hex()
        
        # [발전용 데이터 기록] - 성능을 위해 이전에 설정한 recorder 사용
        recorder.add_entry({"t": datetime.datetime.now().strftime("%H:%M:%S.%f"), "d": current_payload})
        
        # 1. 분절 패킷 처리를 위한 스트림 결합
        combined = pending_payload + current_payload
        last_header_idx = combined.rfind("1d000300")
        
        if last_header_idx != -1:
            # 마지막 헤더 전까지의 완성된 메시지만 분석 대상으로 확정
            process_area = combined[:last_header_idx]
            # 마지막 헤더 이후는 다음 패킷과 합치기 위해 보관 (중복 검사 방지)
            pending_payload = combined[last_header_idx:]
        else:
            # 헤더가 없으면 노이즈 방지를 위해 최소한의 잔여분만 유지
            pending_payload = combined[-300:]
            return

        if not process_area:
            return

        # 2. 완성된 메시지 덩어리(Chunk) 분석
        chunks = process_area.split("1d000300")
        for chunk in chunks[1:]:
            # 엄격한 규격 검증: 최소 길이 및 지문(cb800000/cba00000) 확인
            if len(chunk) < 40: continue
            if not (chunk.startswith("cb800000") or chunk.startswith("cba00000")):
                continue
            
            actual_content = chunk.split("1d00")[0]
            
            # 3. 습격 단계(Key) 탐색
            detected_key = next((k for k in raid_mapping.keys() if k in actual_content), None)
            if not detected_key:
                continue
            
            known_locs = raid_mapping[detected_key].get("locations", {})
            
            # 4. [핵심] 구조적 검증: Key 발견 지점 근처에서만 ID 탐색 (노이즈 차단)
            found_id = None
            key_pos = actual_content.find(detected_key)
            search_area = actual_content[key_pos : key_pos + 40] # 주변 40자 이내
            
            for loc_id in known_locs.keys():
                if loc_id in search_area:
                    found_id = loc_id
                    break
            
            # 5. 교차 검증 및 알림 처리
            if found_id:
                current_time = time.time()
                
                # A. 5분 전(80a0) 패턴 발생 시: 예고 리스트 등록 및 청소
                if detected_key == "80a0":
                    if found_id not in pre_warning_registry:
                        pre_warning_registry[found_id] = []
                    
                    # [메모리 청소] 해당 ID의 기록 중 10분(600초) 이상 된 낡은 데이터 삭제
                    pre_warning_registry[found_id] = [t for t in pre_warning_registry[found_id] 
                                                      if current_time - t < 600]
                    
                    pre_warning_registry[found_id].append(current_time)
                    # 리스트 덮어쓰기 방지를 위해 최신 3개 기록 유지
                    pre_warning_registry[found_id] = pre_warning_registry[found_id][-3:]

                # B. 1분 전(8080) 패턴 발생 시: 3~6분 전 예고 여부 대조
                elif detected_key == "8080":
                    warning_times = pre_warning_registry.get(found_id, [])
                    
                    # 리스트 내 기록 중 하나라도 180~360초 이내에 있다면 검증 성공
                    is_validated = any(180 <= (current_time - t) <= 360 for t in warning_times)
                    
                    if is_validated:
                        cooldown_key = (detected_key, found_id)
                        if current_time - alert_cooldowns.get(cooldown_key, 0) > COOWN_SECONDS:
                            loc_name = known_locs.get(found_id, "미식별 장소")
                            # 실제 습격일 때만 디스코드 발송 (콘솔 출력 X)
                            notifier.send_discord(f"🚨 [검증완료] {loc_name} 습격 1분 전!")
                            alert_cooldowns[cooldown_key] = current_time
                            # 검증에 사용된 예고 데이터 초기화
                            pre_warning_registry[found_id] = []

    except Exception:
        # 프레임 드랍 방지를 위해 에러 로그는 무시하거나 파일로만 기록
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
