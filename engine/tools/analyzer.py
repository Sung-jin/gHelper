import datetime, struct, threading, psutil, socket, platform, subprocess, json
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
import uvicorn
from scapy.all import sniff, Raw, IP, UDP, TCP

app = FastAPI()
captured_data = [] # 실시간 모니터링용 (최신 1000개)
recording_data = [] # 녹화용 (무제한)
is_recording = False
target_app = None
port_process_cache = {}

def get_process_name_by_port(port):
    if port == 0: return "System/Kernel"
    if port in port_process_cache: return port_process_cache[port]
    try:
        for conn in psutil.net_connections(kind='inet'):
            if conn.laddr.port == port and conn.pid:
                name = psutil.Process(conn.pid).name()
                port_process_cache[port] = name
                return name
    except: pass
    if platform.system() == "Darwin":
        try:
            result = subprocess.check_output(["lsof", "-t", f"-i:{port}"], stderr=subprocess.STDOUT)
            pids = result.decode().strip().split('\n')
            if pids:
                pid = int(pids[0]); name = psutil.Process(pid).name()
                port_process_cache[port] = name; return name
        except: pass
    return "Unknown"

def get_server_time_candidate(payload):
    try:
        min_ts, max_ts = 1700000000, 1900000000
        for i in range(len(payload) - 3):
            val_be = struct.unpack('>I', payload[i:i+4])[0]
            if min_ts < val_be < max_ts:
                return {"pos": i, "ts": val_be, "dt": datetime.datetime.fromtimestamp(val_be).strftime('%Y-%m-%d %H:%M:%S')}
        return None
    except: return None

def packet_callback(packet):
    global is_recording, target_app
    if packet.haslayer(Raw) and packet.haslayer(IP):
        payload = packet[Raw].load
        sport = 0; dport = 0
        if packet.haslayer(UDP): sport, dport = packet[UDP].sport, packet[UDP].dport
        elif packet.haslayer(TCP): sport, dport = packet[TCP].sport, packet[TCP].dport

        app_name = get_process_name_by_port(sport)
        dst_ip = packet[IP].dst

        # 기본 정보 구성
        entry = {
            "time": datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3],
            "app": app_name,
            "dest": f"{dst_ip}:{dport}",
            "data": payload.hex(),
            "size": len(payload)
        }

        # 시간 후보군 분석
        candidate = get_server_time_candidate(payload)
        if candidate:
            entry["candidate"] = f"Pos {candidate['pos']}: {candidate['ts']} ({candidate['dt']})"

        # 1. 실시간 모니터링 리스트 추가
        if candidate: # 모니터링은 시간 후보가 있는 것 위주로
            captured_data.insert(0, entry)
            if len(captured_data) > 1000: captured_data.pop()

        # 2. 녹화 로직
        if is_recording:
            if target_app == "All Apps" or app_name == target_app:
                recording_data.append(entry)

@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <html>
        <head>
            <style>
                body { font-family: 'Malgun Gothic', sans-serif; padding: 20px; background: #f0f2f5; }
                .controls { background: white; padding: 20px; border-radius: 12px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
                button { padding: 10px 20px; border-radius: 6px; border: none; cursor: pointer; font-weight: bold; }
                .btn-start { background: #4caf50; color: white; }
                .btn-stop { background: #f44336; color: white; }
                select, input { padding: 10px; border-radius: 6px; border: 1px solid #ddd; }
                .log-item { background: white; margin-bottom: 10px; padding: 15px; border-radius: 10px; border-left: 6px solid #2196f3; }
                .tag-app { background: #e91e63; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
                .recording-status { color: red; font-weight: bold; animation: blink 1s infinite; }
                @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0; } 100% { opacity: 1; } }
            </style>
        </head>
        <body>
            <div class="controls">
                <strong>대상 앱:</strong>
                <select id="appSelect"></select>
                <button class="btn-start" onclick="startRec()">녹화 시작</button>
                <button class="btn-stop" onclick="stopRec()">녹화 종료 및 다운로드</button>
                <span id="recStatus" style="display:none;" class="recording-status">● 녹화 중...</span>
                <input type="text" id="searchInput" placeholder="HEX 데이터 검색..." oninput="render()">
                <span id="stat"></span>
            </div>
            <div id="logs"></div>
            <script>
                let rawLogs = [];
                let knownApps = new Set();

                async function update() {
                    const r = await fetch('/logs');
                    rawLogs = await r.json();
                    updateSelectBox();
                    render();
                }

                function updateSelectBox() {
                    const select = document.getElementById('appSelect');
                    const currentApps = [...new Set(rawLogs.map(l => l.app))].sort();
                    
                    // 기존에 없던 앱이 추가되었을 때만 셀렉트박스 갱신 (깜빡임 방지)
                    let isChanged = false;
                    currentApps.forEach(a => { if(!knownApps.has(a)) { knownApps.add(a); isChanged = true; } });
                    
                    if (isChanged || select.options.length === 0) {
                        const currentVal = select.value;
                        select.innerHTML = '<option value="All Apps">모든 앱 녹화</option>' + 
                            [...knownApps].map(a => `<option value="${a}" ${a===currentVal?'selected':''}>${a}</option>`).join('');
                    }
                }

                function render() {
                    const keyword = document.getElementById('searchInput').value.toLowerCase();
                    // 앱 이름, 목적지, HEX 데이터 중 하나라도 포함되면 표시
                    const filtered = rawLogs.filter(l => 
                        l.app.toLowerCase().includes(keyword) || 
                        l.dest.toLowerCase().includes(keyword) ||
                        l.data.toLowerCase().includes(keyword)
                    );
                    document.getElementById('stat').innerText = `(${filtered.length}개 검색됨)`;
                    document.getElementById('logs').innerHTML = filtered.slice(0, 50).map(l => `
                        <div class="log-item">
                            <span style="color:#888">[${l.time}]</span>
                            <span class="tag-app">${l.app}</span>
                            <span style="font-weight:bold; color:#2196f3;">To: ${l.dest}</span>
                            <div style="margin-top:10px; font-size:16px;">${l.candidate || 'No Timestamp'}</div>
                            <div style="font-family:monospace; font-size:12px; color:#999; word-break:break-all;">HEX: ${l.data.substring(0, 100)}...</div>
                        </div>
                    `).join('');
                }

                async function startRec() {
                    const app = document.getElementById('appSelect').value;
                    await fetch(`/record/start?app=${encodeURIComponent(app)}`);
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
def start_recording(app: str):
    global is_recording, target_app, recording_data
    recording_data = [] # 이전 기록 초기화
    target_app = app
    is_recording = True
    return {"status": "started", "target": app}

@app.get("/record/stop")
def stop_recording():
    global is_recording, recording_data
    is_recording = False
    # 제가 분석하기 좋은 JSON 형태로 반환
    content = json.dumps(recording_data, indent=2)
    filename = f"capture_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

if __name__ == "__main__":
    threading.Thread(target=lambda: sniff(prn=packet_callback, store=0, filter="not port 8000"), daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8000)