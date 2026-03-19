"""
Загрузчик config.yaml
Перечитывает файл при каждом обращении — можно менять на лету.
"""

import yaml
from functools import lru_cache
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config() -> dict:
    """Читает и возвращает конфиг. Вызывай при каждом запросе чтобы подхватывать изменения."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get(key: str, default=None):
    """Удобный доступ по точечному пути: get('model.temperature')"""
    cfg = load_config()
    keys = key.split(".")
    val = cfg
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k)
        else:
            return default
    return val if val is not None else default
