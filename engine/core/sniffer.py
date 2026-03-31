import sys
import json
import psutil
import importlib.util
import os
from scapy.all import sniff

def get_active_ports(pid):
    ports = set()
    try:
        for conn in psutil.net_connections(kind='inet'):
            if conn.pid == pid:
                if conn.status == 'ESTABLISHED' or conn.status == 'LISTEN':
                    ports.add(conn.laddr.port)

        # 포트 추출 결과를 로그로 강제 전송하여 확인
        print(json.dumps({"type": "STATUS", "content": f"추출된 포트: {list(ports)} (PID: {pid})"}))

    except Exception as e:
        print(json.dumps({"type": "ERROR", "content": f"Port extraction error: {str(e)}"}))
    return list(ports)

def start_engine(pid, plugin_path):
    # 1. 동적 포트 감지
    active_ports = get_active_ports(pid)
    print(active_ports)
    if not active_ports:
        # 포트를 찾지 못해도 전체 스니핑을 시도하거나 에러를 반환가능
        print(json.dumps({"type": "STATUS", "content": "No active ports found for PID. Sniffing broadly."}))
        filter_str = ""
    else:
        # Scapy 필터 생성 (예: "tcp port 12345 or udp port 12345 ...")
        filter_str = " or ".join([f"tcp port {p} or udp port {p}" for p in active_ports])
        print(json.dumps({"type": "STATUS", "content": f"Sniffing on ports: {active_ports}"}))

    # 2. 플러그인 동적 로드
    try:
        if not os.path.exists(plugin_path):
            raise FileNotFoundError(f"Plugin not found at {plugin_path}")

        spec = importlib.util.spec_from_file_location("plugin", plugin_path)
        plugin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(plugin)
    except Exception as e:
        print(json.dumps({"type": "ERROR", "content": f"Plugin load failed: {str(e)}"}))
        return

    def packet_callback(packet):
        try:
            parsed_data = plugin.parse(packet)

            if parsed_data:
                print(json.dumps(parsed_data))
                sys.stdout.flush()
            else:
                pass
        except Exception as e:
            # 에러 발생 시에만 STATUS 혹은 ERROR 타입으로 출력
            # print(json.dumps({"type": "ERROR", "content": f"Callback error: {str(e)}"}))
            pass

    # 3. 스니핑 시작
    try:
        # 1. 필터를 제거하고 'ip'로만 설정 (가장 넓은 범위)
        final_filter = "ip"

        # 2. Scapy가 잡고 있는 기본 인터페이스 확인 로그
        from scapy.all import conf
        print(json.dumps({"type": "STATUS", "content": f"Default Interface: {conf.iface}"}))

        # 3. 스니핑 (만약 아무것도 안 잡힌다면 iface="en0" 등으로 강제 지정 테스트 필요)
        sniff(prn=packet_callback, filter=final_filter, store=0)

    except Exception as e:
        print(json.dumps({"type": "ERROR", "content": f"Sniffing error: {str(e)}"}))

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"type": "ERROR", "content": "Usage: sniffer.py [PID] [PLUGIN_PATH]"}))
        sys.exit(1)

    try:
        target_pid = int(sys.argv[1])
        plugin_script = sys.argv[2]
        start_engine(target_pid, plugin_script)
    except ValueError:
        print(json.dumps({"type": "ERROR", "content": "Invalid PID format"}))