"""定时任务：每天 07:30 触发 collect→script→topics，停在选题确认门控。

运行方式（二选一）：
1. Windows 任务计划程序（推荐）：run/install_task.ps1，稳定、开机自启、无需常驻进程。
2. 常驻进程：python -m src.scheduler （使用 APScheduler，需 pip install -r requirements.txt）
"""
from __future__ import annotations

import sys
import time
from datetime import datetime

from .config import load_settings
from .workflow import step_collect, step_script, step_topics
from .llm import build_llm


def daily_job() -> None:
    settings = load_settings()
    date = datetime.now().strftime("%Y-%m-%d")
    print(f"[{date}] 开始每日采集流程 ...")
    r1 = step_collect(settings, date)
    print(f"  采集完成：{r1['count']} 条，警告 {len(r1['warnings'])} 条")
    r2 = step_script(settings, date, build_llm(settings.llm))
    print(f"  口播稿生成：{r2['script']}")
    r3 = step_topics(settings, date, build_llm(settings.llm))
    print(f"  选题生成：{len(r3['topics'])} 个，等待人工确认（门控已启用）")


def main() -> int:
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        print("未安装 apscheduler。推荐用 Windows 任务计划程序：run/install_task.ps1", file=sys.stderr)
        print("或安装依赖：pip install -r requirements.txt", file=sys.stderr)
        return 1

    settings = load_settings()
    hh, mm = (settings.config.get("daily_time", "07:30").split(":") + ["0"])[:2]
    scheduler = BlockingScheduler(timezone=settings.config.get("timezone", "Asia/Shanghai"))
    scheduler.add_job(daily_job, CronTrigger(hour=int(hh), minute=int(mm)), id="daily_morning")
    print(f"定时任务已启动：每天 {hh}:{mm} 执行采集+口播+选题（Ctrl+C 停止）")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
