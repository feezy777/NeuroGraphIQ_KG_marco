"""Multi-source paper search: PubMed/PMC + OpenAlex + Europe PMC."""
from __future__ import annotations

import asyncio
import html as _html
import re
from difflib import SequenceMatcher

import httpx

SEARCH_TIMEOUT = 25

# ── Source APIs ──────────────────────────────────────────────────────────
PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
OPENALEX_BASE = "https://api.openalex.org/works"
EUROPE_PMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
SEMANTIC_SCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1/paper/search"


# ── Unified paper dict ───────────────────────────────────────────────────
def _unified(pmid="", doi="", title="", abstract="", journal="", year=None,
             source="", is_oa=False, fulltext_avail=False, **extra) -> dict:
    return {
        "pmid": pmid, "doi": doi, "title": title, "abstract": abstract,
        "journal": journal, "year": year, "source": source,
        "is_open_access": is_oa, "fulltext_available": fulltext_avail,
        **extra,
    }


# ── PubMed / PMC via NCBI E-utilities ───────────────────────────────────
async def _pubmed_search(query: str, limit: int = 20) -> list[dict]:
    """Search PubMed via E-utilities esearch + efetch."""
    async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
        # 1) Search
        esearch_resp = await client.get(
            f"{PUBMED_BASE}/esearch.fcgi",
            params={"db": "pubmed", "term": query, "retmode": "json",
                    "retmax": limit, "sort": "relevance"},
        )
        if esearch_resp.status_code != 200:
            return []
        id_list = esearch_resp.json().get("esearchresult", {}).get("idlist", [])
        if not id_list:
            return []

        # 2) Fetch metadata
        efetch_resp = await client.get(
            f"{PUBMED_BASE}/efetch.fcgi",
            params={"db": "pubmed", "id": ",".join(id_list), "retmode": "xml", "rettype": "abstract"},
        )
        if efetch_resp.status_code != 200:
            return []
        return _parse_pubmed_xml(efetch_resp.text)


def _parse_pubmed_xml(xml_text: str) -> list[dict]:
    """Parse PubMed efetch XML into unified paper dicts."""
    import xml.etree.ElementTree as ET
    papers = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return papers
    for article in root.iter("PubmedArticle"):
        try:
            medline = article.find("MedlineCitation")
            if medline is None:
                continue
            article_node = medline.find("Article")
            if article_node is None:
                continue

            pmid_el = medline.find("PMID")
            pmid = pmid_el.text.strip() if pmid_el is not None and pmid_el.text else ""

            title_el = article_node.find("ArticleTitle")
            title = title_el.text.strip() if title_el is not None and title_el.text else ""

            journal_el = article_node.find("Journal")
            journal = ""
            year = None
            if journal_el is not None:
                jtitle = journal_el.find("Title")
                journal = jtitle.text.strip() if jtitle is not None and jtitle.text else ""
                pubdate = journal_el.find("JournalIssue/PubDate/Year")
                if pubdate is not None and pubdate.text:
                    try:
                        year = int(pubdate.text)
                    except (ValueError, TypeError):
                        pass

            abstract_parts = []
            abstract_el = article_node.find("Abstract")
            if abstract_el is not None:
                for at in abstract_el.findall("AbstractText"):
                    label = at.get("Label", "")
                    text = at.text or ""
                    abstract_parts.append(f"{label}: {text}" if label else text)
            abstract = " ".join(abstract_parts)

            # DOI
            doi = ""
            for eid in article_node.findall("ELocationID"):
                if eid.get("EIdType") == "doi" and eid.text:
                    doi = eid.text.strip()

            # OA status
            pub_type_list = article_node.find("PublicationTypeList")
            is_oa = False
            if pub_type_list is not None:
                for pt in pub_type_list.findall("PublicationType"):
                    if pt.text and pt.text.strip().lower() in ("open access",):
                        is_oa = True

            if pmid or doi:
                papers.append(_unified(pmid=pmid, doi=doi, title=title, abstract=abstract,
                                       journal=journal, year=year, source="pubmed",
                                       is_oa=is_oa))
        except Exception:
            continue
    return papers


# ── OpenAlex ──────────────────────────────────────────────────────────────
async def _openalex_search(query: str, limit: int = 20) -> list[dict]:
    """Search OpenAlex works API."""
    async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
        try:
            resp = await client.get(
                OPENALEX_BASE,
                params={"search": query, "per-page": min(limit, 50)},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
        except Exception:
            return []
        return _parse_openalex(data.get("results", []))


def _parse_openalex(results: list[dict]) -> list[dict]:
    """Parse OpenAlex results into unified paper dicts."""
    papers = []
    for w in results:
        pmid = (w.get("pmid") or "").strip().lstrip("https://pubmed.ncbi.nlm.nih.gov/")
        doi = (w.get("doi") or "").strip().lstrip("https://doi.org/")
        title = w.get("title") or ""
        abstract = ""
        if w.get("abstract_inverted_index"):
            try:
                idx = w["abstract_inverted_index"]
                max_pos = max(p for ps in idx.values() for p in ps) if idx else 0
                words = [""] * (max_pos + 1)
                for word, positions in idx.items():
                    for p in positions:
                        words[p] = word
                abstract = " ".join(words)
            except Exception:
                pass
        journal = ""
        primary_loc = w.get("primary_location") or {}
        source = primary_loc.get("source") or {}
        if isinstance(source, dict):
            journal = source.get("display_name") or ""
        year = w.get("publication_year")
        is_oa = bool(w.get("open_access", {}).get("is_oa", False))
        if pmid or doi:
            papers.append(_unified(pmid=pmid, doi=doi, title=title, abstract=abstract,
                                   journal=journal, year=year, source="openalex",
                                   is_oa=is_oa))
    return papers


# ── Europe PMC (existing, minimal wrapper) ────────────────────────────────
async def _europepmc_search(query: str, limit: int = 20) -> list[dict]:
    """Search Europe PMC REST API — returns unified dicts."""
    async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
        try:
            resp = await client.get(
                EUROPE_PMC_SEARCH,
                params={"query": query, "format": "json", "pageSize": limit, "resultType": "core"},
            )
            if resp.status_code != 200:
                return []
            payload = resp.json()
        except Exception:
            return []
    results = payload.get("resultList", {}).get("result", [])
    papers = []
    for r in results:
        pmid = (r.get("pmid") or "").strip()
        doi = (r.get("doi") or "").strip()
        year = None
        try:
            year = int(r.get("pubYear", 0)) if r.get("pubYear") else None
        except (ValueError, TypeError):
            pass
        raw_abs = (r.get("abstractText") or "").strip()
        # Strip HTML tags from Europe PMC abstracts (they carry <h4>, <i>, <b> etc.)
        clean_abs = re.sub(r"<[^>]+>", " ", raw_abs)
        clean_abs = _html.unescape(clean_abs)
        clean_abs = re.sub(r"\s+", " ", clean_abs).strip()
        if pmid or doi:
            papers.append(_unified(
                pmid=pmid, doi=doi,
                title=r.get("title") or "",
                abstract=clean_abs,
                journal=r.get("journalTitle") or r.get("journal") or "",
                year=year,
                source="europepmc",
                is_oa=bool(r.get("isOpenAccess", False)),
                fulltext_available=bool(r.get("hasFullText", False)),
            ))
    return papers


# ── Query Builder: region-aware search terms ─────────────────────────────
_CONNECTION_TERMS = [
    "projection", "tract", "connectivity", "fiber pathway", "fiber tract",
    "tractography", "neural connection", "white matter", "axon",
]

# Strong evidence vocabulary — papers with these words are more likely to contain actual evidence
_EVIDENCE_VOCAB = [
    "projects to", "projection from", "projects from", "innervates",
    "anterograde", "retrograde", "tract tracing", "labeled neurons",
    "axon terminal", "bouton", "synaptic contact", "electron microscopy",
    "biocytin", "phaseolus", "wga-hrp", "fluoro-gold", "cholera toxin",
    "connects to", "connection between", "pathway linking",
    "efferent projection", "afferent projection", "output to",
]

_HUMAN_TERMS = ["human", "patient", "subject", "healthy", "brain"]


def _build_search_terms(context: dict) -> str:
    """Build a PubMed-friendly query from retrieval context.

    Uses individual words from region names (not full phrases — too strict).
    Adds connection vocabulary for connection-type objects.
    """
    src = (context.get("source_region") or "").strip()
    tgt = (context.get("target_region") or "").strip()

    # Extract distinctive words from each region (strip modifiers + structural suffixes)
    src_words = _distinctive_words(src)
    tgt_words = _distinctive_words(tgt)

    # Build OR groups of distinctive words, plus full core terms for precision
    parts = []
    # Source region group: core noun phrase + individual words
    src_all = list(dict.fromkeys([_core_term(src)] + src_words))[:4]
    if src_all:
        parts.append("(" + " OR ".join(f'"{t}"[TIAB]' for t in src_all) + ")")
    # Target region group
    tgt_all = list(dict.fromkeys([_core_term(tgt)] + tgt_words))[:4]
    if tgt_all:
        parts.append("(" + " OR ".join(f'"{t}"[TIAB]' for t in tgt_all) + ")")
    # Connection vocabulary (for connections/projections)
    if context.get("object_type") in ("connection", "projection"):
        conn_terms = _CONNECTION_TERMS[:6]
        parts.append("(" + " OR ".join(f'"{t}"[TIAB]' for t in conn_terms) + ")")

    if parts:
        return " AND ".join(parts)
    # Fallback
    info_q = (context.get("_info_query", "") or "").strip()
    return info_q or "neuroscience brain connectivity"


def _distinctive_words(region: str) -> list[str]:
    """Extract meaningful words from a region name, discarding common modifiers."""
    words = [w for w in re.split(r"[\s\-,\/]+", (region or "").lower())
             if len(w) > 2
             and w not in _REGION_MODIFIERS
             and w not in _STRUCTURAL_WORDS
             and not re.fullmatch(r"\d+[a-z]?", w)]
    return list(dict.fromkeys(words))[:5]  # dedup, max 5


_REGION_MODIFIERS = {
    "right", "left", "proper", "superior", "inferior", "medial", "lateral",
    "anterior", "posterior", "dorsal", "ventral", "caudal", "rostral",
    "central", "deep", "superficial", "primary", "secondary", "bilateral",
    "motor", "related", "gray", "white", "intermediate",
}
_STRUCTURAL_WORDS = {"layer", "part", "area", "sublayer", "region", "sector", "division"}


def _core_term(region: str) -> str:
    words = [w for w in re.split(r"[\s\-,\/]+", region or "")
             if w and len(w) > 1
             and not re.fullmatch(r"\d+[a-z]?|\d+", w)
             and w.lower() not in _REGION_MODIFIERS
             and w.lower() not in _STRUCTURAL_WORDS]
    if not words:
        return region.strip()
    core = " ".join(words).strip()
    parts = core.split()
    return " ".join(parts[-3:]) if len(parts) > 3 else core


# ── Multi-source dedup ────────────────────────────────────────────────────
def _dedup_papers(papers: list[dict]) -> list[dict]:
    """Dedup by PMID > DOI > title similarity. First source wins metadata."""
    seen_pmids: set[str] = set()
    seen_dois: set[str] = set()
    result = []
    for p in papers:
        pmid = p.get("pmid", "") or ""
        doi = (p.get("doi", "") or "").lower()
        if pmid and pmid in seen_pmids:
            continue
        if doi and doi in seen_dois:
            continue
        if pmid:
            seen_pmids.add(pmid)
        if doi:
            seen_dois.add(doi)
        result.append(p)
    return result


# ── Species-aware scoring ──────────────────────────────────────────────────
_MOUSE_EVIDENCE = {
    "mouse", "mice", "murine", "tracer", "tracing", "injection",
    "anterograde", "retrograde", "bda", "pha-l", "ctb", "fluoro-gold",
    "biocytin", "cholera toxin", "wga-hrp",
}
_HUMAN_EVIDENCE = {
    "human", "subjects", "patients", "tractography", "diffusion mri",
    "dti", "fmri", "functional connectivity", "dwi", "dsi",
}
_SPECIES_ANIMAL = {
    "rat", "mouse", "mice", "murine", "feline", "canine", "monkey",
    "macaque", "marmoset", "rabbit", "sheep", "frog", "lizard", "fish",
    "bird", "cat", "dog", "pig", "hamster", "gerbil", "ferret",
}


def _detect_species(body: str) -> str | None:
    """Detect primary species from paper text. Returns 'mouse', 'human', or None."""
    body_l = body.lower()
    if any(w in body_l for w in _HUMAN_EVIDENCE):
        return "human"
    if "mouse" in body_l or "mice" in body_l or "murine" in body_l:
        return "mouse"
    if "rat" in body_l:
        return "rat"
    return None


def _resolve_expected_species(context: dict) -> str | None:
    """Expected target species for paper ranking.

    Priority: explicit ``context['species']`` (resource/dataset metadata).
    Fallback keeps only unambiguous signals: a source explicitly named
    ``mouse`` is mouse; clinical-layer granularity / AAL3 / HCP are human.
    ``allen`` and ``molecular`` are deliberately excluded (BR1): Allen_HBA is
    a human atlas and granularity carries no species semantics.
    """
    explicit = (context.get("species") or "").strip().lower()
    if explicit in ("human", "mouse", "rat"):
        return explicit
    atlas = (context.get("source_atlas") or "").lower()
    granularity = (context.get("granularity") or "").lower()
    if "mouse" in atlas:
        return "mouse"
    if "macro" in granularity or "aal" in atlas or "hcp" in atlas:
        return "human"
    return None


def _score_papers(papers: list[dict], context: dict) -> list[dict]:
    """Score papers with evidence patterns + species-aware ranking."""
    src = (context.get("source_region") or "").lower()
    tgt = (context.get("target_region") or "").lower()
    src_core = _core_term(src).lower()
    tgt_core = _core_term(tgt).lower()

    # Determine expected species. Source of truth is explicit metadata
    # (context['species'] from atlas_resources via build_retrieval_context).
    # Atlas-name substring guessing is banned (BR1): "allen" must NOT imply
    # mouse — Allen_HBA is a human atlas; "molecular" granularity says nothing
    # about species. Fallback only recognizes explicitly mouse-named sources
    # and human clinical-layer signals.
    expected_species = _resolve_expected_species(context)

    # Collect all synonyms for matching
    src_terms = [src, _core_term(src).lower()]
    src_terms += [s.lower() for s in (context.get("source_region_synonyms") or []) if s]
    tgt_terms = [tgt, _core_term(tgt).lower()]
    tgt_terms += [s.lower() for s in (context.get("target_region_synonyms") or []) if s]
    # Remove dupes, empty
    src_terms = list(dict.fromkeys(t for t in src_terms if t and t not in ("unknown", "none")))
    tgt_terms = list(dict.fromkeys(t for t in tgt_terms if t and t not in ("unknown", "none")))

    for p in papers:
        title = (p.get("title") or "").lower()
        abstract = (p.get("abstract") or "").lower()
        body = f"{title} {abstract}"

        # Region matching with ALL synonyms (title-weighted 2x)
        src_hit = max((_word_match(st, title) * 2.0 if st in title else _word_match(st, body))
                      for st in src_terms) if src_terms else 0.0
        tgt_hit = max((_word_match(tt, title) * 2.0 if tt in title else _word_match(tt, body))
                      for tt in tgt_terms) if tgt_terms else 0.0

        # Connection evidence pattern detection
        ev_bonus = 0
        body_l = body.lower()
        # Direct projection statements
        if re.search(r"projects?\s+(to|from|into)\s", body_l):
            ev_bonus += 15
        if re.search(r"projections?\s+(to|from)\s", body_l):
            ev_bonus += 12
        # Anterograde tracing
        if re.search(r"(anterograde|anterogradely)\s+(labeled|traced|transported)", body_l):
            ev_bonus += 20
        elif "anterograde" in body_l:
            ev_bonus += 10
        # Retrograde tracing
        if re.search(r"(retrograde|retrogradely)\s+(labeled|traced|transported)", body_l):
            ev_bonus += 20
        elif "retrograde" in body_l:
            ev_bonus += 10
        # Innervation / terminal patterns
        if re.search(r"(innervates?|innervation)\s", body_l):
            ev_bonus += 10
        if re.search(r"(axon|fiber|fibre)[s]?\s+(from|in|terminate|project)", body_l):
            ev_bonus += 8
        # Tractography
        if re.search(r"(tractography|dti|diffusion)\s+(shows?|reveals?|demonstrates?)", body_l):
            ev_bonus += 10

        # Evidence vocabulary hits
        evidence_hits = sum(1 for t in _EVIDENCE_VOCAB if t in body)

        # Connection terms
        conn_hits = sum(1 for t in _CONNECTION_TERMS if t.lower() in body)

        # Best region match: papers matching BOTH regions score highest,
        # but single-region + strong connection evidence also scores well
        region_both = min(src_hit, tgt_hit)  # both regions present
        region_best = max(src_hit, tgt_hit)  # at least one region
        region_bonus = region_both * 30 + region_best * 15

        # Species-aware scoring
        paper_species = _detect_species(body)
        species_bonus = 0
        if expected_species and paper_species:
            if expected_species == paper_species:
                species_bonus = 10
            elif paper_species == "mouse" and expected_species == "human":
                species_bonus = 4
            elif paper_species == "rat" and expected_species == "mouse":
                species_bonus = 6
            elif paper_species == "rat" and expected_species == "human":
                species_bonus = 2

        # Multi-query bonus
        matched_queries = p.get("matched_queries", [])
        strategy_bonus = min(8, len(set(matched_queries)) * 3) if isinstance(matched_queries, list) else 0

        # Query strategy bonus: exact/projection queries are most relevant
        qs = p.get("query_strategy", "")
        strategy_weight = 5 if "exact" in str(qs) else 0

        score = (region_bonus + ev_bonus + evidence_hits * 8 +
                 min(3, conn_hits) * 3 + species_bonus +
                 strategy_bonus + strategy_weight)

        if p.get("fulltext_available"):
            score += 8
        elif p.get("is_open_access"):
            score += 5
        if p.get("abstract"):
            score += 3
        try:
            if p.get("year") and int(p["year"]) >= 2020:
                score += 2
        except (ValueError, TypeError):
            pass

        p["paper_match_score"] = min(100, max(0, round(score)))
        p["species"] = paper_species

    return sorted(papers, key=lambda p: -(p.get("paper_match_score", 0)))


def _word_match(term: str, text: str) -> float:
    """Word-boundary match score (0.0-1.0).

    Returns 1.0 for whole-phrase exact match, ~0.5 for partial word overlap.
    """
    if not term or not text:
        return 0.0
    if term in text:
        return 1.0
    # Check individual words
    words = term.split()
    hits = sum(1 for w in words if w in text)
    if hits > 0:
        return hits / len(words) * 0.5
    # Fuzzy
    return SequenceMatcher(None, term[:40], text[:40]).ratio() * 0.3


# ── Semantic Scholar ─────────────────────────────────────────────────────
async def _semanticscholar_search(query: str, limit: int = 20) -> list[dict]:
    """Search Semantic Scholar Academic Graph API."""
    async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
        try:
            resp = await client.get(
                SEMANTIC_SCHOLAR_BASE,
                params={"query": query, "limit": min(limit, 50),
                        "fields": "paperId,title,abstract,authors,year,venue,externalIds,openAccessPdf,citationCount"},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
        except Exception:
            return []
    papers = []
    for item in data.get("data", []):
        ext = item.get("externalIds") or {}
        pmid = str(ext.get("PubMedId") or "").strip()
        doi = str(ext.get("DOI") or "").strip().lstrip("https://doi.org/")
        title = item.get("title") or ""
        abstract = item.get("abstract") or ""
        year = item.get("year")
        journal = ""
        venue = item.get("venue") or ""
        if isinstance(venue, dict):
            journal = venue.get("name") or venue.get("displayName") or ""
        elif isinstance(venue, str):
            journal = venue
        is_oa = bool(item.get("openAccessPdf"))
        if pmid or doi or title:
            papers.append(_unified(
                pmid=pmid, doi=doi, title=title, abstract=abstract,
                journal=journal, year=year, source="semanticscholar",
                is_oa=is_oa, citation_count=item.get("citationCount"),
            ))
    return papers


# ── Multi-query strategy builder ───────────────────────────────────────────
def _build_query_strategies(context: dict) -> list[tuple[str, str]]:
    """Generate multiple search queries for connection/projection targets.

    Returns list of (query, strategy_label).
    """
    src = (context.get("source_region") or "").strip()
    tgt = (context.get("target_region") or "").strip()
    src_core = _core_term(src)
    tgt_core = _core_term(tgt)
    src_words = _distinctive_words(src)
    tgt_words = _distinctive_words(tgt)

    strategies: list[tuple[str, str]] = []

    def _q(s, t, conn_words):
        """Build a TIAB query: (src_terms) AND (tgt_terms) AND (conn_terms)."""
        parts = []
        if s:
            parts.append("(" + " OR ".join(f'"{x}"[TIAB]' for x in s[:3]) + ")")
        if t:
            parts.append("(" + " OR ".join(f'"{x}"[TIAB]' for x in t[:3]) + ")")
        if conn_words:
            parts.append("(" + " OR ".join(f'"{x}"[TIAB]' for x in conn_words[:4]) + ")")
        return " AND ".join(parts) if parts else ""

    # Strategy 1: exact source + exact target + projection
    q = _q([src, src_core], [tgt, tgt_core], ["projection", "projects to", "efferent", "tract tracing"])
    if q:
        strategies.append((q, "exact+projection"))

    # Strategy 2: source + target + tracing methods
    q = _q([src, src_core], [tgt, tgt_core],
           ["anterograde", "retrograde", "tracer", "biotin", "phaseolus", "fluoro-gold", "biocytin", "cholera toxin"])
    if q:
        strategies.append((q, "exact+tracing"))

    # Strategy 3: source + target + innervation/terminal
    q = _q([src, src_core], [tgt, tgt_core],
           ["innervat", "axon terminal", "bouton", "synaptic", "fiber", "terminal field"])
    if q:
        strategies.append((q, "exact+innervation"))

    # Strategy 4: core region terms with connectivity vocabulary (wider)
    core_src = [src_core] + ([w for w in src_words if w != src_core][:2]) if src_core else src_words[:3]
    core_tgt = [tgt_core] + ([w for w in tgt_words if w != tgt_core][:2]) if tgt_core else tgt_words[:3]
    q = _q(core_src, core_tgt,
           ["projection", "connectivity", "tract", "pathway", "efferent", "afferent"])
    if q and q not in [s[0] for s in strategies]:
        strategies.append((q, "core+connectivity"))

    # Strategy 5: parent-region level (use just core terms, no layer/area modifiers)
    parent_src = [w for w in src_words if len(w) > 4][:3] or [src_core]
    parent_tgt = [w for w in tgt_words if len(w) > 4][:3] or [tgt_core]
    q = _q(parent_src, parent_tgt, ["projection", "connection", "pathway", "tract", "connectivity"])
    if q and q not in [s[0] for s in strategies]:
        strategies.append((q, "parent+connectivity"))

    return strategies


# ── Main multi-source search ──────────────────────────────────────────────
async def multi_search(context: dict, limit: int = 20) -> list[dict]:
    """Multi-query, multi-source search with dedup and evidence-aware ranking."""
    strategies = _build_query_strategies(context)

    # Build loose query fallback
    all_words = set()
    for k in ("source_region", "target_region"):
        val = (context.get(k) or "").strip()
        if val:
            all_words.update(_distinctive_words(val))
    query_loose = " AND ".join(f'"{w}"' for w in list(all_words)[:6]) if all_words else ""

    # Run strategies in parallel across sources
    per_source_limit = max(limit, 25)

    async def search_all():
        tasks = []
        # Run each strategy on all available sources (4 sources)
        for query, strategy in strategies:
            tasks.append((_pubmed_search(query, per_source_limit), "pubmed", strategy))
            tasks.append((_openalex_search(query, per_source_limit), "openalex", strategy))
            tasks.append((_semanticscholar_search(query, per_source_limit), "semanticscholar", strategy))
            tasks.append((_europepmc_search(query, per_source_limit), "europepmc", strategy))
        # Loose fallback on all sources
        if query_loose:
            tasks.append((_pubmed_search(query_loose, per_source_limit), "pubmed", "loose"))
            tasks.append((_openalex_search(query_loose, per_source_limit), "openalex", "loose"))
            tasks.append((_semanticscholar_search(query_loose, per_source_limit), "semanticscholar", "loose"))
            tasks.append((_europepmc_search(query_loose, per_source_limit), "europepmc", "loose"))
        results = await asyncio.gather(*(t[0] for t in tasks), return_exceptions=True)
        return results, tasks

    results, tasks = await search_all()

    # Merge with query metadata
    all_papers: list[dict] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            continue
        _, source, strategy = tasks[i]
        for p in r:
            p.setdefault("discovery_source", source)
            existing = p.get("matched_queries", [])
            if isinstance(existing, list):
                existing.append(strategy)
            p["matched_queries"] = existing
            p.setdefault("query_strategy", strategy)
            all_papers.append(p)

    # Dedup
    papers = _dedup_papers(all_papers)

    # Score with species-aware + evidence pattern ranking
    return _score_papers(papers, context)[:limit]
