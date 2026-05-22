"""
config.py
ClinicalEvidence Agent - centralized configuration.

Structural constants (API base URLS) live here for discoverability.
They change only on upstream API version bumps - a code change, not a config change.

Tunables and secrets load from environment with defaults.
"""

from __future__ import annotations
import os
from dataclasses import dataclass

# ─────────────────────────────────────────────
# Structural constants — NOT runtime tunables.
# ─────────────────────────────────────────────

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
CTGOV_BASE = "https://clinicaltrials.gov/api/v2"
S2_BASE = "https://api.semanticscholar.org/graph/v1"
S2_FIELDS = "paperId,title,abstract,authors.name,year,venue,externalIds,url"

# ─────────────────────────────────────────────
# Tunables + secrets — load from environment.
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class ToolConfig:
    """
    HTTP behaviro shared across all retrieval tools. 
    """
    request_timeout: float = float(os.getenv("CEA_REQUEST_TIMEOUT", "20.0"))
    max_retries: int = int(os.getenv("CEA_MAX_RETRIES", "3"))
    pubmed_api_key: str | None = os.getenv("NCBI_API_KEY")
    s2_api_key: str | None = os.getenv("SEMANTIC_SCHOLAR_API_KEY")

@dataclass(frozen=True)
class ModelConfig:
    """
    LLM Settibgs for agent calls
    """
    decomposer_model: str = os.getenv("CEA_DECOMPOSER_MODEL", "claude-sonnet-4-5")
    max_tokens: int = int(os.getenv("CEA_MAX_TOKENS", "2048"))

# Module-level singletons - import these everywhere
TOOL_CONFIG = ToolConfig()
MODEL_CONFIG = ModelConfig()