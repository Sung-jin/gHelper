import json
import os
import datetime
import threading
import time
from collections import OrderedDict


def parse_window_from_t(t_str: str, date_str: str) -> tuple:
    """
    entry['t'] 예: "22:47:00.020847" -> (date_str, "2240")
    고정 10분 구간: HH:00, HH:10, HH:20, HH:30, HH:40, HH:50
    """
    try:
        time_part = t_str.split(".")[0]
        parts = time_part.split(":")
        if len(parts) < 2:
            return (date_str, "0000")
        hh = int(parts[0])
        mm = int(parts[1])
        slot = (mm // 10) * 10
        hhmm = f"{hh:02d}{slot:02d}"
        return (date_str, hhmm)
    except (ValueError, IndexError):
        return (date_str, "0000")


class PacketRecorder:
    # 고정 10분 구간: hh:00~hh:10, hh:10~hh:20, ... hh:50~(hh+1):00
    WINDOW_MINUTES = 10

    def __init__(self, start_hour=19, end_hour=2, interval_min=10, log_dir="logs"):
        self.start_hour = start_hour
        self.end_hour = end_hour
        self.interval_min = interval_min
        self.log_dir = log_dir
        # window_key (date_str, hhmm) -> list of entries (순서 유지)
        self.window_buffers = OrderedDict()
        self.last_save_time = datetime.datetime.now()

        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

    def is_recording_time(self):
        curr_h = datetime.datetime.now().hour
        if self.start_hour <= curr_h or curr_h < self.end_hour:
            return True
        return False

    def _flush_window(self, key: tuple):
        """한 개 구간을 파일로 저장하고 버퍼에서 제거."""
        if key not in self.window_buffers or not self.window_buffers[key]:
            if key in self.window_buffers:
                del self.window_buffers[key]
            return
        date_str, hhmm = key
        target_dir = os.path.join(self.log_dir, date_str)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)
            print(f"[*] 새 로그 폴더 생성됨: {target_dir}")

        # packet_YYYYMMDD_HHMM.json → 해당 구간이 한눈에 보임 (예: 22:40~22:50)
        filename = os.path.join(target_dir, f"packet_{date_str.replace('-', '')}_{hhmm}.json")
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(self.window_buffers[key], f, indent=2)
            print(f"[+] 패킷 저장 완료: {filename} ({len(self.window_buffers[key])}개)")
        except Exception as e:
            print(f"[!] 저장 오류: {e}")
        del self.window_buffers[key]

    def add_entry(self, entry):
        if not self.is_recording_time():
            return

        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        t_str = entry.get("t") or ""
        key = parse_window_from_t(t_str, date_str)

        # 이전 구간들(이 패킷보다 앞선 구간)은 더 이상 패킷이 안 온다고 보고 저장
        to_flush = [k for k in self.window_buffers if k < key]
        for k in to_flush:
            self._flush_window(k)

        if key not in self.window_buffers:
            self.window_buffers[key] = []
        self.window_buffers[key].append(entry)

    def save_to_file(self):
        """남아 있는 모든 구간 버퍼를 파일로 저장 (종료 시 호출)."""
        for key in list(self.window_buffers.keys()):
            self._flush_window(key)
        self.last_save_time = datetime.datetime.now()

    def _monitoring_loop(self):
        """CMD에 상태만 표시하는 루프"""
        while True:
            status = "🟢 패킷 녹화 중..." if self.is_recording_time() else "🟡 녹화 대기 중 (시간 외)"
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {status}")
            time.sleep(600)

    def start_monitoring_thread(self):
        thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        thread.start()
