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
        if not os.path.exists(file_path):
            return None
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    @classmethod
    def init_app_config(cls, mapping_filename, webhook_url):
        base_path = cls.get_base_path()
        mapping_full_path = os.path.join(base_path, mapping_filename)
        mapping_data = cls.load_json(mapping_full_path)
        if mapping_data:
            cls.set_global("raid_mapping", mapping_data)
        cls.set_global("discord_url", os.getenv("DISCORD_WEBHOOK_URL", webhook_url))
        print(f"[*] 설정 로드 완료: {mapping_full_path}")

class Notifier:
    def send_discord(self, message):
        url = ConfigManager.get_global("discord_url")
        if url and url.startswith("http"):
            try:
                requests.post(url, json={"content": message}, timeout=5)
            except:
                pass
