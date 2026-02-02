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

# MsgID별로 사용자가 붙인 이름을 저장 (메모리 저장)
tag_map = {
    "1c00": "채팅/귓속말",
    "0500": "시스템알림(기본)"
}

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
    except:
        return ""

def packet_callback(packet):
    global is_recording
    if packet.haslayer(Raw) and packet.haslayer(IP):
        if not (packet[IP].dst.startswith("119.205.203") or packet[IP].src.startswith("119.205.203")):
            return

        payload = packet[Raw].load
        sport = 0; dport = 0
        if packet.haslayer(UDP): sport, dport = packet[UDP].sport, packet[UDP].dport
        elif packet.haslayer(TCP): sport, dport = packet[TCP].sport, packet[TCP].dport

        client_port = sport if sport > 1024 else dport
        app_name, pid = get_detailed_port_info(client_port)
        
        # 기본 OpCode 추출
        opcode = payload[2:4].hex() if len(payload) >= 4 else "0000"
        
        # 시스템 알림(0500)인 경우 MsgID(그 뒤 4바이트) 추출
        msg_id = ""
        if opcode == "0500" and len(payload) >= 8:
            msg_id = payload[4:8].hex()

        decoded_text = try_decode(payload)

        entry = {
            "time": datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3],
            "pid": pid,
            "port": client_port,
            "dest": f"{packet[IP].dst}:{dport}",
            "opcode": opcode,
            "msg_id": msg_id,
            "size": len(payload),
            "text": decoded_text,
            "data": payload.hex()
        }

        if is_recording:
            recording_data.append(entry)
        
        captured_data.insert(0, entry)
        if len(captured_data) > 300: captured_data.pop()

@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <html>
        <head>
            <title>Game Recon v3 - Smart Analyzer</title>
            <style>
                body { font-family: 'Malgun Gothic', sans-serif; padding: 0; margin: 0; background: #0f172a; color: #f8fafc; }
                .layout { display: flex; flex-direction: column; height: 100vh; }
                .top-bar { background: #1e293b; padding: 15px 20px; border-bottom: 2px solid #334155; }
                .main-content { display: flex; flex: 1; overflow: hidden; }
                
                /* 왼쪽: 요약 및 통계 패널 */
                .sidebar { width: 350px; background: #1e293b; border-right: 2px solid #334155; overflow-y: auto; padding: 15px; }
                .summary-card { background: #334155; padding: 10px; border-radius: 8px; margin-bottom: 10px; font-size: 13px; cursor: pointer; border: 1px solid transparent; }
                .summary-card:hover { border-color: #3b82f6; }
                .summary-card.active { background: #3b82f6; }
                .msg-label { font-weight: bold; color: #facc15; }
                
                /* 오른쪽: 실시간 로그 패널 */
                .log-panel { flex: 1; overflow-y: auto; padding: 20px; }
                .log-item { background: #1e293b; border-radius: 8px; padding: 12px; margin-bottom: 8px; border-left: 5px solid #475569; display: grid; grid-template-columns: 100px 80px 100px 120px 1fr; gap: 10px; }
                
                button { background: #3b82f6; color: white; border: none; padding: 8px 15px; border-radius: 6px; cursor: pointer; font-weight: bold; }
                .btn-rec { background: #ef4444; }
                input { background: #0f172a; border: 1px solid #475569; color: white; padding: 8px; border-radius: 4px; }
                .tag { font-size: 11px; padding: 2px 5px; border-radius: 4px; background: #475569; }
                .badge-msgid { background: #7c3aed; color: white; }
                .text-yellow { color: #facc15; font-weight: bold; }
            </style>
        </head>
        <body>
            <div class="layout">
                <div class="top-bar">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <strong>RECON ENGINE v3</strong>
                        <div>
                            <button id="btnStart" onclick="startRec()">녹화 시작</button>
                            <button class="btn-rec" onclick="stopRec()">녹화 종료 및 저장</button>
                        </div>
                    </div>
                </div>
                <div class="main-content">
                    <div class="sidebar" id="sidebar">
                        <h4 style="margin-top:0">MsgID 그룹 통계</h4>
                        <div id="summaryList"></div>
                    </div>
                    <div class="log-panel" id="logs">
                        </div>
                </div>
            </div>
            <script>
                let rawLogs = [];
                let tags = {"1c00": "채팅", "0500": "시스템"};
                let activeFilter = null;

                async function update() {
                    const r = await fetch('/logs');
                    const data = await r.json();
                    rawLogs = data.logs;
                    renderSummary(data.summary);
                    renderLogs();
                }

                function renderSummary(summary) {
                    const container = document.getElementById('summaryList');
                    container.innerHTML = summary.map(s => `
                        <div class="summary-card ${activeFilter === s.id ? 'active' : ''}" onclick="setFilter('${s.id}')">
                            <div style="display:flex; justify-content:space-between">
                                <span class="msg-label">${s.name || s.id}</span>
                                <span>${s.count}건</span>
                            </div>
                            <div style="font-size:11px; color:#cbd5e1; margin-top:5px; font-family:monospace;">${s.last_data.substring(0,30)}...</div>
                            <button style="font-size:10px; padding:2px 5px; margin-top:5px;" onclick="renameTag('${s.id}', event)">이름변경</button>
                        </div>
                    `).join('');
                }

                function setFilter(id) {
                    activeFilter = (activeFilter === id) ? null : id;
                    renderLogs();
                }

                async function renameTag(id, event) {
                    event.stopPropagation();
                    const newName = prompt('이 MsgID에 붙일 이름을 입력하세요:');
                    if(newName) {
                        await fetch(`/tag?id=${id}&name=${encodeURIComponent(newName)}`);
                        update();
                    }
                }

                function renderLogs() {
                    const container = document.getElementById('logs');
                    const filtered = activeFilter ? rawLogs.filter(l => (l.opcode === activeFilter || l.msg_id === activeFilter)) : rawLogs;
                    
                    container.innerHTML = filtered.map(l => `
                        <div class="log-item" style="border-left-color: ${l.text ? '#facc15' : '#475569'}">
                            <span style="font-size:12px; color:#94a3b8">${l.time}</span>
                            <span class="tag">PID:${l.pid}</span>
                            <span class="tag">${l.opcode}</span>
                            <span class="tag badge-msgid">${l.msg_id || 'N/A'}</span>
                            <div>
                                <div class="text-yellow">${l.text}</div>
                                <div style="font-family:monospace; font-size:11px; color:#64748b; word-break:break-all;">${l.data}</div>
                            </div>
                        </div>
                    `).join('');
                }

                async function startRec() { await fetch('/record/start'); }
                async function stopRec() { window.location.href = '/record/stop'; }
                
                setInterval(update, 1000);
            </script>
        </body>
    </html>
    """

@app.get("/logs")
def get_logs(): 
    # 통계 생성
    summary = {}
    for l in captured_data:
        # 그룹화 기준: MsgID가 있으면 MsgID로, 없으면 OpCode로
        key = l['msg_id'] if l['msg_id'] else l['opcode']
        if key not in summary:
            summary[key] = {"id": key, "count": 0, "last_data": l['data'], "name": tag_map.get(key, "")}
        summary[key]["count"] += 1
    
    return {
        "logs": captured_data, 
        "summary": sorted(list(summary.values()), key=lambda x: x['count'], reverse=True)
    }

@app.get("/tag")
def set_tag(id: str, name: str):
    tag_map[id] = name
    return {"status": "ok"}

@app.get("/record/start")
def start_recording():
    global is_recording, recording_data
    recording_data = [] 
    is_recording = True
    return {"status": "started"}

@app.get("/record/stop")
def stop_recording():
    global is_recording, recording_data
    is_recording = False
    content = json.dumps(recording_data, indent=2)
    filename = f"recon_v3_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return Response(content=content, media_type="application/json", headers={"Content-Disposition": f"attachment; filename={filename}"})

if __name__ == "__main__":
    threading.Thread(target=lambda: sniff(prn=packet_callback, store=0, filter="not port 8000"), daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
