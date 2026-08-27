"""Europe PMC REST 异步客户端(限流 + 重试 + 本地缓存)。

用于 Macro Paper Knowledge Enrichment V1:按 pmid 查询 core result,
一次调用覆盖 6 个富化字段:
  abstractText / journalInfo.journal.title / pubTypeList.pubType /
  keywordList.keyword / meshHeadingList.meshHeading / authorList.author

约束(用户要求):
* rate limit:默认 3 请求/秒
* retry:指数退避重试 3 次(1s/2s/4s),网络/HTTP 5xx 可恢复
* cache:本地 JSON 文件缓存(pmid → core result),二次运行 0 API 调用(幂等)
* 无 LLM:仅 Europe PMC REST,不涉及任何生成模型

缓存文件格式:
{
  "version": 1,
  "created_at": iso,
  "results": { "<pmid>": {core result dict} }
}
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import httpx

SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
CACHE_VERSION = 1
MAX_ATTEMPTS = 4  # 1 次原始 + 3 次重试
RETRY_BACKOFF = (1.0, 2.0, 4.0)  # 秒


class EuropePmcClient:
    """core result 封装:fetch_by_pmid(pmid) -> dict | None。

    线程/事件循环安全约束:同一实例只在一个 asyncio loop 内使用;
    缓存读写仅在脚本主流程调用 load_cache/save_cache。
    """

    def __init__(self, cache_path: Path | None = None,
                 rate_limit_per_sec: float = 3.0,
                 timeout_seconds: float = 30.0):
        self.cache_path = Path(cache_path) if cache_path else None
        self.rate_interval = 1.0 / rate_limit_per_sec
        self.timeout_seconds = timeout_seconds
        self.cache: dict[str, dict] = {}
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
                    k: (v if isinstance(v, dict) else {})
                    for k, v in data.get("results", {}).items()}
        except (ValueError, OSError) as e:
            print(f"[warn] europepmc cache load failed: {e}")

    def save_cache(self) -> None:
        """结束时持久化缓存(原子写)。"""
        if not self.cache_path:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "version": CACHE_VERSION,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "results": self.cache,
        }, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.cache_path)

    # ---- 主入口 ----

    async def fetch_by_pmid(self, pmid: str) -> dict | None:
        """pmid → Europe PMC core result dict;缓存命中直接返回。"""
        pmid = str(pmid).strip()
        if not pmid:
            return None
        if pmid in self.cache:
            self.cache_hits += 1
            return self.cache[pmid] or None
        result = await self._fetch_with_retry(pmid)
        self.cache[pmid] = result or {}
        return result

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
                                       "(research evidence enrichment)"})
        return self._client

    async def _fetch_with_retry(self, pmid: str) -> dict | None:
        client = self._get_client()
        last_err: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                await self._rate_limit()
                result = await self._search_core(client, pmid)
                self.api_calls += 1
                return result
            except (httpx.HTTPError, asyncio.TimeoutError) as e:
                last_err = e
                if attempt < MAX_ATTEMPTS - 1:
                    self.retries += 1
                    await asyncio.sleep(RETRY_BACKOFF[attempt])
        print(f"[warn] europepmc query failed after retries: {pmid} "
              f"({last_err})")
        return None

    async def _rate_limit(self) -> None:
        """限流:两次请求间隔 >= rate_interval(默认 1/3 s)。"""
        now = time.monotonic()
        wait = self._last_call + self.rate_interval - now
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_call = time.monotonic()

    async def _search_core(self, client: httpx.AsyncClient,
                           pmid: str) -> dict | None:
        params = {"query": f"EXT_ID:{pmid}", "resultType": "core",
                  "format": "json"}
        r = await client.get(SEARCH_URL, params=params)
        r.raise_for_status()
        hits = r.json().get("resultList", {}).get("result", [])
        return hits[0] if hits else None
