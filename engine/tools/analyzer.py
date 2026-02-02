import datetime, struct, threading, psutil, socket, platform, subprocess, json
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
import uvicorn
from scapy.all import sniff, Raw, IP, UDP, TCP

app = FastAPI()
captured_data = [] 
recording_data = [] 
is_recording = False
port_info_cache = {}

# 발견된 OpCode(Header)를 저장하는 세트
found_opcodes = set()

def get_detailed_port_info(port):
    if port == 0: return "System", 0
    if port in port_info_cache: return port_info_cache[port]
    try:
        for conn in psutil.net_connections(kind='inet'):
            if conn.laddr.port == port and conn.pid:
                proc = psutil.Process(conn.pid)
                info = (proc.name(), conn.pid)
                port_info_cache[port] = info
                return info
    except: pass
    return "Unknown", 0

def try_decode(payload):
    try:
        # EUC-KR 디코딩 시도 (한국 게임 표준)
        decoded = payload.decode('euc-kr', errors='ignore')
        printable = "".join(c for c in decoded if c.isprintable())
        # 의미 있는 길이를 2글자로 하향 조정 (어썰트 등 짧은 단어 고려)
        return printable.strip() if len(printable.strip()) >= 2 else ""
    except:
        return ""

def packet_callback(packet):
    global is_recording
    if packet.haslayer(Raw) and packet.haslayer(IP):
        # 게임 서버 대역 필터링
        if not (packet[IP].dst.startswith("119.205.203") or packet[IP].src.startswith("119.205.203")):
            return

        payload = packet[Raw].load
        sport = 0; dport = 0
        if packet.haslayer(UDP): sport, dport = packet[UDP].sport, packet[UDP].dport
        elif packet.haslayer(TCP): sport, dport = packet[TCP].sport, packet[TCP].dport

        client_port = sport if sport > 1024 else dport
        app_name, pid = get_detailed_port_info(client_port)
        
        # 헤더 분석: [2Byte 길이][2Byte OpCode] 가설
        # 0500 (시스템), 1c00 (채팅) 등 식별용
        if len(payload) >= 4:
            opcode = payload[2:4].hex()
            found_opcodes.add(opcode)
        else:
            opcode = "0000"

        decoded_text = try_decode(payload)

        entry = {
            "time": datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3],
            "app": app_name,
            "pid": pid,
            "port": client_port,
            "dest": f"{packet[IP].dst}:{dport}",
            "opcode": opcode,
            "size": len(payload),
            "text": decoded_text,
            "data": payload.hex()
        }

        if is_recording:
            recording_data.append(entry)
        
        captured_data.insert(0, entry)
        if len(captured_data) > 200: captured_data.pop()

@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <html>
        <head>
            <title>Game Recon v2 - OpCode Analyzer</title>
            <style>
                body { font-family: 'Consolas', 'Malgun Gothic', sans-serif; padding: 20px; background: #0f172a; color: #cbd5e1; }
                .top-bar { background: #1e293b; padding: 20px; border-radius: 12px; margin-bottom: 20px; position: sticky; top: 0; z-index: 100; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1); }
                .controls { display: flex; gap: 15px; align-items: center; margin-bottom: 15px; }
                .opcode-badges { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; padding-top: 10px; border-top: 1px solid #334155; }
                .badge { background: #334155; color: #94a3b8; padding: 4px 10px; border-radius: 6px; font-size: 12px; cursor: pointer; border: 1px solid transparent; }
                .badge.active { background: #3b82f6; color: white; border-color: #60a5fa; }
                button { padding: 10px 20px; border-radius: 8px; border: none; cursor: pointer; font-weight: bold; transition: 0.3s; }
                .btn-start { background: #22c55e; color: white; }
                .btn-stop { background: #ef4444; color: white; }
                .log-item { background: #1e293b; margin-bottom: 6px; padding: 10px; border-radius: 8px; display: grid; grid-template-columns: 100px 80px 80px 150px 100px 60px 1fr; gap: 10px; font-size: 13px; align-items: center; }
                .tag-opcode { background: #3b82f6; color: white; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-weight: bold; text-align: center; }
                .text-content { color: #facc15; font-weight: bold; }
                .hex-data { grid-column: 1 / -1; font-size: 11px;
