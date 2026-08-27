"""Macro Candidate Rule Validation V1 —— 候选连接规则层(candidate 状态)。

输入 paper_connection_candidate_rankings(1129 对),输出 candidate 状态:
  pending_rule → rule_pass / rule_failed / rule_blocked

6 条规则(用户定义):
  R1 region 存在性   —— source/target canonical 脑区必须存在于 canonical_brain_regions
  R2 source != target —— 禁止自环
  R3 connection_type 合法 —— candidate 的 connection_type ∈ ontology 允许词表
  R4 direction 合法   —— direction ∈ schema 允许值
  R5 duplicate 检查   —— pair 已存在于 Final / Canonical / Mirror Connection → duplicate_existing
  R6 hierarchy 检查   —— source/target 必须为合法 Macro region;subregion/layer/laterality实体禁止

规则约束:
* 只写本组表(候选层),不修改 Final KG / canonical / mirror / ontology
* 幂等:validator_key = 'macro_candidate_rule_v1' 重跑 = 覆盖旧 run(级联删旧 results)后重建
* severity: R5/R6 为 BLOCK(配置性失败);R3/R4 在无 AI 结果时记 pass-with-note(数据未就绪)
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

VALIDATOR_KEY = "macro_candidate_rule_v1"
VALIDATOR_VERSION = "macro_candidate_rule_validation_v1"
GENERATION_METHOD = "macro_candidate_rule_validation_v1"
ASSERTION_TYPE = "candidate"
SOURCE_TYPE = "rule_validation"

# candidate 层(AI review 词表)允许的 connection_type
ALLOWED_CONNECTION_TYPES = {
    "structural_connection", "functional_connectivity", "projection",
    "association", "unknown",
}
# direction schema 允许值
ALLOWED_DIRECTIONS = {"A_to_B", "B_to_A", "bidirectional", "unknown"}

# 非法 Macro 形态(名称级;子区/层/侧向实体禁止直接进 Macro Final)
_ILLEGAL_NAME_RE = re.compile(
    r"(^|\s)(layer|subregion|sub-region|division|left|right)\b|[./,]",
    re.IGNORECASE,
)
ALLOWED_GRANULARITY = {"macro", "clinical"}

RULES = [
    {"code": "R1", "name": "region 存在性", "severity": "normal"},
    {"code": "R2", "name": "source != target", "severity": "normal"},
    {"code": "R3", "name": "connection_type 合法", "severity": "normal"},
    {"code": "R4", "name": "direction 合法", "severity": "normal"},
    {"code": "R5", "name": "duplicate 检查", "severity": "block"},
    {"code": "R6", "name": "hierarchy 检查", "severity": "block"},
]

RANKING_ROW_SQL = """\
SELECT r.source_region_id, r.target_region_id,
       rs.canonical_name_en AS source_name, rt.canonical_name_en AS target_name,
       rs.granularity_level AS source_gran, rt.granularity_level AS target_gran,
       rs.hemisphere_policy AS source_policy, rt.hemisphere_policy AS target_policy,
       rs.status AS source_status, rt.status AS target_status
FROM paper_connection_candidate_rankings r
JOIN canonical_brain_regions rs ON rs.id = r.source_region_id
JOIN canonical_brain_regions rt ON rt.id = r.target_region_id
WHERE r.id = :rid"""

REVIEW_ROW_SQL = """\
SELECT decision, connection_type, direction
FROM macro_candidate_connection_llm_reviews
WHERE ranking_id = :rid LIMIT 1"""


def _rule(rule: dict, passed: bool, detail: str) -> dict:
    return {"code": rule["code"], "name": rule["name"],
            "passed": bool(passed), "severity": rule["severity"], "detail": detail}


async def check_rule5_duplicate(
    session: AsyncSession, source_region_id: str, target_region_id: str,
) -> dict:
    """Pair 已存在于 Final / Canonical / Mirror Connection → duplicate_existing。"""
    a, b = sorted([source_region_id, target_region_id])
    final_hit = await session.execute(text(
        """SELECT count(*) FROM final_canonical_connections
           WHERE (source_region_id = :a AND target_region_id = :b)
              OR (source_region_id = :b AND target_region_id = :a)"""),
        {"a": a, "b": b})
    final_count = int(final_hit.scalar() or 0)
    canonical_hit = await session.execute(text(
        """SELECT count(*) FROM canonical_connections
           WHERE (source_region_id = :a AND target_region_id = :b)
              OR (source_region_id = :b AND target_region_id = :a)"""),
        {"a": a, "b": b})
    canonical_count = int(canonical_hit.scalar() or 0)
    # mirror:mirror 连接两端 candidate 的 canonical id 无向命中该 pair(上限 20)
    mirror_rows = (await session.execute(
        text("""SELECT c.id FROM mirror_region_connections c
           JOIN candidate_brain_regions cs ON cs.id = c.source_region_candidate_id
           JOIN candidate_brain_regions ct ON ct.id = c.target_region_candidate_id
           WHERE cs.canonical_region_id IS NOT NULL AND ct.canonical_region_id IS NOT NULL
             AND ((cs.canonical_region_id = :a AND ct.canonical_region_id = :b)
               OR (cs.canonical_region_id = :b AND ct.canonical_region_id = :a))
           LIMIT 20"""),
        {"a": a, "b": b})).all()
    mirror_ids = [str(r[0]) for r in mirror_rows]
    return {
        "final": final_count > 0,
        "canonical": canonical_count > 0,
        "mirror": len(mirror_ids) > 0,
        "final_count": final_count,
        "canonical_count": canonical_count,
        "mirror_pairs": mirror_ids,
    }


async def run_rule_checks(session: AsyncSession, ranking_id: str) -> dict:
    """对单条 ranking 执行 6 条规则,返回 {status, rule_results, duplicate_existing, failed_rules}。"""
    row = (await session.execute(
        text(RANKING_ROW_SQL), {"rid": ranking_id})).first()
    if row is None:
        return {"status": "FAIL",
                "rule_results": [_rule(RULES[0], False, "ranking 不存在")],
                "duplicate_existing": {}, "failed_rules": [{"code": "R1", "detail": "ranking 不存在"}]}
    src_id, tgt_id = str(row[0]), str(row[1])
    src_name, tgt_name = row[2] or "", row[3] or ""
    review = (await session.execute(
        text(REVIEW_ROW_SQL), {"rid": ranking_id})).first()
    review_type = review[1] if review else None
    review_direction = review[2] if review else None

    rules = RULES
    results = []
    # R1 region 存在性(canonical JOIN 保证行存在;仍显式校验)
    results.append(_rule(rules[0], bool(row) and src_name and tgt_name,
                         f"{src_name} 与 {tgt_name} 均为 canonical 脑区"))
    # R2 source != target
    results.append(_rule(rules[1], src_id != tgt_id, "无自环"))
    # R3 connection_type 合法(无 AI 审核时按"数据未就绪"放行并注明)
    if review_type is None:
        results.append(_rule(rules[2], True, "AI 审核未给出类型(数据未就绪,不判失败)"))
    else:
        r3_ok = review_type in ALLOWED_CONNECTION_TYPES
        results.append(_rule(rules[2], r3_ok, f"connection_type={review_type}"
                             + ("" if r3_ok else " 不在允许词表")))
    # R4 direction 合法(同上,unknown 为合法值)
    if review_direction is None:
        results.append(_rule(rules[3], True, "AI 审核未给出方向(数据未就绪,不判失败)"))
    else:
        r4_ok = review_direction in ALLOWED_DIRECTIONS
        results.append(_rule(rules[3], r4_ok, f"direction={review_direction}"
                             + ("" if r4_ok else " 不在 schema 允许值")))
    # R5 duplicate 检查(Final / Canonical / Mirror 三端)
    dup = await check_rule5_duplicate(session, src_id, tgt_id)
    dup_detail = (f"final={dup['final_count']} canonical={dup['canonical_count']} "
                  f"mirror={len(dup['mirror_pairs'])}") if (dup["final"] or dup["canonical"] or dup["mirror"]) \
        else "final/canonical/mirror 均不存在"
    results.append(_rule(rules[4], not (dup["final"] or dup["canonical"] or dup["mirror"]),
                         f"duplicate_existing: {dup_detail}"))
    # R6 hierarchy 检查:合法 Macro region(粒度 ∈ macro/clinical;名称无 subregion/layer/laterality 形态;status active)
    def _region_ok(name: str, granularity: str | None, policy: str | None, status: str | None) -> tuple[bool, str]:
        if granularity and granularity not in ALLOWED_GRANULARITY:
            return False, f"granularity_level={granularity} 非 Macro 尺度"
        if status and status != "active":
            return False, f"status={status}"
        if name and _ILLEGAL_NAME_RE.search(name):
            return False, f"名称 '{name}' 含 subregion/layer/laterality 形态"
        return True, "合法 Macro 脑区"
    src_ok, src_detail = _region_ok(src_name, row[4], row[6], row[8])
    tgt_ok, tgt_detail = _region_ok(tgt_name, row[5], row[7], row[9])
    r6_ok = src_ok and tgt_ok
    r6_detail = "合法 Macro 脑区" if r6_ok else f"源: {src_detail}; 目标: {tgt_detail}"
    results.append(_rule(rules[5], r6_ok, r6_detail))

    failed = [r for r in results if not r["passed"]]
    blocked = [r for r in failed if r["severity"] == "block"]
    if blocked:
        status = "BLOCKED"
    elif failed:
        status = "FAIL"
    else:
        status = "PASS"
    return {
        "status": status,
        "rule_results": results,
        "duplicate_existing": dup,
        "failed_rules": [{"code": r["code"], "name": r["name"], "detail": r["detail"]}
                         for r in failed],
    }


async def run_batch(session: AsyncSession) -> dict:
    """全量 1129 rankings 规则验证(幂等:覆盖旧 run)。"""
    all_ids = (await session.execute(text(
        "SELECT id FROM paper_connection_candidate_rankings ORDER BY score DESC"))).all()
    ranking_ids = [str(r[0]) for r in all_ids]

    # 覆盖旧 run(同 validator_key)→ 级联删旧 results
    await session.execute(text(
        "DELETE FROM macro_candidate_rule_validation_runs WHERE validator_key = :k"),
        {"k": VALIDATOR_KEY})
    run_id = (await session.execute(text(
        """INSERT INTO macro_candidate_rule_validation_runs
           (validator_key, validator_version, status, object_count, started_at)
           VALUES (:k, :v, 'created', :n, now())
           RETURNING id"""),
        {"k": VALIDATOR_KEY, "v": VALIDATOR_VERSION, "n": len(ranking_ids)})).scalar()

    passed = failed = blocked = 0
    now = datetime.now(timezone.utc)
    for rid in ranking_ids:
        res = await run_rule_checks(session, rid)
        if res["status"] == "PASS":
            passed += 1
        elif res["status"] == "BLOCKED":
            blocked += 1
        else:
            failed += 1
        await session.execute(text(
            """INSERT INTO macro_candidate_rule_validation_results
               (run_id, ranking_id, source_region_id, target_region_id, validation_status,
                rule_results, duplicate_existing, failed_rules, validator_version,
                validation_timestamp)
               VALUES (:run, :rid,
                  (SELECT source_region_id FROM paper_connection_candidate_rankings WHERE id=:rid),
                  (SELECT target_region_id FROM paper_connection_candidate_rankings WHERE id=:rid),
                  :status, :rules, :dup, :failed, :ver, :ts)
               ON CONFLICT (ranking_id) DO UPDATE SET
                  run_id = EXCLUDED.run_id,
                  validation_status = EXCLUDED.validation_status,
                  rule_results = EXCLUDED.rule_results,
                  duplicate_existing = EXCLUDED.duplicate_existing,
                  failed_rules = EXCLUDED.failed_rules,
                  validator_version = EXCLUDED.validator_version,
                  validation_timestamp = EXCLUDED.validation_timestamp"""),
            {"run": str(run_id), "rid": rid, "status": res["status"],
             "rules": Jsonb(res["rule_results"]), "dup": Jsonb(res["duplicate_existing"]),
             "failed": Jsonb(res["failed_rules"]), "ver": VALIDATOR_VERSION,
             "ts": now})

    await session.execute(text(
        """UPDATE macro_candidate_rule_validation_runs
           SET status='completed', finished_at=now(), passed_count=:p,
               failed_count=:f, blocked_count=:b WHERE id=:id"""),
        {"p": passed, "f": failed, "b": blocked, "id": str(run_id)})
    await session.commit()
    return {"run_id": str(run_id), "object_count": len(ranking_ids),
            "passed": passed, "failed": failed, "blocked": blocked}


async def read_latest(session: AsyncSession, ranking_id: str) -> dict | None:
    """读取跑批后的最新结果(前端展示用)。"""
    r = (await session.execute(text(
        """SELECT id, validation_status, rule_results, duplicate_existing,
                  failed_rules, validator_version, validation_timestamp
           FROM macro_candidate_rule_validation_results
           WHERE ranking_id = :rid ORDER BY validation_timestamp DESC LIMIT 1"""),
        {"rid": ranking_id})).first()
    if r is None:
        return None
    return {
        "ranking_id": ranking_id,
        "validation_status": r[1],
        "rule_results": r[2] or [],
        "duplicate_existing": r[3] or {},
        "failed_rules": r[4] or [],
        "validator_version": r[5],
        "validation_timestamp": r[6].isoformat() if r[6] else None,
    }
