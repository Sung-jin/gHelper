import sys
import datetime
import struct
import os
from scapy.all import sniff, Raw

# 서버 시간을 분석하는 독립적인 함수 (실패해도 안전함)
def get_server_time_info(payload):
    try:
        # 현재 시간 기준 전후 1년 정도의 범위를 타겟으로 설정 (약 1.7억 ~ 1.8억 사이)
        # 2025년 기준 Unix Timestamp는 1,735,689,600 ~ 시작함
        min_ts = 1700000000
        max_ts = 1900000000

        found_patterns = []

        # 4바이트 정수(Big Endian, Little Endian)를 1바이트씩 이동하며 검사
        for i in range(len(payload) - 3):
            # 4바이트씩 읽어서 정수로 변환
            # 'I'는 unsigned int, '>'는 Big Endian, '<'는 Little Endian
            val_be = struct.unpack('>I', payload[i:i+4])[0]
            val_le = struct.unpack('<I', payload[i:i+4])[0]

            if min_ts < val_be < max_ts:
                found_patterns.append(f"BE_at_{i}:{val_be}")
            if min_ts < val_le < max_ts:
                found_patterns.append(f"LE_at_{i}:{val_le}")

        if found_patterns:
            return "|".join(found_patterns)
        return None
    except:
        # 실패 시 아무것도 반환하지 않음 (메인 로직 보호)
        return None

def packet_callback(packet):
    if packet.haslayer(Raw):
        payload = packet[Raw].load

        # 1. 텍스트 디코딩 또는 Hex 변환
        try:
            decoded_payload = payload.decode('utf-8', errors='ignore')
        except:
            decoded_payload = payload.hex()

        # 2. 서버 시간 후보 탐색
        time_candidates = get_server_time_info(payload)

        # 3. 로그 기록
        now = datetime.datetime.now()
        timestamp = now.strftime('%H:%M:%S.%f')[:-3]
        log_file = f"packet_dump_{now.strftime('%Y-%m-%d')}.txt"

        # 후보가 발견되면 로그에 위치와 값을 함께 기록
        time_tag = f" [Candidate: {time_candidates}]" if time_candidates else ""
        log_entry = f"[{timestamp}]{time_tag} {decoded_payload}\n"

        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except:
            pass

        # 4. UI 출력
        print(f"DATA:{decoded_payload[:100]}")
        sys.stdout.flush()

if __name__ == "__main__":
    # main.ts에서 전달받은 PID (현재는 PID 필터링 없이 전체 스니핑)
    target_pid = sys.argv[1] if len(sys.argv) > 1 else "All"

    print(f"STATUS: Monitoring started. Target PID: {target_pid}")
    sys.stdout.flush()

    try:
        # 스니핑 시작
        sniff(prn=packet_callback, store=0)
    except Exception as e:
        print(f"ERROR: Sniffing stopped: {str(e)}")
        sys.stdout.flush()