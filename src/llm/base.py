"""LLM 抽象基类。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResponse:
    text: str
    model: str = ""
    usage: dict[str, Any] = field(default_factory=dict)


class BaseLLM(ABC):
    name: str = "base"

    @abstractmethod
    def complete(self, system: str, prompt: str, **kwargs: Any) -> LLMResponse:
        ...
