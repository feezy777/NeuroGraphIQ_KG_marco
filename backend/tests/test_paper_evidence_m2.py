"""M2: mode=existence 贯穿 + 提取前语义筛选。"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.main import app
from app.models.mirror_kg import MirrorRegionConnection
from app.models.mirror_review import MirrorHumanReviewRecord  # noqa: F401  (schema import side effects)
from app.models.resource import AtlasResource
from app.schemas.mirror_kg import MirrorPromotionStatus, MirrorReviewStatus, MirrorStatus
from app.services import evidence_target_adapter as eta
from app.services import paper_evidence_service as pes


def _run(coro):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _connection(**kwargs) -> MirrorRegionConnection:
    defaults = dict(
        id=uuid.uuid4(),
        batch_id=None,
        resource_id=uuid.uuid4(),
        source_atlas="Macro96",
        granularity_level="macro",
        granularity_family="macro_clinical",
        source_region_name_en="Hippocampus",
        target_region_name_en="Prefrontal Cortex",
        connection_type="projection",
        directionality="unidirectional",
        confidence=0.8,
        evidence_text="evidence",
        mirror_status=MirrorStatus.human_approved,
        review_status=MirrorReviewStatus.approved,
        promotion_status=MirrorPromotionStatus.not_promoted,
        raw_payload_json={},
        normalized_payload_json={},
    )
    defaults.update(kwargs)
    return MirrorRegionConnection(**defaults)


async def _insert_connection(s, **kwargs):
    """Insert a real atlas_resource + connection (FK-safe) and return (conn_id, resource_id)."""
    resource = AtlasResource(
        resource_code=f"m2test-{uuid.uuid4().hex[:10]}",
        source_atlas="Macro96",
        source_version="v1",
        granularity_level="macro",
        granularity_family="macro_clinical",
    )
    s.add(resource)
    await s.flush()
    conn = _connection(resource_id=resource.id, **kwargs)
    s.add(conn)
    await s.commit()
    return conn.id, resource.id


async def _cleanup_connection(s, conn_id, resource_id):
    await s.execute(text("DELETE FROM mirror_region_connections WHERE id=:id"), {"id": conn_id})
    await s.execute(text("DELETE FROM atlas_resources WHERE id=:id"), {"id": resource_id})
    await s.commit()


# ═══════════════════ mode=existence ═══════════════════


def test_retrieval_context_mode_function_keeps_function_terms():
    async def case():
        async with AsyncSessionLocal() as s:
            conn_id, res_id = await _insert_connection(s)
            ctx = await eta.build_retrieval_context(s, "connection", conn_id, mode="function")
            assert ctx["claim_mode"] == "function"
            assert "projection" in ctx["function_terms"]
            assert ctx["relation_keywords"]
            await _cleanup_connection(s, conn_id, res_id)

    _run(case())


def test_retrieval_context_mode_existence_drops_function_terms():
    async def case():
        async with AsyncSessionLocal() as s:
            conn_id, res_id = await _insert_connection(s)
            ctx = await eta.build_retrieval_context(s, "connection", conn_id, mode="existence")
            assert ctx["claim_mode"] == "existence"
            assert ctx["function_terms"] == []
            assert ctx["function_synonyms"] == []
            # relation/direction still retained for existence matching
            assert ctx["relation_keywords"]
            # claim itself unchanged (existence is about retrieval, not the claim)
            assert "Hippocampus" in ctx["claim_text"]
            await _cleanup_connection(s, conn_id, res_id)

    _run(case())


def test_build_search_query_mode_existence_regions_only():
    async def case():
        async with AsyncSessionLocal() as s:
            conn_id, res_id = await _insert_connection(s)
            query_fn = await eta.build_search_query(s, "connection", conn_id)
            assert "Hippocampus" in query_fn
            assert "Prefrontal Cortex" in query_fn
            assert "projection" in query_fn
            query_ex = await eta.build_search_query(s, "connection", conn_id, mode="existence")
            assert "Hippocampus" in query_ex
            assert "Prefrontal Cortex" in query_ex
            assert "projection" not in query_ex.lower()
            await _cleanup_connection(s, conn_id, res_id)

    _run(case())


def test_extract_selected_endpoint_forwards_mode(monkeypatch):
    """POST /evidence/extract-selected forwards mode to context + extractor."""
    captured = {}
    extractor = AsyncMock(return_value=([], "deepseek-test"))

    async def fake_context(session, target_type, target_id, **kwargs):
        captured.update(kwargs)
        return {"claim_text": "c", "claim_components": [], "function_term": "f"}

    monkeypatch.setattr("app.routers.ontology.pes.build_retrieval_context", fake_context)
    monkeypatch.setattr("app.routers.ontology.pes.extract_candidates_for_target", extractor)

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/api/ontology/evidence/extract-selected",
        json={
            "target_type": "connection",
            "target_id": str(uuid.uuid4()),
            "papers": [{"pmid": "99020001", "title": "P"}],
            "mode": "existence",
        },
    )
    assert resp.status_code == 200
    assert captured.get("mode") == "existence"
    assert extractor.await_args.kwargs.get("mode") == "existence"
    assert extractor.await_args.kwargs.get("apply_semantic_filter") is False


# ═══════════════════ 提取前语义筛选 ═══════════════════


def _fake_provider(items):
    provider = AsyncMock()
    provider.complete_json = AsyncMock(
        return_value=SimpleNamespace(
            parsed_json={"items": items},
            raw_text="",
            transport_ok=True,
            model="deepseek-test",
        )
    )
    return provider


def _paper(pmid):
    return {
        "pmid": pmid,
        "doi": f"10.1/{pmid}",
        "title": f"Paper {pmid}",
        "abstract": f"Abstract about {pmid}.",
        "is_open_access": True,
        "fulltext_available": False,
        "year": "2026",
        "source": "europepmc",
    }


def test_semantic_filter_skips_low_relevance(monkeypatch):
    provider = _fake_provider(
        [
            {"pmid": "99030001", "relevance": 0.9, "reason": "directly studies the claim"},
            {"pmid": "99030002", "relevance": 0.1, "reason": "only mentions a region in passing"},
        ]
    )
    monkeypatch.setattr(pes, "get_llm_provider", lambda name: provider)

    async def case():
        keep, skipped = await pes.semantic_filter_papers(
            [_paper("99030001"), _paper("99030002")],
            {"claim_text": "Hippocampus projects to PFC"},
            threshold=0.4,
        )
        assert [p["pmid"] for p in keep] == ["99030001"]
        assert len(skipped) == 1
        assert skipped[0]["pmid"] == "99030002"
        assert skipped[0]["semantic_relevance"] == 0.1
        assert skipped[0]["semantic_skip_reason"]

    _run(case())


def test_semantic_filter_threshold_zero_disables(monkeypatch):
    provider = _fake_provider([{"pmid": "99030003", "relevance": 0.1, "reason": "low"}])
    monkeypatch.setattr(pes, "get_llm_provider", lambda name: provider)

    async def case():
        keep, skipped = await pes.semantic_filter_papers(
            [_paper("99030003")],
            {"claim_text": "c"},
            threshold=0.0,
        )
        assert len(keep) == 1
        assert skipped == []
        provider.complete_json.assert_not_awaited()

    _run(case())


def test_semantic_filter_provider_failure_degrades_to_keep_all(monkeypatch):
    provider = AsyncMock()
    provider.complete_json = AsyncMock(side_effect=RuntimeError("deepseek down"))
    monkeypatch.setattr(pes, "get_llm_provider", lambda name: provider)
    monkeypatch.setattr(pes.asyncio, "sleep", AsyncMock())

    async def case():
        keep, skipped = await pes.semantic_filter_papers(
            [_paper("99030004")],
            {"claim_text": "c"},
            threshold=0.4,
        )
        # conservative: never drop papers because the filter itself failed
        assert len(keep) == 1
        assert skipped == []

    _run(case())


def test_semantic_filter_keeps_papers_missing_from_model_response(monkeypatch):
    provider = _fake_provider(
        [{"pmid": "99030007", "relevance": 0.9, "reason": "directly studies the claim"}]
    )
    monkeypatch.setattr(pes, "get_llm_provider", lambda name: provider)

    async def case():
        keep, skipped = await pes.semantic_filter_papers(
            [_paper("99030007"), _paper("99030008")],
            {"claim_text": "Hippocampus projects to PFC"},
            threshold=0.4,
        )
        assert [p["pmid"] for p in keep] == ["99030007", "99030008"]
        assert skipped == []

    _run(case())


def test_extract_candidates_semantic_skips_appear_as_candidates(monkeypatch):
    """Skipped papers surface in results with SEMANTIC_SKIPPED so users can audit."""
    provider = _fake_provider(
        [
            {"pmid": "99030005", "relevance": 0.9, "reason": "relevant"},
            {"pmid": "99030006", "relevance": 0.05, "reason": "unrelated review"},
        ]
    )
    monkeypatch.setattr(pes, "get_llm_provider", lambda name: provider)

    async def fake_meta(pmid):
        return {
            "pmid": pmid, "title": "P", "abstract": "a", "journal": "J", "year": "2026",
            "is_open_access": True, "source": "europepmc",
        }

    async def fake_fetch(pmid=None, pmcid=None):
        return ""

    fake_extract = AsyncMock(
        return_value={
            "passages": [], "overall_direction": "not_found", "parse_status": "ok",
            "retry_count": 0, "raw_response": "", "assessment": None,
        }
    )
    monkeypatch.setattr(pes, "_verify_paper_with_retry", fake_meta)
    monkeypatch.setattr(pes.pfs, "fetch_oa_fulltext_xml", fake_fetch)
    monkeypatch.setattr(pes, "_extract_from_paper_with_retry", fake_extract)
    monkeypatch.setattr(pes, "_rank_papers", lambda papers, ctx: papers)
    # enable filtering explicitly (default config threshold is 0 = disabled)
    monkeypatch.setattr(
        pes,
        "get_settings",
        lambda: SimpleNamespace(
            paper_semantic_threshold=0.4,
            ontology_residual_model="deepseek-test",
            paper_semantic_max_tokens=1200,
            ontology_residual_backoff_seconds=0,
        ),
    )

    context = {
        "claim_text": "c", "claim_components": [],
        "source_region": "Hippocampus", "target_region": "PFC",
        "function_terms": [], "function_synonyms": [],
        "relation_keywords": [], "source_region_synonyms": [],
        "target_region_synonyms": [],
    }

    async def case():
        async with AsyncSessionLocal() as s:
            sem = asyncio.Semaphore(2)
            results, _ = await pes.extract_candidates_for_target(
                s,
                context=context,
                papers=[_paper("99030005"), _paper("99030006")],
                max_papers=2,
                only_oa=False,
                stop_after_strong_support=False,
                sem_fetch=sem,
                sem_deepseek=sem,
            )
        by_pmid = {r["pmid"]: r for r in results}
        assert by_pmid["99030005"].get("error_code") is None
        assert by_pmid["99030006"]["error_code"] == "SEMANTIC_SKIPPED"
        assert by_pmid["99030006"]["semantic_relevance"] == 0.05
        # extraction only ran for the kept paper
        assert fake_extract.call_count == 1

    _run(case())


# ═══════════════════ 存在性/功能性判定维度 ═══════════════════


def test_extract_dimension_passthrough(monkeypatch):
    provider = AsyncMock()
    provider.complete_json = AsyncMock(
        return_value=SimpleNamespace(
            parsed_json={
                "overall_direction": "supports",
                "paper_relevance": 0.9,
                "assessment": "a",
                "evidence_dimension": "existence",
                "passages": [
                    {
                        "paragraph_id": "results_p001",
                        "section": "Results",
                        "passage": "The hippocampus projects to the prefrontal cortex.",
                        "direction": "supports",
                        "evidence_level": "direct",
                        "reason": "r",
                        "confidence": 0.9,
                        "semantic_confidence": 0.9,
                        "supported_components": ["source_region", "relation"],
                        "evidence_dimension": "existence",
                    }
                ],
            },
            raw_text="",
            transport_ok=True,
            model="deepseek-test",
        )
    )
    monkeypatch.setattr(pes, "get_llm_provider", lambda name: provider)

    async def case():
        windows = [
            {
                "focus_paragraph_id": "results_p001",
                "section_title": "Results",
                "paragraph_index": 0,
                "context": [
                    {
                        "paragraph_id": "results_p001",
                        "paragraph_index": 0,
                        "passage_text": "The hippocampus projects to the prefrontal cortex.",
                        "source_scope": "fulltext",
                        "section_title": "Results",
                        "locator": "results:paragraph:0",
                    }
                ],
            }
        ]
        result = await pes.extract_passage_from_paper(
            claim={
                "claim_text": "c",
                "claim_components": [
                    {"component_type": "source_region", "required": True},
                    {"component_type": "relation", "required": True},
                ],
            },
            title="Paper",
            windows=windows,
        )
        assert result["evidence_dimension"] == "existence"
        assert result["passages"][0]["evidence_dimension"] == "existence"
        assert result["passages"][0]["source_verified"] is True
        # prompt instructs the dimension judgment
        prompt = provider.complete_json.await_args.kwargs["user_prompt"]
        assert "evidence_dimension" in prompt
        assert "existence" in prompt

    _run(case())


def test_core_region_term():
    assert pes._core_region_term("right thalamus proper") == "thalamus"
    assert pes._core_region_term("right putamen") == "putamen"
    assert pes._core_region_term("medial prefrontal cortex") == "prefrontal cortex"
    # structural suffixes stripped, numeric labels dropped, trimmed to 3 words
    assert pes._core_region_term("Agranular insular area, posterior part, layer 6b") == "Agranular insular"
    assert pes._core_region_term("dorsal hippocampal commissure") == "hippocampal commissure"
    assert pes._core_region_term("Superior colliculus, motor related, intermediate gray layer, sublayer a") == "colliculus"
    # no modifiers → unchanged (case preserved, search is case-insensitive)
    assert pes._core_region_term("Hippocampus") == "Hippocampus"
    assert pes._core_region_term("") == ""
    assert pes._core_region_term(None) == ""


def test_build_epmc_query_loosened_for_connection():
    ctx = {
        "object_type": "connection",
        "source_region": "right thalamus proper",
        "target_region": "right putamen",
        "source_region_synonyms": [],
        "target_region_synonyms": [],
        "function_terms": [],
        "function_synonyms": [],
        "relation_keywords": ["projection"],
    }
    q = pes._build_epmc_query(ctx).lower()
    # core terms loosen the exact-phrase requirement
    assert "thalamus" in q
    assert "putamen" in q
    # connection-evidence vocabulary replaces the rare "structural_connection"
    assert "tractography" in q
    assert "structural connectivity" in q
    assert "projection" in q
    # default is ABSTRACT-only (less noise); BODY version available as fallback
    assert 'body:"' not in q
    q_wide = pes._build_epmc_query(ctx, abstract_only=False).lower()
    assert 'body:"' in q_wide


def test_existence_mode_prompt_rule(monkeypatch):
    """existence mode instructs the model to accept region-pair connectivity without direction."""
    provider = AsyncMock()
    provider.complete_json = AsyncMock(
        return_value=SimpleNamespace(
            parsed_json={
                "overall_direction": "not_found",
                "paper_relevance": 0,
                "assessment": "a",
                "passages": [],
            },
            raw_text="",
            transport_ok=True,
            model="deepseek-test",
        )
    )
    monkeypatch.setattr(pes, "get_llm_provider", lambda name: provider)

    async def case():
        # existence mode
        await pes.extract_passage_from_paper(
            claim={"claim_text": "c", "claim_components": [], "claim_mode": "existence"},
            title="T",
            windows=[],
        )
        prompt = provider.complete_json.await_args.kwargs["user_prompt"]
        assert "Existence mode" in prompt
        assert "supported_components excluding 'direction'" in prompt
        assert "INDIRECT evidence is still evidence" in prompt
        assert "confidence 0.3-0.5" in prompt
        # function mode keeps the strict direction rule
        await pes.extract_passage_from_paper(
            claim={"claim_text": "c", "claim_components": [], "claim_mode": "function"},
            title="T",
            windows=[],
        )
        prompt2 = provider.complete_json.await_args.kwargs["user_prompt"]
        assert "Existence mode" not in prompt2
        assert "Direction matters" in prompt2

    _run(case())


def test_extract_dimension_absent_defaults_none():
    from app.services.ontology_residual_schemas import PaperMultiPassageExtraction

    parsed = PaperMultiPassageExtraction.model_validate(
        {"overall_direction": "supports", "paper_relevance": 0.5, "assessment": "a", "passages": []}
    )
    assert parsed.evidence_dimension is None
