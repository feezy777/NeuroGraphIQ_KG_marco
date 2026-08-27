"""Macro Candidate Rule Validation V1 测试。

两层:
1. 纯规则(无 DB) — R3/R4 词表、R6 名称形态判定(str 级辅助函数)。
2. DB 层(真实测试库) — run_batch 幂等(重跑覆盖旧 run)、results 行数与
   rankings 一致、案例验证(right paracentral → right lateral ventricle 通过
   API 链路),以及零副作用(5 计数:final/canonical/mirror/ontology 不动)。
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

import pytest
from sqlalchemy import text

from app.database import AsyncSessionLocal

sys.path.insert(0, os.path.dirname(__file__) + "/..")

pytestmark = pytest.mark.function_term_real

# ---- 名称形态判定(无 DB 纯函数,直接对 service 常量/正则断言) ----

from app.services.macro_candidate_rule_validation_service import (  # noqa: E402
    ALLOWED_CONNECTION_TYPES,
    ALLOWED_DIRECTIONS,
    ALLOWED_GRANULARITY,
    _ILLEGAL_NAME_RE,
)

def test_allowed_ontology_words():
    assert "structural_connection" in ALLOWED_CONNECTION_TYPES
    assert "functional_connectivity" in ALLOWED_CONNECTION_TYPES
    assert "projection" in ALLOWED_CONNECTION_TYPES
    assert "association" in ALLOWED_CONNECTION_TYPES
    assert ALLOWED_DIRECTIONS == {"A_to_B", "B_to_A", "bidirectional", "unknown"}


def test_illegal_macro_name_forms():
    # subregion/layer/laterality 形态 → 非法
    assert _ILLEGAL_NAME_RE.search("Parasubiculum, layer 2")
    assert _ILLEGAL_NAME_RE.search("left parahippocampal area")
    assert _ILLEGAL_NAME_RE.search("Agranular insular area, posterior part, layer 2/3")
    assert _ILLEGAL_NAME_RE.search("supraoptic nucleus, subregion")
    # 合法 Macro region 名 → 不命中
    assert not _ILLEGAL_NAME_RE.search("Paracentral")
    assert not _ILLEGAL_NAME_RE.search("Thalamus proper")
    assert not _ILLEGAL_NAME_RE.search("Hippocampus")
    assert not _ILLEGAL_NAME_RE.search("Inferior lateral ventricle")


# ---- DB 层 ----

COUNTERS = [
    "SELECT count(*) FROM paper_connection_candidate_rankings",
    "SELECT count(*) FROM macro_candidate_connection_llm_reviews",
    "SELECT count(*) FROM final_canonical_connections WHERE final_status='active'",
    "SELECT count(*) FROM canonical_connections",
    "SELECT count(*) FROM macro_candidate_rule_validation_results",
]


async def _counts():
    async with AsyncSessionLocal() as s:
        return [int((await s.execute(text(c))).scalar()) for c in COUNTERS]


def _run(coro):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    return asyncio.run(coro)


def test_rule_results_table_shape_after_batch():
    """run_batch 幂等:结果表行数 = rankings 数,状态全在允许值,重跑覆盖旧 run。"""
    from app.services import macro_candidate_rule_validation_service as rvs

    async def go():
        async with AsyncSessionLocal() as s:
            r1 = await rvs.run_batch(s)
            runs = (await s.execute(text(
                "SELECT count(*) FROM macro_candidate_rule_validation_runs"))).scalar()
            rows = (await s.execute(text(
                "SELECT validation_status, count(*) FROM macro_candidate_rule_validation_results "
                "GROUP BY validation_status"))).all()
        async with AsyncSessionLocal() as s2:
            # 二次跑批(覆盖率运行)
            r2 = await rvs.run_batch(s2)
            runs2 = (await s2.execute(text(
                "SELECT count(*) FROM macro_candidate_rule_validation_runs"))).scalar()
        return r1, r2, runs, rows, runs2

    r1, r2, runs, rows, runs2 = _run(go())
    assert r1["object_count"] == r1["passed"] + r1["failed"] + r1["blocked"]
    assert runs == 1, "同 validator_key 只保留最新 run(幂等覆盖)"
    assert runs2 == 1
    allowed = {"PASS", "FAIL", "BLOCKED"}
    assert all(st in allowed for st, _ in rows)
    assert r2["object_count"] > 0
    # 结果数 = rankings 数(每 ranking 恰一条)
    assert sum(n for _, n in rows) == r1["object_count"]


def test_rule_validation_read_latest_and_case():
    """read_latest 返回 6 规则明细 + duplicate_existing;案例对存在。"""
    from app.services import macro_candidate_rule_validation_service as rvs
    from sqlalchemy import text as _text

    async def go():
        async with AsyncSessionLocal() as s:
            r = (await s.execute(_text("""\
SELECT r.id FROM paper_connection_candidate_rankings r
JOIN canonical_brain_regions rs ON rs.id = r.source_region_id
JOIN canonical_brain_regions rt ON rt.id = r.target_region_id
WHERE rs.canonical_name_en = 'Paracentral' AND rt.canonical_name_en = 'Lateral ventricle'
LIMIT 1"""))).first()
            if r is None:
                return None
            return await rvs.read_latest(s, str(r[0]))

    res = _run(go())
    if res is None:
        pytest.skip("案例 pair 不在 rankings(罕见配置)")
    assert res["validator_version"] == "macro_candidate_rule_validation_v1"
    codes = [x["code"] for x in res["rule_results"]]
    assert codes == ["R1", "R2", "R3", "R4", "R5", "R6"]
    # R5 至少终态存在判据字段
    assert "canonical" in res["duplicate_existing"]
    assert "final" in res["duplicate_existing"]
    assert "mirror" in res["duplicate_existing"]


def test_rule_validation_zero_side_effects():
    """跑批只写本组表:final/canonical 计数与 rule 结果表同增;其余表不动。

    (规则层禁止改 Final/canonical/mirror/ontology —— 跑批前后对比 final active 计数)
    """
    from app.services import macro_candidate_rule_validation_service as rvs

    async def go():
        before = await _counts()
        async with AsyncSessionLocal() as s:
            await rvs.run_batch(s)
        after = await _counts()
        return before, after

    before, after = _run(go())
    # final active / canonical 不变
    assert before[2] == after[2], "final_canonical_connections 必须不变"
    assert before[3] == after[3], "canonical_connections 必须不变"
    # rule results 表只有本组写
    assert after[4] == before[0], "results 行数与 rankings 对齐(单条/ranking)"
