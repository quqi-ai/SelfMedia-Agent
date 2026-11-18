"""发布接口预留：只生成待发布包，绝不自动发布。

如需接入真实发布（公众号草稿箱 / 小红书），继承 BasePublisher 实现 publish()，
并在 CLI 中要求显式 --token CONFIRM-<id> 才能调用。
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from ..gates import GateError, ensure_approved
from ..models import ArticleDraft
from ..utils import write_json


class PublishResult:
    def __init__(self, status: str, path: str, message: str):
        self.status = status
        self.path = path
        self.message = message

    def to_dict(self) -> dict:
        return {"status": self.status, "path": self.path, "message": self.message}


class BasePublisher(ABC):
    name = "base"

    def __init__(self, workdir: Path):
        self.workdir = workdir

    def prepare(self, draft: ArticleDraft, require_confirm: bool = True) -> PublishResult:
        """生成待发布包。require_confirm=True 时必须先通过 drafts 门控。"""
        if require_confirm:
            ensure_approved(self.workdir, "drafts", [draft.id])
        out_dir = self.workdir / "publish"
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "platform": draft.platform,
            "title": draft.title,
            "body_markdown": draft.body_markdown,
            "body_html": draft.body_html,
            "source_refs": draft.source_refs,
            "draft_id": draft.id,
            "prepared_at": __import__("datetime").datetime.now().astimezone().isoformat(),
        }
        path = out_dir / f"{draft.id}_{draft.platform}.json"
        write_json(path, payload)
        return PublishResult("prepared", str(path),
                             "待发布包已生成；未执行任何线上发布。请人工审核后通过 publish 命令显式确认。")

    @abstractmethod
    def publish(self, draft: ArticleDraft, confirm_token: str) -> PublishResult:
        """真实发布接口（预留）。confirm_token 必须等于 f'CONFIRM-{draft.id}'。"""
        ...


class WeChatPublisher(BasePublisher):
    name = "wechat"

    def publish(self, draft: ArticleDraft, confirm_token: str) -> PublishResult:
        expected = f"CONFIRM-{draft.id}"
        if confirm_token != expected:
            raise GateError(f"发布需要显式确认 token：{expected}（当前未提供或错误）")
        # TODO: 接入公众号草稿箱 API（需 AppID/AppSecret 与 IP 白名单），此处刻意不实现。
        return PublishResult("reserved", "", "公众号发布接口已预留，未执行真实发布。")


class XiaohongshuPublisher(BasePublisher):
    name = "xiaohongshu"

    def publish(self, draft: ArticleDraft, confirm_token: str) -> PublishResult:
        expected = f"CONFIRM-{draft.id}"
        if confirm_token != expected:
            raise GateError(f"发布需要显式确认 token：{expected}（当前未提供或错误）")
        # TODO: 小红书无官方开放发布 API，需人工发布或合规工具；此处刻意不实现。
        return PublishResult("reserved", "", "小红书发布接口已预留，未执行真实发布。")


def get_publisher(platform: str, workdir: Path) -> BasePublisher:
    return {"wechat": WeChatPublisher, "xiaohongshu": XiaohongshuPublisher}.get(
        platform, WeChatPublisher)(workdir)
