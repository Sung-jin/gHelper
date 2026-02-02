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
                .hex-data { grid-column: 1 / -1; font-size: 11px; color: #64748b; word-break: break-all; margin-top: 4px; font-family: monospace; }
                input { background: #0f172a; border: 1px solid #334155; color: white; padding: 8px 12px; border-radius: 6px; width: 200px; }
                .recording-status { color: #ef4444; font-weight: bold; animation: blink 1s infinite; margin-left: 10px; }
                @keyframes blink { 50% { opacity: 0; } }
            </style>
        </head>
        <body>
            <div class="top-bar">
                <div class="controls">
                    <strong style="color:#3b82f6; font-size: 1.2em;">RECON ENGINE v2</strong>
                    <button class="btn-start" onclick="startRec()">녹화 시작</button>
                    <button class="btn-stop" onclick="stopRec()">녹화 종료 및 저장</button>
                    <span id="recStatus" style="display:none;" class="recording-status">● RECORDING</span>
                    <input type="text" id="searchInput" placeholder="검색 (PID, Header, Text)..." oninput="render()">
                </div>
                <div class="opcode-badges" id="opcodeContainer">
                    <span style="font-size: 12px; color: #64748b; width: 100%;">발견된 OpCodes:</span>
                    </div>
            </div>
            <div id="logs"></div>
            <script>
                let rawLogs = [];
                let activeFilter = null;

                async function update() {
                    const r = await fetch('/logs');
                    const data = await r.json();
                    rawLogs = data.logs;
                    updateOpcodeBadges(data.opcodes);
                    render();
                }

                function updateOpcodeBadges(opcodes) {
                    const container = document.getElementById('opcodeContainer');
                    const existingBadges = container.querySelectorAll('.badge');
                    const currentValues = Array.from(existingBadges).map(b => b.innerText);
                    
                    opcodes.forEach(op => {
                        if (!currentValues.includes(op)) {
                            const span = document.createElement('span');
                            span.className = 'badge';
                            span.innerText = op;
                            span.onclick = () => {
                                activeFilter = (activeFilter === op) ? null : op;
                                document.querySelectorAll('.badge').forEach(b => b.classList.remove('active'));
                                if (activeFilter) span.classList.add('active');
                                render();
                            };
                            container.appendChild(span);
                        }
                    });
                }

                function render() {
                    const keyword = document.getElementById('searchInput').value.toLowerCase();
                    const filtered = rawLogs.filter(l => {
                        const matchesKeyword = l.opcode.toLowerCase().includes(keyword) || 
                                               l.text.toLowerCase().includes(keyword) ||
                                               l.pid.toString().includes(keyword);
                        const matchesFilter = activeFilter ? (l.opcode === activeFilter) : true;
                        return matchesKeyword && matchesFilter;
                    });

                    document.getElementById('logs').innerHTML = filtered.map(l => `
                        <div class="log-item" style="border-left: 4px solid ${l.text ? '#facc15' : '#334155'}">
                            <span>${l.time}</span>
                            <span style="color:#94a3b8">PID:${l.pid}</span>
                            <span style="color:#64748b">${l.port}</span>
                            <span style="color:#64748b; font-size:11px;">${l.dest}</span>
                            <span class="tag-opcode">${l.opcode}</span>
                            <span>${l.size}B</span>
                            <span class="text-content">${l.text}</span>
                            <div class="hex-data">DATA: ${l.data}</div>
                        </div>
                    `).join('');
                }

                async function startRec() { await fetch('/record/start'); document.getElementById('recStatus').style.display = 'inline'; }
                async function stopRec() { 
                    document.getElementById('recStatus').style.display = 'none'; 
                    window.location.href = '/record/stop'; 
                }

                setInterval(update, 1000);
            </script>
        </body>
    </html>
    """

@app.get("/logs")
def get_logs(): 
    return {"logs": captured_data, "opcodes": sorted(list(found_opcodes))}

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
    filename = f"recon_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return Response(content=content, media_type="application/json", headers={"Content-Disposition": f"attachment; filename={filename}"})

if __name__ == "__main__":
    threading.Thread(target=lambda: sniff(prn=packet_callback, store=0, filter="not port 8000"), daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
