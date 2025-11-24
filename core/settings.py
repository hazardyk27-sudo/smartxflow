import os
import json
from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class Settings:
    scrape_value: int = 1
    scrape_unit_index: int = 0
    cookie_string: Optional[str] = None

class SettingsManager:
    def __init__(self, path: str):
        self.path = path
    def load(self) -> Settings:
        if not os.path.exists(self.path):
            return Settings()
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        v = int(data.get("scrape_value", 1))
        u = int(data.get("scrape_unit_index", 0))
        c = data.get("cookie_string")
        return Settings(scrape_value=max(1, v), scrape_unit_index=0 if u == 0 else 1, cookie_string=c)
    def save(self, s: Settings) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(asdict(s), f, ensure_ascii=False, indent=2)