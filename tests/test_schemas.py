"""
tests/test_schemas.py
Smoke tests verifying schema validation contracts hold at agent boundaries.
These run on every commit as part of CI regression.
"""
import pytest
from pydantic import ValidationError
from schemas.agent_io import(
    ClinicalQuestion, 
    PICOQuery,
    DecomposedQuery,
    PipelineStatus,
    PaperMetadata,
    ScoutResult,
    EvidenceLevel, 
    BiasRisk,
    StudyDesign,
    ClinicalSummary,
    UncertaintyReport,
    EvidenceGap,
    PipelineState,
    GRADEAssessment,
    PaperSource
)

# Clinical Question 

def test_clinical_question_valid():
    q = ClinicalQuestion(
        question = "What is the evidence for SGLT2 inhibitors in HFpEF?",
        session_id="sess-001",
    )
    assert q.session_id =="sess-001"

def test_clinical_question_too_short():
    with pytest.raises(ValidationError):
        ClinicalQuestion(question="Too short",
                         session_id="sess-002")

# DecomposedQuery

def _make_pico(i: int) -> PICOQuery:
    return PICOQuery(
        sub_query_id = f"pico-{i}",
        population="Adults with HFpEF (EF >= 50%)",
        intervention = "SGLT2 inhibitor (empagliflozin or dapagliflozin)",
        comparison="Placebo", 
        outcome = "Composite of CV death or worsening HF", 
        free_text_query="SGLT2 inhibitor HFpEF heart failure preserved ejection fraction"
    )
    
def test_decomposed_query_valid():
    dq = DecomposedQuery(
        session_id="sess-001",
        original_question="SGLT2 inhibitors in HFpEF?",
        pico_queries = [_make_pico(0),_make_pico(1)],
        status = PipelineStatus.PROCEED,
        clarification_prompt="Some clarification prompt"        
    )
    assert len(dq.pico_queries) == 2

def test_clarification_needed_requires_prompt():
    with pytest.raises(ValidationError, match="clarification_prompt"):
        DecomposedQuery(
            session_id="sess-003",
            original_question = "Some ambiguous question here?",
            pico_queries=[_make_pico(0)],
            status=PipelineStatus.CLARIFICATION_NEEDED,
            clarification_prompt = None # Should Fail
        )

def test_clarification_needed_with_prompt():
    dq = DecomposedQuery(
        session_id="sess-004",
        original_question="Ambiguous clinical question about X?",
        pico_queries=[_make_pico(0)],
        status=PipelineStatus.CLARIFICATION_NEEDED,
        clarification_prompt="Could you clarify the target patient population?",
    )
    assert dq.status == PipelineStatus.CLARIFICATION_NEEDED

def test_pico_queries_max_length():
    with pytest.raises(ValidationError):
        DecomposedQuery(
            session_id="sess-005",
            original_question = "Broad clinical question about many interventions?",
            pico_queries=[_make_pico(i) for i in range(7)], 
            clarification_prompt="Some clarification prompt"
        )

# Scout Result

def test_scout_result_relevance_score_bounds():
    with pytest.raises(ValidationError):
        PaperMetadata(
            paper_id="123456789",
            source="pubmed",
            title = "Test Paper",
            study_design = StudyDesign.RCT,
            relevance_score = 1.5 # > 1.0, should fail.
        )
def test_scout_result_valid():
    paper = PaperMetadata(
        paper_id="pubmed:36507710",
        source=PaperSource.PUBMED,
        title="EMPEROR-Preserved: Empagliflozin in HFpEF",
        study_design=StudyDesign.RCT,
        relevance_score=0.92,
        publication_year=2021,
        journal="NEJM",
    )
    result = ScoutResult(
        sub_query_id="pico-0",
        session_id="sess-001",
        papers=[paper],
        total_retrieved=1,
        recall_at_10 = 0.0
    )
    assert result.papers[0].paper_id == "pubmed:36507710"
    assert paper.source == PaperSource.PUBMED


# ── GRADEAssessment ──────────────────────────────────────────────────────────

def test_grade_assessment_valid():
    ga = GRADEAssessment(
        paper_id="36507710",
        session_id="sess-001",
        evidence_level=EvidenceLevel.HIGH,
        bias_risk=BiasRisk.LOW,
        appraiser_rationale="Large double-blind RCT with pre-specified endpoints and low attrition.",
        inconsistency_flag = False,
        indirectness_flag=False,
        imprecision_flag=False,
        publication_bias_flag=False       
        
    )
    assert ga.evidence_level == EvidenceLevel.HIGH


# ── ClinicalSummary ──────────────────────────────────────────────────────────

def test_cited_claim_requires_paper():
    """A claim with no supporting papers must fail validation."""
    from schemas.agent_io import CitedClaim
    with pytest.raises(ValidationError):
        CitedClaim(claim_text="Empagliflozin reduces HF hospitalizations.", supporting_paper_ids=[])


# ── UncertaintyReport auto-status ────────────────────────────────────────────

def test_uncertainty_report_auto_evidence_gap():
    """Low confidence + many gaps should auto-set status to EVIDENCE_GAP."""
    report = UncertaintyReport(
        session_id="sess-001",
        overall_confidence=0.25,
        hallucination_risk=0.1,
        evidence_gaps=[
            EvidenceGap(gap_description=f"Gap {i}", affected_pico_component="O")
            for i in range(3)
        ],
        further_research_needed=True,
        status=PipelineStatus.PROCEED,  # should be overridden by validator
    )
    assert report.status == PipelineStatus.EVIDENCE_GAP


# ── PipelineState ────────────────────────────────────────────────────────────

def test_pipeline_state_initial():
    state = PipelineState(
        session_id="sess-001",
        clinical_question=ClinicalQuestion(
            question="What is the evidence for SGLT2 inhibitors in HFpEF?",
            session_id="sess-001"
        )
    )
    assert state.decomposed_query is None
    assert state.pipeline_status == PipelineStatus.PROCEED
    assert state.iteration_count == 0
        
