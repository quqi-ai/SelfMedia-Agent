"""命令行入口。

常用：
  python -m src.cli collect
  python -m src.cli script
  python -m src.cli topics
  python -m src.cli approve --stage topics --ids t-001 --note "写这条"
  python -m src.cli drafts
  python -m src.cli approve --stage drafts --ids d-xxx
  python -m src.cli publish
  python -m src.cli run-all --auto-approve --date 2026-11-17
  python -m src.cli verify
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

from . import gates, workflow
from .config import load_settings
from .gates import GateError
from .llm import build_llm
from .utils import read_json


def today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")


def dump(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="src.cli", description="个人自媒体 Agent MVP")
    # --date 既支持放在子命令前，也支持放在子命令后（两个 dest 合并）
    p.add_argument("--date", dest="global_date", default=None, help="运行日期 YYYY-MM-DD，默认今天")
    sub = p.add_subparsers(dest="cmd", required=True)

    def dated(name: str, **kw) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, **kw)
        sp.add_argument("--date", dest="date", default=None, help="运行日期 YYYY-MM-DD")
        return sp

    dated("collect", help="采集 + 整理去重 + 评分")
    dated("script", help="生成通勤口播稿（音频预留）")
    dated("topics", help="生成选题列表（待确认）")
    dated("drafts", help="按已确认选题生成公众号 + 小红书初稿")
    dated("publish", help="生成待发布包（不自动发布）")
    dated("status", help="查看当日流程状态与确认记录")

    ap = dated("approve", help="人工确认门控")
    ap.add_argument("--stage", required=True, choices=["topics", "drafts", "publish"])
    ap.add_argument("--ids", required=True, help="逗号分隔的 ID，如 t-001,t-002")
    ap.add_argument("--note", default="")

    rj = dated("reject", help="人工驳回")
    rj.add_argument("--stage", required=True, choices=["topics", "drafts", "publish"])
    rj.add_argument("--ids", required=True)
    rj.add_argument("--note", default="")

    ra = dated("run-all", help="端到端跑通（默认在确认门控处停止）")
    ra.add_argument("--auto-approve", action="store_true", help="仅用于本地验证：自动通过门控")
    ra.add_argument("--no-fixtures", action="store_true", help="禁用样例兜底")

    dated("verify", help="本地自检（临时目录，不污染正式数据）")
    dated("inbox", help="查看通知收件箱")
    nt = dated("notify", help="测试通知渠道")
    nt.add_argument("--title", default="测试通知")
    nt.add_argument("--message", default="自媒体 Agent 通知链路正常。")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings()
    date = getattr(args, "date", None) or getattr(args, "global_date", None) or today()
    workdir = settings.workdir(date)

    try:
        if args.cmd == "collect":
            dump(workflow.step_collect(settings, date))
        elif args.cmd == "script":
            dump(workflow.step_script(settings, date, build_llm(settings.llm)))
        elif args.cmd == "topics":
            dump(workflow.step_topics(settings, date, build_llm(settings.llm)))
        elif args.cmd == "drafts":
            dump(workflow.step_drafts(settings, date, build_llm(settings.llm)))
        elif args.cmd == "publish":
            dump(workflow.step_publish_prepare(settings, date))
        elif args.cmd == "approve":
            ids = [x.strip() for x in args.ids.split(",") if x.strip()]
            dump({"approved": gates.approve(workdir, args.stage, ids, args.note)})
        elif args.cmd == "reject":
            ids = [x.strip() for x in args.ids.split(",") if x.strip()]
            dump({"rejected": gates.reject(workdir, args.stage, ids, args.note)})
        elif args.cmd == "status":
            dump({
                "date": date,
                "workdir": str(workdir),
                "state": read_json(workdir / "state.json", {}),
                "approvals": gates.summary(workdir),
                "files": sorted(p.name for p in workdir.glob("*")) if workdir.exists() else [],
            })
        elif args.cmd == "run-all":
            dump(workflow.run_all(settings, date, args.auto_approve, not args.no_fixtures))
        elif args.cmd == "verify":
            from .verify import run_verify
            result = run_verify()
            dump(result)
            return 0 if result["passed"] else 1
        elif args.cmd == "inbox":
            inbox = settings.root / settings.config.get("notify", {}).get("inbox_dir", "data/inbox")
            jl = inbox / "notifications.jsonl"
            notices = [json.loads(l) for l in jl.read_text(encoding="utf-8").splitlines() if l.strip()] if jl.exists() else []
            dump({
                "inbox": str(inbox),
                "notices": notices,
                "mail_drafts": sorted(p.name for p in (inbox / "mail_drafts").glob("*.md")) if (inbox / "mail_drafts").exists() else [],
            })
        elif args.cmd == "notify":
            from .notifier import Notice, notify
            n = Notice(event="manual_test", title=args.title, summary=args.message,
                       action="这是一条测试通知，无需处理")
            dump({"delivered": notify(settings, n)})
    except GateError as e:
        print(f"[门控阻断] {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"[错误] {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
