"""PubMed eutils 客户端测试(httpx MockTransport,无真实网络)。

覆盖:缓存命中零 API 调用、未命中走 esearch+esummary、解析 doi、
重试(第一次失败第二次成功)、持久化往返(幂等)。
无 pytest-asyncio —— 用 asyncio.run 包裹异步逻辑。
"""

import asyncio
import json

import httpx

from app.services.pubmed_client import PubmedClient


def _mock_esearch(responses: list[dict | list[str]]):
    """esearch mock:连续调用依次返回 responses 中的结果。"""

    def _esearch_json(idlist):
        return {"esearchresult": {"idlist": idlist}}

    def _esummary_json(items):
        return {"result": items}

    def handler(request: httpx.Request) -> httpx.Response:
        if "esearch" in str(request.url):
            resp = responses.pop(0) if responses else []
            return httpx.Response(200, json=_esearch_json(resp))
        ids = request.url.params["id"].split(",")
        result = {"uids": ids}
        for pid in ids:
            result[pid] = {"title": f"Title {pid}",
                           "articleids": [{"idtype": "doi",
                                           "value": f"10.m/{pid}"}]}
        return httpx.Response(200, json=_esummary_json(result))

    return handler


def _client(handler, cache_path=None) -> PubmedClient:
    c = PubmedClient(cache_path=cache_path, rate_limit_per_sec=1000)
    c._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return c


def test_cache_hit_no_api_call(tmp_path):
    cache_file = tmp_path / "cache.json"
    cache_file.write_text(json.dumps(
        {"version": 1, "queries": {"Q1": [{"pmid": "1", "title": "T",
                                           "doi": "10.x/1"}]}}),
        encoding="utf-8")
    c = _client(lambda req: (_ for _ in ()).throw(
        AssertionError("API must not be called on cache hit")),
        cache_path=cache_file)
    c.load_cache()
    hits = asyncio.run(c.lookup("Q1"))
    assert hits == [{"pmid": "1", "title": "T", "doi": "10.x/1"}]
    assert c.cache_hits == 1
    assert c.api_calls == 0
    asyncio.run(c.aclose())


def test_miss_calls_esearch_and_esummary():
    handler = _mock_esearch([["1", "2"]])
    c = _client(handler)
    hits = asyncio.run(c.lookup("(Habas[Author]) AND 2009[Date - Publication]"))
    assert c.api_calls == 2  # esearch + esummary
    assert len(hits) == 2
    assert hits[0]["pmid"] == "1"
    assert hits[0]["doi"] == "10.m/1"
    asyncio.run(c.aclose())


def test_empty_esearch_no_esummary():
    handler = _mock_esearch([[]])
    c = _client(handler)
    hits = asyncio.run(c.lookup("Nonsense[Author]"))
    assert hits == []
    assert c.api_calls == 1  # 只 esearch,不调 esummary
    asyncio.run(c.aclose())


def test_retry_on_transient_error():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if "esearch" in str(request.url):
            if calls["n"] == 1:
                return httpx.Response(503, json={})  # 首次失败
            return httpx.Response(200, json={"esearchresult": {"idlist": ["9"]}})
        return httpx.Response(200, json={"result": {
            "9": {"title": "T9", "articleids": [{"idtype": "doi",
                                                 "value": "10.r/9"}]}}})

    c = _client(handler)
    hits = asyncio.run(c.lookup("Q"))
    assert calls["n"] == 3  # 1 失败 + 重试成功(esearch 1+1, esummary 1)
    assert hits == [{"pmid": "9", "title": "T9", "doi": "10.r/9"}]
    assert c.retries == 1
    asyncio.run(c.aclose())


def test_save_load_roundtrip(tmp_path):
    cache_file = tmp_path / "cache.json"
    handler = _mock_esearch([["5"]])
    c = _client(handler, cache_path=cache_file)
    asyncio.run(c.lookup("Q"))
    c.save_cache()
    assert cache_file.exists()
    # 新实例加载缓存 → 命中
    c2 = _client(lambda req: (_ for _ in ()).throw(
        AssertionError("API must not be called")), cache_path=cache_file)
    c2.load_cache()
    hits = asyncio.run(c2.lookup("Q"))
    assert hits == [{"pmid": "5", "title": "Title 5", "doi": "10.m/5"}]
    assert c2.cache_hits == 1
    assert c2.api_calls == 0
    asyncio.run(c2.aclose())
