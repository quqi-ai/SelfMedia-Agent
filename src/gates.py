"""人工确认门控：选题 → 初稿 → 发布，三道门，写入 approvals.json 留痕。"""
from __future__ import annotations

from pathlib import Path

from .utils import now_iso, read_json, write_json


class GateError(RuntimeError):
    """未通过人工确认时抛出，阻断后续流程。"""


APPROVAL_FILE = "approvals.json"


def _load(workdir: Path) -> dict:
    return read_json(workdir / APPROVAL_FILE, {}) or {}


def _save(workdir: Path, data: dict) -> None:
    write_json(workdir / APPROVAL_FILE, data)


def approve(workdir: Path, stage: str, ids: list[str], note: str = "") -> dict:
    """人工确认。stage ∈ topics / drafts / publish。"""
    data = _load(workdir)
    rec = data.setdefault(stage, {"ids": [], "note": "", "at": "", "by": "human"})
    rec["ids"] = list(dict.fromkeys(rec.get("ids", []) + ids))
    rec["note"] = note
    rec["at"] = now_iso()
    _save(workdir, data)
    return rec


def reject(workdir: Path, stage: str, ids: list[str], note: str = "") -> dict:
    data = _load(workdir)
    rec = data.setdefault(stage + "_rejected", {"ids": [], "note": "", "at": ""})
    rec["ids"] = list(dict.fromkeys(rec.get("ids", []) + ids))
    rec["note"] = note
    rec["at"] = now_iso()
    _save(workdir, data)
    return rec


def ensure_approved(workdir: Path, stage: str, ids: list[str]) -> None:
    """校验：要求的 ids 必须全部已确认，否则阻断。"""
    approved = set(_load(workdir).get(stage, {}).get("ids", []))
    missing = [i for i in ids if i not in approved]
    if missing:
        raise GateError(
            f"人工确认未通过（stage={stage}）。待确认 ID：{missing}。"
            f"请先执行：python -m src.cli approve --stage {stage} --ids {','.join(missing)} --note '...'"
        )


def is_approved(workdir: Path, stage: str, item_id: str) -> bool:
    return item_id in set(_load(workdir).get(stage, {}).get("ids", []))


def summary(workdir: Path) -> dict:
    return _load(workdir)
