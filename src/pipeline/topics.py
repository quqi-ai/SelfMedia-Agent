"""选题生成：结合资讯 + 热点问题 + 公众号素材，产出待确认的选题列表。"""
from __future__ import annotations

import json
from pathlib import Path

from ..config import Settings
from ..llm.base import BaseLLM
from ..models import NewsItem, Topic
from ..utils import extract_json, load_prompt, read_json, write_json


def load_hot_questions(settings: Settings) -> list[dict]:
    src = settings.sources.get("hot_questions", {})
    fp = settings.root / src.get("fallback_fixture", "fixtures/hot_questions_sample.json")
    data = read_json(fp, []) or []
    # 配置了真实 endpoint 时可在此扩展；当前仅使用本地清单作为热点问题来源
    return data[:12]


def generate_topics(settings: Settings, llm: BaseLLM, items: list[NewsItem],
                    workdir: Path, date: str) -> list[Topic]:
    system = load_prompt(settings.root, "00_system")
    digest = "\n".join(f"- {it.title}（{it.source}，热度 {it.heat_score}）" for it in items[:15])
    hot = "\n".join(
        f"- [{q.get('source','?')}] {q.get('question','')}（热度 {q.get('heat','?')}）"
        for q in load_hot_questions(settings)
    )
    prompt = load_prompt(settings.root, "02_topics", date=date, digest=digest, hot_questions=hot)

    resp = llm.complete(system, prompt)
    try:
        raw = extract_json(resp.text)
        if isinstance(raw, dict):
            raw = raw.get("topics", [raw])
        topics = [Topic.from_dict({**t, "id": t.get("id") or f"t-{i+1:03d}"})
                  for i, t in enumerate(raw[:8])]
    except Exception:
        # LLM 输出不可解析时，回退到 fixture，保证流程可继续
        fb = settings.root / settings.sources.get("fixtures", {}).get("topics", "fixtures/topics_sample.json")
        raw = read_json(fb, []) or []
        topics = [Topic.from_dict(t) for t in raw[:5]]

    if not topics:
        topics = [Topic(id="t-001", title="待补充选题", angle="", core_thesis="", priority="B")]

    write_json(workdir / "topics.json", [t.to_dict() for t in topics])
    return topics
