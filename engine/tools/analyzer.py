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

# --- [전처리 필터 설정] ---
# 1. OpCode 및 MsgID 블랙리스트 (핑, 좌표 등 반복 노이즈)
blacklist_opcodes = set(["0300", "0700", "0000"]) 
blacklist_msgids = set(["86020000"]) 

# 2. 외침/채팅 패턴 블랙리스트 (정규표현식)
CHAT_FILTER_PATTERN = re.compile(r"\(\d+\+?\) \[.+\]|\(\d+위\) \[.+\]")

tag_map = {"1c00": "채팅/외침", "0500": "시스템알림"}

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
        
        # [단계 1] 채팅/외침 패턴 필터링 (정규식)
        decoded_text = try_decode(payload)
        if CHAT_FILTER_PATTERN.search(decoded_text):
            return

        # [단계 2] OpCode 및 MsgID 추출
        opcode = payload[2:4].hex()
        msg_id = payload[4:8].hex() if opcode == "0500" and len(payload) >= 8 else ""

        # [단계 3] 블랙리스트 필터링 (노이즈 제거)
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
            <title>Game Recon v7 - Ultimate Filter</title>
            <style>
                body { font-family: 'Malgun Gothic', sans-serif; margin: 0; background: #0f172a; color: #f8fafc; display: flex; flex-direction: column; height: 100vh; }
                .header { background: #1e293b; padding: 15px; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #334155; }
                .container { display: flex; flex: 1; overflow: hidden; }
                .sidebar { width: 320px; background: #1e293b; border-right: 2px solid #334155; padding: 15px; overflow-y: auto; }
                .main { flex: 1; padding: 20px; overflow-y: auto; }
                .log-item { background: #1e293b; padding: 10px; border-radius: 8px; margin-bottom: 8px; display: grid; grid-template-columns: 100px 80px 80px 100px 1fr 60px; gap: 10px; font-size: 12px; border-left: 4px solid #475569; }
                .badge { background: #475569; padding: 2px 6px; border-radius: 4px; font-family: monospace; }
                .text-yellow { color: #facc15; font-weight: bold; }
                .btn { cursor: pointer; border: none; padding: 5px 10px; border-radius: 4px; font-weight: bold; }
                .btn-danger { background: #ef4444; color: white; }
                .card { background: #334155; padding: 10px; border-radius: 6px; margin-bottom: 10px; font-size: 12px; }
            </style>
        </head>
        <body>
            <div class="header">
                <strong>RECON ENGINE v7 (Noise + Chat Filter)</strong>
                <div>
                    <button class="btn" onclick="fetch('/clear')">로그 비우기</button>
                </div>
            </div>
            <div class="container">
                <div class="sidebar">
                    <h4>전처리 필터 통계</h4>
                    <p style="font-size:11px; color:#94a3b8">실시간 수집 중인 패킷들 (클릭 시 차단):</p>
                    <div id="statsList"></div>
                    <hr style="border:0.5px solid #334155;">
                    <h4>현재 차단된 ID</h4>
                    <div id="blacklistItems" style="font-size:11px; color:#ef4444;"></div>
                </div>
                <div class="main" id="logs"></div>
            </div>
            <script>
                async function update() {
                    const r = await fetch('/data');
                    const d = await r.json();
                    
                    document.getElementById('statsList').innerHTML = d.summary.map(s => `
                        <div class="card">
                            <div style="display:flex; justify-content:space-between">
                                <b>${s.name || s.id}</b> <span>${s.count}건</span>
                            </div>
                            <button class="btn btn-danger" style="font-size:10px; margin-top:5px; width:100%" onclick="addFilter('${s.id}')">이 ID 차단하기</button>
                        </div>
                    `).join('');

                    document.getElementById('blacklistItems').innerHTML = d.blacklist.join(', ');

                    document.getElementById('logs').innerHTML = d.logs.map(l => `
                        <div class="log-item" style="border-left-color: ${l.text ? '#facc15' : '#475569'}">
                            <span>${l.time}</span>
                            <span class="badge">PID:${l.pid}</span>
                            <span class="badge">${l.opcode}</span>
                            <span class="badge" style="background:#7c3aed">${l.msg_id || '-'}</span>
                            <span class="${l.text ? 'text-yellow' : ''}">${l.text || l.data.substring(0,50)+'...'}</span>
                            <button class="btn" onclick="navigator.clipboard.writeText('${l.data}')">HEX</button>
                        </div>
                    `).join('');
                }

                async function addFilter(id) { await fetch(`/filter/add?id=${id}`); }
                setInterval(update, 1000);
            </script>
        </body>
    </html>
    """

@app.get("/data")
def get_data():
    summary = {}
    for l in captured_data:
        key = l['msg_id'] if l['msg_id'] else l['opcode']
        if key not in summary:
            summary[key] = {"id": key, "count": 0, "name": tag_map.get(key, "")}
        summary[key]["count"] += 1
    
    return {
        "logs": captured_data,
        "summary": sorted(list(summary.values()), key=lambda x: x['count'], reverse=True),
        "blacklist": list(blacklist_opcodes | blacklist_msgids)
    }

@app.get("/filter/add")
def add_filter(id: str):
    if len(id) == 4: blacklist_opcodes.add(id)
    else: blacklist_msgids.add(id)
    return {"ok": True}

@app.get("/clear")
def clear_logs():
    captured_data.clear()
    return {"ok": True}

if __name__ == "__main__":
    threading.Thread(target=lambda: sniff(prn=packet_callback, store=0, filter="not port 8000"), daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
