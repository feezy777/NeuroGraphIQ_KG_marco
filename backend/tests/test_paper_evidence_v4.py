"""Phase D: unified paper entity + structured paragraphs + link columns."""

from __future__ import annotations

import asyncio
import uuid
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services import paper_evidence_service as pes


def _run(coro):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_doi_normalize():
    assert pes.normalize_doi(" https://doi.org/10.1000/XYZ ") == "10.1000/xyz"
    assert pes.normalize_doi("http://dx.doi.org/10.1/AB") == "10.1/ab"
    assert pes.normalize_doi("DOI:10.2/Cd") == "10.2/cd"
    assert pes.normalize_doi("10.3/ef") == "10.3/ef"


def _paper(pmid="99010001", doi=None):
    doi = doi or f"10.1000/v4-{pmid}"
    return {
        "pmid": pmid,
        "doi": doi,
        "title": "V4 Paper",
        "journal": "J V4",
        "year": "2026",
        "authors": "A B",
        "abstract": "The hippocampus supports memory consolidation.",
        "is_open_access": True,
        "source": "europepmc",
    }


def test_paper_source_dedup_by_pmid_and_doi():
    async def case():
        async with AsyncSessionLocal() as s:
            p1 = await pes.ensure_paper_source(s, _paper(pmid="99010001"))
            p2 = await pes.ensure_paper_source(s, _paper(pmid="99010001"))
            assert p1.id == p2.id
            await s.commit()
            count = (
                await s.execute(
                    text("SELECT COUNT(*) FROM paper_sources WHERE pmid='99010001'")
                )
            ).scalar_one()
            assert count == 1
            pid = p1.id
            # doi-only upsert with same normalized doi must dedupe too
            p3 = await pes.ensure_paper_source(s, _paper(pmid="", doi="HTTP://DOI.ORG/10.1000/V4-99010001"))
            assert p3.id == pid
            await s.commit()
            total = (
                await s.execute(text("SELECT COUNT(*) FROM paper_sources WHERE id=:pid"), {"pid": pid})
            ).scalar_one()
            assert total == 1
            # cleanup
            await s.execute(
                text("DELETE FROM paper_sources WHERE id=:pid OR normalized_doi='10.1000/v4-99010001'"),
                {"pid": pid},
            )
            await s.commit()

    _run(case())


def test_paper_passages_dedup_by_paragraph_id():
    async def case():
        async with AsyncSessionLocal() as s:
            paper = await pes.ensure_paper_source(s, _paper(pmid="99010002"))
            await s.commit()
            paragraphs = pes.parse_fulltext_paragraphs(
                "Introduction\nFirst paragraph text about hippocampus.\n\n"
                "Methods\nSecond paragraph about tracing.\n"
            )
            assert len(paragraphs) == 2
            assert paragraphs[0]["section_title"] == "Introduction"
            assert paragraphs[0]["paragraph_id"].startswith("introduction_p")
            saved1 = await pes.ensure_paper_passages(s, paper.id, paragraphs)
            saved2 = await pes.ensure_paper_passages(s, paper.id, paragraphs)
            assert len(saved1) == 2
            assert len(saved2) == 2
            assert [p["id"] for p in saved1] == [p["id"] for p in saved2]
            await s.commit()
            count = (
                await s.execute(
                    text("SELECT COUNT(*) FROM paper_passages WHERE paper_id=:pid"),
                    {"pid": paper.id},
                )
            ).scalar_one()
            assert count == 2
            candidates = await pes.recall_candidate_passages(s, paper.id, "hippocampus", limit=10)
            assert candidates
            assert any("hippocampus" in c["passage_text"].lower() for c in candidates)
            # cleanup
            await s.execute(text("DELETE FROM paper_sources WHERE id=:pid"), {"pid": paper.id})
            await s.commit()

    _run(case())


def test_paper_extract_pipeline_paragraph_ids():
    async def case():
        async with AsyncSessionLocal() as s:
            paper = await pes.ensure_paper_source(s, _paper(pmid="99010003"))
            await s.commit()
            paragraphs = pes.parse_fulltext_paragraphs(
                "Results\nNeurons in the hippocampus were activated during recall.\n\n"
                "Discussion\nThe hippocampus is critical for memory consolidation.\n"
            )
            saved = await pes.ensure_paper_passages(s, paper.id, paragraphs)
            by_id = {p["paragraph_id"]: p for p in saved}
            assert "results_p001" in by_id
            assert "discussion_p002" in by_id
            candidates = await pes.recall_candidate_passages(s, paper.id, "memory consolidation", limit=10)
            assert candidates[0]["paragraph_id"] == "discussion_p002"
            await s.execute(text("DELETE FROM paper_sources WHERE id=:pid"), {"pid": paper.id})
            await s.commit()

    _run(case())
