"""
tools/semantic_scholar_tool.py
Async Semantic Scholar Graph API wrapper
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx
from config import S2_BASE, S2_FIELDS,TOOL_CONFIG
from schemas.agent_io import PaperMetadata, PaperSource

class SemanticScholarTool:
    def __init__(
        self,
        api_key: Optional[str] = None, 
        client: Optional[httpx.AsyncClient] = None
    ) -> None:
        self._api_key = api_key or TOOL_CONFIG.s2_api_key
        self._client = client or httpx.AsyncClient(timeout=TOOL_CONFIG.request_timeout)
        self._owns_client = client is None
    
    async def __aenter__(self) -> "SemanticScholarTool":
        return self
    
    async def __aexit__(self, *_: object) -> None:
        if self._owns_client:
            await self._client.aclose()
    
    async def search(self, query: str, max_results: int = 20) -> list[PaperMetadata]:
        params = {
            "query": query,
            "limit": max_results,
            "fields": S2_FIELDS,
        }
        headers = {"x-api-key": self._api_key} if self._api_key else {}
        data = await self._request_json(
            f"{S2_BASE}/paper/search", params=params, headers=headers
        )
        return self._parse_papers(data.get("data", []))
    
    @staticmethod
    def _parse_papers(papers: list[dict[str, Any]]) -> list[PaperMetadata]:
        out: list[PaperMetadata] = []
        for p in papers:
            pid = p.get("paperId")
            if not pid:
                continue
            out.append(
                PaperMetadata(
                    paper_id=f"s2:{pid}",
                    source=PaperSource.SEMANTIC_SCHOLAR,
                    title=p.get("title", ""),
                    abstract=p.get("abstract"),
                    authors=[a.get("name", "") for a in p.get("authors") or []],
                    publication_year=p.get("year"),
                    journal=p.get("venue"),
                    doi=(p.get("externalIds") or {}).get("DOI"),
                    url=p.get("url"),
                    raw_metadata={"externalIds": p.get("externalIds") or {}},
                )
            )
        return out
    async def _request_json(
        self, url: str, params: dict[str, Any], headers: dict[str, str]
    ) -> dict[str, Any]:
        last_exc: Optional[Exception] = None
        for attempt in range(TOOL_CONFIG.max_retries):
            try:
                resp = await self._client.get(url, params=params, headers=headers)
                if resp.status_code == 429:
                    await asyncio.sleep(2 ** attempt + 0.5)
                    continue
                resp.raise_for_status()
                result: dict[str, Any] = resp.json()
                return result
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_exc = exc
                await asyncio.sleep(2 ** attempt + 0.5)
        raise RuntimeError(
            f"S2 request failed after {TOOL_CONFIG.max_retries} attempts: {last_exc}"
        )