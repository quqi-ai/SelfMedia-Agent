"""LLM 客户端：mock（离线验证）与 live（OpenAI 兼容 API）双模式。"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable

from .base import BaseLLM, LLMResponse


class MockLLM(BaseLLM):
    """离线模式：用内置生成器产出结构化样例，供全流程验证。返回内容会明确标注为示例。"""

    name = "mock"

    def complete(self, system: str, prompt: str, **kwargs: Any) -> LLMResponse:
        stage = _detect_stage(system, prompt)
        text = _mock_generate(stage, prompt)
        return LLMResponse(text=text, model="mock-local", usage={"stage": stage})


class OpenAICompatibleLLM(BaseLLM):
    """OpenAI 兼容 Chat Completions 接口（ urllib 实现，无需额外依赖）。"""

    name = "live"

    def __init__(self, base_url: str, api_key: str, model: str,
                 temperature: float = 0.7, max_tokens: int = 3000, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def complete(self, system: str, prompt: str, **kwargs: Any) -> LLMResponse:
        payload = {
            "model": kwargs.get("model", self.model),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")[:500]
            raise RuntimeError(f"LLM HTTP {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"LLM 网络错误（检查 base_url/代理）: {e.reason}") from e
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return LLMResponse(text=text, model=self.model, usage=usage)


def build_llm(cfg: dict[str, Any]) -> BaseLLM:
    """工厂：cfg['mode']=='live' 时走真实 API，否则 mock。"""
    mode = (cfg.get("mode") or "mock").lower()
    if mode == "live":
        key_env = cfg.get("api_key_env", "OPENAI_API_KEY")
        api_key = os.environ.get(key_env, "")
        if not api_key:
            raise RuntimeError(f"live 模式需要设置环境变量 {key_env}（或在配置里切回 mock）")
        return OpenAICompatibleLLM(
            base_url=cfg.get("base_url", "https://api.openai.com/v1"),
            api_key=api_key,
            model=cfg.get("model", "gpt-4o-mini"),
            temperature=cfg.get("temperature", 0.7),
            max_tokens=cfg.get("max_tokens", 3000),
            timeout=cfg.get("timeout", 60),
        )
    return MockLLM()


def _detect_stage(system: str, prompt: str) -> str:
    blob = (system + "\n" + prompt)
    for stage in ("topics", "audio", "wechat_draft", "xiaohongshu", "format", "digest"):
        if f"[{stage}]" in blob:
            return stage
    if "选题" in blob:
        return "topics"
    if "口播" in blob:
        return "audio"
    if "小红书" in blob:
        return "xiaohongshu"
    if "公众号" in blob or "长文" in blob:
        return "wechat_draft"
    return "generic"


def _mock_generate(stage: str, prompt: str) -> str:
    """内置样例生成器。注意：产出的都是示例占位文本，明确标注需人工二次创作。"""
    if stage == "topics":
        return json.dumps([
            {
                "id": "t-mock-01",
                "title": "当 Agent 开始自己写代码：这周最值得聊的三个变化",
                "angle": "从「工具」到「同事」的临界点，用三个真实更新串起来",
                "core_thesis": "Agent 的价值不在单点能力，而在于它开始能独立闭环一段工作流",
                "material_sources": ["news_sample#1", "news_sample#2"],
                "priority": "S",
                "value_reason": "兼具信息量与情绪共鸣，适合做本周第一篇",
            },
            {
                "id": "t-mock-02",
                "title": "我把三个 Agent 框架拉到一起跑了一遍，结果有点意外",
                "angle": "实测对比 + 个人体验，降低理解门槛",
                "core_thesis": "框架差异没那么重要，真正决定效果的是任务拆解方式",
                "material_sources": ["news_sample#3"],
                "priority": "A",
                "value_reason": "调查实验型，活人感强",
            },
            {
                "id": "t-mock-03",
                "title": "为什么大家突然都在聊 MCP？",
                "angle": "现象解读 + 一点历史类比",
                "core_thesis": "MCP 火不是因为技术新，而是它解决了接口碎片化的老问题",
                "material_sources": ["hot_questions#1"],
                "priority": "B",
                "value_reason": "蹭热点但需谨慎，避免同质化",
            },
        ], ensure_ascii=False, indent=2)

    if stage == "audio":
        return (
            "「示例口播稿·mock 模式生成，正式使用请切换 live 并由人工过稿」\n\n"
            "早上好，这里是你的 AI 早报。今天用五分钟，聊聊昨天到今天最值得知道的几件事。\n\n"
            "先说第一条。国产大模型又有新动作，重点是开源和Agent能力。事情是这样的，"
            "几个团队几乎同时放出了更新，节奏快得有点离谱。我自己的感受是，"
            "大家卷的已经不是参数，而是谁能把活真的干完。\n\n"
            "第二条，跟Agent框架有关。有人把几个主流框架放在一起实测，"
            "结论挺反直觉的，具体差别的其实在任务怎么拆。\n\n"
            "最后留个小悬念，今天公众号我会写一篇长的，聊聊这背后的变化。"
            "好，以上就是今天的早报，祝你通勤顺利。"
        )

    if stage in ("wechat_draft", "xiaohongshu"):
        title = "当 Agent 开始自己干活，我们到底在激动什么"
        if stage == "xiaohongshu":
            return (
                "【示例小红书文案·mock 模式，需人工改写】\n\n"
                "标题备选：\n"
                "1. 这几天 AI 圈最值得追的三个变化\n"
                "2. 我好像第一次觉得 Agent 真能替我干活了\n\n"
                "正文：\n"
                "故事是这样的。这两天我盯着几个更新看，越看越觉得不对劲。\n\n"
                "以前我们说 Agent，总觉得是个玩具。但这次不一样，它开始能自己拆任务、"
                "自己调工具、自己收尾。\n\n"
                "我的真实感受是，兴奋里带点慌。兴奋是因为真的好用，慌是因为这可能来得比想象中快。\n\n"
                "你们怎么看？评论区聊聊。\n\n"
                "#AI #Agent #人工智能 #效率工具 #科技早报"
            )
        return (
            f"# {title}\n\n"
            "> 示例草稿（mock 模式生成，仅用于流程验证；正式稿需按卡兹克风格由人工二次创作并过四层自检）\n\n"
            "故事是这样的。\n\n"
            "这两天我刷到几条更新，本来没太在意，看着看着就有点坐不住了。\n\n"
            "以前聊 Agent，我心里其实一直打个问号。它到底能自己干多少活？"
            "这次的几个变化，算是给了我一个挺明确的答案。\n\n"
            "先说第一条，坦率的讲，最打动我的不是参数，是它开始能把一个任务从头做到尾。"
            "我自己上手试了一下，那种感觉挺微妙的，就像你把一个实习生丢进工位，"
            "结果他真的把活干完了。\n\n"
            "说到这个，就不得不提第二个变化。几个框架放在一起比，"
            "我原以为差距会很大，结果我发现，真正拉开差距的不是框架，是你怎么把任务拆给它。\n\n"
            "回到最开始那个问题，Agent 会不会取代我们。我现在更倾向于另一个想法，"
            "它先改变的是「你怎么安排自己的时间」。\n\n"
            "大时代啊，朋友们。\n\n"
            "我自己也还在摸索，以上只是一些不成熟的观察。但有一点我挺确定，"
            "保持好奇，比焦虑有用得多。\n\n"
            "以上，既然看到这里了，如果觉得不错，随手点个赞、在看、转发三连吧。"
            "谢谢你看我的文章，我们，下次再见。\n"
        )

    return "【mock 模式】该阶段无内置样例输出。"
