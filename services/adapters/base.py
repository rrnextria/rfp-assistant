from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class GenerateResult:
    text: str
    model: str
    tokens_used: int


class AdapterError(Exception):
    """Raised when an AI provider returns an error."""


class ModelAdapter(ABC):
    @abstractmethod
    async def generate(self, prompt: str, context: list[str]) -> GenerateResult:
        ...

    @abstractmethod
    async def async_stream(self, prompt: str, context: list[str]) -> AsyncIterator[str]:
        ...
