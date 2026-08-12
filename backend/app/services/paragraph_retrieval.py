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


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _hit_count(text: str, terms: list[str]) -> tuple[int, list[str]]:
    """Count matching terms + matched-token names (word-boundary, not raw substring)."""
    norm_text = _norm(text)
    hits: list[str] = []
    hit_count = 0
    for t in terms:
        tn = _norm(t)
        if not tn:
            continue
        # prefer word-boundary match: "thalamus" should NOT match "hypothalamus"
        if re.search(rf"\b{re.escape(tn)}\b", norm_text):
            hit_count += len(re.findall(rf"\b{re.escape(tn)}\b", norm_text))
            hits.append(tn)
        elif tn in norm_text:
            # fallback: substring match (lower weight applied in scoring)
            hit_count += 1
            hits.append(tn)
    return hit_count, hits


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
    """Score paragraphs with word-boundary matching + term frequency weighting.

    word-boundary match = 1×; substring-only fallback = 0.5× multiplier.
    All three concept groups (source / target / function) are scored independently
    and summed, rather than forcing a rigid boolean tier.
    """
    source_terms = [_norm(t) for t in ([source_region] + (source_region_synonyms or [])) if t]
    target_terms = [_norm(t) for t in ([target_region] + (target_region_synonyms or [])) if t]
    function_terms_all = [_norm(t) for t in ((function_terms or []) + (function_synonyms or [])) if t]
    relation_terms = [r for r in (relation_keywords or []) if r]
    scored: list[dict] = []
    for para in paragraphs:
        text = para.get("passage_text") or ""
        norm = _norm(text)
        # word-boundary hits (full weight)
        s_bw = sum(
            len(re.findall(rf"\b{re.escape(t)}\b", norm)) for t in source_terms
        )
        t_bw = sum(
            len(re.findall(rf"\b{re.escape(t)}\b", norm)) for t in target_terms
        )
        f_bw = sum(
            len(re.findall(rf"\b{re.escape(t)}\b", norm)) for t in function_terms_all
        )
        # substring-only hits (fallback, half weight)
        s_str = sum(1 for t in source_terms if t in norm and not re.search(rf"\b{re.escape(t)}\b", norm))
        t_str = sum(1 for t in target_terms if t in norm and not re.search(rf"\b{re.escape(t)}\b", norm))
        f_str = sum(1 for t in function_terms_all if t in norm and not re.search(rf"\b{re.escape(t)}\b", norm))
        r_hits = _hit_count(text, relation_terms)

        src_score = s_bw * 20 + s_str * 10
        tgt_score = t_bw * 20 + t_str * 10
        fn_score = f_bw * 15 + f_str * 8
        rel_score = r_hits[0] * 6

        # proximity bonus: both region groups hit in the same paragraph
        proximity = 0.0
        if s_bw > 0 and t_bw > 0:
            proximity = 30.0
        elif (s_bw > 0 or s_str > 0) and (t_bw > 0 or t_str > 0):
            proximity = 15.0

        lexical = src_score + tgt_score + fn_score + rel_score + proximity

        # synonym-only bonus
        all_hits = set()
        for t_set in (_hit_count(text, source_terms), _hit_count(text, target_terms), _hit_count(text, function_terms_all)):
            all_hits.update(t_set[1])
        canonical_set_norm = {_norm(t) for t in source_terms} | {_norm(t) for t in target_terms} | {_norm(t) for t in (function_terms or []) if t}
        synonym_only = [h for h in all_hits if h not in canonical_set_norm]
        if synonym_only:
            lexical += 5

        section_prior = 0.0
        raw_section = _norm(para.get("section_title") or "")
        for key_section in ("abstract", "results", "discussion", "conclusion"):
            if key_section in raw_section:
                section_prior = 0.15  # high-signal sections
                break
        else:
            if "introduction" in raw_section:
                section_prior = 0.03
            elif "methods" in raw_section:
                section_prior = 0.05

        s_hits = _hit_count(text, source_terms)
        f_hits = _hit_count(text, function_terms_all)
        total = lexical + section_prior * 100
        scored.append(
            {
                **para,
                "lexical_score": round(lexical, 1),
                "matched_terms": sorted(f_hits[1]),
                "matched_synonyms": sorted(synonym_only),
                "matched_regions": sorted(set(s_hits[1] + _hit_count(text, target_terms)[1])),
                "matched_relations": sorted(r_hits[1]),
                "section_prior": round(section_prior, 4),
                "total_retrieval_score": round(total, 2),
            }
        )
    scored.sort(key=lambda p: (-p["total_retrieval_score"], p.get("paragraph_index") or 0))
    return scored


def build_windows(
    ranked: list[dict],
    all_paragraphs: list[dict],
    *,
    top_k: int = 40,
    window: int = 2,
) -> list[dict]:
    """Wrap each candidate with ±window context; mark focus_paragraph_id.

    The abstract paragraph is always included (head) — a paper is relevant via
    its abstract even when body scoring pushes it below top_k.
    """
    by_index = {p.get("paragraph_index"): p for p in all_paragraphs if p.get("paragraph_index") is not None}
    candidates = list(ranked[:top_k])
    abstract_para = next(
        (p for p in all_paragraphs if p.get("source_scope") == "abstract"),
        None,
    )
    if abstract_para is not None and not any(
        c.get("paragraph_id") == abstract_para.get("paragraph_id") for c in candidates
    ):
        candidates.insert(0, abstract_para)
    windows: list[dict] = []
    for cand in candidates[:top_k]:
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
