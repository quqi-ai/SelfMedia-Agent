"""配置加载：项目根目录定位 + JSON 配置读取。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .utils import read_json

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    root: Path
    config: dict[str, Any]
    sources: dict[str, Any]

    @property
    def data_root(self) -> Path:
        return self.root / self.config.get("run_root", "data")

    def workdir(self, date: str) -> Path:
        return self.data_root / date

    @property
    def llm(self) -> dict[str, Any]:
        return self.config.get("llm", {})

    @property
    def audio(self) -> dict[str, Any]:
        return self.config.get("audio", {})

    @property
    def publish(self) -> dict[str, Any]:
        return self.config.get("publish", {})

    @property
    def gates(self) -> dict[str, Any]:
        return self.config.get("gates", {})


def load_settings(root: Path | None = None) -> Settings:
    root = root or ROOT
    cfg = read_json(root / "config" / "config.json", {}) or {}
    src = read_json(root / "config" / "sources.json", {}) or {}
    if not cfg:
        raise FileNotFoundError(f"配置文件缺失：{root / 'config' / 'config.json'}")
    return Settings(root=root, config=cfg, sources=src)
