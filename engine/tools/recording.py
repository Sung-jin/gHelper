import datetime
import time
import json
import os
import threading

class PacketRecorder:
    def __init__(self, start_hour=19, end_hour=2, interval_min=10, log_dir="logs"):
        """
        생성자: 녹화 설정값을 초기화합니다.
        """
        self.start_hour = start_hour
        self.end_hour = end_hour
        self.interval_min = interval_min
        self.log_dir = log_dir

        self.current_log_data = []
        self.current_file_label = ""

        # 저장 폴더 생성
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

    def is_recording_time(self):
        """현재 시간이 녹화 범위 내에 있는지 확인"""
        now = datetime.datetime.now()
        current_hour = now.hour

        if self.start_hour <= current_hour or current_hour < self.end_hour:
            return True
        return False

    def monitor_status(self):
        """별도 스레드에서 돌아갈 상태 표시 함수"""
        print(f"[*] 모니터링 시작 (활성 시간: {self.start_hour:02d}:00 ~ {self.end_hour:02d}:00)")
        while True:
            is_active = self.is_recording_time()
            status = "● 녹화 중" if is_active else f"○ 대기 중 ({self.start_hour:02d}:00 시작)"
            # \r을 사용하여 한 줄에서 계속 갱신
            print(f"\r현재 시간: {datetime.datetime.now().strftime('%H:%M:%S')} | 상태: {status} | 쌓인 패킷: {len(self.current_log_data)}개", end="")
            time.sleep(1)

    def start_monitoring_thread(self):
        thread = threading.Thread(target=self.monitor_status, daemon=True)
        thread.start()

    def _save_to_file(self, data_to_save, label):
        """내부적인 파일 저장 함수 (비동기 호출용)"""
        if not data_to_save:
            return

        filename = f"recon_{label}.json"
        filepath = os.path.join(self.log_dir, filename)

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)
            print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] 저장 완료: {filename} ({len(data_to_save)} 패킷)")
        except Exception as e:
            print(f"\n[!] 파일 저장 중 오류 발생: {e}")

    def add_entry(self, entry):
        now = datetime.datetime.now()

        rounded_minute = (now.minute // self.interval_min) * self.interval_min
        file_label = now.strftime("%Y%m%d_%H") + str(rounded_minute).zfill(2)

        # 1. 녹화 시간이 아닐 때
        if not self.is_recording_time():
            if self.current_log_data:
                # 쌓여있던 데이터가 있다면 비우면서 저장
                self._flush(self.current_file_label)
            return

        # 2. 처음 시작하거나, 라벨(시간대)이 바뀌었을 때 (10분 경과 시)
        if self.current_file_label != "" and self.current_file_label != file_label:
            self._flush(self.current_file_label)

        # 데이터 추가 및 라벨 갱신
        self.current_log_data.append(entry)
        self.current_file_label = file_label

    def _flush(self, label):
        """현재까지 쌓인 데이터를 즉시 파일로 넘기고 리스트를 비움"""
        if not self.current_log_data:
            return

        temp_data = self.current_log_data[:]
        self.current_log_data = []
        # 파일 저장은 백그라운드 스레드에서 진행 (게임 렉 방지)
        threading.Thread(target=self._save_to_file, args=(temp_data, label), daemon=True).start()
