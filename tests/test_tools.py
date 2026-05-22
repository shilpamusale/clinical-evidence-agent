"""Smoke tests for tool layer using mocked HTTP responses. No live API calls."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from schemas.agent_io import PaperSource
from tools.ct_gov_tool import CTGovTool
from tools.pubmed_tool import PubMedTool
from tools.semantic_scholar_tool import SemanticScholarTool


PUBMED_ESEARCH = {"esearchresult": {"idlist": ["12345678"]}}
PUBMED_EFETCH_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>12345678</PMID>
      <Article>
        <ArticleTitle>SGLT2 inhibitors in HFpEF</ArticleTitle>
        <Abstract><AbstractText>Background...</AbstractText></Abstract>
        <Journal><Title>NEJM</Title></Journal>
        <AuthorList>
          <Author><LastName>Smith</LastName><Initials>J</Initials></Author>
        </AuthorList>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <History/>
      <ArticleIdList>
        <ArticleId IdType="doi">10.1056/example</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>"""


def _mock_response(status: int = 200, json_data: dict | None = None, text: str = ""):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.json.return_value = json_data or {}
    resp.text = text
    resp.raise_for_status = MagicMock(return_value=None)  # no-op on success
    return resp


@pytest.mark.asyncio
async def test_pubmed_tool_returns_typed_papers():
    esearch_resp = _mock_response(json_data=PUBMED_ESEARCH)
    efetch_resp = _mock_response(text=PUBMED_EFETCH_XML)

    # raise_for_status must be a no-op (not raise) for success path
    esearch_resp.raise_for_status = MagicMock(return_value=None)
    efetch_resp.raise_for_status = MagicMock(return_value=None)

    client = MagicMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(side_effect=[esearch_resp, efetch_resp])

    async with PubMedTool(client=client) as tool:
        papers = await tool.search("SGLT2 inhibitors HFpEF")

    assert len(papers) == 1
    assert papers[0].paper_id == "pubmed:12345678"
    assert papers[0].source == PaperSource.PUBMED
    assert papers[0].journal == "NEJM"

@pytest.mark.asyncio
async def test_ctgov_tool_parses_studies():
    payload = {
        "studies": [
            {
                "protocolSection": {
                    "identificationModule": {
                        "nctId": "NCT04567890",
                        "briefTitle": "Trial X",
                    },
                    "statusModule": {
                        "overallStatus": "COMPLETED",
                        "startDateStruct": {"date": "2020-01-15"},
                    },
                    "descriptionModule": {"briefSummary": "Studied X in Y."},
                    "designModule": {"phases": ["PHASE3"]},
                }
            }
        ]
    }
    client = MagicMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(return_value=_mock_response(json_data=payload))
    async with CTGovTool(client=client) as tool:
        papers = await tool.search("Trial X")
    assert papers[0].paper_id == "nct:NCT04567890"
    assert papers[0].publication_year == 2020
    assert papers[0].raw_metadata["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_s2_tool_parses_papers():
    payload = {
        "data": [
            {
                "paperId": "abc123",
                "title": "Heart failure RCT",
                "abstract": "We studied...",
                "authors": [{"name": "Doe J"}],
                "year": 2023,
                "venue": "JAMA",
                "externalIds": {"DOI": "10.1001/example", "PubMed": "987654"},
                "url": "https://semanticscholar.org/paper/abc123",
            }
        ]
    }
    client = MagicMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(return_value=_mock_response(json_data=payload))
    async with SemanticScholarTool(client=client) as tool:
        papers = await tool.search("heart failure")
    assert papers[0].paper_id == "s2:abc123"
    assert papers[0].doi == "10.1001/example"
    assert papers[0].raw_metadata["externalIds"]["PubMed"] == "987654"