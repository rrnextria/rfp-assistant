from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


# --- Base schemas ---

class AgentInput(BaseModel):
    pass


class AgentOutput(BaseModel):
    pass


# --- Concrete agent schemas ---

class RFPIngestionInput(AgentInput):
    rfp_id: str
    file_content: str


class RFPIngestionOutput(AgentOutput):
    raw_text: str
    rfp_id: str


class RequirementExtractionInput(AgentInput):
    rfp_id: str
    raw_text: str


class RequirementExtractionOutput(AgentOutput):
    requirements: list[dict[str, Any]]
    requirement_ids: list[str]


class QuestionnaireExtractionInput(AgentInput):
    rfp_id: str
    raw_text: str


class QuestionnaireExtractionOutput(AgentOutput):
    questionnaire_items: list[dict[str, Any]]
    item_ids: list[str]


class ResponseGenerationInput(AgentInput):
    question: str
    mode: str = "answer"
    detail_level: str = "balanced"
    context_chunks: list[dict[str, Any]] = Field(default_factory=list)
    user_context: dict[str, Any] = Field(default_factory=dict)


class ResponseGenerationOutput(AgentOutput):
    answer: str
    citations: list[dict[str, Any]]
    confidence: float


class QuestionnaireCompletionInput(AgentInput):
    rfp_id: str
    user_context: dict[str, Any] = Field(default_factory=dict)


class QuestionnaireCompletionOutput(AgentOutput):
    completed: int
    flagged: int
    item_results: list[dict[str, Any]]


# --- Agent base class ---

class Agent(ABC):
    @abstractmethod
    async def run(self, input_data: AgentInput) -> AgentOutput:
        ...


# --- AgentPipeline ---

class AgentPipeline:
    """Ordered pipeline of agents passing output to next as input."""

    def __init__(self, agents: list[Agent]) -> None:
        self._agents = agents

    async def run(
        self,
        initial_input: AgentInput,
        skip: set[type[Agent]] | None = None,
    ) -> AgentOutput:
        current_output: AgentOutput | None = None

        for agent in self._agents:
            if skip and type(agent) in skip:
                continue

            if current_output is None:
                result = await agent.run(initial_input)
            else:
                # Convert previous output to dict and pass as next input
                try:
                    next_input = type(initial_input)(**current_output.model_dump())
                except Exception:
                    next_input = initial_input
                result = await agent.run(next_input)

            current_output = result

        return current_output or AgentOutput()


# --- ResponseGenerationAgent ---

class ResponseGenerationAgent(Agent):
    """Wraps ask_pipeline with structured input/output."""

    async def run(self, input_data: AgentInput) -> AgentOutput:
        if not isinstance(input_data, ResponseGenerationInput):
            raise ValueError("Expected ResponseGenerationInput")

        # Import here to avoid circular
        from pipeline import ask_pipeline, AskResponse
        from common.db import get_session_factory

        factory = get_session_factory()
        async with factory() as db:
            result: AskResponse = await ask_pipeline(
                question=input_data.question,
                mode=input_data.mode,
                detail_level=input_data.detail_level,
                user_context=input_data.user_context,
                db=db,
            )

        return ResponseGenerationOutput(
            answer=result.answer,
            citations=[
                {"chunk_id": c.chunk_id, "doc_id": c.doc_id, "snippet": c.snippet}
                for c in result.citations
            ],
            confidence=result.confidence,
        )
