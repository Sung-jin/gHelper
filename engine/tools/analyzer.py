import datetime, struct, threading, psutil, socket, json, re
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
import uvicorn
from scapy.all import sniff, Raw, IP, UDP, TCP

app = FastAPI()
captured_data = [] 
recording_data = [] 
is_recording = False
port_info_cache = {}

# --- 필터 설정 영역 ---
blacklist_opcodes = set(["0300", "0700", "0000"]) 
blacklist_msgids = set(["86020000"]) 

# 차단할 텍스트 패턴 (정규표현식)
# 1. (숫자위) [닉네임] 형태 -> 예: (23위) [EZKK]
# 2. (999+) [닉네임] 형태 -> 예: (999+) [이쥐]
CHAT_FILTER_PATTERN = re.compile(r"\(\d+\+?\) \[.+\]|\(\d+위\) \[.+\]")

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
        # EUC-KR로 디코딩하여 실제 읽을 수 있는 한글 텍스트 추출
        decoded = payload.decode('euc-kr', errors='ignore')
        printable = "".join(c for c in decoded if c.isprintable())
        return printable.strip()
    except: return ""

def packet_callback(packet):
    global is_recording
    if packet.haslayer(Raw) and packet.haslayer(IP):
        if not (packet[IP].dst.startswith("119.205.203") or packet[IP].src.startswith("119.205.203")):
            return

        payload = packet[Raw].load
        if len(payload) < 4: return
        
        # 1. 텍스트 먼저 추출 (필터링을 위해)
        decoded_text = try_decode(payload)

        # 2. [전처리 필터] 정규식을 이용한 외침 차단
        # (숫위) [닉네임] 이나 (999+) [닉네임]이 포함되어 있으면 즉시 종료
        if CHAT_FILTER_PATTERN.search(decoded_text):
            return

        # 3. 기본 OpCode 및 MsgID 추출
        opcode = payload[2:4].hex()
        msg_id = payload[4:8].hex() if opcode == "0500" and len(payload) >= 8 else ""

        # 4. 블랙리스트 OpCode/MsgID 체크
        if opcode in blacklist_opcodes or (msg_id and msg_id in blacklist_msgids):
            return

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

        if is_recording: recording_data.append(entry)
        captured_data.insert(0, entry)
        if len(captured_data) > 500: captured_data.pop()

@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <html>
        <head>
            <title>Game Recon v6 - Smart Text Filter</title>
            <style>
                body { font-family: 'Malgun Gothic', sans-serif; margin: 0; background: #0f172a; color: #f8fafc; display: flex; flex-direction: column; height: 100vh; }
                .header { background: #1e293b; padding: 15px; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #334155; }
                .container { display: flex; flex: 1; overflow: hidden; }
                .sidebar { width: 300px; background: #1e293b; border-right: 2px solid #334155; padding: 15px; }
                .main { flex: 1; padding: 20px; overflow-y: auto; }
                .log-item { background: #1e293b; padding: 10px; border-radius: 8px; margin-bottom: 8px; display: grid; grid-template-columns: 100px 80px 80px 100px 1fr; gap: 10px; font-size: 12px; border-left: 4px solid #475569; }
                .badge { background: #475569; padding: 2px 6px; border-radius: 4px; font-family: monospace; }
                .text-yellow { color: #facc15; font-weight: bold; }
                .filter-info { font-size: 12px; color: #94a3b8; background: #334155; padding: 10px; border-radius: 6px; }
            </style>
        </head>
        <body>
            <div class="header">
                <strong>RECON ENGINE v6 (Smart Regex Filter)</strong>
                <button style="cursor:pointer; padding:5px 15px;" onclick="fetch('/clear')">로그 초기화</button>
            </div>
            <div class="container">
                <div class="sidebar">
                    <h4>자동 필터 활성화</h4>
                    <div class="filter-info">
                        현재 다음 패턴을 자동으로 차단 중입니다:<br><br>
                        1. <b>(숫자위) [닉네임]</b><br>
                        2. <b>(999+) [닉네임]</b><br><br>
                        이제 텍스트가 깨끗하게 보입니다.
                    </div>
                </div>
                <div class="main" id="logs"></div>
            </div>
            <script>
                async function update() {
                    const r = await fetch('/data');
                    const d = await r.json();
                    document.getElementById('logs').innerHTML = d.map(l => `
                        <div class="log-item" style="border-left-color: ${l.text ? '#facc15' : '#475569'}">
                            <span>${l.time}</span>
                            <span class="badge">PID:${l.pid}</span>
                            <span class="badge">${l.opcode}</span>
                            <span class="badge" style="background:#7c3aed">${l.msg_id || '-'}</span>
                            <span class="${l.text ? 'text-yellow' : ''}">${l.text || l.data.substring(0,60)+'...'}</span>
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

@app.get("/record/stop")
def stop_recording():
    content = json.dumps(recording_data, indent=2)
    return Response(content=content, media_type="application/json", headers={"Content-Disposition": "attachment; filename=recon_v6.json"})

if __name__ == "__main__":
    threading.Thread(target=lambda: sniff(prn=packet_callback, store=0, filter="not port 8000"), daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
