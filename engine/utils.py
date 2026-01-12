import psutil
import json

def get_process_list():
    process_list = []
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            # 중복 제거를 원한다면 이름만 담거나, PID를 함께 담아 리스트업
            process_list.append(proc.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return json.dumps(process_list)

if __name__ == "__main__":
    print(get_process_list())