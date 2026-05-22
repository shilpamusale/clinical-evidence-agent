"""
Golden tests for QueryDecomposer with mocked Anthropic client.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from agents.query_decomposer import QueryDecomposer
from schemas.agent_io import ClinicalQuestion, PipelineStatus

def _mock_anthropic_response(payload:dict):
    block = MagicMock()
    block.type = "text"
    block.text = json.dumps(payload)
    response = MagicMock()
    response.content = [block]
    return response

@pytest.mark.asyncio
async def test_decomposer_proceed_path():
    payload = {
        "status": "PROCEED",
        "pico_queries" : [
            {
                "sub_query_id": "sq_1",
                "population": "adults with HFpEF",
                "intervention": "SGLT2 inhibitors",
                "comparison": "placebo",
                "outcome":"HF hospitalization",
                "free_text_query": "SGLT2 inhibitors HF2EF hospitalization",
            }
        ],
        "clarification_prompt": None,
    }
    client = MagicMock()
    client.messages.create = AsyncMock(return_value = _mock_anthropic_response(payload))
    decomposer = QueryDecomposer(client = client)
    result = await decomposer.run(
        ClinicalQuestion(
            question="What is the evidence for SGLT2 inhibitors in HFpEF?",
            session_id="sess-001"
        )
    )
    assert result.status == PipelineStatus.PROCEED
    assert len(result.pico_queries) == 1
    assert result.pico_queries[0].intervention == "SGLT2 inhibitors"

@pytest.mark.asyncio
async def test_decomposer_clarification_path():
    payload = {
        "status": "CLARIFICATION_NEEDED",
        "pico_queries": [],
        "clarification_prompt": "Which population are you asking about?"
    }
    client = MagicMock()
    client.messages.create = AsyncMock(return_value = _mock_anthropic_response(payload))
    decomposer = QueryDecomposer(client=client)
    result = await decomposer.run(
        ClinicalQuestion(
            question ="Is this drug good?", 
            session_id="sess-002"             
            )
        )
    assert result.status == PipelineStatus.CLARIFICATION_NEEDED
    assert result.clarification_prompt == "Which population are you asking about?"

@pytest.mark.asyncio
async def test_decomposer_handles_code_fences():
    """Claude sometimes wraps JSON in ```json fences; parser must strip them."""
    raw_payload = {
        "status": "PROCEED",
        "pico_queries": [
            {
                "sub_query_id": "sq-1",
                "population": "p",
                "intervention": "i",
                "comparison": None,
                "outcome": "o",
                "free_text_query": "q",
            }
        ],
        "clarification_prompt": None,
    }
    block = MagicMock()
    block.type = "text"
    block.text = f"```json\n{json.dumps(raw_payload)}\n```"
    response = MagicMock()
    response.content = [block]
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=response)
    decomposer = QueryDecomposer(client=client)
    result = await decomposer.run(
        ClinicalQuestion(question="Test question about SGLT2.", session_id="sess-003")
    )
    assert result.status == PipelineStatus.PROCEED
    