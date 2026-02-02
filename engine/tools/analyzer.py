import datetime, struct, threading, psutil, socket, json, re
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
import uvicorn
from scapy.all import sniff, Raw, IP, UDP, TCP

app = FastAPI()
captured_data = [] 

# --- [통합 필터 설정] ---
# 1. 화이트리스트: 0500(시스템)만 일단 통과
WHITELIST_OPCODE = "0500"

# 2. 정규식 블랙리스트: 순위 외침 제거
CHAT_FILTER_PATTERN = re.compile(r"\(\d+위\) \[.+\]|\(999\+\) \[.+\]")

# 3. 사용자 지정 MsgID 블랙리스트 (UI에서 추가 가능)
blacklist_msgids = set(["86020000"]) # 예시: 핑이나 무의미한 알림 ID

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
        decoded = payload.decode('euc-kr', errors='ignore')
        printable = "".join(c for c in decoded if c.isprintable())
        return printable.strip()
    except: return ""

def packet_callback(packet):
    if packet.haslayer(Raw) and packet.haslayer(IP):
        if not (packet[IP].dst.startswith("119.205.203") or packet[IP].src.startswith("119.205.203")):
            return

        payload = packet[Raw].load
        if len(payload) < 4: return
        
        # [검증 1] OpCode 화이트리스트 (0500만 허용)
        opcode = payload[2:4].hex()
        if opcode != WHITELIST_OPCODE:
            return

        # [검증 2] 상세 MsgID 추출 및 블랙리스트 검사
        msg_id = payload[4:8].hex() if len(payload) >= 8 else "00000000"
        if msg_id in blacklist_msgids:
            return

        # [검증 3] 정규식 기반 외침 제거
        decoded_text = try_decode(payload)
        if CHAT_FILTER_PATTERN.search(decoded_text):
            return

        # 모든 검증을 통과한 '진짜 시스템 패킷'만 저장
        sport, dport = (packet[IP].sport, packet[IP].dport) if packet.haslayer(TCP) or packet.haslayer(UDP) else (0,0)
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

        captured_data.insert(0, entry)
        if len(captured_data) > 1000: captured_data.pop()

@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <html>
        <head>
            <title>RECON v9 - Ultimate Filter</title>
            <style>
                body { font-family: 'Malgun Gothic', sans-serif; margin: 0; background: #0f172a; color: #f8fafc; display: flex; flex-direction: column; height: 100vh; }
                .header { background: #1e293b; padding: 15px; border-bottom: 2px solid #334155; display: flex; justify-content: space-between; align-items: center; }
                .container { display: flex; flex: 1; overflow: hidden; }
                .sidebar { width: 320px; background: #1e293b; border-right: 2px solid #334155; padding: 15px; overflow-y: auto; }
                .main { flex: 1; padding: 20px; overflow-y: auto; }
                .log-item { background: #1e293b; padding: 12px; border-radius: 8px; margin-bottom: 8px; display: grid; grid-template-columns: 100px 100px 1fr 60px; gap: 15px; font-size: 13px; border-left: 5px solid #3b82f6; }
                .badge-id { background: #7c3aed; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-weight: bold; }
                .btn { cursor: pointer; border: none; padding: 5px 10px; border-radius: 4px; font-weight: bold; }
                .btn-danger { background: #ef4444; color: white; margin-top: 5px; width: 100%; }
                .card { background: #334155; padding: 10px; border-radius: 6px; margin-bottom: 10px; }
                .text-yellow { color: #facc15; font-weight: bold; }
            </style>
        </head>
        <body>
            <div class="header">
                <strong>RECON ENGINE v9 (0500 + Regex + MsgID Filter)</strong>
                <button class="btn" onclick="fetch('/clear')">로그 초기화</button>
            </div>
            <div class="container">
                <div class="sidebar">
                    <h4>MsgID 그룹 및 제외</h4>
                    <p style="font-size:11px; color:#94a3b8">아래 리스트에서 반복되는 무의미한 ID를 차단하세요.</p>
                    <div id="summaryList"></div>
                    <hr style="border:0.5px solid #334155;">
                    <h4>차단된 MsgID</h4>
                    <div id="blacklistDisplay" style="font-size:11px; color:#ef4444; word-break:break-all;"></div>
                </div>
                <div class="main" id="logs"></div>
            </div>
            <script>
                async function update() {
                    const r = await fetch('/data');
                    const d = await r.json();
                    
                    // 요약 리스트 업데이트
                    document.getElementById('summaryList').innerHTML = d.summary.map(s => `
                        <div class="card">
                            <div style="display:flex; justify-content:space-between">
                                <span class="badge-id">${s.id}</span>
                                <span>${s.count}건</span>
                            </div>
                            <button class="btn btn-danger" onclick="addFilter('${s.id}')">이 ID 차단하기</button>
                        </div>
                    `).join('');

                    document.getElementById('blacklistDisplay').innerHTML = d.blacklist.join(', ');

                    // 로그 업데이트
                    document.getElementById('logs').innerHTML = d.logs.map(l => `
                        <div class="log-item">
                            <span style="color:#94a3b8">${l.time}</span>
                            <span class="badge-id">${l.msg_id}</span>
                            <div>
                                <div class="text-yellow">${l.text || '(텍스트 없음)'}</div>
                                <div style="font-family:monospace; font-size:11px; color:#64748b; word-break:break-all;">${l.data}</div>
                            </div>
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
        mid = l['msg_id']
        summary[mid] = summary.get(mid, 0) + 1
    
    return {
        "logs": captured_data,
        "summary": [{"id": k, "count": v} for k, v in sorted(summary.items(), key=lambda x: x[1], reverse=True)],
        "blacklist": list(blacklist_msgids)
    }

@app.get("/filter/add")
def add_filter(id: str):
    blacklist_msgids.add(id)
    return {"ok": True}

@app.get("/clear")
def clear_logs():
    captured_data.clear()
    return {"ok": True}

if __name__ == "__main__":
    threading.Thread(target=lambda: sniff(prn=packet_callback, store=0, filter="not port 8000"), daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
