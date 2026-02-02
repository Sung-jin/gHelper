import datetime, struct, threading, psutil, socket, json, re
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
import uvicorn
from scapy.all import sniff, Raw, IP, UDP, TCP

app = FastAPI()
captured_data = [] 

# --- [전처리 화이트리스트/블랙리스트 설정] ---
# 허용할 OpCode (이것만 로그에 쌓임)
WHITELIST_OPCODE = "0500"

# 차단할 텍스트 패턴 (순위 외침)
# (숫자위) [닉네임] 또는 (999+) [닉네임]
CHAT_FILTER_PATTERN = re.compile(r"\(\d+위\) \[.+\]|\(999\+\) \[.+\]")

def get_detailed_port_info(port):
    if port == 0: return "System", 0
    try:
        for conn in psutil.net_connections(kind='inet'):
            if conn.laddr.port == port and conn.pid:
                proc = psutil.Process(conn.pid)
                return proc.name(), conn.pid
    except: pass
    return "Unknown", 0

def try_decode(payload):
    try:
        # 시스템 메시지의 한글 텍스트 추출 시도
        decoded = payload.decode('euc-kr', errors='ignore')
        printable = "".join(c for c in decoded if c.isprintable())
        return printable.strip()
    except: return ""

def packet_callback(packet):
    if packet.haslayer(Raw) and packet.haslayer(IP):
        # 119.205.203 대역 필터
        if not (packet[IP].dst.startswith("119.205.203") or packet[IP].src.startswith("119.205.203")):
            return

        payload = packet[Raw].load
        if len(payload) < 4: return
        
        # [단계 1] OpCode 추출 및 화이트리스트 검사
        opcode = payload[2:4].hex()
        if opcode != WHITELIST_OPCODE:
            # 0500이 아니면 아예 무시 (핑, 좌표, 일반채팅 등 전부 탈락)
            return

        # [단계 2] 텍스트 디코딩 및 정규식 검사 (순위 외침 제거)
        decoded_text = try_decode(payload)
        if CHAT_FILTER_PATTERN.search(decoded_text):
            return

        # [단계 3] 상세 MsgID 추출 (0500 뒤의 4바이트)
        msg_id = payload[4:8].hex() if len(payload) >= 8 else ""

        sport, dport = (0, 0)
        if packet.haslayer(UDP): sport, dport = packet[UDP].sport, packet[UDP].dport
        elif packet.haslayer(TCP): sport, dport = packet[TCP].sport, packet[TCP].dport

        client_port = sport if sport > 1024 else dport
        app_name, pid = get_detailed_port_info(client_port)
        
        entry = {
            "time": datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3],
            "pid": pid,
            "opcode": opcode,
            "msg_id": msg_id,
            "size": len(payload),
            "text": decoded_text,
            "data": payload.hex()
        }

        # 중요한 0500 패킷만 남기므로 보관 개수를 1000개로 늘려도 무방
        captured_data.insert(0, entry)
        if len(captured_data) > 1000: captured_data.pop()

@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <html>
        <head>
            <title>Game Recon v8 - 0500 ONLY</title>
            <style>
                body { font-family: 'Malgun Gothic', sans-serif; margin: 0; background: #0f172a; color: #f8fafc; display: flex; flex-direction: column; height: 100vh; }
                .header { background: #1e293b; padding: 15px; border-bottom: 2px solid #334155; display: flex; justify-content: space-between; }
                .main { flex: 1; padding: 20px; overflow-y: auto; }
                .log-item { background: #1e293b; padding: 12px; border-radius: 8px; margin-bottom: 8px; display: grid; grid-template-columns: 100px 80px 120px 1fr; gap: 15px; font-size: 13px; border-left: 5px solid #3b82f6; }
                .badge-id { background: #7c3aed; padding: 2px 6px; border-radius: 4px; font-family: monospace; }
                .text-yellow { color: #facc15; font-weight: bold; }
            </style>
        </head>
        <body>
            <div class="header">
                <strong>RECON ENGINE v8 (0500 화이트리스트 모드)</strong>
                <button onclick="fetch('/clear')">로그 비우기</button>
            </div>
            <div class="main" id="logs"></div>
            <script>
                async function update() {
                    const r = await fetch('/data');
                    const d = await r.json();
                    document.getElementById('logs').innerHTML = d.map(l => `
                        <div class="log-item">
                            <span>${l.time}</span>
                            <span>Op:${l.opcode}</span>
                            <span class="badge-id">ID:${l.msg_id}</span>
                            <div>
                                <div class="text-yellow">${l.text}</div>
                                <div style="font-family:monospace; font-size:11px; color:#64748b; word-break:break-all;">${l.data}</div>
                            </div>
                        </div>
                    `).join('');
                }
                setInterval(update, 1000);
            </script>
        </body>
    </html>
    """

@app.get("/data")
def get_data(): return captured_data

@app.get("/clear")
def clear_logs():
    captured_data.clear()
    return {"ok": True}

if __name__ == "__main__":
    threading.Thread(target=lambda: sniff(prn=packet_callback, store=0, filter="not port 8000"), daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
