"""
agents/query_decomposer.py

Decompose a clinical question into a 1-6 PICO sub-queries.
Returns a validated DecomposedQuery: rountes to CLARIFICATION_NEEDED when ambiguous.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

from anthropic import AsyncAnthropic

from config import MODEL_CONFIG
from schemas.agent_io import(
    ClinicalQuestion,
    DecomposedQuery,
    PICOQuery,
    PipelineStatus
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are a clinical evidence synthesis specialist. Your task is to decompose a clinical question into structured PICO sub-queries for parallel literature retrieval.

PICO framework:
- Population: patient group (e.g., "adults with heart failure with preserved ejection fraction")
- Intervention: treatment or exposure being evaluated
- Comparison: control or alternative (may be null if not specified)
- Outcome: clinical endpoint of interest

Rules:
1. Produce 1-6 sub-queries. Complex multi-faceted questions warrant more; simple ones need only 1-2.
2. Each sub-query must have a non-empty population, intervention, and outcome. Comparison may be null.
3. Generate a free_text_query for each PICO — a concise PubMed-style search string combining the elements.
4. If the question is too ambiguous to decompose (missing critical context), set status to CLARIFICATION_NEEDED and provide a clarification_prompt instead of pico_queries.

Return ONLY a JSON object matching this schema:
{
  "status": "PROCEED" | "CLARIFICATION_NEEDED",
  "pico_queries": [
    {
      "sub_query_id": "sq-1",
      "population": "...",
      "intervention": "...",
      "comparison": "..." | null,
      "outcome": "...",
      "free_text_query": "..."
    }
  ],
  "clarification_prompt": null | "..."
}
"""
class QueryDecomposer:
    def __init__(self, client: Optional[AsyncAnthropic] = None) -> None:
        self._client = client or AsyncAnthropic()
    
    async def run(self, question: ClinicalQuestion) -> DecomposedQuery:
      response = await self._client.messages.create(
          model=MODEL_CONFIG.decomposer_model,
          max_tokens=MODEL_CONFIG.max_tokens,
          system=SYSTEM_PROMPT,
          messages=[{"role": "user", "content": question.question}],
      )
      text = self._extract_text(response)
      payload = self._parse_json(text)
      
      status = PipelineStatus(payload.get("status", "PROCEED"))
      
      if status == PipelineStatus.CLARIFICATION_NEEDED:
            return DecomposedQuery(
                session_id=question.session_id,
                original_question=question.question,
                pico_queries=[
                    PICOQuery(
                        sub_query_id="sq-placeholder",
                        population="UNRESOLVED",
                        intervention="UNRESOLVED",
                        comparison=None,
                        outcome="UNRESOLVED",
                        free_text_query="UNRESOLVED",
                    )
                ],
                status=PipelineStatus.CLARIFICATION_NEEDED,
                clarification_prompt=payload.get("clarification_prompt"),
            )

        
      pico_queries = [
          PICOQuery(
              sub_query_id=q.get("sub_query_id") or f"sq-{uuid.uuid4().hex[:8]}",
              population=q["population"],
              intervention=q["intervention"],
              comparison=q.get("comparison"),
              outcome=q["outcome"],
              free_text_query=q["free_text_query"],
          )
          for q in payload.get("pico_queries", [])
      ]
      return DecomposedQuery(
          session_id=question.session_id,
          original_question=question.question,
          pico_queries=pico_queries,
          status=PipelineStatus.PROCEED,
          clarification_prompt=None,
      )
  
    @staticmethod
    def _extract_text(response: Any) -> str:
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text: str = block.text
                return text
        raise ValueError("No text block in Anthropic response")
    
    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
      cleaned = text.strip()
      if cleaned.startswith("```"):
          cleaned = cleaned.split("```")[1]
          if cleaned.startswith("json"):
              cleaned = cleaned[4:]
          cleaned = cleaned.strip()
      try:
          result: dict[str, Any] = json.loads(cleaned)
          return result
      except json.JSONDecodeError as exc:
          raise ValueError(
              f"Failed to parse Claude response as JSON: {exc}\n{text}"
          )
        