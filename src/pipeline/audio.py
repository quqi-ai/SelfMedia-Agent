"""口播稿生成 + 音频输出预留接口。"""
from __future__ import annotations

import json
from pathlib import Path

from ..config import Settings
from ..llm.base import BaseLLM
from ..models import NewsItem
from ..utils import load_prompt, write_json, write_text


class AudioRenderer:
    """音频输出预留：默认只写元数据；接入 TTS 时继承并覆盖 render()。"""

    def __init__(self, settings: Settings):
        self.settings = settings

    def prepare(self, script_md: str, workdir: Path) -> dict:
        audio_cfg = self.settings.audio
        out_dir = workdir / audio_cfg.get("output_dir", "audio")
        out_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "enabled": audio_cfg.get("enabled", False),
            "provider": audio_cfg.get("provider", "reserved"),
            "voice": audio_cfg.get("voice", ""),
            "format": audio_cfg.get("format", "mp3"),
            "script_chars": len(script_md),
            "estimated_minutes": round(len(script_md) / 320, 1),  # 中文约 320 字/分钟
            "output_path": str(out_dir / f"script.{audio_cfg.get('format', 'mp3')}"),
            "status": "reserved" if not audio_cfg.get("enabled") else "pending_tts",
        }
        write_json(out_dir / "audio_meta.json", meta)
        (out_dir / "README.md").write_text(
            "# 音频输出预留\n\n"
            "默认只生成本口播稿与 audio_meta.json。接入 TTS 时，在 "
            "`src/pipeline/audio.py::AudioRenderer.render()` 中调用 edge-tts / "
            "Azure TTS / 火山引擎等，将音频写入 output_path。\n\n"
            "发布流程与音频合成相互独立，均需人工确认。\n",
            encoding="utf-8",
        )
        return meta

    def render(self, script_md: str, workdir: Path) -> Path:
        raise NotImplementedError("音频合成接口预留：请接入具体 TTS  provider 后调用")


def generate_audio_script(settings: Settings, llm: BaseLLM, items: list[NewsItem],
                          workdir: Path, date: str) -> tuple[str, dict]:
    system = load_prompt(settings.root, "00_system")
    digest = "\n".join(
        f"{i+1}. [{it.category}] {it.title} | {it.source} | {it.published_at[:16]} | 摘要：{it.summary[:120]}"
        for i, it in enumerate(items[:12])
    )
    prompt = load_prompt(settings.root, "01_audio_script", date=date, digest=digest)
    resp = llm.complete(system, prompt)
    script_md = resp.text.strip()
    path = workdir / "audio_script.md"
    write_text(path, script_md)
    meta = AudioRenderer(settings).prepare(script_md, workdir)
    return script_md, meta
