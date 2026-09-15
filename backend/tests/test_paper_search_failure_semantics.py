"""Phase 3E.1 — a FAILED search request is not an empty scientific result.

Bug being locked down: every provider function in ``paper_search_multi`` mapped
HTTP 429, HTTP 5xx, timeouts and bare exceptions to ``[]``, indistinguishable
from "the search completed and matched nothing". Phase 3E recorded 35 circuit
concepts as SEARCH_FAILURE because of this; the same queries return 9-10 papers
once failures are visible.

No network: the HTTP client is a stub.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from app.services import paper_search_multi as psm


# ---------------------------------------------------------------------------
# Stub HTTP boundary
# ---------------------------------------------------------------------------
class _Resp:
    def __init__(self, status_code: int, body: Any, headers: dict | None = None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}
        self.text = body if isinstance(body, str) else json.dumps(body)

    def json(self) -> Any:
        if isinstance(self._body, str):
            return json.loads(self._body)
        return self._body


class _Client:
    """Replays a scripted sequence of responses."""

    def __init__(self, script: list):
        self.script = list(script)
        self.calls = 0

    def _next(self):
        self.calls += 1
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(item, Exception):
            raise item
        return item

    async def __aenter__(self) -> "_Client":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def get(self, url: str, params: dict | None = None) -> _Resp:
        return self._next()


def _patch(monkeypatch, script: list, *, capture: dict | None = None):
    def factory(**kwargs):
        client = _Client(script)
        if capture is not None:
            capture["client"] = client
        return client

    monkeypatch.setattr(psm.httpx, "AsyncClient", factory)
    # retry timing must be deterministic, never wall-clock
    monkeypatch.setattr(psm, "_backoff", lambda seconds: asyncio.sleep(0))
    return capture


EPMC_OK = {"resultList": {"result": [
    {"pmid": "1", "doi": "10.1/x", "title": "A paper", "abstractText": "abs",
     "pubYear": "2020", "journalTitle": "J"}]}}


# ===========================================================================
# §12.1 / §12.2 / §12.8 — the three legitimate outcomes
# ===========================================================================
def test_1_http_200_with_papers_returns_the_normal_list(monkeypatch):
    _patch(monkeypatch, [_Resp(200, EPMC_OK)])
    papers = asyncio.run(psm._europepmc_search("q"))
    assert len(papers) == 1 and papers[0]["pmid"] == "1"
    # success shape unchanged (§13)
    assert set(papers[0]) >= {"pmid", "doi", "title", "abstract", "journal", "year", "source"}


def test_2_http_200_with_empty_result_list_returns_empty(monkeypatch):
    """The ONLY case where [] is a scientific answer."""
    _patch(monkeypatch, [_Resp(200, {"resultList": {"result": []}})])
    assert asyncio.run(psm._europepmc_search("q")) == []


def test_2b_an_empty_search_is_not_an_error(monkeypatch):
    _patch(monkeypatch, [_Resp(200, {"resultList": {"result": []}})])
    try:
        asyncio.run(psm._europepmc_search("q"))
    except psm.LiteratureSearchError:  # pragma: no cover
        pytest.fail("an empty result set must not raise")


# ===========================================================================
# §12.3 / §12.4 — 429
# ===========================================================================
def test_3_rate_limit_then_success_retries_and_succeeds(monkeypatch):
    cap: dict = {}
    _patch(monkeypatch, [_Resp(429, {"error": "slow down"}), _Resp(200, EPMC_OK)], capture=cap)
    papers = asyncio.run(psm._europepmc_search("q"))
    assert len(papers) == 1
    assert cap["client"].calls == 2


def test_4_repeated_rate_limit_raises_and_never_returns_empty(monkeypatch):
    _patch(monkeypatch, [_Resp(429, {"error": "slow down"})])
    with pytest.raises(psm.LiteratureSearchError) as exc:
        asyncio.run(psm._europepmc_search("q"))
    assert exc.value.provider == "europepmc"
    assert exc.value.status_code == 429
    assert exc.value.retryable is True
    assert "rate limited" in exc.value.message


def test_4b_retry_after_header_is_honoured(monkeypatch):
    seen: list[float] = []

    async def spy(seconds):
        seen.append(seconds)

    _patch(monkeypatch, [_Resp(429, {}, headers={"Retry-After": "7"}), _Resp(200, EPMC_OK)])
    monkeypatch.setattr(psm, "_backoff", spy)   # after _patch, which also stubs it
    asyncio.run(psm._europepmc_search("q"))
    assert seen == [7.0], seen


def test_4c_retry_count_is_bounded(monkeypatch):
    cap: dict = {}
    _patch(monkeypatch, [_Resp(429, {})], capture=cap)
    with pytest.raises(psm.LiteratureSearchError):
        asyncio.run(psm._europepmc_search("q"))
    assert cap["client"].calls == psm.MAX_SEARCH_ATTEMPTS


# ===========================================================================
# §12.5 / §12.6 — transport
# ===========================================================================
def test_5_timeout_then_success_retries_and_succeeds(monkeypatch):
    _patch(monkeypatch, [httpx.ReadTimeout("slow"), _Resp(200, EPMC_OK)])
    assert len(asyncio.run(psm._europepmc_search("q"))) == 1


def test_6_repeated_timeout_raises_a_transport_failure(monkeypatch):
    _patch(monkeypatch, [httpx.ReadTimeout("slow")])
    with pytest.raises(psm.LiteratureSearchError) as exc:
        asyncio.run(psm._europepmc_search("q"))
    assert exc.value.retryable is True
    assert "transport failure" in exc.value.message


def test_6b_network_error_is_a_transport_failure(monkeypatch):
    _patch(monkeypatch, [httpx.ConnectError("refused")])
    with pytest.raises(psm.LiteratureSearchError) as exc:
        asyncio.run(psm._europepmc_search("q"))
    assert "transport failure" in exc.value.message


# ===========================================================================
# §12.7 / §12.8 — 5xx and non-retryable
# ===========================================================================
def test_7_503_then_success_retries_and_succeeds(monkeypatch):
    _patch(monkeypatch, [_Resp(503, {}), _Resp(200, EPMC_OK)])
    assert len(asyncio.run(psm._europepmc_search("q"))) == 1


def test_7b_repeated_503_raises_an_upstream_error(monkeypatch):
    _patch(monkeypatch, [_Resp(503, {})])
    with pytest.raises(psm.LiteratureSearchError) as exc:
        asyncio.run(psm._europepmc_search("q"))
    assert exc.value.status_code == 503 and exc.value.retryable is True


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_8_client_errors_are_not_retried(monkeypatch, code):
    cap: dict = {}
    _patch(monkeypatch, [_Resp(code, {})], capture=cap)
    with pytest.raises(psm.LiteratureSearchError) as exc:
        asyncio.run(psm._europepmc_search("q"))
    assert cap["client"].calls == 1, "a 4xx must not be retried"
    assert exc.value.status_code == code and exc.value.retryable is False


# ===========================================================================
# §12.9 — malformed responses
# ===========================================================================
def test_9_malformed_json_is_invalid_response(monkeypatch):
    _patch(monkeypatch, [_Resp(200, "not json at all")])
    with pytest.raises(psm.LiteratureSearchError) as exc:
        asyncio.run(psm._europepmc_search("q"))
    assert "invalid JSON" in exc.value.message
    assert exc.value.status_code == 200


def test_9b_missing_result_list_is_not_no_papers(monkeypatch):
    """200 but no resultList = malformed, NOT 'zero matches'."""
    _patch(monkeypatch, [_Resp(200, {"hitCount": 0})])
    with pytest.raises(psm.LiteratureSearchError) as exc:
        asyncio.run(psm._europepmc_search("q"))
    assert "resultList" in exc.value.message


def test_9c_the_other_providers_fail_loudly_too(monkeypatch):
    _patch(monkeypatch, [_Resp(200, {"results": None})])
    with pytest.raises(psm.LiteratureSearchError) as e1:
        asyncio.run(psm._openalex_search("q"))
    assert e1.value.provider == "openalex"
    _patch(monkeypatch, [_Resp(200, {})])
    with pytest.raises(psm.LiteratureSearchError) as e2:
        asyncio.run(psm._semanticscholar_search("q"))
    assert e2.value.provider == "semanticscholar"


# ===========================================================================
# §12.10 — the aggregator must not swallow provider failures
# ===========================================================================
def _stub_sources(monkeypatch, *, failing: set[str]):
    async def make(source: str, papers: list[dict]):
        if source in failing:
            raise psm.LiteratureSearchError(source, "rate limited",
                                            status_code=429, retryable=True)
        return papers

    for name, fn in (("_pubmed_search", "pubmed"), ("_openalex_search", "openalex"),
                     ("_europepmc_search", "europepmc"),
                     ("_semanticscholar_search", "semanticscholar")):
        monkeypatch.setattr(
            psm, name,
            (lambda s: (lambda query, limit=20: make(s, [psm._unified(pmid="9", title="t", doi="d")] if s not in failing else [])))(fn),
        )


def test_10_a_provider_failure_never_looks_like_an_empty_search(monkeypatch):
    _stub_sources(monkeypatch, failing={"europepmc"})
    diag: dict = {}
    papers = asyncio.run(psm.multi_search({"source_region": "hippocampus",
                                           "target_region": "cortex"}, 5, diag))
    assert papers, "healthy providers must still contribute"
    assert diag["provider_failures"], "the failure must be reported"
    assert any(f["provider"] == "europepmc" for f in diag["provider_failures"])
    assert diag["partial"] is True
    assert diag["all_providers_failed"] is False


def test_10b_all_providers_failing_is_flagged_not_silent(monkeypatch):
    _stub_sources(monkeypatch, failing={"pubmed", "openalex", "europepmc", "semanticscholar"})
    diag: dict = {}
    papers = asyncio.run(psm.multi_search({"source_region": "hippocampus",
                                           "target_region": "cortex"}, 5, diag))
    assert papers == []
    assert diag["all_providers_failed"] is True
    assert len(diag["provider_failures"]) >= 4


def test_10c_callers_that_pass_no_diagnostics_still_work(monkeypatch):
    """Back-compat: the two production callers use the old signature."""
    _stub_sources(monkeypatch, failing={"europepmc"})
    papers = asyncio.run(psm.multi_search({"source_region": "hippocampus"}, 5))
    assert isinstance(papers, list) and papers


def test_10d_a_clean_search_reports_no_failures(monkeypatch):
    _stub_sources(monkeypatch, failing=set())
    diag: dict = {}
    asyncio.run(psm.multi_search({"source_region": "hippocampus"}, 5, diag))
    assert diag["provider_failures"] == []
    assert diag["partial"] is False and diag["all_providers_failed"] is False


# ===========================================================================
# §11 — nothing else moved
# ===========================================================================
def test_11_dedup_and_ranking_are_untouched():
    papers = [psm._unified(pmid="1", doi="a", title="T"),
              psm._unified(pmid="1", doi="a", title="T"),
              psm._unified(pmid="2", doi="", title="Other")]
    assert len(psm._dedup_papers(papers)) == 2


def test_11b_the_failure_type_carries_machine_readable_fields():
    err = psm.LiteratureSearchError("europepmc", "rate limited",
                                    status_code=429, retryable=True)
    assert err.as_diagnostic() == {"provider": "europepmc", "status_code": 429,
                                   "retryable": True, "message": "rate limited"}


# ===========================================================================
# Phase 3E.2D-2A — exact retrieval events (captured BEFORE dedup)
# ===========================================================================
# A PublicationDiscoveryHit must be able to say "THIS exact query, through THIS
# source, found THIS paper at THIS rank". The deduplicated return value cannot
# express that: one paper found by three queries is ONE entry there. These tests
# lock down the separate, pre-dedup channel.
_SOURCES = ("pubmed", "openalex", "semanticscholar", "europepmc")

# A single-region context: the approved MVP shape (broad, source-only).
CTX: dict[str, Any] = {
    "source_region": "Left Hippocampus",
    "source_region_synonyms": ["hippocampus"],
    "object_type": "brain_region",
    "granularity": "macro",
    "species": "human",
}


def _stub_providers(monkeypatch, behaviour: dict):
    """Replace the four provider functions with deterministic stubs.

    ``behaviour[source]`` is either a ``list[dict]`` returned for EVERY query,
    a ``callable(query) -> list[dict]``, or a ``BaseException`` instance to
    raise. A source not named returns nothing.

    Returns a call log ``{source: [query, ...]}``.
    """
    calls: dict[str, list[str]] = {s: [] for s in _SOURCES}
    for name in _SOURCES:
        spec = behaviour.get(name, [])

        async def stub(query, limit=20, _spec=spec, _name=name):
            calls[_name].append(query)
            if isinstance(_spec, BaseException):
                raise _spec
            if callable(_spec):
                return [dict(p) for p in _spec(query)]
            return [dict(p) for p in _spec]

        monkeypatch.setattr(psm, f"_{name}_search", stub)
    return calls


def _paper(**over):
    base = {"pmid": "999", "doi": "10.9/shared", "title": "Shared paper",
            "abstract": "hippocampus", "journal": "J", "year": 2024,
            "source": "stub", "is_oa": True}
    base.update(over)
    return psm._unified(**base)


def _search(monkeypatch, behaviour, **kwargs):
    _stub_providers(monkeypatch, behaviour)
    return asyncio.run(psm.multi_search(CTX, **kwargs))


def test_12a_one_paper_found_by_three_queries_yields_three_events(monkeypatch):
    """ACCEPTANCE EXAMPLE 1: final list = 1, retrieval events = one per query."""
    calls = _stub_providers(monkeypatch, {"pubmed": [_paper()]})
    events: list[dict] = []
    result = asyncio.run(psm.multi_search(CTX, retrieval_events=events, diagnostics={}))

    # The call log is ground truth for how many queries were really issued:
    # the strategy list PLUS the separately-built loose fallback query.
    issued = calls["pubmed"]
    assert len(issued) >= 3, "the single-region context must issue several queries"
    assert len(result) == 1, "the normal return value is still deduplicated"
    assert len(events) == len(issued)
    # Every exact query string survives -- this is what the deduped list loses.
    assert {e["query_text"] for e in events} == set(issued)
    assert len({e["query_text"] for e in events}) == len(issued)


def test_12b_one_paper_from_two_providers_yields_two_events(monkeypatch):
    """ACCEPTANCE EXAMPLE 2: final list = 1, retrieval events = 2, two sources."""
    first_query = psm._build_query_strategies(CTX)[0][0]
    only_first = lambda q, _q=first_query: [_paper()] if q == _q else []

    events: list[dict] = []
    result = _search(monkeypatch, {"pubmed": only_first, "europepmc": only_first},
                     retrieval_events=events)

    assert len(result) == 1
    assert len(events) == 2
    assert {e["source"] for e in events} == {"pubmed", "europepmc"}
    assert {e["query_text"] for e in events} == {first_query}


def test_12c_original_provider_rank_survives_later_selection(monkeypatch):
    """A paper the provider ranked 2nd keeps rank 2 even if it is the survivor."""
    first_query = psm._build_query_strategies(CTX)[0][0]
    trio = [_paper(pmid="1", doi="10.1/a", title="A"),
            _paper(pmid="2", doi="10.1/b", title="B"),
            _paper(pmid="3", doi="10.1/c", title="C")]
    _stub_providers(monkeypatch, {"pubmed": lambda q, _q=first_query: trio if q == _q else []})

    events: list[dict] = []
    result = asyncio.run(psm.multi_search(CTX, limit=1, retrieval_events=events))

    assert [e["result_rank"] for e in events] == [1, 2, 3], "provider ranks, 1-based"
    assert len(result) == 1
    survivor = result[0]["pmid"]
    survivor_rank = next(e["result_rank"] for e in events if e["paper"]["pmid"] == survivor)
    # If rank were recomputed from the final (deduped, truncated) list it would
    # always be 1. It must instead still be the paper's ORIGINAL provider rank.
    assert survivor_rank == ["1", "2", "3"].index(survivor) + 1


def test_12d_query_text_and_query_strategy_are_separate_concepts(monkeypatch):
    calls = _stub_providers(monkeypatch, {"pubmed": [_paper()]})
    events: list[dict] = []
    asyncio.run(psm.multi_search(CTX, retrieval_events=events))

    # Strategy queries carry their strategy label; the separately-built loose
    # fallback is labelled 'loose'. Both are queries, neither is the other.
    expected = {q: label for q, label in psm._build_query_strategies(CTX)}
    expected.update({q: "loose" for q in calls["pubmed"] if q not in expected})

    assert events, "the collector must have been filled"
    for event in events:
        assert event["query_strategy"] == expected[event["query_text"]]
        # The label is a family name, the query is the literal string sent:
        # neither may stand in for the other in the record.
        assert event["query_text"]
        assert event["query_strategy"]
        assert event["query_strategy"] not in event["query_text"]
    # The strategy queries are boolean TIAB expressions; the loose fallback is
    # built differently. Both are legitimate queries and both carry their own
    # exact text -- the format is the search layer's business, not this record's.
    assert any("[TIAB]" in e["query_text"] for e in events)
    assert any(e["query_strategy"] == "loose" for e in events)


def test_12e_no_collector_supplied_observes_unchanged_behaviour(monkeypatch):
    spec = {"pubmed": [_paper(pmid="1", doi="10.1/a"), _paper(pmid="2", doi="10.1/b")]}

    baseline = _search(monkeypatch, spec, diagnostics={})
    events: list[dict] = []
    with_collector = _search(monkeypatch, spec, diagnostics={}, retrieval_events=events)

    assert isinstance(with_collector, list)
    assert [p["pmid"] for p in with_collector] == [p["pmid"] for p in baseline]
    assert len(with_collector) == len(baseline) == 2
    assert events, "the collector must still have been filled"


def test_12f_a_failed_invocation_creates_no_retrieval_event(monkeypatch):
    failure = psm.LiteratureSearchError("pubmed", "HTTP 429", status_code=429, retryable=True)
    other_query = psm._build_query_strategies(CTX)[0][0]
    events: list[dict] = []
    diagnostics: dict = {}
    result = _search(monkeypatch,
                     {"pubmed": failure,
                      "europepmc": lambda q, _q=other_query: [_paper()] if q == _q else []},
                     diagnostics=diagnostics, retrieval_events=events)

    assert [e["source"] for e in events] == ["europepmc"]
    assert len(result) == 1
    assert diagnostics["provider_failures"], "the failure is still reported"
    assert {f["provider"] for f in diagnostics["provider_failures"]} == {"pubmed"}
    assert diagnostics["all_providers_failed"] is False


def test_12g_a_successful_empty_result_creates_no_event(monkeypatch):
    events: list[dict] = []
    diagnostics: dict = {}
    result = _search(monkeypatch, {}, diagnostics=diagnostics, retrieval_events=events)

    assert result == []
    assert events == [], "retrieving nothing is not a retrieval fact"
    assert diagnostics["provider_failures"] == []
    assert diagnostics["all_providers_failed"] is False, "empty is not failure"


def test_12h_an_event_carries_no_raw_provider_payload(monkeypatch):
    events: list[dict] = []
    _search(monkeypatch, {"pubmed": [_paper()]}, retrieval_events=events)
    for event in events:
        assert set(event) == {"query_text", "query_strategy", "source",
                              "result_rank", "paper"}
        assert isinstance(event["paper"], dict), "the normalised mapping, not a response"


# ===========================================================================
# Phase 3E.2D-2A.1 — a source-only search must not carry an empty target clause
# ===========================================================================
# The approved first BrainRegion MVP search is source-only. `_build_query_
# strategies` passed `[tgt, tgt_core]` to its query builder, and with no target
# that list is `["", ""]` — TRUTHY — so `if t:` let it through and emitted
# `(""[TIAB] OR ""[TIAB])`. A source-only search is a broad search over the
# source, not a search ANDed against an empty target.
_DEGENERATE = '""[TIAB]'


def test_13a_a_source_only_context_emits_no_empty_tiab_clause():
    for query, _label in psm._build_query_strategies(CTX):
        assert _DEGENERATE not in query, query
        assert '""' not in query, query


def test_13b_every_source_only_strategy_still_carries_a_source_term():
    for query, label in psm._build_query_strategies(CTX):
        assert "hippocampus" in query.lower(), f"{label} lost its source region"


def test_13c_source_only_strategies_keep_their_connection_vocabulary():
    """The fix must drop the EMPTY group only — never a populated one."""
    by_label = {label: query for query, label in psm._build_query_strategies(CTX)}
    assert "projection" in by_label["exact+projection"]
    assert "anterograde" in by_label["exact+tracing"]
    assert "synaptic" in by_label["exact+innervation"]
    assert "connectivity" in by_label["core+connectivity"]
    assert "pathway" in by_label["parent+connectivity"]


def test_13d_two_region_queries_still_carry_both_region_groups():
    """The ordinary source -> target connection query is untouched."""
    strategies = psm._build_query_strategies(
        {"source_region": "Hippocampus", "target_region": "Prefrontal Cortex"}
    )
    by_label = {label: query for query, label in strategies}
    for query, _label in strategies:
        assert _DEGENERATE not in query, query
        assert "hippocampus" in query.lower()
        assert "prefrontal" in query.lower() or "cortex" in query.lower()
    # Three groups survive for the populated case: source AND target AND
    # connection. The source-only case has two, which is the whole point.
    for label in ("exact+projection", "exact+tracing", "exact+innervation"):
        assert by_label[label].count(" AND ") == 2, label


def test_13e_the_recorded_query_text_is_the_cleaned_query_actually_issued(monkeypatch):
    """No reconstruction: the event must record the exact string the provider got."""
    calls = _stub_providers(monkeypatch, {"pubmed": [_paper()]})
    events: list[dict] = []
    asyncio.run(psm.multi_search(CTX, retrieval_events=events))

    issued = calls["pubmed"]
    assert events, "the collector must have been filled"
    assert [e["query_text"] for e in events] == issued, "order and text must match verbatim"
    for event in events:
        assert _DEGENERATE not in event["query_text"]


# ===========================================================================
# Phase 3E.2D-2A.2 — diagnostics describe EXECUTION STATE, not retrieval yield
# ===========================================================================
# Whether an invocation succeeded does not depend on how many papers it
# returned. The old flags were derived from `bool(all_papers)`, so three
# providers answering "nothing here" plus one provider being DOWN reported
# `all_providers_failed = True` — a total outage that never happened.
def _diag(monkeypatch, behaviour):
    diagnostics: dict = {}
    papers = _search(monkeypatch, behaviour, diagnostics=diagnostics)
    return papers, diagnostics


def test_14a_partial_failure_with_successful_empty_results(monkeypatch):
    """MANDATORY: three providers ANSWERED, one was DOWN. Not an outage.

    Also the §8 cross-check: a successful EMPTY invocation counts as a success
    while contributing zero retrieval events. Success and retrieval yield are
    different things.
    """
    events: list[dict] = []
    diagnostics: dict = {}
    papers = _search(monkeypatch, {
        "pubmed": [],
        "openalex": [],
        "semanticscholar": [],
        "europepmc": psm.LiteratureSearchError("europepmc", "HTTP 503",
                                               status_code=503, retryable=True),
    }, diagnostics=diagnostics, retrieval_events=events)

    assert papers == []
    assert events == [], "an empty answer retrieved no publication"
    assert diagnostics["provider_failures"], "the outage IS still reported"
    assert {f["provider"] for f in diagnostics["provider_failures"]} == {"europepmc"}
    assert diagnostics["partial"] is True, "some succeeded, some failed"
    assert diagnostics["all_providers_failed"] is False, \
        "three providers completed successfully; this is NOT a total outage"


def test_14b_every_invocation_failing_is_a_total_outage(monkeypatch):
    err = psm.LiteratureSearchError("x", "HTTP 503", status_code=503, retryable=True)
    papers, diagnostics = _diag(monkeypatch, {s: err for s in _SOURCES})

    assert papers == []
    assert diagnostics["partial"] is False, "nothing succeeded to be partial about"
    assert diagnostics["all_providers_failed"] is True


def test_14c_all_invocations_succeed_and_return_nothing(monkeypatch):
    papers, diagnostics = _diag(monkeypatch, {s: [] for s in _SOURCES})

    assert papers == []
    assert diagnostics["provider_failures"] == []
    assert diagnostics["partial"] is False
    assert diagnostics["all_providers_failed"] is False, \
        "answering with nothing is an answer, not a failure"


def test_14d_partial_failure_with_papers_is_partial_not_outage(monkeypatch):
    papers, diagnostics = _diag(monkeypatch, {
        "pubmed": [_paper()],
        "europepmc": psm.LiteratureSearchError("europepmc", "HTTP 503",
                                               status_code=503, retryable=True),
    })

    assert papers, "the surviving source's results are still returned"
    assert diagnostics["partial"] is True
    assert diagnostics["all_providers_failed"] is False


def test_14e_one_provider_failing_one_query_can_still_succeed_another(monkeypatch):
    """Guards against counting a provider by its FIRST result alone."""
    first_query = psm._build_query_strategies(CTX)[0][0]

    def flaky(query, _first=first_query):
        if query == _first:
            raise psm.LiteratureSearchError("pubmed", "HTTP 429",
                                            status_code=429, retryable=True)
        return [_paper()]

    papers, diagnostics = _diag(monkeypatch, {"pubmed": flaky})

    assert papers, "the provider's other invocations succeeded"
    assert diagnostics["partial"] is True
    assert diagnostics["all_providers_failed"] is False, \
        "one failed invocation does not make a provider fail all of them"


def test_14f_nothing_attempted_is_not_a_total_outage(monkeypatch):
    """'Nothing was attempted' must not be reported as 'everything failed'.

    An empty CONTEXT is NOT enough to reach this branch. ``_build_query_
    strategies({})`` still emits five connection-vocabulary strategies -- with
    no region named at all -- so invocations DO happen and succeed with ``[]``.
    Asserting only the final flags would then pass for the wrong reason: the
    zero-attempt branch was never entered.

    The branch is reached only when the builder itself yields nothing, so the
    builder is stubbed to empty here, and the providers are counted to prove
    that not one was called.
    """
    called: list[str] = []
    for name in _SOURCES:
        async def stub(query, limit=20, _name=name):
            called.append(_name)
            raise AssertionError(f"provider {_name} must not be invoked here")
        monkeypatch.setattr(psm, f"_{name}_search", stub)

    # The only way to have zero tasks: no strategies AND no loose fallback.
    monkeypatch.setattr(psm, "_build_query_strategies", lambda context: [])

    events: list[dict] = []
    diagnostics: dict = {}
    papers = asyncio.run(
        psm.multi_search({}, diagnostics=diagnostics, retrieval_events=events))

    assert called == [], "no provider invocation may occur when nothing is attempted"
    assert papers == []
    assert events == []
    assert diagnostics["provider_failures"] == [], \
        "a provider that was never invoked cannot have failed"
    assert diagnostics["partial"] is False
    assert diagnostics["all_providers_failed"] is False, \
        "an unsearched query is not a failed search"


def test_14g_the_public_diagnostics_shape_is_unchanged(monkeypatch):
    _, diagnostics = _diag(monkeypatch, {"pubmed": [_paper()]})
    assert set(diagnostics) == {"provider_failures", "partial", "all_providers_failed"}, \
        "internal invocation counters must stay local, not leak into diagnostics"
