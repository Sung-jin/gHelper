# engine/monitor.py
import sys
import os
import datetime
from scapy.all import sniff, Raw

def packet_callback(packet):
    if packet.haslayer(Raw):
        payload = packet[Raw].load
        try:
            # 1. 텍스트 디코딩 시도
            decoded_payload = payload.decode('utf-8', errors='ignore')
        except:
            # 2. 실패 시 16진수 변환
            decoded_payload = payload.hex()

        # 날짜 기반 파일명 생성 (yyyy-MM-dd)
        current_date = datetime.datetime.now().strftime('%Y-%m-%d')
        log_file = f"packet_dump_{current_date}.txt"

        timestamp = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
        log_entry = f"[{timestamp}] {decoded_payload}\n"

        # 'a' (append) 모드로 파일 열기
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_entry)

        # UI 출력을 위해 첫 100자만 전달
        print(f"DATA:{decoded_payload[:100]}")
        sys.stdout.flush()

if __name__ == "__main__":
    target_pid = sys.argv[1] if len(sys.argv) > 1 else "All"

    # 시작 시 로그
    print(f"STATUS: Monitoring started. Appending to daily log files.")
    sys.stdout.flush()

    # 스니핑 시작
    sniff(prn=packet_callback, store=0)