"""Deterministic paragraph retrieval over structured paper_passages.

Two stages, deliberately separated from Europe PMC paper search:
  * paper search: find relevant papers;
  * paragraph retrieval: find evidence paragraphs inside one paper.

Retrieval is lexical / weighted (no vector DB in V1). Every candidate carries
debug metadata (lexical_score, matched_terms, matched_synonyms, matched_regions,
section_prior, total_retrieval_score) so tests and tuning stay observable.
"""

from __future__ import annotations

import re

from app.services.oa_xml_parser import SECTION_PRIORS


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _hit_count(text: str, terms: list[str]) -> tuple[int, list[str]]:
    norm_text = _norm(text)
    hits = [t for t in terms if t and _norm(t) and _norm(t) in norm_text]
    return len(hits), hits


def score_paragraphs(
    paragraphs: list[dict],
    *,
    source_region: str = "",
    target_region: str = "",
    source_region_synonyms: list[str] | None = None,
    target_region_synonyms: list[str] | None = None,
    function_terms: list[str] | None = None,
    function_synonyms: list[str] | None = None,
    relation_keywords: list[str] | None = None,
) -> list[dict]:
    """Score paragraphs; returns new dicts with retrieval debug metadata."""
    source_terms = [source_region] + (source_region_synonyms or [])
    target_terms = [target_region] + (target_region_synonyms or [])
    function_terms_all = (function_terms or []) + (function_synonyms or [])
    relation_terms = [r for r in (relation_keywords or []) if r]
    scored: list[dict] = []
    for para in paragraphs:
        text = para.get("passage_text") or ""
        s_hits = _hit_count(text, [t for t in source_terms if t])
        t_hits = _hit_count(text, [t for t in target_terms if t])
        f_hits = _hit_count(text, [t for t in function_terms_all if t])
        r_hits = _hit_count(text, relation_terms)
        s_hit = s_hits[0] > 0
        t_hit = t_hits[0] > 0
        f_hit = f_hits[0] > 0
        any_region = s_hit or t_hit
        if s_hit and t_hit and f_hit:
            lexical = 100
        elif s_hit and t_hit:
            lexical = 60
        elif any_region and f_hit:
            lexical = 40
        elif f_hit:
            lexical = 20
        elif any_region:
            lexical = 10
        else:
            lexical = 0
        # canonical vs synonym: synonym-only hits add a small bonus
        canonical_hits = set(s_hits[1] + t_hits[1] + f_hits[1])
        all_hits = set(s_hits[1] + t_hits[1] + f_hits[1])
        canonical_set = {_norm(t) for t in source_terms if t} | {
            _norm(t) for t in target_terms if t
        } | {_norm(t) for t in (function_terms or []) if t}
        synonym_only = [h for h in all_hits if _norm(h) not in canonical_set]
        if synonym_only:
            lexical += 10
        if r_hits[0] > 0:
            lexical += 5
        section_prior = SECTION_PRIORS.get(_norm(para.get("section_title") or ""), 0.0)
        total = lexical + section_prior
        scored.append(
            {
                **para,
                "lexical_score": lexical,
                "matched_terms": sorted(f_hits[1]),
                "matched_synonyms": sorted(synonym_only),
                "matched_regions": sorted(set(s_hits[1] + t_hits[1])),
                "matched_relations": sorted(r_hits[1]),
                "section_prior": round(section_prior, 4),
                "total_retrieval_score": round(total, 4),
            }
        )
    scored.sort(key=lambda p: (-p["total_retrieval_score"], p.get("paragraph_index") or 0))
    return scored


def build_windows(
    ranked: list[dict],
    all_paragraphs: list[dict],
    *,
    top_k: int = 20,
    window: int = 1,
) -> list[dict]:
    """Wrap each candidate with ±window context; mark focus_paragraph_id."""
    by_index = {p.get("paragraph_index"): p for p in all_paragraphs if p.get("paragraph_index") is not None}
    windows: list[dict] = []
    for cand in ranked[:top_k]:
        idx = cand.get("paragraph_index")
        focus = cand.get("paragraph_id")
        context = []
        if idx is not None:
            for delta in range(-window, window + 1):
                neighbor = by_index.get(idx + delta)
                if neighbor is not None:
                    context.append(neighbor)
        windows.append(
            {
                "focus_paragraph_id": focus,
                "section_title": cand.get("section_title"),
                "paragraph_index": idx,
                "total_retrieval_score": cand.get("total_retrieval_score"),
                "lexical_score": cand.get("lexical_score"),
                "matched_terms": cand.get("matched_terms", []),
                "matched_synonyms": cand.get("matched_synonyms", []),
                "matched_regions": cand.get("matched_regions", []),
                "section_prior": cand.get("section_prior"),
                "context": context,
            }
        )
    return windows
