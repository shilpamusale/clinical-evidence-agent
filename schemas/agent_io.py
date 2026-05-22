"""
schemas/agent_io.py

ClinicalEvidence Agent - Pydantic v2 schemas for all agent I/O boundaries. 
Every agent receives and returns a typed schema; no raw dicts cross agent
boundaries. Thi is the contract layer for the entire pipeline.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, model_validator

# ─────────────────────────────────────────────
# Shared enums
# ─────────────────────────────────────────────

class EvidenceLevel(str, Enum):
    """
    GRADE evidence quality levels.
    """
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"
    VERY_LOW = "VERY_LOW"
    
class StudyDesign(str, Enum):
    RCT = "RCT"
    SYSTEMATIC_REVIEW = "SYSTEMATIC_REVIEW"
    META_ANALYSIS = "META_ANALYSIS"
    COHORT = "COHORT"
    CASE_CONTROL = "CASE_CONTROL"
    CASE_SERIES = "CASE_SERIES"
    EXPERT_OPINION = "EXPERT_OPINION"
    UNKNOWN = "UNKNOWN"

class BiasRisk(str, Enum):
    LOW = "LOW"
    UNCLEAR = "UNCLEAR"
    HIGH = "HIGH"

class PipelineStatus(str, Enum):
    PROCEED = "PROCEED"
    CLARIFICATION_NEEDED = "CLARIFICATION_NEEDED"
    EVIDENCE_GAP = "EVIDENCE_GAP"
    COMPLETE = "COMPLETE"
    
# ─────────────────────────────────────────────
# 1. Query Decomposer → Input / Output
# ─────────────────────────────────────────────

class ClinicalQuestion(BaseModel):
    """
    Raw user input - entry point to the pipeline.
    """
    question : str = Field(
        ...,
        min_length = 10, 
        description = "The clinical question to synthesize evidence for.",
        examples = ["What is the evidence for SGLT2 inhibitors in HFpEF? "]
    )
    session_id: str = Field(
        ..., 
        description="UUID for this pipeline run; used for tracing and caching."
    )
    
class PICOQuery(BaseModel):
    """
        Structured PICO sub-query produced by the Query Decomposer.
    """
    sub_query_id: str
    population: str = Field(..., description="Patient population (P)")
    intervention: str = Field(..., description="Intervention being evaluated (I)")
    comparison: Optional[str] = Field(None, description="Comparison/control arm (C)")
    outcome: str = Field(..., description = "Outcome of interest (O)")
    free_text_query: str = Field(
        ..., 
        description = "Derived PubMed/CT.gov search string from PICO elements."
    )
class DecomposedQuery(BaseModel):
    """
    Output of Query Decomposer - N PICO sub-queries ready for parallel Scount 
    """
    session_id: str 
    original_question: str
    pico_queries: list[PICOQuery] = Field(
        ..., 
        min_length = 1, 
        max_length = 6, 
        description = "1-6 PICO sub-queries; bounded to prevent runaway parallel calls."
    )
    status: PipelineStatus = PipelineStatus.PROCEED
    clarification_prompt: Optional[str] = Field(
        None,
        description = "If status=CLARIFICATION_NEEDED, the question to surface to the user."
    )
    
    @model_validator(mode="after")
    def clarification_prompt_required_when_needed(self) -> "DecomposedQuery":
        if self.status == PipelineStatus.CLARIFICATION_NEEDED:
            if not self.clarification_prompt:
                raise ValueError(
                    "clarification_prompt must be set when status = CLARIFICATION_NEEDED"
                )
        return self
    
# ─────────────────────────────────────────────
# 2. Literature Scout → Output
# ─────────────────────────────────────────────

class ScoutResult(BaseModel):
    """
    Output of one Literature Scout instance for one PICO sub-query.
    """
    sub_query_id: str
    session_id: str
    papers: list[PaperMetadata] = Field(default_factory=list)
    total_retrieved: int
    recall_at_10: Optional[float] = Field(
        None, 
        ge=0.0, 
        le=1.0,
        description=("Populated during eval runs; None in production.")
    )

# ─────────────────────────────────────────────
# 3. Evidence Extractor → Output
# ─────────────────────────────────────────────

class ExtractedEffect(BaseModel):
    """
    Quantitative outcome extracted from a paper.
    """
    outcome_label: str
    effect_size: Optional[str] = None
    p_value: Optional[str] = None
    sample_size: Optional[int] = None

class EvidenceCard(BaseModel):
    """
    Structured evidence card for one paper - output of Evidence Extractor.
    """
    paper_id: str
    session_id: str
    pico_population: str
    pico_intervention: str
    pico_outcome: str
    study_design: StudyDesign
    effects: list[ExtractedEffect] = Field(default_factory=list)
    key_findings: str = Field(
        ...,
        description = "1-3 sentence narrative summary of this paper's findings."
    )
    extraction_confidence: float = Field(
        ..., 
        ge = 0.0,
        le = 1.0, 
        description = "ClinicalBERT NER extraction confidence score."
    )
       
# ─────────────────────────────────────────────
# 4. Critical Appraiser → Output
# ─────────────────────────────────────────────
class GRADEAssessment(BaseModel):
    """
    GRADE quality assessment for one evidence card.
    """
    paper_id: str
    session_id: str
    evidence_level: EvidenceLevel
    bias_risk: BiasRisk
    inconsistency_flag: bool = Field(
        False,
        description = " True if findings conflict with other retrieved papers."
    )
    indirectness_flag: bool = Field(
        False, 
        description = "True if PICO population/intervention doesn't match question."
    )
    imprecision_flag: bool = Field(
        False, 
        description = "True if confidence intervals are wide or sample size is small."         
    )
    publication_bias_flag: bool = Field(
        False, 
        description = "True if evidence base shows signs of publication bias."
    )
    appraiser_rationale: str = Field(
        ..., 
        description = "Chain-of-thought reasoning for the GRADE level assigned."
    )

# ─────────────────────────────────────────────
# 5. Synthesis Agent → Output
# ─────────────────────────────────────────────
class CitedClaim(BaseModel):
    """
        A single factual claim in the synthesis with its grounding paper(s).
    """
    claim_text: str
    supporting_paper_ids: list[str] = Field(
        ..., 
        min_length=1,
        description = "Every factual claim must link to >= 1 retrieved paper."
    )
class ClinicalSummary(BaseModel):
    """
    Final structured synthesis output - main deliverable of the pipeline. 
    """
    session_id: str
    clinical_question: str
    overall_evidence_level: EvidenceLevel
    recommendation: str = Field(
        ..., 
        description = "GRADE-graded recommendation statement."
    )
    narrative_summary: str = Field(
        ..., 
        description = "Full structured narrative synthesis across all PICO sub-queries."
    )
    cited_claims: list[CitedClaim] = Field(
        default_factory = list, 
        description = "Granular claim-level citation map for hallucination auditing."
    )
    papers_included: int
    papers_excluded: int
    status: PipelineStatus = PipelineStatus.COMPLETE

# ─────────────────────────────────────────────
# 6. Uncertainty Agent → Output
# ─────────────────────────────────────────────

class EvidenceGap(BaseModel):
    """
    One identified gap in the evidence base.
    """
    gap_description: str
    affected_pico_component: str # "P" | "I" | "C" | "O"
    recommended_study_type: Optional[StudyDesign] = None
    
class UncertaintyReport(BaseModel):
    """
        Output of Uncertainty Agent - confidence quantifucation and gap analysis. 
    """
    session_id: str
    overall_confidence: float = Field(
        ..., 
        description = "Aggregate confidence score across all synthesized evidence."        
    )
    hallucination_risk: float = Field(
        ..., 
        ge=0.0, 
        le = 1.0,
        description = "Proportion of claims lacking direct paper grounding."
    )
    evidence_gaps: list[EvidenceGap] = Field(default_factory = list)
    further_research_needed: bool
    status: PipelineStatus
    
    @model_validator(mode="after")
    def flag_evidence_gap_stauts(self) -> "UncertaintyReport":
        if len(self.evidence_gaps) > 2 and self.overall_confidence < 0.4:
            object.__setattr__(self, "status", PipelineStatus.EVIDENCE_GAP)
        return self
# ─────────────────────────────────────────────
# 7. Top-level pipeline state (for LangGraph)
# ─────────────────────────────────────────────

class PipelineState(BaseModel):
    """
        LangGraph state object passed between all nodes.
        Each agent reads its required fields and writes its output fields.
        Optional fields are None until the relevant agent runs.
    """
    session_id: str
    clinical_question: ClinicalQuestion
    decomposed_query: Optional[DecomposedQuery] = None
    scout_results: list[ScoutResult] = Field(default_factory=list)
    evidence_cards: list[EvidenceCard] = Field(default_factory=list)
    grade_assessments: list[GRADEAssessment] = Field(default_factory=list)
    clinical_summary: Optional[ClinicalSummary] = None
    uncertainty_report: Optional[UncertaintyReport] = None
    pipeline_status: PipelineStatus = PipelineStatus.PROCEED
    iteration_count: int = 0

class PaperSource(str, Enum):
    PUBMED ="PUBMED"
    CLINICALTRIALS_GOV = "CLINICALTRIALS_GOV"
    SEMANTIC_SCHOLAR = "SEMANTIC_SCHOLAR"

class PaperMetadata(BaseModel):
    """
    Unified shape returned bu every retrieval tool.
    Literature Scout fans these in.
    """
    paper_id: str = Field(..., description="Source-prefixed ID, e.g. 'pubmed:12345678'")
    source: PaperSource
    title: str
    abstract: Optional[str] = None
    authors: list[str] = Field(default_factory=list)
    publication_year: Optional[int] = None
    journal: Optional[str] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    # Source-specific extras kept in a typed bag, not parsed yet — Evidence Extractor's job
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    
    @model_validator(mode="after")
    def _validate_id_prefix(self) -> "PaperMetadata":
        expected = {
            PaperSource.PUBMED: "pubmed:",
            PaperSource.CLINICALTRIALS_GOV: "nct:",
            PaperSource.SEMANTIC_SCHOLAR: "s2:",
        }[self.source]
        if not self.paper_id.startswith(expected):
            raise ValueError(f"paper_id must start with '{expected}' for source {self.source}")
        return self
    
    
    