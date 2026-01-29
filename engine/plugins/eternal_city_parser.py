import struct
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
    """입장 시간 관련 시스템 패킷 파싱"""
    # 16 00 뒤의 특정 바이트에서 서버 시간 추출 (예시 구조)
    try:
        if len(payload) >= 6:
            server_ts = struct.unpack('>I', payload[2:6])[0]
            return {"sub_type": "TIME_SYNC", "server_time": server_ts}
    except: pass
    return None

def parse(packet):
    """Main Entry: 모든 세부 파서를 순차적으로 실행"""
    if not packet.haslayer(Raw): return None
    payload = packet[Raw].load
    if not payload.startswith(SYSTEM_HEADER): return None

    # 여러 정보를 동시에 추출할 수 있도록 딕셔너리 조립
    data = {"game": "eternal-city", "type": "SYSTEM"}

    raid = parse_raid(payload)
    if raid: data.update(raid)

    time_info = parse_entry_time(payload)
    if time_info: data.update(time_info)

    return data if "sub_type" in data else None