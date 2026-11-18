"""流程编排：把采集→整理→口播→选题→确认→写作→确认→发布串起来。"""
from __future__ import annotations

import json
from pathlib import Path

from . import gates
from .collectors import run_collectors
from .config import Settings, load_settings
from .gates import GateError
from .llm import build_llm
from .models import NewsItem, RunState, Topic, deduplicate, to_markdown_table
from .pipeline.audio import generate_audio_script
from .pipeline.rank import rank_items
from .pipeline.topics import generate_topics
from .pipeline.writing import (
    generate_wechat_draft, generate_xiaohongshu, render_wechat_html,
)
from .publisher import get_publisher
from .notifier import notify, notice_digest_ready, notice_drafts_ready, notice_publish_ready
from .utils import now_iso, read_json, write_json, write_text


def _state(workdir: Path, date: str) -> RunState:
    d = read_json(workdir / "state.json", None)
    return RunState.from_dict(d) if d else RunState(date=date)


def _save_state(workdir: Path, s: RunState) -> None:
    s.updated_at = now_iso()
    write_json(workdir / "state.json", s.to_dict())


def _load_items(workdir: Path) -> list[NewsItem]:
    return [NewsItem.from_dict(d) for d in (read_json(workdir / "news.json", []) or [])]


def _load_topics(workdir: Path) -> list[Topic]:
    return [Topic.from_dict(d) for d in (read_json(workdir / "topics.json", []) or [])]


def step_collect(settings: Settings, date: str, use_fixtures: bool = True) -> dict:
    workdir = settings.workdir(date)
    workdir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timedelta, timezone
    since = datetime.now(timezone(timedelta(hours=8)))
    items, warns = run_collectors(settings, since, use_fixtures)
    dd = settings.config.get("dedup", {})
    items = deduplicate(
        items,
        threshold=float(dd.get("title_similarity_threshold", 0.86)),
        drop_tracking=set(dd.get("drop_tracking_params", [])),
    )
    items = rank_items(items, settings.config)
    write_json(workdir / "news.json", [it.to_dict() for it in items])
    write_text(workdir / "digest.md",
               f"# 每日资讯整理（{date}）\n\n共 {len(items)} 条（已去重）\n\n" +
               to_markdown_table(items) + "\n")
    s = _state(workdir, date)
    s.stage = "collected"
    s.warnings = warns
    _save_state(workdir, s)
    return {"count": len(items), "warnings": warns, "workdir": str(workdir)}


def step_script(settings: Settings, date: str, llm) -> dict:
    workdir = settings.workdir(date)
    items = _load_items(workdir)
    if not items:
        raise RuntimeError("没有资讯，请先执行 collect")
    script, meta = generate_audio_script(settings, llm, items, workdir, date)
    s = _state(workdir, date)
    s.stage = "scripted"
    s.transcript_path = str(workdir / "audio_script.md")
    _save_state(workdir, s)
    return {"script": str(workdir / "audio_script.md"), "audio_meta": meta, "chars": len(script)}


def step_topics(settings: Settings, date: str, llm) -> dict:
    workdir = settings.workdir(date)
    items = _load_items(workdir)
    topics = generate_topics(settings, llm, items, workdir, date)
    s = _state(workdir, date)
    s.stage = "topics_pending"
    _save_state(workdir, s)
    delivery = notify(settings, notice_digest_ready(settings, date, workdir, len(topics)))
    return {"topics": [t.to_dict() for t in topics], "gate": "topics",
            "note": "选题已生成，等待人工确认", "notified": delivery}


def step_drafts(settings: Settings, date: str, llm) -> dict:
    workdir = settings.workdir(date)
    topics = [t for t in _load_topics(workdir) if t.status == "confirmed"]

    # 自动模式：从 approvals.json 读取已确认 id 并同步 topic 状态
    approved_ids = set(read_json(workdir / "approvals.json", {}).get("topics", {}).get("ids", []))
    topics = [t for t in topics if t.id in approved_ids] or [t for t in _load_topics(workdir) if t.id in approved_ids]
    if settings.gates.get("require_topic_approval", True):
        if not approved_ids:
            raise GateError("选题尚未人工确认，阻断写作。请先 approve --stage topics")
        topics = [t for t in _load_topics(workdir) if t.id in approved_ids]
    if not topics:
        raise GateError("没有已确认的选题，无法生成初稿")

    items = _load_items(workdir)
    drafts: list[dict] = []
    for t in topics:
        wd = generate_wechat_draft(settings, llm, t, items, workdir)
        html, warns = render_wechat_html(wd.body_markdown)
        wd.body_html = html
        write_text(workdir / f"{wd.id}_wechat.html", html)
        xd = generate_xiaohongshu(settings, llm, t, wd.body_markdown, workdir)
        drafts.extend([wd.to_dict(), xd.to_dict()])

    write_json(workdir / "drafts.json", drafts)
    s = _state(workdir, date)
    s.stage = "drafts_pending"
    _save_state(workdir, s)
    delivery = notify(settings, notice_drafts_ready(settings, date, workdir, drafts))
    return {"drafts": drafts, "gate": "drafts",
            "note": "初稿已生成（公众号优先 + 小红书），等待人工确认", "notified": delivery}


def step_publish_prepare(settings: Settings, date: str) -> dict:
    workdir = settings.workdir(date)
    drafts = [d for d in (read_json(workdir / "drafts.json", []) or [])]
    approved = set(read_json(workdir / "approvals.json", {}).get("drafts", {}).get("ids", []))
    if settings.gates.get("require_draft_approval", True) and not approved:
        raise GateError("初稿尚未人工确认，阻断发布包生成。请先 approve --stage drafts")
    results = []
    for d in drafts:
        if not approved or d["id"] in approved:
            pub = get_publisher(d["platform"], workdir)
            from .models import ArticleDraft
            res = pub.prepare(ArticleDraft(**{k: v for k, v in d.items() if k in ArticleDraft.__dataclass_fields__}),
                              require_confirm=settings.gates.get("require_publish_approval", True))
            results.append({"id": d["id"], **res.to_dict()})
    s = _state(workdir, date)
    s.stage = "publish_pending"
    _save_state(workdir, s)
    delivery = notify(settings, notice_publish_ready(settings, date, workdir, len(results)))
    return {"results": results, "note": "仅生成待发布包，未执行任何线上发布", "notified": delivery}


def run_all(settings: Settings, date: str, auto_approve: bool = False,
            use_fixtures: bool = True) -> dict:
    """一键跑通到发布包阶段（默认在确认门前停止；auto_approve 仅用于本地验证）。"""
    llm = build_llm(settings.llm)
    out: dict = {"date": date}
    out["collect"] = step_collect(settings, date, use_fixtures)
    out["script"] = step_script(settings, date, llm)
    out["topics"] = step_topics(settings, date, llm)

    workdir = settings.workdir(date)
    if auto_approve:
        ids = [t["id"] for t in (read_json(workdir / "topics.json", []) or [])]
        gates.approve(workdir, "topics", ids, note="auto_approve（仅本地验证）")
    out["drafts"] = step_drafts(settings, date, llm)

    if auto_approve:
        ids = [d["id"] for d in (read_json(workdir / "drafts.json", []) or [])]
        gates.approve(workdir, "drafts", ids, note="auto_approve（仅本地验证）")
    out["publish"] = step_publish_prepare(settings, date)
    return out
