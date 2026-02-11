import scapy.all as scapy
import datetime
import sys
import os
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

def packet_callback(packet):
    if not packet.haslayer(scapy.Raw):
        return

    try:
        payload_hex = packet[scapy.Raw].load.hex()
        # 오직 녹화만 수행 (화면 출력 없음)
        recorder.add_entry({
            "t": datetime.datetime.now().strftime("%H:%M:%S.%f"),
            "d": payload_hex
        })

        # 나중 분석을 위해 로직 구조만 유지 (알림 및 출력 제거)
        if "1d000300" in payload_hex:
            pass 

    except Exception:
        pass

if __name__ == "__main__":
    print("="*50)
    print("  Packet Recording System v2.1 (Silent Mode)")
    print(f"  Schedule: {recorder.start_hour}:00 ~ {recorder.end_hour}:00")
    print("="*50)

    recorder.start_monitoring_thread()
    notifier.send_discord("🚀 패킷 분석기 가동 (백그라운드 녹화 시작)")

    try:
        scapy.sniff(filter="tcp", prn=packet_callback, store=0)
    except KeyboardInterrupt:
        recorder.save_to_file() # 종료 전 남은 데이터 저장
        print("\n[!] 종료합니다.")
        sys.exit(0)
