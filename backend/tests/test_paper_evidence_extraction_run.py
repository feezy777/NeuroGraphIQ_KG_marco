"""Single-paper extraction worker contract and legacy-wrapper parity."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services import paper_evidence_service as pes


class _Result:
    def __init__(self, row=None):
        self._row = row

    def first(self):
        return self._row


class _Session:
    def __init__(self):
        self.commits = 0

    async def execute(self, *args, **kwargs):
        return _Result((uuid.UUID(int=2),))

    async def commit(self):
        self.commits += 1


def _run(coro):
    return asyncio.run(coro)


def _paper(*, is_open_access=True):
    return {
        "pmid": "99100001",
        "doi": "10.1000/worker",
        "title": "Worker paper",
        "journal": "J Worker",
        "year": "2026",
        "abstract": "The hippocampus projects to prefrontal cortex.",
        "is_open_access": is_open_access,
        "source": "europepmc",
        "paper_match_score": 7.5,
    }


def _context():
    return {
        "claim_text": "Hippocampus projects to prefrontal cortex",
        "claim_components": [
            {"component_type": "source_region", "required": True},
            {"component_type": "target_region", "required": True},
        ],
        "source_region": "Hippocampus",
        "target_region": "Prefrontal cortex",
        "source_region_synonyms": [],
        "target_region_synonyms": [],
        "function_terms": [],
        "function_synonyms": [],
        "relation_keywords": ["projects"],
    }


def _install_pipeline_mocks(monkeypatch, extraction, *, is_open_access=True):
    meta = {**_paper(is_open_access=is_open_access), "pmcid": "PMC99100001"}
    monkeypatch.setattr(pes, "_verify_paper_with_retry", AsyncMock(return_value=meta))
    monkeypatch.setattr(
        pes.pfs, "fetch_oa_fulltext_xml", AsyncMock(return_value="<article />")
    )
    monkeypatch.setattr(
        pes,
        "ensure_paper_source",
        AsyncMock(return_value=SimpleNamespace(id=uuid.UUID(int=1))),
    )
    monkeypatch.setattr(pes, "ensure_paper_passages", AsyncMock())
    paragraphs = [
        {
            "paragraph_id": "abstract_p001",
            "passage_text": meta["abstract"],
            "source_scope": "abstract",
            "section_title": "Abstract",
            "paragraph_index": 0,
            "locator": "abstract:paragraph:0",
        }
    ]
    monkeypatch.setattr(pes, "load_paper_passages", AsyncMock(return_value=paragraphs))
    monkeypatch.setattr(
        pes,
        "build_semantic_windows",
        lambda all_paragraphs, **kwargs: [
            {
                "focus_paragraph_id": "abstract_p001",
                "context": all_paragraphs,
            }
        ],
    )
    async def fake_extract(*, on_stage=None, **kwargs):
        await pes._emit_extraction_stage(on_stage, "locating")
        await pes._emit_extraction_stage(on_stage, "judging")
        return extraction

    monkeypatch.setattr(
        pes, "_extract_from_paper_with_retry", AsyncMock(side_effect=fake_extract)
    )


def test_stage_progress_contract():
    assert pes.STAGE_PROGRESS == {
        "queued": 0,
        "fetching": 10,
        "parsing": 25,
        "retrieving": 40,
        "locating": 55,
        "judging": 75,
        "verifying": 90,
        "completed": 100,
        "no_evidence": 100,
        "failed": 100,
        "cancelled": 100,
    }


def test_single_paper_worker_success_preserves_candidate_fields_and_stages(monkeypatch):
    passage = {
        "paragraph_id": "abstract_p001",
        "passage": "The hippocampus projects to prefrontal cortex.",
        "direction": "supports",
        "supported_components": ["source_region", "target_region"],
        "source_verified": True,
        "evidence_dimension": "existence",
    }
    _install_pipeline_mocks(
        monkeypatch,
        {
            "overall_direction": "supports",
            "assessment": "direct support",
            "passages": [passage],
            "not_found_reason": None,
            "evidence_dimension": "existence",
            "llm_model": "deepseek-worker-test",
        },
    )
    stages = []

    async def on_stage(stage):
        stages.append(stage)

    envelope = _run(
        pes.extract_candidate_for_paper(
            _Session(),
            context=_context(),
            paper=_paper(),
            only_oa=False,
            sem_fetch=asyncio.Semaphore(1),
            sem_deepseek=asyncio.Semaphore(1),
            mode="existence",
            on_stage=on_stage,
        )
    )

    assert envelope["status"] == "completed"
    assert envelope["llm_model"] == "deepseek-worker-test"
    candidate = envelope["candidate"]
    assert candidate["model_direction"] == "supports"
    assert candidate["coverage_summary"]["overall_direction"] == "supports"
    assert candidate["passages"][0]["paper_id"] == str(uuid.UUID(int=1))
    assert candidate["not_found_reason"] is None
    assert candidate["evidence_dimension"] == "existence"
    assert stages == [
        "queued",
        "fetching",
        "parsing",
        "retrieving",
        "locating",
        "judging",
        "verifying",
        "completed",
    ]


def test_stage_callback_failure_does_not_mask_success_or_failure(monkeypatch):
    _install_pipeline_mocks(
        monkeypatch,
        {
            "overall_direction": "not_found",
            "assessment": "no matching evidence",
            "passages": [],
            "parse_status": "ok",
        },
    )

    async def broken_callback(stage):
        raise RuntimeError(f"callback failed at {stage}")

    success = _run(
        pes.extract_candidate_for_paper(
            _Session(),
            context=_context(),
            paper=_paper(),
            only_oa=False,
            sem_fetch=asyncio.Semaphore(1),
            sem_deepseek=asyncio.Semaphore(1),
            mode="function",
            on_stage=broken_callback,
        )
    )
    failure = _run(
        pes.extract_candidate_for_paper(
            _Session(),
            context=_context(),
            paper={},
            only_oa=False,
            sem_fetch=asyncio.Semaphore(1),
            sem_deepseek=asyncio.Semaphore(1),
            mode="function",
            on_stage=broken_callback,
        )
    )

    assert success["status"] == "no_evidence"
    assert failure["status"] == "failed"
    assert failure["reason"] == "missing_identifier"


def test_retry_stage_progress_is_monotonic(monkeypatch):
    attempts = 0

    async def flaky_two_stage(*, on_stage=None, **kwargs):
        nonlocal attempts
        attempts += 1
        await on_stage("locating")
        await on_stage("judging")
        if attempts == 1:
            raise ValueError("parse_error")
        return {"overall_direction": "not_found", "passages": []}

    monkeypatch.setattr(pes, "extract_passage_two_stage", flaky_two_stage)
    monkeypatch.setattr(pes.asyncio, "sleep", AsyncMock())
    stages = []

    async def record(stage):
        stages.append(stage)

    emitter = pes._ExtractionStageEmitter(record)

    result = _run(
        pes._extract_from_paper_with_retry(
            claim=_context(),
            title="Worker paper",
            windows=[],
            on_stage=emitter.emit,
        )
    )

    assert result["overall_direction"] == "not_found"
    assert attempts == 2
    assert stages == ["locating", "judging"]


def test_two_stage_extraction_propagates_real_provider_model(monkeypatch):
    provider = AsyncMock()
    provider.complete_json = AsyncMock(
        side_effect=[
            SimpleNamespace(
                parsed_json={
                    "candidates": [
                        {
                            "paragraph_id": "results_p001",
                            "relevance": 0.9,
                            "relation_cue": "direct_connection",
                            "reason": "direct",
                        }
                    ]
                },
                raw_text="",
                transport_ok=True,
                model="deepseek-resolved-test",
            ),
            SimpleNamespace(
                parsed_json={
                    "overall_direction": "not_found",
                    "paper_relevance": 0.4,
                    "assessment": "no direct evidence",
                    "not_found_reason": "regions_cooccur_no_connection",
                    "passages": [],
                },
                raw_text="",
                transport_ok=True,
                model="deepseek-resolved-test",
            ),
        ]
    )
    monkeypatch.setattr(pes, "get_llm_provider", lambda name: provider)
    monkeypatch.setattr(
        pes,
        "get_settings",
        lambda: SimpleNamespace(
            ontology_residual_model="deepseek-configured-test",
            ontology_residual_max_tokens=1200,
        ),
    )
    windows = [
        {
            "context": [
                {
                    "paragraph_id": "results_p001",
                    "passage_text": "Hippocampus and prefrontal cortex were examined.",
                    "section_title": "Results",
                }
            ]
        }
    ]

    result = _run(
        pes.extract_passage_two_stage(
            claim=_context(), title="Worker paper", windows=windows
        )
    )

    assert result["llm_model"] == "deepseek-resolved-test"
    assert provider.complete_json.await_count == 2


def test_single_paper_worker_returns_explicit_no_evidence_envelope(monkeypatch):
    _install_pipeline_mocks(
        monkeypatch,
        {
            "overall_direction": "not_found",
            "assessment": "no matching evidence",
            "passages": [],
            "not_found_reason": "claim absent",
            "evidence_dimension": "function",
            "llm_model": "deepseek-worker-test",
            "parse_status": "ok",
        },
    )

    envelope = _run(
        pes.extract_candidate_for_paper(
            _Session(),
            context=_context(),
            paper=_paper(),
            only_oa=False,
            sem_fetch=asyncio.Semaphore(1),
            sem_deepseek=asyncio.Semaphore(1),
            mode="function",
        )
    )

    assert envelope["status"] == "no_evidence"
    assert envelope["candidate"]["model_direction"] == "not_found"
    assert envelope["candidate"]["coverage_summary"]["overall_direction"] == "not_found"
    assert envelope["candidate"]["passages"] == []
    assert envelope["candidate"]["not_found_reason"] == "claim absent"
    assert envelope["candidate"]["evidence_dimension"] == "function"


def test_single_paper_worker_returns_explicit_non_oa_envelope(monkeypatch):
    _install_pipeline_mocks(
        monkeypatch,
        {"overall_direction": "not_found", "passages": []},
        is_open_access=False,
    )

    envelope = _run(
        pes.extract_candidate_for_paper(
            _Session(),
            context=_context(),
            paper=_paper(is_open_access=False),
            only_oa=True,
            sem_fetch=asyncio.Semaphore(1),
            sem_deepseek=asyncio.Semaphore(1),
            mode="function",
        )
    )

    assert envelope["status"] == "no_evidence"
    assert envelope["reason"] == "non_oa"
    assert envelope["candidate"]["passages"] == []
    pes.ensure_paper_source.assert_not_awaited()
    pes._extract_from_paper_with_retry.assert_not_awaited()


def test_single_paper_worker_keeps_provider_failure_explicit(monkeypatch):
    _install_pipeline_mocks(
        monkeypatch,
        {"overall_direction": "not_found", "passages": []},
    )
    pes._extract_from_paper_with_retry.side_effect = ValueError("parse_error")

    envelope = _run(
        pes.extract_candidate_for_paper(
            _Session(),
            context=_context(),
            paper=_paper(),
            only_oa=False,
            sem_fetch=asyncio.Semaphore(1),
            sem_deepseek=asyncio.Semaphore(1),
            mode="function",
        )
    )

    assert envelope["status"] == "failed"
    assert envelope["error_stage"] == "extract"
    assert envelope["candidate"]["error_code"] == "DEEPSEEK_PARSE_FAILED"
    assert envelope["candidate"]["passages"] == []


def test_single_paper_worker_classifies_fetch_timeout_by_fetch_stage(monkeypatch):
    monkeypatch.setattr(
        pes,
        "_verify_paper_with_retry",
        AsyncMock(side_effect=httpx.ReadTimeout("paper fetch timed out")),
    )

    envelope = _run(
        pes.extract_candidate_for_paper(
            _Session(),
            context=_context(),
            paper=_paper(),
            only_oa=False,
            sem_fetch=asyncio.Semaphore(1),
            sem_deepseek=asyncio.Semaphore(1),
            mode="function",
        )
    )

    assert envelope["status"] == "failed"
    assert envelope["error_stage"] == "fetch"
    assert envelope["candidate"]["error_code"] == "EUROPE_PMC_TIMEOUT"


@pytest.mark.parametrize(
    "parse_status",
    ["provider_error", "parse_error", "network_error", "schema_error"],
)
def test_single_paper_worker_rejects_returned_processing_failure(
    monkeypatch, parse_status
):
    _install_pipeline_mocks(
        monkeypatch,
        {
            "overall_direction": "not_found",
            "assessment": "processing failed",
            "passages": [],
            "parse_status": parse_status,
        },
    )

    envelope = _run(
        pes.extract_candidate_for_paper(
            _Session(),
            context=_context(),
            paper=_paper(),
            only_oa=False,
            sem_fetch=asyncio.Semaphore(1),
            sem_deepseek=asyncio.Semaphore(1),
            mode="function",
        )
    )

    assert envelope["status"] == "failed"
    assert envelope["error_stage"] == "extract"
    assert envelope["reason"] == parse_status
    assert envelope["candidate"]["error_code"] == "DEEPSEEK_PARSE_FAILED"


def test_judge_retry_exhaustion_raises_processing_failure(monkeypatch):
    provider = AsyncMock()
    provider.complete_json = AsyncMock(side_effect=RuntimeError("provider unavailable"))
    monkeypatch.setattr(pes, "get_llm_provider", lambda name: provider)
    monkeypatch.setattr(
        pes,
        "get_settings",
        lambda: SimpleNamespace(
            ontology_residual_model="deepseek-test",
            ontology_residual_max_tokens=1200,
        ),
    )

    candidates = [
        {
            "paragraph_id": "results_p001",
            "relevance": 0.9,
            "relation_cue": "direct_connection",
            "passage_text": "The hippocampus projects to prefrontal cortex.",
            "section": "Results",
        }
    ]

    with pytest.raises(ValueError, match="evidence judge failed"):
        _run(pes.judge_candidates(_context(), candidates, "Worker paper"))

    assert provider.complete_json.await_count == 2


def test_legacy_wrapper_delegates_serially_and_stops_after_strong_support(monkeypatch):
    papers = [_paper(), {**_paper(), "pmid": "99100002", "title": "Second"}]
    worker = AsyncMock(
        side_effect=[
            {
                "status": "completed",
                "reason": None,
                "llm_model": "deepseek-worker-test",
                "candidate": {
                    "pmid": "99100001",
                    "coverage_summary": {
                        "overall_direction": "supports",
                        "full_claim_supported": True,
                    },
                    "passages": [],
                },
            },
            {
                "status": "completed",
                "reason": None,
                "llm_model": "deepseek-worker-test",
                "candidate": {"pmid": "99100002", "passages": []},
            },
        ]
    )
    monkeypatch.setattr(pes, "extract_candidate_for_paper", worker)
    monkeypatch.setattr(pes, "_rank_papers", lambda items, context: items)

    candidates, model = _run(
        pes.extract_candidates_for_target(
            _Session(),
            context=_context(),
            papers=papers,
            max_papers=2,
            only_oa=False,
            stop_after_strong_support=True,
            mode="existence",
            sem_fetch=asyncio.Semaphore(1),
            sem_deepseek=asyncio.Semaphore(1),
            apply_semantic_filter=False,
        )
    )

    assert [candidate["pmid"] for candidate in candidates] == ["99100001"]
    assert model == "deepseek-worker-test"
    assert worker.await_count == 1
    assert worker.await_args.kwargs["paper"] is papers[0]
    assert worker.await_args.kwargs["mode"] == "existence"


def test_legacy_wrapper_preserves_ranked_order_and_applies_max_after_filter(
    monkeypatch,
):
    papers = [
        {**_paper(), "pmid": "99100001", "title": "First"},
        {**_paper(), "pmid": "99100002", "title": "Second"},
        {**_paper(), "pmid": "99100003", "title": "Third"},
        {**_paper(), "pmid": "99100004", "title": "Skipped"},
    ]
    semantic_filter = AsyncMock(return_value=(papers[:3], [papers[3]]))
    monkeypatch.setattr(pes, "semantic_filter_papers", semantic_filter)
    monkeypatch.setattr(
        pes, "_rank_papers", lambda items, context: [items[2], items[0], items[1]]
    )
    processed = []

    async def worker(session, *, paper, **kwargs):
        processed.append(paper["pmid"])
        return {
            "status": "no_evidence",
            "reason": "no_verified_evidence",
            "llm_model": "deepseek-worker-test",
            "candidate": {
                "pmid": paper["pmid"],
                "coverage_summary": {"overall_direction": "not_found"},
                "passages": [],
            },
        }

    monkeypatch.setattr(pes, "extract_candidate_for_paper", worker)

    candidates, _ = _run(
        pes.extract_candidates_for_target(
            _Session(),
            context=_context(),
            papers=papers,
            max_papers=2,
            only_oa=False,
            stop_after_strong_support=False,
            mode="function",
            sem_fetch=asyncio.Semaphore(1),
            sem_deepseek=asyncio.Semaphore(1),
            apply_semantic_filter=True,
        )
    )

    assert processed == ["99100003", "99100001"]
    assert [candidate["pmid"] for candidate in candidates] == [
        "99100003",
        "99100001",
        "99100004",
    ]
    assert candidates[-1]["error_code"] == "SEMANTIC_SKIPPED"
    semantic_filter.assert_awaited_once_with(papers, _context())
