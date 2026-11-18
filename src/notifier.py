"""通知模块：把「产物就绪」主动送到用户眼前。

设计原则（与项目一致）：
1. 多渠道可插拔，任一渠道失败只记 warning，绝不阻断主流程。
2. 始终有「文件收件箱」兜底 —— 就算桌面通知和邮件都不可用，也能在面板/文件里看到。
3. 邮件等外部动作保留人工确认，不做无人值守推送。

渠道：
- inbox   写 data/inbox/YYYY-MM-DD.md 与 notifications.jsonl（默认开启，零依赖）
- desktop Windows 桌面 Toast（best-effort，零依赖，仅电脑前有效）
- wecom   企业微信机器人主动推送到授权人手机（走 wecom-cli，已授权）
- mail    生成待发送邮件草稿到 data/inbox/mail_drafts/（Agent Mail 开通后人工确认发送）
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# wecom-cli 在 Windows 上可能是 sh 包装脚本，Python subprocess 无法直接执行。
# 如需稳定从 Python 调用，可设置环境变量指向底层 node 入口；
# 未设置时退回 PATH 中的 wecom-cli（Linux/macOS/Git Bash 通常可直接用）。
_WECOM_JS = Path(os.environ.get("WECOM_CLI_JS", ""))
_NODE_EXE = Path(os.environ.get("WECOM_NODE_EXE", ""))


def _wecom_cmd(args: list[str]) -> list[str]:
    """构造可执行的 wecom-cli 命令。"""
    if _WECOM_JS.is_file() and _NODE_EXE.is_file():
        return [str(_NODE_EXE), str(_WECOM_JS)] + args
    return ["wecom-cli"] + args  # 兜底：PATH 中可用时

from .utils import now_iso, write_text


@dataclass
class Notice:
    """一条通知。"""

    event: str                       # digest_ready / drafts_ready / publish_ready
    title: str
    summary: str = ""
    workdir: str = ""                # 相关产物目录（相对或绝对）
    action: str = ""                 # 用户下一步该做什么
    links: list[str] = field(default_factory=list)  # 关键文件路径
    at: str = field(default_factory=now_iso)
    delivered: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BaseChannel:
    name = "base"

    def send(self, notice: Notice, cfg: dict, root: Path) -> bool:
        raise NotImplementedError


class InboxChannel(BaseChannel):
    """文件收件箱：按日期写 Markdown，同时追加 JSONL 便于程序读取。"""

    name = "inbox"

    def send(self, notice: Notice, cfg: dict, root: Path) -> bool:
        try:
            inbox = root / cfg.get("inbox_dir", "data/inbox")
            inbox.mkdir(parents=True, exist_ok=True)
            date = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
            md_path = inbox / f"{date}.md"
            links = "\n".join(f"- `{p}`" for p in notice.links) if notice.links else "（无）"
            block = (
                f"\n\n---\n\n## {notice.at} · {notice.event}\n\n"
                f"**{notice.title}**\n\n{notice.summary}\n\n"
                f"> 下一步：{notice.action}\n\n"
                f"产物链接：\n{links}\n"
            )
            with md_path.open("a", encoding="utf-8") as f:
                f.write(block)
            with (inbox / "notifications.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(notice.to_dict(), ensure_ascii=False) + "\n")
            return True
        except Exception:
            return False


class DesktopChannel(BaseChannel):
    """Windows 桌面 Toast。用系统自带 WinRT，无需第三方模块；失败静默降级。"""

    name = "desktop"

    def send(self, notice: Notice, cfg: dict, root: Path) -> bool:
        try:
            title = notice.title.replace("'", "''").replace('"', "'")
            msg = notice.summary.replace("'", "''").replace('"', "'")[:180]
            ps = f"""
$ErrorActionPreference='Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
    [Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$texts = $t.GetElementsByTagName('text')
$texts.Item(0).AppendChild($t.CreateTextNode('{title}')) | Out-Null
$texts.Item(1).AppendChild($t.CreateTextNode('{msg}')) | Out-Null
$toast = [Windows.UI.Notifications.ToastNotification]::new($t)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('SelfMediaAgent').Show($toast)
"""
            r = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                capture_output=True, text=True, timeout=12,
            )
            return r.returncode == 0
        except Exception:
            return False


class WeComChannel(BaseChannel):
    """企业微信：通过 wecom-cli 把通知推给授权人（自己的手机）。

    - 用 `wecom-cli identity whoami` 动态取授权人身份作为 chat_id（发给自己，合规）。
    - 不在代码/配置里硬编码任何 ID；ID 仅内部流转，绝不回显。
    - CLI 未安装/未授权时静默降级为 False，由 inbox 兜底。
    """

    name = "wecom"

    def _self_chat_id(self) -> str | None:
        try:
            r = subprocess.run(
                _wecom_cmd(["identity", "whoami"]),
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode != 0:
                return None
            data = json.loads(r.stdout)
            # 授权真人用户身份的 ID 在 extra_identity_context 文本里，正则提取「授权真人用户身份」段的 ID
            ctx = data.get("extra_identity_context", "")
            m = re.search(r"授权真人用户身份：[\s\S]*?ID[：:]\s*([A-Za-z0-9_-]+)", ctx)
            if m:
                return m.group(1)
            return data.get("userid") or data.get("chat_id")
        except Exception:
            return None

    def send(self, notice: Notice, cfg: dict, root: Path) -> bool:
        chat_id = self._self_chat_id()
        if not chat_id:
            return False
        # 组装 Markdown（企业微信 markdown 语法）。
        # 手机端不展示本机绝对路径（点不开、观感差），改为可读的产物类型提示。
        lines = [f"## {notice.title}", ""]
        if notice.summary:
            lines += [f"> {notice.summary}", ""]
        if notice.action:
            lines += [f"**下一步**：{notice.action}", ""]
        if notice.links:
            names = []
            for p in notice.links[:5]:
                n = Path(p).name
                names.append(f"- {n}")
            lines += ["**已生成**"] + names + [""]
        lines += [
            "<font color=\"comment\">产物在电脑 WorkBuddy 面板，回电脑处理</font>",
            f"<font color=\"comment\">{notice.at} · 个人自媒体 Agent</font>",
        ]
        content = "\n".join(lines)[:20000]
        payload = json.dumps({
            "chat_id": chat_id,
            "msg_type": "markdown",
            "markdown": {"content": content},
        }, ensure_ascii=False)
        try:
            r = subprocess.run(
                _wecom_cmd(["message", "aibot", "send", "--json", payload]),
                capture_output=True, text=True, timeout=30,
            )
            if r.returncode != 0:
                return False
            out = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}
            return bool(out.get("success"))
        except Exception:
            return False


class MailDraftChannel(BaseChannel):
    """邮件草稿：生成待发送内容，不真正发送。Agent Mail 开通后人工确认再发。"""

    name = "mail"

    def send(self, notice: Notice, cfg: dict, root: Path) -> bool:
        try:
            d = root / cfg.get("inbox_dir", "data/inbox") / "mail_drafts"
            d.mkdir(parents=True, exist_ok=True)
            links = "\n".join(f"- {p}" for p in notice.links) if notice.links else "（无）"
            body = (
                f"# {notice.title}\n\n{notice.summary}\n\n"
                f"**下一步**：{notice.action}\n\n"
                f"## 产物\n{links}\n\n"
                f"---\n生成时间 {notice.at} · 由个人自媒体 Agent 自动发出，请人工复核后发布。\n"
            )
            (d / f"{notice.event}_{notice.at.replace(':', '-')}.md").write_text(
                f"收件人：{cfg.get('to', '（待配置）')}\n"
                f"主题：{notice.title}\n\n{body}", encoding="utf-8")
            return True
        except Exception:
            return False


CHANNELS: dict[str, BaseChannel] = {
    "inbox": InboxChannel(),
    "desktop": DesktopChannel(),
    "wecom": WeComChannel(),
    "mail": MailDraftChannel(),
}


def notify(settings, notice: Notice) -> dict[str, bool]:
    """按配置投递通知。返回每个渠道是否成功；失败不影响主流程。"""
    cfg = settings.config.get("notify", {})
    enabled = cfg.get("channels", ["inbox"])
    results: dict[str, bool] = {}
    for name in enabled:
        ch = CHANNELS.get(name)
        if not ch:
            continue
        try:
            results[name] = bool(ch.send(notice, cfg, settings.root))
        except Exception:
            results[name] = False
    notice.delivered = results
    # 投递结果留痕到独立日志（InboxChannel 写通知时 delivered 尚未赋值，故单独记录）
    try:
        inbox = settings.root / cfg.get("inbox_dir", "data/inbox")
        inbox.mkdir(parents=True, exist_ok=True)
        with (inbox / "delivery_log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": notice.at, "event": notice.event,
                                "title": notice.title, "delivered": results}, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return results


# ---- 三个触发点的通知内容模板 ----

def notice_digest_ready(settings, date: str, workdir: Path, topics_count: int) -> Notice:
    return Notice(
        event="digest_ready",
        title=f"早报就绪 · {date} · {topics_count} 个选题待确认",
        summary=f"今日资讯已采集去重，口播稿与 {topics_count} 个公众号选题已生成，等你挑选题。",
        workdir=str(workdir),
        action=f"打开选题：python -m src.cli --date {date} status ，确认后回复我继续写稿",
        links=[str(workdir / "topics.json"), str(workdir / "audio_script.md"), str(workdir / "digest.md")],
    )


def notice_drafts_ready(settings, date: str, workdir: Path, drafts: list[dict]) -> Notice:
    wechat = [d for d in drafts if d.get("platform") == "wechat"]
    xhs = [d for d in drafts if d.get("platform") == "xiaohongshu"]
    return Notice(
        event="drafts_ready",
        title=f"初稿就绪 · {date} · 公众号 {len(wechat)} 篇 + 小红书 {len(xhs)} 篇",
        summary="已按卡兹克风格 + 花叔排版生成公众号初稿，并衍生小红书版本，等你过稿。",
        workdir=str(workdir),
        action=f"查看：python -m src.cli --date {date} status ，确认后我生成待发布包",
        links=[str(workdir / "drafts.json")] + [str(workdir / f"{d['id']}_wechat.md") for d in wechat[:3]],
    )


def notice_publish_ready(settings, date: str, workdir: Path, count: int) -> Notice:
    return Notice(
        event="publish_ready",
        title=f"待发布包就绪 · {date} · {count} 份",
        summary="待发布包已生成（含配图 HTML），未执行任何线上发布。",
        workdir=str(workdir),
        action="人工审核后手动发布；线上发布接口仍为预留状态",
        links=[str(workdir / "publish")],
    )
