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
