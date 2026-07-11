import os
import json

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")

class ConfigService:
    @staticmethod
    def get_config():
        default_config = {
            "crawler_aktif": True,
            "jam_update": "09:00",
            "rentang_data": "5",
            "auto_hapus": True,
            "ai_aktif": True
        }
        if not os.path.exists(CONFIG_PATH):
            return default_config
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Merge with defaults
                return {**default_config, **data}
        except Exception:
            return default_config

    @staticmethod
    def save_config(new_config):
        config = ConfigService.get_config()
        config.update(new_config)
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
        return config
