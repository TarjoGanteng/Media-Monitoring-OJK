import os
import json

def _get_config_path():
    """Mendapatkan path config.json dengan fallback ke /tmp jika read-only di Vercel."""
    p = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
    try:
        test_file = p + ".tmp"
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("1")
        if os.path.exists(test_file):
            os.remove(test_file)
        return p
    except Exception:
        import tempfile
        return os.path.join(tempfile.gettempdir(), "config.json")


class ConfigService:
    @staticmethod
    def get_config():
        default_config = {
            "crawler_aktif": True,
            "jam_update": "09:00",
            "rentang_data": "5",
            "auto_hapus": True,
            "ai_aktif": True,
        }
        config_path = _get_config_path()
        if not os.path.exists(config_path):
            return default_config
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {**default_config, **data}
        except Exception:
            return default_config

    @staticmethod
    def save_config(new_config):
        config = ConfigService.get_config()
        config.update(new_config)
        config_path = _get_config_path()
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4)
        except Exception:
            import tempfile
            alt_path = os.path.join(tempfile.gettempdir(), "config.json")
            with open(alt_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4)
        return config
