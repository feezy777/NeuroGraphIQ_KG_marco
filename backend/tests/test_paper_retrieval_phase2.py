"""Phase 2: OA XML parsing, weighted retrieval, DeepSeek judgment, strict verification."""

from __future__ import annotations

import asyncio
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services import oa_xml_parser
from app.services import paper_evidence_service as pes
from app.services import paper_fetch_service as pfs
from app.services.paragraph_retrieval import build_windows, score_paragraphs


def _run(coro):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


OA_XML = """<?xml version="1.0"?>
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <body>
    <sec>
      <title>Introduction</title>
      <p id="int_p1">Both the basolateral amygdala (BLA) and the prefrontal cortex (PFC) participate in fear regulation.</p>
      <p id="int_p2">Fear extinction learning depends on interactions between limbic structures.</p>
    </sec>
    <sec>
      <title>Methods</title>
      <p id="meth_p1">We injected anterograde tracers into the BLA of adult mice.</p>
    </sec>
    <sec>
      <title>Results</title>
      <p id="res_p1">Anterograde tracing revealed dense BLA terminals in the infralimbic cortex.</p>
      <p id="res_p2">Optogenetic activation of BLA terminals in the infralimbic cortex facilitated extinction learning.</p>
    </sec>
    <sec>
      <title>Discussion</title>
      <p id="disc_p1">We conclude that the BLA to infralimbic cortex pathway contributes to fear extinction.</p>
    </sec>
  </body>
</article>
"""


def test_oa_xml_parses_sections_and_stable_ids():
    paragraphs = oa_xml_parser.parse_oa_xml(OA_XML)
    assert len(paragraphs) == 6
    by_id = {p["paragraph_id"]: p for p in paragraphs}
    assert set(by_id) == {"int_p1", "int_p2", "meth_p1", "res_p1", "res_p2", "disc_p1"}
    assert by_id["res_p1"]["section_title"] == "Results"
    assert by_id["int_p1"]["section_title"] == "Introduction"
    assert by_id["disc_p1"]["section_title"] == "Discussion"
    # stable composite ids when no XML id present
    xml_no_id = OA_XML.replace(' id="int_p1"', "").replace(' id="int_p2"', "").replace(' id="meth_p1"', "")
    a = oa_xml_parser.parse_oa_xml(xml_no_id)
    b = oa_xml_parser.parse_oa_xml(xml_no_id)
    assert [p["paragraph_id"] for p in a] == [p["paragraph_id"] for p in b]
    assert all(p["paragraph_id"].startswith("introduction_p") for p in a[:2])


def test_score_paragraphs_ranking_priorities():
    paragraphs = [
        {"paragraph_id": "r1", "section_title": "Results", "paragraph_index": 0, "passage_text": "BLA terminals in the infralimbic cortex facilitated fear extinction."},
        {"paragraph_id": "r2", "section_title": "Results", "paragraph_index": 1, "passage_text": "BLA and infralimbic cortex activity correlated during fear conditioning."},
        {"paragraph_id": "i1", "section_title": "Introduction", "paragraph_index": 2, "passage_text": "The infralimbic cortex is involved in fear extinction."},
        {"paragraph_id": "m1", "section_title": "Methods", "paragraph_index": 3, "passage_text": "We used standard tracing protocols."},
    ]
    ranked = score_paragraphs(
        paragraphs,
        source_region="BLA",
        target_region="infralimbic cortex",
        function_terms=["fear extinction"],
        relation_keywords=["terminal", "projection"],
    )
    assert ranked[0]["paragraph_id"] == "r1"
    assert ranked[0]["total_retrieval_score"] > ranked[1]["total_retrieval_score"]
    # word-boundary matching: all 3 concept groups hit, proximity bonus
    assert "bla" in [m.lower() for m in ranked[0].get("matched_regions", [])]
    assert "infralimbic cortex" in [m.lower() for m in ranked[0].get("matched_regions", [])]
    # co-occurrence paragraph ranks below full source+target+function hit
    assert ranked[1]["paragraph_id"] == "r2"
    # Introduction function-only ranks above unrelated Methods
    assert ranked[2]["paragraph_id"] == "i1"
    assert ranked[3]["paragraph_id"] == "m1"


def test_build_epmc_query_uses_synonym_or_groups():
    context = {
        "source_region": "BLA",
        "source_region_synonyms": ["basolateral amygdala"],
        "target_region": "infralimbic cortex",
        "target_region_synonyms": ["IL"],
        "function_terms": ["fear extinction"],
        "function_synonyms": ["extinction learning"],
        "relation_keywords": [],
    }
    q = pes._build_epmc_query(context)
    # default is ABSTRACT-only (less noise); BODY variant available as fallback
    assert 'ABSTRACT:"BLA" OR ABSTRACT:"basolateral amygdala"' in q
    assert 'ABSTRACT:"infralimbic cortex" OR ABSTRACT:"IL"' in q
    assert 'ABSTRACT:"fear extinction" OR ABSTRACT:"extinction learning"' in q
    assert 'BODY:' not in q
    assert q.count(" AND ") == 2
    q_wide = pes._build_epmc_query(context, abstract_only=False)
    assert 'ABSTRACT:"BLA" OR BODY:"BLA"' in q_wide


def test_synonym_hit_boost_and_section_prior():
    paragraphs = [
        {"paragraph_id": "p1", "section_title": "Results", "paragraph_index": 0, "passage_text": "Amygdala stimulation altered extinction behavior."},
        {"paragraph_id": "p2", "section_title": "Introduction", "paragraph_index": 1, "passage_text": "Amygdala stimulation altered extinction behavior."},
    ]
    ranked = score_paragraphs(
        paragraphs,
        source_region="BLA",
        source_region_synonyms=["basolateral amygdala", "amygdala"],
        function_terms=["fear extinction"],
        function_synonyms=["extinction behavior"],
    )
    assert ranked[0]["paragraph_id"] == "p1"  # Results prior wins over identical text in Introduction
    assert ranked[0]["matched_synonyms"]
    assert ranked[0]["section_prior"] > ranked[1]["section_prior"]


def test_build_windows_marks_focus_and_context():
    all_paragraphs = [
        {"paragraph_id": "p0", "paragraph_index": 0, "passage_text": "prev"},
        {"paragraph_id": "p1", "paragraph_index": 1, "passage_text": "current"},
        {"paragraph_id": "p2", "paragraph_index": 2, "passage_text": "next"},
    ]
    ranked = score_paragraphs(all_paragraphs, source_region="current")
    windows = build_windows(ranked, all_paragraphs, top_k=1, window=1)
    assert windows[0]["focus_paragraph_id"] == "p1"
    assert [p["paragraph_id"] for p in windows[0]["context"]] == ["p0", "p1", "p2"]


def test_verify_extraction_passages_strict():
    paragraph_map = {
        "res_p1": {"paragraph_id": "res_p1", "passage_text": "BLA terminals in the infralimbic cortex.", "source_scope": "fulltext", "locator": "r:0", "paragraph_index": 0},
    }
    # fabricated paragraph id + REAL passage → fuzzy locate recovers it (id-independent)
    out = pes._verify_extraction_passages(
        [{"paragraph_id": "made_up_99", "passage": "BLA terminals in the infralimbic cortex.", "direction": "supports"}],
        paragraph_map,
    )
    assert out[0]["source_verified"] is True
    assert out[0]["source_verification_method"] == "similarity_located"
    assert out[0]["paragraph_id"] == "res_p1"
    # fabricated passage with valid id → still rejected
    # fabricated passage with valid id
    out = pes._verify_extraction_passages(
        [{"paragraph_id": "res_p1", "passage": "The hippocampus encodes all memories.", "direction": "supports"}],
        paragraph_map,
    )
    assert out[0]["source_verified"] is False
    # whitespace normalized
    out = pes._verify_extraction_passages(
        [{"paragraph_id": "res_p1", "passage": "BLA  terminals in the\ninfralimbic cortex.", "direction": "supports"}],
        paragraph_map,
    )
    assert out[0]["source_verified"] is True
    assert out[0]["source_verification_method"] == "normalized_whitespace"
    # unicode normalized
    out = pes._verify_extraction_passages(
        [{"paragraph_id": "res_p1", "passage": "BLA terminals in the infralimbic cortex\u2014confirmed.", "direction": "supports"}],
        {"res_p1": {"paragraph_id": "res_p1", "passage_text": "BLA terminals in the infralimbic cortex-confirmed.", "source_scope": "fulltext", "locator": "r:0", "paragraph_index": 0}},
    )
    assert out[0]["source_verified"] is True
    assert out[0]["source_verification_method"] == "normalized_unicode"


def test_dedupe_and_overall_direction():
    raw = [
        {"paragraph_id": "a", "passage": "same text", "direction": "supports"},
        {"paragraph_id": "a", "passage": "same text", "direction": "supports"},
        {"paragraph_id": "a", "passage": "same text longer version with more detail", "direction": "supports"},
        {"paragraph_id": "a", "passage": "same text", "direction": "contradicts"},
    ]
    deduped = pes._dedupe_extraction_passages(raw)
    assert len(deduped) == 2
    assert {p["direction"] for p in deduped} == {"supports", "contradicts"}
    supports = [p for p in deduped if p["direction"] == "supports"][0]
    assert supports["passage"] == "same text longer version with more detail"

    class _P:
        def __init__(self, direction):
            self.direction = direction
            self.passages = []

    mixed = SimpleNamespace(passages=[SimpleNamespace(direction="supports"), SimpleNamespace(direction="contradicts")])
    assert pes._combine_overall_direction(mixed) == "mixed"
    only_contra = SimpleNamespace(passages=[SimpleNamespace(direction="contradicts")])
    assert pes._combine_overall_direction(only_contra) == "contradicts"
    empty = SimpleNamespace(passages=[], overall_direction="supports")
    assert pes._combine_overall_direction(empty) == "not_found"


def test_paper_fetch_retries_transport_error(monkeypatch):
    monkeypatch.setattr(pfs, "RETRY_TIMEOUTS", (0.0, 0.0, 0.0))

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"resultList": {"result": [{"pmid": "1", "title": "T", "pmcid": "PMC1"}]}}

    class FakeClient:
        def __init__(self):
            self.calls = 0

        async def get(self, url, params=None):
            self.calls += 1
            if self.calls < 3:
                raise httpx.TransportError("boom")
            return FakeResponse()

    client = FakeClient()
    resp = _run(pfs._get_with_retry(client, "http://x", {}))
    assert client.calls == 3
    assert resp.status_code == 200


def test_paper_fetch_retries_429(monkeypatch):
    monkeypatch.setattr(pfs, "RETRY_TIMEOUTS", (0.0, 0.0, 0.0))

    class FakeResponse:
        def __init__(self, code):
            self.status_code = code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("429", request=None, response=None)

    class FakeClient:
        def __init__(self):
            self.calls = 0

        async def get(self, url, params=None):
            self.calls += 1
            return FakeResponse(429 if self.calls < 3 else 200)

    client = FakeClient()
    resp = _run(pfs._get_with_retry(client, "http://x", {}))
    assert client.calls == 3
    assert resp.status_code == 200


def test_ensure_paper_cached_reuses_fresh_metadata():
    async def case():
        async with AsyncSessionLocal() as s:
            paper = {
                "pmid": "99070001",
                "doi": "10.1/phase2",
                "title": "Cached Paper",
                "journal": "J",
                "year": "2026",
                "authors": "A",
                "abstract": "x",
                "source": "europepmc",
            }
            source = await pes.ensure_paper_source(s, paper)
            await s.commit()
            try:
                with patch.object(pfs, "fetch_paper_metadata", new=AsyncMock(return_value=paper)):
                    cached, metadata = await pfs.ensure_paper_cached(s, pmid="99070001")
                    assert cached.id == source.id
                    assert metadata is None
                    pfs.fetch_paper_metadata.assert_not_awaited()
            finally:
                await s.execute(text("DELETE FROM paper_sources WHERE id=:pid"), {"pid": source.id})
                await s.commit()

    _run(case())


# ── Controlled E2E: BLA → infralimbic cortex participates in fear extinction ──

CONTROLLED_CLAIM = {
    "claim_text": "Basolateral amygdala (BLA) to infralimbic cortex projection participates in fear extinction",
    "structured_claim": {
        "target_type": "connection",
        "source_region": "BLA",
        "target_region": "infralimbic cortex",
        "relation": "projection",
    },
    "claim_components": [
        {"component_type": "source_region", "statement": "源脑区为 BLA", "required": True, "metadata": {}},
        {"component_type": "target_region", "statement": "靶脑区为 infralimbic cortex", "required": True, "metadata": {}},
        {"component_type": "relation", "statement": "BLA 到 infralimbic cortex 存在投射", "required": True, "metadata": {}},
        {"component_type": "direction", "statement": "投射方向为 BLA -> infralimbic cortex", "required": True, "metadata": {}},
        {"component_type": "function", "statement": "该投射参与 fear extinction", "required": True, "metadata": {}},
    ],
}


class FakeDeepSeekProvider:
    def __init__(self, parsed):
        self.parsed = parsed

    async def complete_json(self, **kwargs):
        return SimpleNamespace(
            raw_text=json.dumps(self.parsed),
            parsed_json=self.parsed,
            transport_ok=True,
            error=None,
            model="test",
        )

    async def complete_text(self, **kwargs):
        return SimpleNamespace(raw_text=json.dumps(self.parsed), transport_ok=True, error=None)


def test_controlled_e2e_retrieval_and_judgment(monkeypatch):
    async def case():
        async with AsyncSessionLocal() as s:
            # paper + passages from controlled XML
            paper = {
                "pmid": "99070002",
                "doi": "10.1/e2e-phase2",
                "title": "BLA to infralimbic fear extinction",
                "journal": "J",
                "year": "2026",
                "authors": "A B",
                "abstract": "",
                "source": "europepmc",
            }
            source = await pes.ensure_paper_source(s, paper)
            await s.commit()
            paragraphs = oa_xml_parser.parse_oa_xml(OA_XML)
            await pes.ensure_paper_passages(s, source.id, paragraphs)
            await s.commit()
            try:
                all_paragraphs = await pes.load_paper_passages(s, source.id)
                # Results paragraphs must rank above co-occurrence / reverse-like context
                ranked = score_paragraphs(
                    all_paragraphs,
                    source_region="BLA",
                    target_region="infralimbic cortex",
                    function_terms=["fear extinction"],
                    relation_keywords=["terminal", "projection", "pathway"],
                )
                top_ids = [p["paragraph_id"] for p in ranked[:3]]
                assert "res_p1" in top_ids
                assert "res_p2" in top_ids
                windows = build_windows(ranked, all_paragraphs, top_k=10, window=1)
                # Top focus is either a Results paragraph or the Discussion paragraph
                # that states the full claim verbatim; Introduction co-occurrence must NOT lead.
                assert windows[0]["focus_paragraph_id"] in ("res_p1", "res_p2", "disc_p1")
                assert all(w["focus_paragraph_id"] != "int_p1" for w in windows[:3])
                # DeepSeek returns Results direct + Discussion interpretive (all verbatim)
                parsed = {
                    "overall_direction": "supports",
                    "paper_relevance": 0.9,
                    "assessment": "Results demonstrate BLA terminals in infralimbic cortex facilitate extinction.",
                    "passages": [
                        {
                            "paragraph_id": "res_p1",
                            "section": "Results",
                            "passage": "Anterograde tracing revealed dense BLA terminals in the infralimbic cortex.",
                            "direction": "supports",
                            "evidence_level": "direct",
                            "reason": "direct anatomical evidence of the projection",
                            "confidence": 0.92,
                            "semantic_confidence": 0.92,
                            "supported_components": ["source_region", "target_region", "relation", "direction"],
                        },
                        {
                            "paragraph_id": "res_p2",
                            "section": "Results",
                            "passage": "Optogenetic activation of BLA terminals in the infralimbic cortex facilitated extinction learning.",
                            "direction": "supports",
                            "evidence_level": "direct",
                            "reason": "activation of the projection affects extinction",
                            "confidence": 0.9,
                            "semantic_confidence": 0.9,
                            "supported_components": ["function"],
                        },
                        {
                            "paragraph_id": "disc_p1",
                            "section": "Discussion",
                            "passage": "We conclude that the BLA to infralimbic cortex pathway contributes to fear extinction.",
                            "direction": "supports",
                            "evidence_level": "interpretive",
                            "reason": "author interpretation of the pathway",
                            "confidence": 0.7,
                            "semantic_confidence": 0.7,
                            "supported_components": ["relation", "function", "direction"],
                        },
                    ],
                }
                monkeypatch.setattr(
                    pes,
                    "get_llm_provider",
                    lambda name: FakeDeepSeekProvider(parsed),
                )
                result = await pes.extract_passage_from_paper(
                    claim=CONTROLLED_CLAIM,
                    title=paper["title"],
                    windows=windows,
                )
                assert result["overall_direction"] == "supports"
                assert result["paper_relevance"] == pytest.approx(0.9)
                assert result["assessment"]
                assert len(result["passages"]) >= 2
                assert result["coverage_summary"]["full_claim_supported"] is True
                assert result["coverage_summary"]["has_conflict"] is False
                assert set(result["coverage_summary"]["supported_components"]) >= {
                    "source_region", "target_region", "relation", "direction", "function",
                }
                assert result["coverage_summary"]["uncovered_components"] == []
                by_id = {p["paragraph_id"]: p for p in result["passages"]}
                assert "res_p1" in by_id and "res_p2" in by_id and "disc_p1" in by_id
                assert by_id["res_p1"]["source_verified"] is True
                assert by_id["res_p1"]["source_verification_method"] == "exact"
                assert by_id["res_p1"]["evidence_level"] == "direct"
                assert by_id["disc_p1"]["evidence_level"] == "interpretive"
                # a single passage does NOT alone prove the full claim
                assert "function" not in (by_id["res_p1"]["supported_components"] or [])
                # No reverse-direction or co-occurrence paragraph accepted as evidence
                returned_ids = {p["paragraph_id"] for p in result["passages"]}
                assert "int_p1" not in returned_ids  # co-occurrence only
            finally:
                await s.execute(text("DELETE FROM paper_passages WHERE paper_id=:pid"), {"pid": source.id})
                await s.execute(text("DELETE FROM paper_sources WHERE id=:pid"), {"pid": source.id})
                await s.commit()

    _run(case())


def test_controlled_e2e_fabricated_passage_rejected(monkeypatch):
    async def case():
        async with AsyncSessionLocal() as s:
            paper = {
                "pmid": "99070003",
                "doi": "10.1/e2e-fake",
                "title": "Fake passage paper",
                "journal": "J",
                "year": "2026",
                "authors": "A",
                "abstract": "",
                "source": "europepmc",
            }
            source = await pes.ensure_paper_source(s, paper)
            await s.commit()
            paragraphs = oa_xml_parser.parse_oa_xml(OA_XML)
            await pes.ensure_paper_passages(s, source.id, paragraphs)
            await s.commit()
            try:
                all_paragraphs = await pes.load_paper_passages(s, source.id)
                windows = build_windows(
                    score_paragraphs(all_paragraphs, source_region="BLA", target_region="infralimbic cortex"),
                    all_paragraphs,
                    top_k=5,
                )
                parsed = {
                    "overall_direction": "supports",
                    "paper_relevance": 0.8,
                    "assessment": "contains a fabricated passage",
                    "passages": [
                        {
                            "paragraph_id": "res_p1",
                            "section": "Results",
                            "passage": "The amygdala directly encodes extinction memory in prefrontal cortex.",
                            "direction": "supports",
                            "evidence_level": "direct",
                            "reason": "fabricated",
                            "confidence": 0.9,
                            "semantic_confidence": 0.9,
                        }
                    ],
                }
                monkeypatch.setattr(pes, "get_llm_provider", lambda name: FakeDeepSeekProvider(parsed))
                result = await pes.extract_passage_from_paper(
                    claim=CONTROLLED_CLAIM,
                    title=paper["title"],
                    windows=windows,
                )
                assert result["passages"][0]["source_verified"] is False
                assert result["passages"][0]["source_verification_method"] is None
                assert result["retrieval_summary"]["verified_count"] == 0
            finally:
                await s.execute(text("DELETE FROM paper_passages WHERE paper_id=:pid"), {"pid": source.id})
                await s.execute(text("DELETE FROM paper_sources WHERE id=:pid"), {"pid": source.id})
                await s.commit()

    _run(case())


class PromptCapturingProvider:
    def __init__(self, parsed):
        self.parsed = parsed
        self.last_user_prompt = ""

    async def complete_json(self, **kwargs):
        self.last_user_prompt = kwargs.get("user_prompt") or ""
        return SimpleNamespace(
            raw_text=json.dumps(self.parsed),
            parsed_json=self.parsed,
            transport_ok=True,
            error=None,
            model="test",
        )

    async def complete_text(self, **kwargs):
        self.last_user_prompt = kwargs.get("user_prompt") or ""
        return SimpleNamespace(raw_text=json.dumps(self.parsed), transport_ok=True, error=None)


def test_deepseek_prompt_contains_direction_and_verbatim_rules(monkeypatch):
    provider = PromptCapturingProvider(
        {
            "overall_direction": "not_found",
            "paper_relevance": 0.0,
            "assessment": "no evidence",
            "passages": [],
        }
    )
    monkeypatch.setattr(pes, "get_llm_provider", lambda name: provider)
    windows = [
        {
            "focus_paragraph_id": "p1",
            "paragraph_index": 0,
            "section_title": "Results",
            "context": [{"paragraph_id": "p1", "paragraph_index": 0, "passage_text": "text", "source_scope": "fulltext"}],
        }
    ]
    result = _run(
        pes.extract_passage_from_paper(claim=CONTROLLED_CLAIM, title="T", windows=windows)
    )
    assert result["overall_direction"] == "not_found"
    assert result["passages"] == []
    prompt = provider.last_user_prompt
    assert "Direction matters" in prompt
    assert "Keyword co-occurrence is NOT evidence" in prompt
    assert "never invent" in prompt
    assert "copy exactly" in prompt
    assert "focus:p1" in prompt


def test_deepseek_retries_transport_error(monkeypatch):
    parsed = {
        "overall_direction": "supports",
        "paper_relevance": 0.8,
        "assessment": "ok",
        "passages": [
            {
                "paragraph_id": "p1",
                "section": "Results",
                "passage": "BLA terminals in the infralimbic cortex.",
                "direction": "supports",
                "evidence_level": "direct",
                "reason": "r",
                "confidence": 0.8,
                "semantic_confidence": 0.8,
            }
        ],
    }

    class FlakyProvider:
        def __init__(self):
            self.calls = 0

        async def complete_json(self, **kwargs):
            self.calls += 1
            if self.calls < 2:
                return SimpleNamespace(raw_text="", parsed_json=None, transport_ok=False, error="timeout")
            return SimpleNamespace(
                raw_text=json.dumps(parsed),
                parsed_json=parsed,
                transport_ok=True,
                error=None,
                model="test",
            )

        async def complete_text(self, **kwargs):
            self.calls += 1
            if self.calls == 3:
                return SimpleNamespace(
                    raw_text=json.dumps(parsed),
                    transport_ok=True,
                    error=None,
                )
            if self.calls < 3:
                return SimpleNamespace(raw_text="", transport_ok=False, error="timeout")
            return SimpleNamespace(raw_text="", transport_ok=False, error="timeout")

    provider = FlakyProvider()
    monkeypatch.setattr(pes, "get_llm_provider", lambda name: provider)
    monkeypatch.setattr(pes.asyncio, "sleep", AsyncMock())
    windows = [
        {
            "focus_paragraph_id": "p1",
            "paragraph_index": 0,
            "section_title": "Results",
            "context": [{"paragraph_id": "p1", "paragraph_index": 0, "passage_text": "BLA terminals in the infralimbic cortex.", "source_scope": "fulltext"}],
        }
    ]
    result = _run(
        pes.extract_passage_from_paper(claim=CONTROLLED_CLAIM, title="T", windows=windows)
    )
    assert provider.calls == 3
    assert result["retry_count"] == 2
    assert result["passages"][0]["source_verified"] is True


def _run_extract_with_parsed(monkeypatch, parsed, claim=CONTROLLED_CLAIM, custom_paragraphs=None):
    async def case():
        async with AsyncSessionLocal() as s:
            paper = {
                "pmid": "99070010",
                "doi": "10.1/coverage",
                "title": "Coverage paper",
                "journal": "J",
                "year": "2026",
                "authors": "A",
                "abstract": "",
                "source": "europepmc",
            }
            source = await pes.ensure_paper_source(s, paper)
            await s.commit()
            paras = custom_paragraphs if custom_paragraphs is not None else oa_xml_parser.parse_oa_xml(OA_XML)
            await pes.ensure_paper_passages(s, source.id, paras)
            await s.commit()
            try:
                all_paragraphs = await pes.load_paper_passages(s, source.id)
                windows = build_windows(
                    score_paragraphs(all_paragraphs, source_region="BLA", target_region="infralimbic cortex"),
                    all_paragraphs,
                    top_k=10,
                )
                monkeypatch.setattr(pes, "get_llm_provider", lambda name: FakeDeepSeekProvider(parsed))
                return await pes.extract_passage_from_paper(
                    claim=claim,
                    title=paper["title"],
                    windows=windows,
                )
            finally:
                await s.execute(text("DELETE FROM paper_passages WHERE paper_id=:pid"), {"pid": source.id})
                await s.execute(text("DELETE FROM paper_sources WHERE id=:pid"), {"pid": source.id})
                await s.commit()

    return _run(case())


def test_coverage_partial_when_function_missing(monkeypatch):
    parsed = {
        "overall_direction": "supports",
        "paper_relevance": 0.7,
        "assessment": "only the projection is shown, no functional evidence",
        "passages": [
            {
                "paragraph_id": "res_p1",
                "section": "Results",
                "passage": "Anterograde tracing revealed dense BLA terminals in the infralimbic cortex.",
                "direction": "supports",
                "evidence_level": "direct",
                "reason": "projection exists",
                "confidence": 0.85,
                "semantic_confidence": 0.85,
                "supported_components": ["source_region", "target_region", "relation", "direction"],
            }
        ],
    }
    result = _run_extract_with_parsed(monkeypatch, parsed)
    assert result["coverage_summary"]["uncovered_components"] == ["function"]
    assert result["coverage_summary"]["full_claim_supported"] is False
    assert result["coverage_summary"]["has_conflict"] is False
    assert result["overall_direction"] == "partial"


def test_coverage_mixed_when_support_and_contradict_coexist(monkeypatch):
    paragraphs = [
        {
            "source_scope": "fulltext",
            "section_title": "Results",
            "paragraph_id": "res_p1",
            "paragraph_index": 0,
            "passage_text": "Anterograde tracing revealed dense BLA terminals in the infralimbic cortex.",
            "text_hash": pes.passage_hash("Anterograde tracing revealed dense BLA terminals in the infralimbic cortex."),
            "locator": "results:paragraph:0",
        },
        {
            "source_scope": "fulltext",
            "section_title": "Discussion",
            "paragraph_id": "disc_p1",
            "paragraph_index": 1,
            "passage_text": "We conclude that the BLA to infralimbic cortex pathway does not contribute to fear extinction.",
            "text_hash": pes.passage_hash("We conclude that the BLA to infralimbic cortex pathway does not contribute to fear extinction."),
            "locator": "discussion:paragraph:0",
        },
    ]
    parsed = {
        "overall_direction": "mixed",
        "paper_relevance": 0.6,
        "assessment": "projection is shown but functional effect is explicitly denied",
        "passages": [
            {
                "paragraph_id": "res_p1",
                "section": "Results",
                "passage": "Anterograde tracing revealed dense BLA terminals in the infralimbic cortex.",
                "direction": "supports",
                "evidence_level": "direct",
                "reason": "projection exists",
                "confidence": 0.85,
                "semantic_confidence": 0.85,
                "supported_components": ["source_region", "target_region", "relation", "direction"],
            },
            {
                "paragraph_id": "disc_p1",
                "section": "Discussion",
                "passage": "We conclude that the BLA to infralimbic cortex pathway does not contribute to fear extinction.",
                "direction": "contradicts",
                "evidence_level": "interpretive",
                "reason": "authors explicitly deny a functional role",
                "confidence": 0.6,
                "semantic_confidence": 0.6,
                "supported_components": ["function"],
            },
        ],
    }
    result = _run_extract_with_parsed(monkeypatch, parsed, custom_paragraphs=paragraphs)
    assert result["coverage_summary"]["has_conflict"] is True
    assert result["coverage_summary"]["full_claim_supported"] is False
    assert result["coverage_summary"]["contradicted_components"] == ["function"]
    assert result["overall_direction"] == "mixed"
