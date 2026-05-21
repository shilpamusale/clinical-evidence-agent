# ClinicalEvidence Agent

> **Multi-agent clinical evidence synthesis using PICO decomposition,
> parallel retrieval, and GRADE-graded recommendations.**

[![CI](https://github.com/shilpamusale/clinical-evidence-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/shilpamusale/clinical-evidence-agent/actions)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![LangGraph](https://img.shields.io/badge/orchestration-LangGraph-green)](https://github.com/langchain-ai/langgraph)
[![Claude](https://img.shields.io/badge/LLM-Claude%203%20Sonnet%2FOpus-blueviolet)](https://anthropic.com)

---

## What This Is

ClinicalEvidence Agent autonomously answers complex clinical questions by
searching PubMed, ClinicalTrials.gov, and Semantic Scholar — then critically
appraising and synthesizing the retrieved evidence using GRADE methodology.

**Example query:**
> *"What is the evidence for SGLT2 inhibitors in heart failure with preserved
> ejection fraction?"*

**System output:** A structured clinical summary with GRADE-graded recommendation,
per-claim citation grounding, confidence score, and an evidence gap report
where the literature is insufficient.

---

## Why the Architecture Is Not a Generic RAG Pipeline

Standard RAG retrieves documents given a query. This system does something
structurally different:

1. **PICO decomposition before retrieval** — the Query Decomposer breaks the
   clinical question into structured Population / Intervention / Comparison /
   Outcome sub-queries before any search happens. This improves recall on
   complex multi-faceted questions that a single search string would miss.

2. **Parallel Literature Scouts** — one Scout instance runs per PICO sub-query
   concurrently, enabling horizontal scaling of evidence collection. Sequential
   pipelines cannot match this on breadth.

3. **Conditional routing on evidence quality** — low-evidence scenarios surface
   an Evidence Gap report rather than forcing a weak synthesis. A clinically safer
   failure mode than a hallucinated summary.

4. **Human-in-loop escalation** — ambiguous clinical questions trigger a
   clarification request before the pipeline proceeds. Uncertainty is a
   first-class agent behavior, not an afterthought.

---

## Agent Architecture

```
Clinical Question
       │
       ▼
┌─────────────────┐
│ Query Decomposer│  → Structured PICO sub-queries (1–6)
└────────┬────────┘
         │  parallel dispatch
    ┌────┴─────────────┬──────────────┐
    ▼                  ▼              ▼
┌──────────┐   ┌──────────┐   ┌──────────┐
│Literature│   │Literature│   │Literature│  ← one per PICO sub-query
│  Scout 1 │   │  Scout 2 │   │  Scout N │
└────┬─────┘   └────┬─────┘   └────┬─────┘
     └───────────────┴──────────────┘
                     │
                     ▼
          ┌──────────────────┐
          │Evidence Extractor│  → EvidenceCards (PICO elements, effect sizes)
          └────────┬─────────┘
                   │
                   ▼
          ┌──────────────────┐
          │Critical Appraiser│  → GRADEAssessments (bias risk, evidence level)
          └────────┬─────────┘
                   │
          ┌────────┴─────────┐
          ▼                  ▼
  ┌───────────────┐  ┌──────────────────┐
  │Synthesis Agent│  │Uncertainty Agent │
  └───────┬───────┘  └────────┬─────────┘
          └──────────┬────────┘
                     ▼
           Structured Clinical Summary
           + Confidence Report
           + Evidence Gap Analysis
```

---

## Evaluation Harness

The eval harness measures three distinct things: retrieval quality,
appraisal accuracy, and synthesis faithfulness. Each has a separate
benchmark dataset and metric.

### Benchmark Results

| Task | Dataset | Metric | Result |
|---|---|---|---|
| Evidence retrieval | BioASQ | Recall@10 | TBD |
| Evidence retrieval | PubMedQA | MRR | TBD |
| Evidence retrieval | PubMedQA | NDCG | TBD |
| Study quality appraisal | Cochrane Risk of Bias corpus | Cohen's κ vs. human appraisers | TBD |
| Synthesis faithfulness | Held-out clinical guideline questions | Hallucination rate | TBD |
| GRADE calibration | Known GRADE-graded recommendations | GRADE level agreement | TBD |
| Synthesis quality | Blinded clinician review (n=3, 5-point scale) | Mean score | TBD |

*TBD cells populated after experiment execution. All eval runs are
reproducible via `make eval`.*

### Multi-Agent Coordination Ablation

A core architectural claim is that parallel PICO retrieval outperforms
sequential single-query retrieval. This is measured explicitly as an ablation:

| Comparison | Metric | Result |
|---|---|---|
| Parallel Scouts (N sub-queries) vs. Single Scout | BioASQ Recall@10 | TBD |
| PICO decomposition vs. free-form query | PubMedQA accuracy | TBD |
| With Uncertainty Agent vs. without | Hallucination rate | TBD |

### Eval Infrastructure

- Automated nightly eval runs on held-out BioASQ and PubMedQA splits via
  GitHub Actions
- Clinician review panel: 3 blinded reviewers rate synthesis quality on a
  5-point scale
- Hallucination detection: citation grounding check verifying every factual
  claim in `ClinicalSummary.cited_claims` links to a real retrieved paper
- Regression dashboard: Streamlit UI at `eval/dashboard.py` showing metric
  trends across agent versions

---

## Tech Stack

| Layer | Technology | Reason |
|---|---|---|
| Agent orchestration | LangGraph (stateful multi-agent) | Explicit state transitions; auditable agent boundaries |
| LLMs | Claude 3 Sonnet (retrieval/appraisal), Opus (synthesis) | Tiered by task complexity; cost-performance optimization |
| Biomedical NLP | ClinicalBERT, scispaCy, BioSentVec | Domain-specific embeddings outperform general-purpose on biomedical text |
| Data sources | PubMed E-utilities, ClinicalTrials.gov, Semantic Scholar APIs | Coverage across trials, literature, and preprints |
| Vector store | ChromaDB + BioSentVec embeddings | Semantic similarity over abstracts and full text |
| Knowledge graph | Neo4j (papers, diseases, treatments, trials, authors) | Relational reasoning beyond embedding similarity |
| Reranker | MedCPT cross-encoder | Precision improvement on retrieved evidence before appraisal |
| Cache | Redis (query-level) | Latency reduction for repeated clinical questions |
| Serving | FastAPI + Docker + Cloud Run | Serverless; auto-scaling; reproducible environment |
| Observability | LangSmith tracing | Full agent trace logging; captures every tool call and reasoning step |
| CI/CD | GitHub Actions + pytest + mypy + ruff | Schema regression on every commit; type safety enforced |
| Eval dashboard | Streamlit | Interactive metric visualization across agent versions |

---

## Project Structure

```
clinical-evidence-agent/
├── agents/
│   ├── query_decomposer.py      # PICO decomposition via Claude
│   ├── literature_scout.py      # Parallel PubMed/CT.gov/Semantic Scholar retrieval
│   ├── evidence_extractor.py    # ClinicalBERT NER + effect size extraction
│   ├── critical_appraiser.py    # GRADE methodology implementation
│   ├── synthesis_agent.py       # Narrative synthesis with citation grounding
│   └── uncertainty_agent.py     # Confidence scoring + evidence gap detection
├── schemas/
│   └── agent_io.py              # Pydantic v2 schemas for all agent I/O boundaries
├── tools/
│   ├── pubmed_tool.py           # Async PubMed E-utilities wrapper
│   ├── ct_gov_tool.py           # ClinicalTrials.gov API wrapper
│   └── semantic_scholar_tool.py # Semantic Scholar API wrapper
├── graph/
│   └── pipeline.py              # LangGraph state machine definition
├── eval/
│   ├── harness.py               # Retrieval, appraisal, and synthesis evals
│   └── dashboard.py             # Streamlit regression dashboard
├── tests/
│   └── test_schemas.py          # Schema boundary smoke tests (12 tests)
├── .github/
│   └── workflows/
│       └── ci.yml               # mypy + pytest on every push
└── .devcontainer/
    └── devcontainer.json        # GitHub Codespaces config
```

---

## Quickstart

```bash
# Clone and open in GitHub Codespaces (recommended)
# Or locally:
git clone https://github.com/shilpamusale/clinical-evidence-agent.git
cd clinical-evidence-agent
pip install -r requirements.txt

# Set environment variables
export ANTHROPIC_API_KEY=your_key_here
export LANGSMITH_API_KEY=your_key_here

# Run the pipeline on a sample question
python -m graph.pipeline \
  --question "What is the evidence for SGLT2 inhibitors in HFpEF?" \
  --session-id demo-001

# Run the full eval harness
make eval

# Run schema smoke tests
pytest tests/test_schemas.py -v

# Launch eval dashboard
streamlit run eval/dashboard.py
```

---

## Key Design Decisions

**Why PICO decomposition before retrieval, not query expansion?**
Query expansion adds synonyms to a single search string. PICO decomposition
produces structurally independent sub-queries targeting different facets of
the clinical question. For complex multi-component questions, this consistently
improves recall because no single search string can cover all PICO components
without excessive noise.

**Why parallel Scouts rather than sequential retrieval?**
Sequential retrieval on N sub-queries introduces latency proportional to N.
Parallel dispatch keeps latency bounded at the slowest single Scout call.
For a synthesis system where retrieval breadth determines downstream quality,
sequential is a hard constraint on coverage — parallel removes it.

**Why surface an Evidence Gap report rather than synthesize anyway?**
In clinical contexts, a confident-sounding summary based on weak evidence
is more dangerous than an explicit gap report. The Uncertainty Agent's
conditional routing to `PipelineStatus.EVIDENCE_GAP` is a clinically safer
failure mode than forcing a synthesis the evidence base cannot support.

**Why LangGraph over CrewAI or custom orchestration?**
LangGraph exposes explicit state transitions — every edge in the graph is a
deliberate design decision. For a healthcare agent where every state
transition needs to be auditable and explainable, explicit is better than
magic. CrewAI abstracts state away, which reduces debuggability in exactly
the cases that matter most.

---

## Limitations and Future Work

- **Synthetic eval gap**: BioASQ and PubMedQA are proxy tasks; a pilot study
  with real clinician queries would validate whether benchmark gains transfer
  to production use cases.
- **Full-text access**: Evidence Extractor currently operates on abstracts for
  papers behind paywalls; PMC Open Access corpus partially covers this.
- **GRADE automation fidelity**: Automated GRADE assessment approximates
  expert panel judgment; Cohen's κ against Cochrane corpus quantifies this gap
  explicitly.
- **Scope**: Current system targets evidence synthesis, not clinical decision
  support. It surfaces evidence for clinician judgment — it does not make
  clinical recommendations autonomously.

---

## Author

**Shilpa Musale**
[github.com/shilpamusale](https://github.com/shilpamusale) ·
[linkedin.com/in/shilpamusale](https://linkedin.com/in/shilpamusale)

Domain expertise: Healthcare AI · Clinical NLP · Multi-Agent Systems ·
Evidence-Based Medicine · GRADE Methodology · Revenue Cycle Management
