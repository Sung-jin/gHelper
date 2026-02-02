import struct
import time
from scapy.all import Raw

# 이터널시티 전용 상수
SYSTEM_HEADER = b'\x16\x00'

def parse_raid(payload):
    """습격전 공지 파싱"""
    try:
        text = payload.decode('euc-kr', errors='ignore')
        if "습격전" in text:
            return {"sub_type": "RAID_ALERT", "content": text.strip()}
    except: pass
    return None

def parse_entry_time(payload):
    """서버 시간(Server Tick) 추출 - 위치: payload[2:6]"""
    try:
        if len(payload) >= 6:
            # 이전 분석에 근거한 4바이트 Unsigned Int (Big-endian)
            server_ts = struct.unpack('>I', payload[2:6])[0]
            return server_ts
    except: pass
    return None

def parse(packet):
    if not packet.haslayer(Raw): return None
    payload = packet[Raw].load
    if not payload.startswith(SYSTEM_HEADER): return None

    # 모든 패킷에 대해 일단 서버 시간 추출 시도
    server_time = parse_entry_time(payload)

    data = {
        "game": "eternal-city",
        "type": "SYSTEM",
        "server_time": server_time,
        "local_time": time.time(),
        "raw_hex": payload.hex() # 분석을 위해 원본 패킷도 헥사값으로 포함
    }

    try:
        text = payload.decode('euc-kr', errors='ignore').strip()

        if "습격전" in text:
            data["sub_type"] = "RAID_ALERT"
            data["content"] = text
        elif "패러사이트" in text:
            data["sub_type"] = "INVASION_ALERT"
            data["content"] = text
        else:
            data["sub_type"] = "TIME_SYNC"
            data["content"] = text
    except:
        data["sub_type"] = "UNKNOWN_SYSTEM"

    return data