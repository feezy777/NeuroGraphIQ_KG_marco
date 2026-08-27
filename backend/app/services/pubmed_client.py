"""PubMed eutils 异步客户端(限流 + 重试 + 本地缓存)。

用于 Macro Evidence Literature PubMed Backfill:对 (author+year) 查询
esearch 取 PMID 列表,esummary 取 title/doi。

约束(用户要求):
* rate limit:默认 3 请求/秒(eutils 建议 ≤3/s)
* retry:指数退避重试 3 次(1s/2s/4s),网络/HTTP 5xx 可恢复
* cache:本地 JSON 文件缓存(query → hits),二次运行 0 API 调用(幂等)
* 无 LLM:仅 eutils REST,不涉及任何生成模型

缓存文件格式:
{
  "version": 1,
  "created_at": iso,
  "queries": { "<query>": [{"pmid", "title", "doi"}, ...] }
}
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import httpx

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
CACHE_VERSION = 1
MAX_ATTEMPTS = 4  # 1 次原始 + 3 次重试
RETRY_BACKOFF = (1.0, 2.0, 4.0)  # 秒


class PubmedClient:
    """esearch+esummary 封装:lookup(query) -> [{pmid, title, doi}]。

    线程/事件循环安全约束:同一实例只在一个 asyncio loop 内使用;
    缓存读写仅在脚本主流程调用 load_cache/save_cache。
    """

    def __init__(self, cache_path: Path | None = None,
                 rate_limit_per_sec: float = 3.0,
                 timeout_seconds: float = 30.0):
        self.cache_path = Path(cache_path) if cache_path else None
        self.rate_interval = 1.0 / rate_limit_per_sec
        self.timeout_seconds = timeout_seconds
        self.cache: dict[str, list[dict]] = {}
        self.api_calls = 0
        self.cache_hits = 0
        self.retries = 0
        self._last_call = 0.0
        self._client: httpx.AsyncClient | None = None

    # ---- 缓存 ----

    def load_cache(self) -> None:
        """启动时加载本地缓存(不存在则空)。"""
        if not self.cache_path or not self.cache_path.exists():
            return
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            if data.get("version") == CACHE_VERSION:
                self.cache = {
                    k: (v if isinstance(v, list) else [])
                    for k, v in data.get("queries", {}).items()}
        except (ValueError, OSError) as e:
            print(f"[warn] pubmed cache load failed: {e}")

    def save_cache(self) -> None:
        """结束时持久化缓存(原子写)。"""
        if not self.cache_path:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "version": CACHE_VERSION,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "queries": self.cache,
        }, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.cache_path)

    # ---- 主入口 ----

    async def lookup(self, query: str) -> list[dict]:
        """query → hits;缓存命中直接返回,不调 API。"""
        if query in self.cache:
            self.cache_hits += 1
            return self.cache[query]
        hits = await self._fetch_with_retry(query)
        self.cache[query] = hits
        return hits

    async def aclose(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ---- 内部 ----

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds),
                headers={"User-Agent": "NeuroGraphIQ-KG/1.0 "
                                       "(research evidence backfill)"})
        return self._client

    async def _fetch_with_retry(self, query: str) -> list[dict]:
        client = self._get_client()
        last_err: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                await self._rate_limit()
                pmids = await self._esearch(client, query)
                self.api_calls += 1
                if not pmids:
                    return []
                await self._rate_limit()
                hits = await self._esummary(client, pmids)
                self.api_calls += 1
                return hits
            except (httpx.HTTPError, asyncio.TimeoutError) as e:
                last_err = e
                if attempt < MAX_ATTEMPTS - 1:
                    self.retries += 1
                    await asyncio.sleep(RETRY_BACKOFF[attempt])
        print(f"[warn] pubmed query failed after retries: {query} "
              f"({last_err})")
        return []

    async def _rate_limit(self) -> None:
        """eutils 限流:两次请求间隔 >= rate_interval(默认 1/3 s)。"""
        now = time.monotonic()
        wait = self._last_call + self.rate_interval - now
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_call = time.monotonic()

    async def _esearch(self, client: httpx.AsyncClient,
                       query: str) -> list[str]:
        params = {"db": "pubmed", "term": query, "retmode": "json",
                  "retmax": 10}
        r = await client.get(ESEARCH_URL, params=params)
        r.raise_for_status()
        return list(r.json().get("esearchresult", {}).get("idlist", []))

    async def _esummary(self, client: httpx.AsyncClient,
                        pmids: list[str]) -> list[dict]:
        params = {"db": "pubmed", "id": ",".join(pmids),
                  "retmode": "json"}
        r = await client.get(ESUMMARY_URL, params=params)
        r.raise_for_status()
        result = r.json().get("result", {})
        hits = []
        for pid in pmids:
            item = result.get(pid) or {}
            doi = next((a.get("value", "") for a in (item.get("articleids")
                                                     or [])
                        if a.get("idtype") == "doi"), "")
            hits.append({"pmid": pid,
                         "title": item.get("title", ""),
                         "doi": doi or ""})
        return hits
