import json
import os
import sys
import requests

class ConfigManager:
    _global_config = {}

    @staticmethod
    def get_base_path():
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    @classmethod
    def set_global(cls, key, value):
        cls._global_config[key] = value

    @classmethod
    def get_global(cls, key, default=None):
        return cls._global_config.get(key, default)

    @staticmethod
    def load_json(file_path):
        """전달받은 절대 경로의 JSON 파일을 읽습니다."""
        if not os.path.exists(file_path):
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
        base_path = cls.get_base_path()
        mapping_full_path = os.path.join(base_path, mapping_filename)

        # 수정된 load_json 호출
        mapping_data = cls.load_json(mapping_full_path)
        if mapping_data:
            cls.set_global("raid_mapping", mapping_data)

        final_url = os.getenv("DISCORD_WEBHOOK_URL", webhook_url)
        cls.set_global("discord_url", final_url)
        print(f"[*] 설정 로드 완료: {mapping_full_path}")

class Notifier:
    def send_discord(self, message):
        webhook_url = ConfigManager.get_global("discord_url")
        if webhook_url and webhook_url.startswith("http"):
            try:
                requests.post(webhook_url, json={"content": message}, timeout=5)
            except Exception as e:
                print(f"\n[!] 알림 전송 실패: {e}")
