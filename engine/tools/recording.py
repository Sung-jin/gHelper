import json
import os
import datetime
import threading
import time

class PacketRecorder:
    def __init__(self, start_hour=19, end_hour=2, interval_min=10, log_dir="logs"):
        self.start_hour = start_hour
        self.end_hour = end_hour
        self.interval_min = interval_min
        self.log_dir = log_dir
        self.buffer = []
        self.last_save_time = datetime.datetime.now()
        
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

    def is_recording_time(self):
        curr_h = datetime.datetime.now().hour
        if self.start_hour <= curr_h or curr_h < self.end_hour:
            return True
        return False

    def add_entry(self, entry):
        if self.is_recording_time():
            self.buffer.append(entry)
            # 설정된 시간이 지나면 자동 저장
            if (datetime.datetime.now() - self.last_save_time).seconds >= self.interval_min * 60:
                self.save_to_file()

    def save_to_file(self):
        if not self.buffer:
            return
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # 1. 저장할 폴더 경로를 먼저 계산합니다.
        target_dir = os.path.join(self.log_dir, date_str)
        
        # 2. [핵심] 해당 날짜의 하위 폴더가 없으면 생성합니다.
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)
            print(f"[*] 새 로그 폴더 생성됨: {target_dir}")
        
        # 3. 최종 파일 경로 계산
        filename = os.path.join(target_dir, f"packet_{timestamp}.json")
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.buffer, f, indent=2)
            self.buffer = []
            self.last_save_time = datetime.datetime.now()
            print(f"[+] 패킷 저장 완료: {filename}") # 저장 확인용 출력
        except Exception as e:
            print(f"[!] 저장 오류: {e}")

    def _monitoring_loop(self):
        """CMD에 상태만 표시하는 루프"""
        while True:
            status = "🟢 패킷 녹화 중..." if self.is_recording_time() else "🟡 녹화 대기 중 (시간 외)"
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {status}")
            time.sleep(600) # 10분마다 상태 출력

    def start_monitoring_thread(self):
        thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        thread.start()
