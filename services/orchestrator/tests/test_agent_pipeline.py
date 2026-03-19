from __future__ import annotations

import sys
import pytest

sys.path.insert(0, "/home/ravi/git/rfp-assistant/services/orchestrator")


@pytest.mark.asyncio
async def test_agent_pipeline_runs_in_order():
    from agents import Agent, AgentInput, AgentOutput, AgentPipeline

    order = []

    class AgentA(Agent):
        async def run(self, input_data):
            order.append("A")
            return AgentOutput()

    class AgentB(Agent):
        async def run(self, input_data):
            order.append("B")
            return AgentOutput()

    pipeline = AgentPipeline([AgentA(), AgentB()])
    await pipeline.run(AgentInput())
    assert order == ["A", "B"]


@pytest.mark.asyncio
async def test_agent_pipeline_skip():
    from agents import Agent, AgentInput, AgentOutput, AgentPipeline

    ran = []

    class AgentX(Agent):
        async def run(self, input_data):
            ran.append("X")
            return AgentOutput()

    class AgentY(Agent):
        async def run(self, input_data):
            ran.append("Y")
            return AgentOutput()

    pipeline = AgentPipeline([AgentX(), AgentY()])
    await pipeline.run(AgentInput(), skip={AgentX})
    assert "X" not in ran
    assert "Y" in ran


def test_response_generation_input_valid():
    from agents import ResponseGenerationInput
    inp = ResponseGenerationInput(
        question="What is your uptime SLA?",
        mode="answer",
        detail_level="balanced",
        context_chunks=[],
        user_context={"user_id": "u1", "role": "end_user", "teams": []},
    )
    assert inp.confidence if hasattr(inp, "confidence") else True
    assert inp.question == "What is your uptime SLA?"


def test_confidence_in_range():
    from pipeline import compute_confidence
    chunks = [{"score": 0.01}, {"score": 0.008}, {"score": 0.006}]
    conf = compute_confidence(chunks)
    assert 0.0 <= conf <= 1.0
