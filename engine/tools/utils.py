import json
import os
import sys
import requests

class ConfigManager:
    _global_config = {}

    @staticmethod
    def get_base_path():
        """
        실행 파일(.exe) 또는 스크립트가 있는 실제 폴더 경로를 반환
        PyInstaller 의 frozen 상태를 체크하여 외부 파일을 참조
        """
        if getattr(sys, 'frozen', False):
            # .exe 파일로 실행 중인 경우
            return os.path.dirname(sys.executable)
        # .py 스크립트로 실행 중인 경우
        return os.path.dirname(os.path.abspath(__file__))

    @classmethod
    def set_global(cls, key, value):
        cls._global_config[key] = value

    @classmethod
    def get_global(cls, key, default=None):
        return cls._global_config.get(key, default)

    @staticmethod
    def load_json(cls, file_path):
        base_path = cls.get_base_path()
        mapping_full_path = os.path.join(base_path, file_path)

        if not os.path.exists(mapping_full_path):
            print(f"\n[Error] 파일을 찾을 수 없습니다: {file_path}")
            return None

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[Error] {file_path} 로드 실패: {e}")
            return None

    @classmethod
    def init_app_config(cls, mapping_filename, webhook_url):
        """
        앱 초기화 시 파일명만 받아서 get_base_path()와 결합하여 경로를 설정
        """
        # 실행 파일 옆의 실제 경로를 계산
        base_path = cls.get_base_path()
        mapping_full_path = os.path.join(base_path, mapping_filename)

        # 1. 매핑 데이터 로드
        mapping_data = cls.load_json(mapping_full_path)
        if mapping_data:
            cls.set_global("raid_mapping", mapping_data)

        # 2. 웹훅 URL 설정 (환경 변수 우선)
        final_url = os.getenv("DISCORD_WEBHOOK_URL", webhook_url)
        cls.set_global("discord_url", final_url)

        print(f"[*] 설정 로드 완료: {mapping_full_path}")

class Notifier:
    def __init__(self):
        pass

    def send_discord(self, message):
        webhook_url = ConfigManager.get_global("discord_url")
        if webhook_url and webhook_url.startswith("http"):
            try:
                requests.post(webhook_url, json={"content": message}, timeout=5)
            except Exception as e:
                print(f"\n[!] 알림 전송 실패: {e}")