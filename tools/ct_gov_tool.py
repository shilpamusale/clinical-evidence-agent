"""
tools/ct_gov_tool.py
Async ClinicalTrails.gov API Wrapper
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx

from config import CTGOV_BASE, TOOL_CONFIG
from schemas.agent_io import PaperMetadata, PaperSource

logger = logging.getLogger(__name__)

class CTGovTool:
    def __init__(self, client: Optional[httpx.AsyncClient]=None) -> None:
        self._client = client or httpx.AsyncClient(timeout=TOOL_CONFIG.request_timeout)
        self._owns_client = client is None
    async def __aenter__(self)-> "CTGovTool":
        return self
    
    async def __aexit__(self, *_: object) -> None:
        if self._owns_client:
            await self._client.aclose()
            
    async def search(self, query: str, max_results: int = 20) -> list[PaperMetadata]:
        params: dict[str, str | int] = {
            "query.term": query,
            "pageSize": max_results,
            "format": "json",
        }
        data = await self._request_json(f"{CTGOV_BASE}/studies", params)
        studies = data.get("studies", [])
        assert isinstance(studies, list)          # narrows type for mypy
        return self._parse_studies(studies)
    
    @staticmethod
    def _parse_studies(studies: list[dict[str, Any]]) -> list[PaperMetadata]:
        out: list[PaperMetadata] = []
        for s in studies:
            protocol: dict[str, Any] = s.get("protocolSection", {})
            ident: dict[str, Any] = protocol.get("identificationModule", {})
            status: dict[str, Any] = protocol.get("statusModule", {})
            description: dict[str, Any] = protocol.get("descriptionModule", {})
            
            nct_id = ident.get("nctId")
            if not nct_id:
                continue
            year_str = status.get("startDateStruct", {}).get("date", "")
            try:
                year = int(year_str.split("-")[0]) if year_str else None
            except ValueError:
                year = None
            
            out.append(
                PaperMetadata(
                    paper_id=f"nct:{nct_id}",
                    source=PaperSource.CLINICALTRIALS_GOV,
                    title=ident.get("briefTitle", ""),
                    abstract=description.get("briefSummary"),
                    authors=[],
                    publication_year=year,
                    journal=None,
                    doi=None,
                    url=f"https://clinicaltrials.gov/study/{nct_id}",
                    raw_metadata={
                        "phase": protocol.get("designModule", {}).get("phases", []),
                        "status": status.get("overallStatus"),
                    },
                )
            )
        return out

    async def _request_json(self, url: str, params: dict[str, str | int]) -> dict[str, Any]:
        last_exc: Optional[Exception] = None
        for attempt in range(TOOL_CONFIG.max_retries):
            try:
                resp = await self._client.get(url, params=params)
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
            f"CT.gov request failed after {TOOL_CONFIG.max_retries} attempts: {last_exc}"
        )      
            
            
            
            
            

    
