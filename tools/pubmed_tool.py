"""
tools/pubmed_tool.py
Async PubMed E-utilities wrapper. Uses esearch -> efectch with retry+backoff.
"""
from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from typing import Any,Optional
import httpx

from config import EUTILS_BASE, TOOL_CONFIG
from schemas.agent_io import PaperMetadata, PaperSource

logger = logging.getLogger(__name__)

class PubMedTool:
    """
    E-Utilities client. One instance per pipeline run; safe for concurrent calls.
    """
    def __init__(
        self,
        api_key: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        # Explicit arg wins over config — preserves testability.
        self._api_key = api_key or TOOL_CONFIG.pubmed_api_key
        self._client = client or httpx.AsyncClient(timeout=TOOL_CONFIG.request_timeout)
        self._owns_client = client is None
    
    async def __aenter__(self) -> "PubMedTool":
        return self
    async def __aexit__(self, *_:object) -> None:
        if self._owns_client:
            await self._client.aclose()
    async def search(self, query: str, max_results: int = 20) -> list[PaperMetadata]:
        """
           Search PubMed for `query`, return up to `max_results` papers with abstracts.
        """
        pmids = await self._esearch(query, max_results)
        if not pmids:
            return []
        return await self._efetch(pmids)
   
    async def _esearch(self, query: str, max_results: int) -> list[str]:
        params: dict[str, Any] = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
        }
        if self._api_key:
            params["api_key"] = self._api_key
        data = await self._request_json(f"{EUTILS_BASE}/esearch.fcgi", params)
        id_list: list[str] = data.get("esearchresult", {}).get("idlist", [])
        return id_list
    
    async def _efetch(self, pmids: list[str]) -> list[PaperMetadata]:
        params: dict[str, Any] = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
        }
        if self._api_key:
            params["api_key"] = self._api_key
        xml_text = await self._request_text(f"{EUTILS_BASE}/efetch.fcgi", params)
        return self._parse_efetch_xml(xml_text)
    
    @staticmethod
    def _parse_efetch_xml(xml_text: str) -> list[PaperMetadata]:
        root = ET.fromstring(xml_text)
        papers: list[PaperMetadata] = []
        
        for article in root.findall(".//PubmedArticle"):
            pmid_el = article.find(".//PMID")
            title_el = article.find(".//ArticleTitle")
            abstract_el = article.find(".//Abstract/AbstractText")
            year_el = article.find(".//PubDate/Year")
            journal_el = article.find(".//Journal/Title")
            doi_el = article.find(".//ArticleId[@IdType='doi']")
            
            if pmid_el is None or title_el is None:
                continue
            
            pmid = (pmid_el.text or "").strip()
            authors = [
                f"{(a.findtext('LastName') or '').strip()} "
                f"{(a.findtext('Initials') or '').strip()}".strip()
                for a in article.findall(".//Author")
                if a.find("LastName") is not None
            ]
            try:
                year = int((year_el.text or "").strip()) if year_el is not None else None
            except ValueError:
                year = None
            
            papers.append(PaperMetadata(
                    paper_id=f"pubmed:{pmid}",
                    source=PaperSource.PUBMED,
                    title=(title_el.text or "").strip(),
                    abstract=(abstract_el.text or "").strip() if abstract_el is not None else None,
                    authors=authors,
                    publication_year=year,
                    journal=(journal_el.text or "").strip() if journal_el is not None else None,
                    doi=(doi_el.text or "").strip() if doi_el is not None else None,
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    raw_metadata={},
                )
            )
        return papers
    
    async def _request_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = (await self._request(url, params)).json()
        return result
    
    async def _request_text(self, url: str, params: dict[str, Any]) -> str:
        return (await self._request(url, params)).text
     
    async def _request(self, url: str, params: dict[str, Any]) -> httpx.Response:
        last_exec: Optional[Exception] = None
        for attempt in range(TOOL_CONFIG.max_retries):
            try:
                resp = await self._client.get(url, params=params)
                if resp.status_code == 429:
                    await asyncio.sleep(2 ** attempt + 0.5)
                    continue
                resp.raise_for_status()
                return resp 
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_exec = exc
                await asyncio.sleep(2 ** attempt + 0.5)
        raise RuntimeError(
            f"PubMed request failed after {TOOL_CONFIG.max_retries} attempts: {last_exec}"
        )       
        
        
        
        