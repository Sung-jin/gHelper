import time
import struct
from scapy.all import IP, UDP, Raw, send

def send_mock_packet():
    print("Mock packet sender started...")
    target_ip = "127.0.0.1" # 자기 자신에게 보냄

    while True:
        # 1. 현재 서버 시간 생성 (Unix Timestamp)
        current_ts = int(time.time())

        # 2. 가짜 패킷 데이터 생성 (앞뒤로 더미 데이터 추가)
        # 0x5a 0x0f (더미) + 4바이트 시간 + 더미 데이터들
        header = b'\x5a\x0f'
        timestamp_bin = struct.pack('>I', current_ts) # Big-endian 4바이트
        footer = b'\x11\x22\x33\x44\x55\x66\x77\x88'

        payload = header + timestamp_bin + footer

        # 3. UDP 패킷 전송
        pkt = IP(dst=target_ip)/UDP(dport=9999)/Raw(load=payload)
        send(pkt, verbose=False)

        print(f"Sent packet with TS: {current_ts}")
        time.sleep(1) # 1초마다 전송

if __name__ == "__main__":
    send_mock_packet()