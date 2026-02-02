import datetime, struct, threading, psutil, socket, json
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
import uvicorn
from scapy.all import sniff, Raw, IP, UDP, TCP

app = FastAPI()
captured_data = [] 
recording_data = [] 
is_recording = False
port_info_cache = {}

# 필터 설정 (여기에 등록된 OpCode나 MsgID는 아예 수집하지 않음)
# 분석하시면서 무의미하다고 판단되는 ID를 여기에 추가하세요.
blacklist_opcodes = set(["0300", "0700", "0000"]) # 예: 0300, 0700이 좌표/상태값일 확률이 높음
blacklist_msgids = set(["86020000"]) # 예: 너무 자주 발생하는 시스템 ID

# 통계 및 태그
tag_map = {"1c00": "채팅", "0500": "시스템알림"}
blocked_counts = {} # 차단된 패킷 통계

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
        return printable.strip() if len(printable.strip()) >= 2 else ""
    except: return ""

def packet_callback(packet):
    global is_recording
    if packet.haslayer(Raw) and packet.haslayer(IP):
        # 게임 서버 IP 대역 필터
        if not (packet[IP].dst.startswith("119.205.203") or packet[IP].src.startswith("119.205.203")):
            return

        payload = packet[Raw].load
        if len(payload) < 4: return

        # 헤더 추출
        opcode = payload[2:4].hex()
        msg_id = payload[4:8].hex() if opcode == "0500" and len(payload) >= 8 else ""

        # [핵심] 전처리 필터링: 블랙리스트에 있으면 즉시 버림
        if opcode in blacklist_opcodes or (msg_id and msg_id in blacklist_msgids):
            key = msg_id if msg_id else opcode
            blocked_counts[key] = blocked_counts.get(key, 0) + 1
            return

        sport = 0; dport = 0
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
            "text": try_decode(payload),
            "data": payload.hex()
        }

        if is_recording: recording_data.append(entry)
        
        captured_data.insert(0, entry)
        # 노이즈를 제거했으므로 보관 개수를 500개로 늘려도 안전함
        if len(captured_data) > 500: captured_data.pop()

@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <html>
        <head>
            <title>Game Recon v4 - Noise Filter</title>
            <style>
                body { font-family: 'Malgun Gothic', sans-serif; margin: 0; background: #0f172a; color: #f8fafc; display: flex; flex-direction: column; height: 100vh; }
                .header { background: #1e293b; padding: 15px; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #334155; }
                .container { display: flex; flex: 1; overflow: hidden; }
                .sidebar { width: 350px; background: #1e293b; border-right: 2px solid #334155; padding: 15px; overflow-y: auto; }
                .main { flex: 1; padding: 20px; overflow-y: auto; }
                .card { background: #334155; padding: 12px; border-radius: 8px; margin-bottom: 10px; font-size: 13px; }
                .btn { cursor: pointer; border: none; padding: 5px 10px; border-radius: 4px; font-weight: bold; }
                .btn-danger { background: #ef4444; color: white; }
                .btn-add { background: #10b981; color: white; margin-top: 5px; }
                .log-item { background: #1e293b; padding: 10px; border-radius: 8px; margin-bottom: 8px; display: grid; grid-template-columns: 100px 80px 80px 100px 1fr 80px; gap: 10px; font-size: 12px; border-left: 4px solid #475569; }
                .badge { background: #475569; padding: 2px 6px; border-radius: 4px; font-family: monospace; }
                .text-yellow { color: #facc15; font-weight: bold; }
            </style>
        </head>
        <body>
            <div class="header">
                <strong>RECON ENGINE v4 (Anti-Noise)</strong>
                <div>
                    <button class="btn" onclick="location.href='/record/stop'">녹화저장</button>
                    <button class="btn btn-danger" onclick="fetch('/clear')">로그 비우기</button>
                </div>
            </div>
            <div class="container">
                <div class="sidebar">
                    <h4>실시간 수집 통계</h4>
                    <div id="stats"></div>
                    <hr style="border: 0.5px solid #334155;">
                    <h4>현재 차단 목록 (Blacklist)</h4>
                    <div id="blacklist"></div>
                </div>
                <div class="main" id="logs"></div>
            </div>
            <script>
                async function update() {
                    const r = await fetch('/data');
                    const d = await r.json();
                    
                    document.getElementById('stats').innerHTML = d.summary.map(s => `
                        <div class="card">
                            <div style="display:flex; justify-content:space-between">
                                <b>${s.name || s.id}</b>
                                <span>${s.count}건</span>
                            </div>
                            <button class="btn btn-danger btn-add" style="font-size:10px" onclick="addFilter('${s.id}')">수집 제외(차단)</button>
                        </div>
                    `).join('');

                    document.getElementById('blacklist').innerHTML = d.blacklist.map(id => `
                        <div style="font-size:12px; margin-bottom:5px; color:#94a3b8">
                            • ${id} <button onclick="removeFilter('${id}')" style="font-size:9px">해제</button>
                        </div>
                    `).join('');

                    document.getElementById('logs').innerHTML = d.logs.map(l => `
                        <div class="log-item" style="border-left-color: ${l.text ? '#facc15' : '#475569'}">
                            <span>${l.time}</span>
                            <span class="badge">PID:${l.pid}</span>
                            <span class="badge">${l.opcode}</span>
                            <span class="badge" style="background:#7c3aed">${l.msg_id}</span>
                            <span class="${l.text ? 'text-yellow' : ''}">${l.text || l.data.substring(0,40)+'...'}</span>
                            <button class="btn" style="font-size:10px" onclick="copy('${l.data}')">HEX</button>
                        </div>
                    `).join('');
                }

                async function addFilter(id) { await fetch(`/filter/add?id=${id}`); }
                async function removeFilter(id) { await fetch(`/filter/remove?id=${id}`); }
                function copy(txt) { navigator.clipboard.writeText(txt); alert('HEX 복사됨'); }
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

@app.get("/filter/remove")
def remove_filter(id: str):
    blacklist_opcodes.discard(id)
    blacklist_msgids.discard(id)
    return {"ok": True}

@app.get("/clear")
def clear_logs():
    captured_data.clear()
    return {"ok": True}

# (녹화 관련 엔드포인트는 이전과 동일)
@app.get("/record/stop")
def stop_recording():
    content = json.dumps(recording_data, indent=2)
    return Response(content=content, media_type="application/json", headers={"Content-Disposition": "attachment; filename=recon_v4.json"})

if __name__ == "__main__":
    threading.Thread(target=lambda: sniff(prn=packet_callback, store=0, filter="not port 8000"), daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
