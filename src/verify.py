"""本地自检：在临时目录跑通全流程，验证门控、去重、排版校验，不污染正式数据。"""
from __future__ import annotations

import tempfile
from pathlib import Path

from . import gates
from .config import load_settings
from .models import NewsItem, deduplicate
from .pipeline.rank import rank_items
from .pipeline.writing import render_wechat_html
from .workflow import run_all


def run_verify() -> dict:
    checks: list[dict] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(cond), "detail": detail})

    settings = load_settings()

    # 1. 去重 + URL 归一化
    a = NewsItem(source="A", title="智谱发布新一代开源Agent模型工具调用提升",
                 url="https://example.com/a?utm_source=rss", published_at="2026-11-16T10:00:00+08:00",
                 summary="摘要" * 30)
    b = NewsItem(source="B", title="智谱发布新一代开源 Agent 模型，工具调用提升明显",
                 url="https://www.example.com/a", published_at="2026-11-16T11:00:00+08:00",
                 summary="更长的摘要" * 30)
    ded = deduplicate([a, b], threshold=0.86)
    check("URL+标题去重", len(ded) == 1, f"输入 2 条，保留 {len(ded)} 条")

    # 2. 评分排序
    ranked = rank_items(ded + [NewsItem(source="C", title="无关消息", url="https://x.com/1",
                                        published_at="2026-11-16T10:00:00+08:00")], settings.config)
    check("热度评分与排序", ranked[0].heat_score >= ranked[-1].heat_score,
          f"top={ranked[0].heat_score}, bottom={ranked[-1].heat_score}")

    # 3. 排版硬规则校验
    html, warns = render_wechat_html("# 标题\n\n正文<span>测试</span>\n\n> 引用\n\n外链[点我](https://x.com)")
    check("排版渲染无红线命中", len(warns) == 0, f"warnings={warns}")
    check("span 包裹 + 内联样式", '<span style=' in html and 'style=' in html, "")

    # 4. 门控阻断
    with tempfile.TemporaryDirectory() as td:
        wd = Path(td)
        blocked = False
        try:
            gates.ensure_approved(wd, "topics", ["t-001"])
        except gates.GateError:
            blocked = True
        check("未确认时门控阻断", blocked)
        gates.approve(wd, "topics", ["t-001"], "ok")
        check("确认后可放行", gates.is_approved(wd, "topics", "t-001"))

    # 5. 端到端（临时根目录）
    with tempfile.TemporaryDirectory() as td:
        tmp_root = Path(td)
        (tmp_root / "config").mkdir()
        (tmp_root / "prompts").mkdir()
        (tmp_root / "fixtures").mkdir()
        import shutil
        for f in ("config.json", "sources.json"):
            shutil.copy(settings.root / "config" / f, tmp_root / "config" / f)
        for f in (settings.root / "prompts").glob("*.md"):
            shutil.copy(f, tmp_root / "prompts" / f.name)
        for f in (settings.root / "fixtures").glob("*.json"):
            shutil.copy(f, tmp_root / "fixtures" / f.name)
        tmp_settings = load_settings(tmp_root)
        result = run_all(tmp_settings, date="2026-11-17", auto_approve=True, use_fixtures=True)
        checks.append({
            "name": "端到端 run-all",
            "ok": len(result["collect"]["warnings"]) >= 0 and
                  len(result["topics"]["topics"]) > 0 and
                  len(result["drafts"]["drafts"]) >= 2 and
                  len(result["publish"]["results"]) >= 1,
            "detail": f"news={result['collect']['count']}, topics={len(result['topics']['topics'])}, "
                      f"drafts={len(result['drafts']['drafts'])}, publish={len(result['publish']['results'])}",
        })

    passed = all(c["ok"] for c in checks)
    return {"passed": passed, "checks": checks, "total": len(checks),
            "failed": sum(1 for c in checks if not c["ok"])}
