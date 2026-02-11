import scapy.all as scapy
import datetime
import sys
import os

from utils import ConfigManager, Notifier
from recording import PacketRecorder

# ==========================================
# 1. 초기 설정 및 환경 구축
# ==========================================
ConfigManager.init_app_config(
    mapping_filename="mapping.json",
    webhook_url="YOUR_DISCORD_WEBHOOK_URL"
)
recorder = PacketRecorder(
    start_hour=19,
    end_hour=2,
    interval_min=10,
    log_dir=os.path.join(ConfigManager.get_base_path(), "logs")
)
notifier = Notifier()
raid_mapping = ConfigManager.get_global("raid_mapping", {})

# ==========================================
# 2. 패킷 처리 핵심 로직
# ==========================================
def packet_callback(packet):
    """
    네트워크에서 캡처된 모든 TCP 패킷이 거쳐가는 함수
    """
    if not packet.haslayer(scapy.Raw):
        return

    try:
        # 데이터 추출 및 전처리
        payload_hex = packet[scapy.Raw].load.hex()
        recorder.add_entry({
            "time": datetime.datetime.now().strftime("%H:%M:%S.%f"),
            "data": payload_hex
        })

        if "1d000300" in payload_hex:
            segments = payload_hex.split("1d000300")
            for seg in segments[1:]:
                if len(seg) > 100: continue

                opcode = seg[0:4]

                # 1. mapping.json의 키에 해당 Opcode가 있는지 확인
                if opcode in raid_mapping:
                    timing_info = raid_mapping[opcode]
                    data_part = seg[4:]

                    # 2. ID 추출 (패딩 처리)
                    potential_id = data_part[4:10] if data_part.startswith("0000") else data_part[:6]

                    # 3. 장소 확인
                    locations = timing_info.get("locations", {})
                    location_name = locations.get(potential_id, f"❓ 미식별 지역({potential_id})")

                    # 4. 알림 전송
                    msg = (
                        f"📢 **[{timing_info['type']}]** {location_name}\n"
                        f"- Opcode: `{opcode}` | ID: `{potential_id}`\n"
                        f"- 원본: `1d000300{seg[:22]}`"
                    )
                    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {location_name} 감지!")
                    notifier.send_discord(msg)

    except Exception as e:
        # 패킷 처리 중 오류가 발생해도 프로그램이 멈추지 않도록 예외 처리
        pass

# ==========================================
# 3. 프로그램 실행
# ==========================================
if __name__ == "__main__":
    print("="*50)
    print("  Packet Analyzer System v2.0")
    print("="*50)

    # 상태 모니터링 스레드 시작
    recorder.start_monitoring_thread()

    # 시작 알림
    notifier.send_discord("🚀 패킷 분석 시작")

    try:
        # 스니핑 시작 (store=0으로 설정하여 메모리 누수 방지)
        scapy.sniff(filter="tcp", prn=packet_callback, store=0)
    except KeyboardInterrupt:
        print("\n[!] 사용자에 의해 프로그램이 종료되었습니다.")
        sys.exit(0)