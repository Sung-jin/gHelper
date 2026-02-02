import datetime, struct, threading, psutil, socket, platform, subprocess, json
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
import uvicorn
from scapy.all import sniff, Raw, IP, UDP, TCP

app = FastAPI()
captured_data = [] 
recording_data = [] 
is_recording = False
target_app = "city.exe"
port_info_cache = {}

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
    """바이트 데이터를 한글(EUC-KR)로 변환 시도"""
    try:
        # 한글 게임은 주로 EUC-KR을 사용합니다.
        decoded = payload.decode('euc-kr', errors='ignore')
        # 출력 가능한 문자들만 필터링 (노이즈 제거)
        printable = "".join(c for c in decoded if c.isprintable())
        return printable.strip() if len(printable.strip()) > 1 else ""
    except:
        return ""

def packet_callback(packet):
    global is_recording
    if packet.haslayer(Raw) and packet.haslayer(IP):
        # 게임 서버 IP 대역 필터링 (119.205.203.xxx)
        if not (packet[IP].dst.startswith("119.205.203") or packet[IP].src.startswith("119.205.203")):
            return

        payload = packet[Raw].load
        sport = 0; dport = 0
        if packet.haslayer(UDP): sport, dport = packet[UDP].sport, packet[UDP].dport
        elif packet.haslayer(TCP): sport, dport = packet[TCP].sport, packet[TCP].dport

        # 클라이언트 포트 판별 (보통 1024 이상의 포트가 클라이언트 쪽)
        client_port = sport if sport > 1024 else dport
        app_name, pid = get_detailed_port_info(client_port)
        
        # 분석 핵심 데이터 추출
        # 앞 2바이트: 전체 길이, 뒤 2바이트: 타입(OpCode) 가설 적용
        header = payload[:4].hex() 
        decoded_text = try_decode(payload)

        entry = {
            "time": datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3],
            "app": app_name,
            "pid": pid,
            "port": client_port,
            "dest": f"{packet[IP].dst}:{dport}",
            "header": header,
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
            <title>Game Packet Recon Engine</title>
            <style>
                body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 20px; background: #1a1a1a; color: #eee; }
                .controls { background: #2d2d2d; padding: 20px; border-radius: 12px; margin-bottom: 20px; position: sticky; top: 0; z-index: 100; box-shadow: 0 4px 15px rgba(0,0,0,0.5); display: flex; gap: 15px; align-items: center; }
                button { padding: 10px 20px; border-radius: 6px; border: none; cursor: pointer; font-weight: bold; transition: 0.2s; }
                .btn-start { background: #2e7d32; color: white; }
                .btn-stop { background: #c62828; color: white; }
                button:hover { opacity: 0.8; }
                .log-item { background: #262626; margin-bottom: 8px; padding: 12px; border-radius: 8px; border-left: 5px solid #444; display: grid; grid-template-columns: 100px 80px 80px 150px 100px 60px 1fr; gap: 10px; align-items: center; }
                .log-item:hover { background: #333; }
                .tag { padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: bold; text-align: center; }
                .tag-pid { background: #6a1b9a; color: white; }
                .tag-header { background: #0277bd; color: white; font-family: monospace; font-size: 14px; }
                .text-content { color: #ffeb3b; font-weight: bold; border-left: 2px solid #555; padding-left: 10px; }
                .hex-data { font-family: monospace; color: #777; font-size: 11px; grid-column: 1 / -1; margin-top: 5px; word-break: break-all; }
                .recording-status { color: #f44336; font-weight: bold; animation: blink 1s infinite; }
                @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0; } 100% { opacity: 1; } }
            </style>
        </head>
        <body>
            <div class="controls">
                <h2 style="margin:0; color:#4caf50;">Recon Engine</h2>
                <button class="btn-start" onclick="startRec()">녹화 시작</button>
                <button class="btn-stop" onclick="stopRec()">녹화 종료 및 저장</button>
                <span id="recStatus" style="display:none;" class="recording-status">● RECORDING</span>
                <input type="text" id="searchInput" placeholder="Header 또는 텍스트 검색..." oninput="render()" style="background:#444; color:white; border:1px solid #555; padding:8px; border-radius:4px; width:250px;">
                <span id="stat"></span>
            </div>
            <div id="logHeader" class="log-item" style="background:#444; font-weight:bold; position:sticky; top:85px;">
                <span>Time</span><span>PID</span><span>Port</span><span>Destination</span><span>Header</span><span>Size</span><span>Decoded Text</span>
            </div>
            <div id="logs"></div>
            <script>
                let rawLogs = [];
                async function update() {
                    const r = await fetch('/logs');
                    rawLogs = await r.json();
                    render();
                }
                function render() {
                    const keyword = document.getElementById('searchInput').value.toLowerCase();
                    const filtered = rawLogs.filter(l => 
                        l.header.toLowerCase().includes(keyword) || 
                        l.text.toLowerCase().includes(keyword) ||
                        l.pid.toString().includes(keyword)
                    );
                    document.getElementById('stat').innerText = `(${filtered.length} packets)`;
                    document.getElementById('logs').innerHTML = filtered.map(l => `
                        <div class="log-item" style="border-left-color: ${l.text ? '#ffeb3b' : '#444'}">
                            <span>${l.time}</span>
                            <span class="tag tag-pid">PID: ${l.pid}</span>
                            <span style="color:#aaa">${l.port}</span>
                            <span style="font-size:12px; color:#888">${l.dest}</span>
                            <span class="tag tag-header">${l.header}</span>
                            <span>${l.size}B</span>
                            <span class="text-content">${l.text}</span>
                            <div class="hex-data">RAW: ${l.data}</div>
                        </div>
                    `).join('');
                }
                async function startRec() {
                    await fetch('/record/start');
                    document.getElementById('recStatus').style.display = 'inline';
                }
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
def get_logs(): return captured_data

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
    # 포트 8000(FastAPI) 제외하고 스니핑
    threading.Thread(target=lambda: sniff(prn=packet_callback, store=0, filter="not port 8000"), daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
