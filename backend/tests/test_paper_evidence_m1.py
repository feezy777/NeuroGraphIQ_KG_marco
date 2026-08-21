"""M1: 验证分级 — HTML 清理 / similarity 匹配 / 模糊段落定位 / 召回窗口 / 同源。"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services import paper_evidence_service as pes
from app.services import paper_fetch_service as pfs
from app.services import oa_xml_parser
from app.services.paragraph_retrieval import build_windows


def _run(coro):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _paper(pmid="99010001"):
    return {
        "pmid": pmid,
        "doi": f"10.1000/m1-{pmid}",
        "title": "M1 Paper",
        "journal": "J M1",
        "year": "2026",
        "authors": "A B",
        "abstract": "The hippocampus supports memory consolidation.",
        "is_open_access": True,
        "source": "europepmc",
    }


def test_clean_html_text():
    assert pfs.clean_html_text("<p>Hippocampus &amp; amygdala</p>") == "Hippocampus & amygdala"
    assert pfs.clean_html_text("<p> A <i>B</i>  C </p>") == "A B C"
    assert pfs.clean_html_text("") == ""
    assert pfs.clean_html_text(None) == ""


def test_oa_xml_long_section_title_truncated():
    """paragraph_id / locator must fit varchar(128) even for long section titles."""
    long_title = ("Very Long Section Title About Functional Connectivity " * 8).strip()
    xml = (
        f'<?xml version="1.0"?><article><body><sec><title>{long_title}</title>'
        "<p>Some passage text.</p></sec></body></article>"
    )
    paragraphs = oa_xml_parser.parse_oa_xml(xml)
    assert paragraphs
    assert len(paragraphs[0]["paragraph_id"]) <= 128
    assert len(paragraphs[0]["locator"]) <= 128


def test_oa_xml_parser_unescape():
    xml = (
        '<?xml version="1.0"?><article><body><sec><title>Results</title>'
        "<p>Hippocampus &amp; cortex interactions</p></sec></body></article>"
    )
    paragraphs = oa_xml_parser.parse_oa_xml(xml)
    assert paragraphs
    assert "Hippocampus & cortex" in paragraphs[0]["passage_text"]


def test_verify_similarity_accepts_light_rewrites():
    source = (
        "The dorsal hippocampus projects to the medial prefrontal cortex "
        "and supports working memory consolidation."
    )
    # light rewrite: punctuation / hyphenation / word order tweaks
    passage = (
        "The dorsal hippocampus projects to the medial prefrontal cortex, "
        "supporting working-memory consolidation."
    )
    ok, method = pes.verify_passage_against_source(passage, source)
    assert ok is True
    assert method == "similarity"
    # unrelated text must not pass
    ok2, _ = pes.verify_passage_against_source(
        "The cerebellum controls motor coordination", source
    )
    assert ok2 is False
    # empty passage never passes
    ok3, _ = pes.verify_passage_against_source("", source)
    assert ok3 is False


def test_verify_extraction_passages_fuzzy_locate():
    paragraph_map = {
        "results_p001": {
            "paragraph_id": "results_p001",
            "source_scope": "fulltext",
            "section_title": "Results",
            "paragraph_index": 0,
            "passage_text": "Neurons in the hippocampus were activated during recall of spatial memories.",
            "locator": "results:paragraph:0",
        },
        "methods_p002": {
            "paragraph_id": "methods_p002",
            "source_scope": "fulltext",
            "section_title": "Methods",
            "paragraph_index": 1,
            "passage_text": "Animals were anesthetized with isoflurane before surgery.",
            "locator": "methods:paragraph:0",
        },
    }
    # wrong paragraph_id but passage is real → verified via fuzzy locate
    items = [
        {
            "paragraph_id": "bogus_id",
            "passage": "Neurons in the hippocampus were activated during recall of spatial memory.",
        }
    ]
    verified = pes._verify_extraction_passages(items, paragraph_map)
    assert verified[0]["source_verified"] is True
    assert verified[0]["source_verification_method"] in (
        "similarity",
        "similarity_located",
    )
    assert verified[0]["paragraph_id"] == "results_p001"
    assert verified[0]["source_locator"] == "results:paragraph:0"
    # unrelated passage → not verified (no guesswork)
    items2 = [{"paragraph_id": "bogus_id", "passage": "The cerebellum regulates balance."}]
    v2 = pes._verify_extraction_passages(items2, paragraph_map)
    assert v2[0]["source_verified"] is False


def test_verify_extraction_passages_id_hit_prefers_exact():
    paragraph_map = {
        "results_p001": {
            "paragraph_id": "results_p001",
            "source_scope": "fulltext",
            "section_title": "Results",
            "paragraph_index": 0,
            "passage_text": "Neurons in the hippocampus were activated during recall of spatial memories.",
            "locator": "results:paragraph:0",
        },
    }
    items = [
        {
            "paragraph_id": "results_p001",
            "passage": "Neurons in the hippocampus were activated during recall of spatial memories.",
        }
    ]
    verified = pes._verify_extraction_passages(items, paragraph_map)
    assert verified[0]["source_verified"] is True
    assert verified[0]["source_verification_method"] in ("exact", "normalized_whitespace")


def test_build_windows_abstract_forced_and_params():
    all_paras = [
        {
            "paragraph_id": "abstract_p001",
            "paragraph_index": 0,
            "passage_text": "The hippocampus supports memory consolidation.",
            "source_scope": "abstract",
            "section_title": "Abstract",
            "locator": "abstract:paragraph:0",
        }
    ]
    for i in range(1, 46):
        all_paras.append(
            {
                "paragraph_id": f"p{i:03d}",
                "paragraph_index": i,
                "passage_text": f"Body paragraph {i} about unrelated results.",
                "source_scope": "fulltext",
                "section_title": "Results",
                "locator": f"results:paragraph:{i}",
            }
        )
    # abstract scored lowest on purpose (no terms hit)
    ranked = sorted(
        all_paras,
        key=lambda p: (0 if p["paragraph_id"] == "abstract_p001" else 1, p["paragraph_index"]),
    )
    windows = build_windows(ranked, all_paras, top_k=40, window=2)
    assert len(windows) == 40
    assert windows[0]["focus_paragraph_id"] == "abstract_p001"
    # abstract window carries itself + 2 following neighbors (index 0 has no predecessors)
    assert len(windows[0]["context"]) == 3


def test_load_source_reuses_cached_passages(monkeypatch):
    async def case():
        async with AsyncSessionLocal() as s:
            paper = await pes.ensure_paper_source(s, _paper(pmid="99010004"))
            await s.commit()
            paras = [
                {
                    "source_scope": "fulltext",
                    "section_title": "Results",
                    "paragraph_id": "results_p001",
                    "paragraph_index": 0,
                    "passage_text": "The hippocampus projects to the prefrontal cortex.",
                    "text_hash": pes.passage_hash("The hippocampus projects to the prefrontal cortex."),
                    "locator": "results:paragraph:0",
                }
            ]
            await pes.ensure_paper_passages(s, paper.id, paras)
            await s.commit()

            async def boom(pmid: str):  # pragma: no cover - must not be called
                raise AssertionError("network must not be called when cache exists")

            monkeypatch.setattr(pes, "verify_paper", boom)
            monkeypatch.setattr(pes, "fetch_fulltext", boom)
            source, scope = await pes._load_source(s, "99010004")
            assert scope == "fulltext"
            assert "hippocampus" in source
            assert "prefrontal" in source
            await s.execute(text("DELETE FROM paper_sources WHERE id=:pid"), {"pid": paper.id})
            await s.commit()

    _run(case())


def test_load_source_falls_back_to_network_when_uncached(monkeypatch):
    async def case():
        async with AsyncSessionLocal() as s:
            async def fake_verify(pmid: str):
                return {
                    "pmid": pmid,
                    "abstract": "Abstract only fallback text.",
                    "source": "europepmc",
                }

            async def fake_fetch(pmid: str):
                return ""

            monkeypatch.setattr(pes, "verify_paper", fake_verify)
            monkeypatch.setattr(pes, "fetch_fulltext", fake_fetch)
            source, scope = await pes._load_source(s, "99010005")
            assert scope == "abstract"
            assert source == "Abstract only fallback text."

    _run(case())
