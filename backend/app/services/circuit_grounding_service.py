"""CR1 canonical grounding — Mirror Circuit → Canonical Circuit.

服务职责（只读分析 + 幂等分批构建，绝不修改 mirror_region_circuits 及
其成员表）：

  * ``analyze_mirror_circuit_data`` — 只读数据分析：circuit 总数、粒度
    分布、region 成员 grounding 状态、成员数分布、名称空/重复、canonical
    覆盖、projection / function 关联规模。
  * ``build_circuit_grounding`` — 分批构建 grounding 表（每批 500-1000，
    幂等）：回填 canonical_circuits.provenance 已覆盖的 mirror circuit ids
    （CI1.2-B 的 293 个）；未覆盖行按 frozen 判定顺序分类（species /
    成员不足 / 无 grounded 成员 / unknown role），不创建任何 canonical
    circuit；失败行写 unresolved + 原因。
  * ``grounding_stats`` / ``unresolved_report`` — 聚合统计输出。

约束：不执行 circuit abstraction / inference / Final promotion；不创建
新的 canonical_circuits；不修改 mirror 行。CR1 只记录映射状态。
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_circuit import MirrorCircuitCanonicalGrounding

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #

DEFAULT_BATCH_SIZE = 500
MIN_BATCH_SIZE = 500
MAX_BATCH_SIZE = 1000
GROUNDING_SOURCE = "cr1_circuit_grounding_v1"

# CR1 frozen rules —— 判定顺序（_plan_row 内同样序）：
#   1. canonical_circuits.provenance_json->>'source_mirror_circuit_id' 命中 → grounded（回填）
#   2. granularity_level 属于跨物种/非 human 池                          → species_granularity_mismatch
#   3. region 成员数 = 0                                                → no_region_members
#   4. region 成员数 < 2                                                → too_few_regions
#   5. grounded region 成员数 = 0                                       → no_grounded_regions
#   6. 其余（≥2 成员但未被 canonicalizer 处理）                           → unknown_region_role
_SPECIES_GRANULARITIES = {"molecular_attr"}

_RR_SPECIES = "species_granularity_mismatch"
_RR_NO_MEMBERS = "no_region_members"
_RR_TOO_FEW = "too_few_regions"
_RR_NO_GROUNDED = "no_grounded_regions"
_RR_UNKNOWN_ROLE = "unknown_region_role"


def _normalize_circuit_name(name: str) -> str:
    """名称标准化：strip + 压缩内部空白（保留原始大小写）。"""
    return " ".join(name.strip().split())


# --------------------------------------------------------------------------- #
# 只读数据分析
# --------------------------------------------------------------------------- #


async def analyze_mirror_circuit_data(session: AsyncSession) -> dict[str, Any]:
    """只读统计当前 Mirror Circuit 数据全景（不写任何表）。"""
    row = (
        await session.execute(
            text(
                """
                SELECT
                  (SELECT count(*) FROM mirror_region_circuits) AS circuit_total,
                  (SELECT count(*) FROM mirror_circuit_regions) AS region_members_total,
                  (SELECT count(*) FROM mirror_circuit_steps) AS steps_total,
                  (SELECT count(*) FROM mirror_circuit_functions) AS functions_total,
                  (SELECT count(*) FROM mirror_circuit_projection_memberships) AS projections_total,
                  (SELECT count(*) FROM canonical_circuits) AS canonical_total,
                  count(*) FILTER (WHERE circuit_name IS NULL OR btrim(circuit_name) = '') AS name_empty,
                  count(*) FILTER (WHERE name_cn IS NULL OR btrim(name_cn) = '') AS name_cn_missing
                FROM mirror_region_circuits
                """
            )
        )
    ).mappings().first()

    granularity = {
        r[0]: int(r[1])
        for r in (
            await session.execute(
                text(
                    "SELECT granularity_level, count(*) FROM mirror_region_circuits "
                    "GROUP BY 1 ORDER BY 2 DESC"
                )
            )
        ).all()
    }

    member_grounding = (
        await session.execute(
            text(
                """
                SELECT
                  count(*) FILTER (WHERE m.region_candidate_id IS NULL) AS candidate_missing,
                  count(*) FILTER (WHERE m.region_candidate_id IS NOT NULL
                                    AND cb.canonical_region_id IS NULL) AS candidate_ungrounded,
                  count(*) FILTER (WHERE cb.canonical_region_id IS NOT NULL) AS candidate_grounded
                FROM mirror_circuit_regions m
                LEFT JOIN candidate_brain_regions cb ON cb.id = m.region_candidate_id
                """
            )
        )
    ).mappings().first()

    per_circuit = {
        r[0]: int(r[1])
        for r in (
            await session.execute(
                text(
                    """
                    SELECT n, count(*) FROM (
                      SELECT circuit_id, count(*) n FROM mirror_circuit_regions GROUP BY 1
                    ) x GROUP BY 1 ORDER BY 1
                    """
                )
            )
        ).all()
    }

    dup = (
        await session.execute(
            text(
                """
                SELECT count(*) AS groups, coalesce(sum(n - 1), 0) AS extra_rows
                FROM (
                  SELECT circuit_name, count(*) n FROM mirror_region_circuits
                  WHERE circuit_name IS NOT NULL GROUP BY 1 HAVING count(*) > 1
                ) x
                """
            )
        )
    ).mappings().first()

    canonical_coverage = (
        await session.execute(
            text(
                "SELECT count(*) FROM canonical_circuits "
                "WHERE provenance_json->>'source_mirror_circuit_id' IS NOT NULL"
            )
        )
    ).scalar()

    projections = (
        await session.execute(
            text(
                "SELECT count(DISTINCT circuit_id), count(DISTINCT projection_id) "
                "FROM mirror_circuit_projection_memberships"
            )
        )
    ).all()[0]

    return {
        "total_mirror_circuits": int(row["circuit_total"]),
        "region_members_total": int(row["region_members_total"]),
        "circuit_steps_total": int(row["steps_total"]),
        "circuit_functions_total": int(row["functions_total"]),
        "projection_memberships_total": int(row["projections_total"]),
        "canonical_circuits_existing": int(row["canonical_total"]),
        "canonical_coverage": int(canonical_coverage),
        "granularity_distribution": granularity,
        "member_grounding": {
            "candidate_missing": int(member_grounding["candidate_missing"]),
            "candidate_ungrounded": int(member_grounding["candidate_ungrounded"]),
            "candidate_grounded": int(member_grounding["candidate_grounded"]),
        },
        "members_per_circuit": per_circuit,
        "naming": {
            "circuit_name_filled": int(row["circuit_total"]) - int(row["name_empty"]),
            "name_cn_filled": int(row["circuit_total"]) - int(row["name_cn_missing"]),
        },
        "duplicates": {
            "groups": int(dup["groups"]) if dup else 0,
            "extra_rows": int(dup["extra_rows"]) if dup else 0,
        },
        "projection_circuits": int(projections[0]),
        "distinct_projections": int(projections[1]),
    }


# --------------------------------------------------------------------------- #
# 内存加载（一次全量，避免 N+1）
# --------------------------------------------------------------------------- #


async def _load_existing_grounding(
    session: AsyncSession, atlas_filter: str | None = None
) -> set[str]:
    """已写 grounding 的 mirror circuit ids；atlas_filter 非空时只统计该 atlas。"""
    sql = (
        "SELECT g.mirror_circuit_id::text "
        "FROM mirror_circuit_canonical_grounding g "
        "JOIN mirror_region_circuits c ON c.id = g.mirror_circuit_id "
        "WHERE c.source_atlas = :atlas"
        if atlas_filter
        else "SELECT mirror_circuit_id::text FROM mirror_circuit_canonical_grounding"
    )
    rows = (await session.execute(text(sql), {"atlas": atlas_filter} if atlas_filter else {})).scalars().all()
    return set(rows)


async def _load_canonical_coverage(session: AsyncSession) -> dict[str, tuple[str, str, str]]:
    """canonical_circuits.provenance 已覆盖的 mirror ids → (canonical_id, en, cn)。

    CI1.2-B 写 provenance 时用 ``source_mirror_circuit_id`` 单值键（非数组）。
    """
    rows = (
        await session.execute(
            text(
                "SELECT id, canonical_name_en, canonical_name_cn, "
                "provenance_json->>'source_mirror_circuit_id' "
                "FROM canonical_circuits "
                "WHERE provenance_json->>'source_mirror_circuit_id' IS NOT NULL"
            )
        )
    ).all()
    return {mid: (str(cc_id), en, cn) for cc_id, en, cn, mid in rows}


async def _load_resolved_connections(session: AsyncSession) -> dict[str, int]:
    """projection membership → CN1 grounding 已 grounded 的 canonical connections。

    返回 {circuit_id: resolved_connection_count}。projection_id 指向
    mirror_region_connections，经 mirror_connection_canonical_grounding
    判定该 projection 是否已落到 canonical 层。
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT p.circuit_id::text, count(DISTINCT g.canonical_connection_id)
                FROM mirror_circuit_projection_memberships p
                JOIN mirror_connection_canonical_grounding g
                  ON g.mirror_connection_id = p.projection_id
                WHERE g.status = 'grounded'
                GROUP BY 1
                """
            )
        )
    ).all()
    return {cid: int(n) for cid, n in rows}


# --------------------------------------------------------------------------- #
# grounding 构建
# --------------------------------------------------------------------------- #

# 成员统计聚合（每批一次，GROUP BY 在 LIMIT 前 —— 无 N+1）
_CIRCUIT_STATS_SQL = """
SELECT c.id, c.granularity_level, c.source_atlas, c.circuit_name, c.name_cn,
       c.circuit_type, c.confidence, c.evidence_text, c.function_association,
       count(DISTINCT m.id) AS total_members,
       count(DISTINCT m.id) FILTER (WHERE cb.canonical_region_id IS NOT NULL) AS grounded_members,
       count(DISTINCT p.id) AS projection_memberships,
       count(DISTINCT f.id) AS function_count
FROM mirror_region_circuits c
LEFT JOIN mirror_circuit_regions m ON m.circuit_id = c.id
LEFT JOIN candidate_brain_regions cb ON cb.id = m.region_candidate_id
LEFT JOIN mirror_circuit_projection_memberships p ON p.circuit_id = c.id
LEFT JOIN mirror_circuit_functions f ON f.circuit_id = c.id
"""


def _plan_row(
    row: Any, *, coverage: dict[str, tuple[str, str, str]] | None = None
) -> dict[str, Any]:
    """为单条 mirror circuit 行做 grounding 计划（纯内存，不写库）。

    返回 kind ∈ grounded / unresolved。判定顺序见模块常量注释；
    coverage 命中（CI1.2-B 已 canonicalized）直接回填 grounded，
    canonical 侧名称随行带回。
    """
    cid = str(row[0])
    granularity = row[1]
    atlas = row[2]
    raw_name = row[3] or ""
    name_cn = row[4]
    circuit_type = row[5]
    confidence = float(row[6]) if row[6] is not None else None
    total_members = int(row[9])
    grounded_members = int(row[10])
    projection_memberships = int(row[11])
    function_count = int(row[12])

    norm_name = _normalize_circuit_name(raw_name)

    cov = coverage.get(cid) if coverage else None
    if cov:
        return {
            "kind": "grounded",
            "mirror_id": cid,
            "canonical_id": cov[0],
            "canonical_name_en": cov[1],
            "canonical_name_cn": cov[2],
            "granularity": granularity,
            "atlas": atlas,
            "circuit_type": circuit_type,
            "total_members": total_members,
            "grounded_members": grounded_members,
            "projection_memberships": projection_memberships,
            "function_count": function_count,
            "confidence": confidence,
            "evidence_text": row[7],
            "function_association": row[8],
        }

    if granularity in _SPECIES_GRANULARITIES:
        reason = _RR_SPECIES
    elif total_members == 0:
        reason = _RR_NO_MEMBERS
    elif total_members < 2:
        reason = _RR_TOO_FEW
    elif grounded_members == 0:
        reason = _RR_NO_GROUNDED
    else:
        reason = _RR_UNKNOWN_ROLE

    return {
        "kind": "unresolved",
        "mirror_id": cid,
        "canonical_name_en": norm_name,
        "canonical_name_cn": name_cn,
        "granularity": granularity,
        "atlas": atlas,
        "circuit_type": circuit_type,
        "total_members": total_members,
        "grounded_members": grounded_members,
        "projection_memberships": projection_memberships,
        "function_count": function_count,
        "confidence": confidence,
        "reason": reason,
        "evidence_text": row[7],
        "function_association": row[8],
    }


def _build_provenance(plan: dict[str, Any]) -> dict[str, Any]:
    """CR1 provenance：source circuit id + evidence + function association。"""
    return {
        "source_circuit_id": plan["mirror_id"],
        "mapping_method": GROUNDING_SOURCE,
        "granularity_level": plan["granularity"],
        "evidence_text": plan["evidence_text"],
        "function_association": plan["function_association"],
        "region_members": {
            "total": plan["total_members"],
            "grounded": plan["grounded_members"],
        },
        "projection_memberships": plan["projection_memberships"],
    }


async def _write_grounding_rows(
    session: AsyncSession,
    plans: list[dict[str, Any]],
    *,
    created_by: str,
    resolved_connections: dict[str, int],
) -> None:
    """写入一批 grounding 行（CR1 不创建 canonical circuit）。"""
    for plan in plans:
        session.add(MirrorCircuitCanonicalGrounding(
            mirror_circuit_id=uuid.UUID(plan["mirror_id"]),
            canonical_circuit_id=uuid.UUID(plan["canonical_id"]) if plan.get("canonical_id") else None,
            canonical_name_en=plan.get("canonical_name_en"),
            canonical_name_cn=plan.get("canonical_name_cn"),
            granularity_level=plan["granularity"],
            source_atlas=plan["atlas"],
            circuit_type=plan["circuit_type"],
            total_region_members=plan["total_members"],
            grounded_region_members=plan["grounded_members"],
            ungrounded_region_members=plan["total_members"] - plan["grounded_members"],
            projection_membership_count=plan["projection_memberships"],
            resolved_connection_count=resolved_connections.get(plan["mirror_id"], 0),
            function_count=plan["function_count"],
            mapping_method=GROUNDING_SOURCE,
            status="grounded" if plan["kind"] == "grounded" else "unresolved",
            unresolved_reason=plan.get("reason"),
            confidence=plan["confidence"],
            provenance_json=_build_provenance(plan),
            created_by=created_by,
        ))


async def build_circuit_grounding(
    session: AsyncSession,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    dry_run: bool = False,
    created_by: str = GROUNDING_SOURCE,
    atlas_filter: str | None = None,
) -> dict[str, Any]:
    """分批构建 Mirror → Canonical grounding 表（幂等）。

    batch_size 必须落在 [500, 1000]；dry_run=True 只预测不写入。
    重跑时已有 grounding 行全部跳过，新行按同规则补建。
    atlas_filter 只处理指定 source_atlas 的行（None=全量，生产默认；
    测试隔离用）。
    """
    if not (MIN_BATCH_SIZE <= batch_size <= MAX_BATCH_SIZE):
        raise ValueError(
            f"batch_size must be within [{MIN_BATCH_SIZE}, {MAX_BATCH_SIZE}], got {batch_size}"
        )

    existing = await _load_existing_grounding(session, atlas_filter=atlas_filter)
    coverage = await _load_canonical_coverage(session)
    resolved_connections = await _load_resolved_connections(session)

    counts = {
        "total_mirror_rows": 0,
        "already_grounded_rows": len(existing),
        "grounded": {"backfilled_from_canonical": 0},
        "unresolved": {
            _RR_SPECIES: 0,
            _RR_NO_MEMBERS: 0,
            _RR_TOO_FEW: 0,
            _RR_NO_GROUNDED: 0,
            _RR_UNKNOWN_ROLE: 0,
        },
    }

    # keyset 分页扫描 mirror circuits（可选按 source_atlas 过滤）
    last_id: uuid.UUID | None = None
    where_atlas = "WHERE c.source_atlas = :atlas" if atlas_filter else ""
    where_both = "WHERE c.source_atlas = :atlas AND c.id > :last_id" if atlas_filter else "WHERE c.id > :last_id"
    while True:
        sql = _CIRCUIT_STATS_SQL + f"{where_both if last_id is not None else where_atlas} GROUP BY c.id ORDER BY c.id LIMIT :limit"
        params: dict[str, Any] = {"limit": batch_size}
        if last_id is not None:
            params["last_id"] = last_id
        if atlas_filter:
            params["atlas"] = atlas_filter
        rows = (await session.execute(text(sql), params)).all()
        if not rows:
            break

        plans: list[dict[str, Any]] = []
        for row in rows:
            mid = str(row[0])
            counts["total_mirror_rows"] += 1
            if mid in existing:
                continue
            plan = _plan_row(row, coverage=coverage)
            if plan["kind"] == "grounded":
                counts["grounded"]["backfilled_from_canonical"] += 1
            else:
                counts["unresolved"][plan["reason"]] += 1
            plans.append(plan)

        if plans and not dry_run:
            await _write_grounding_rows(
                session, plans, created_by=created_by, resolved_connections=resolved_connections
            )
            await session.commit()
        for plan in plans:
            existing.add(plan["mirror_id"])
        last_id = rows[-1][0]

    counts["dry_run"] = dry_run
    return counts


# --------------------------------------------------------------------------- #
# 聚合统计 / unresolved report
# --------------------------------------------------------------------------- #


async def grounding_stats(session: AsyncSession) -> dict[str, Any]:
    """从 grounding 表聚合输出（总/成功/失败/覆盖数）。"""
    row = (
        await session.execute(
            text(
                """
                SELECT count(*) AS total,
                       count(*) FILTER (WHERE status = 'grounded') AS grounded,
                       count(*) FILTER (WHERE status = 'unresolved') AS unresolved,
                       count(DISTINCT canonical_circuit_id) AS distinct_canonical
                FROM mirror_circuit_canonical_grounding
                """
            )
        )
    ).mappings().first()
    reasons = {
        r[0]: int(r[1])
        for r in (
            await session.execute(
                text(
                    """
                    SELECT unresolved_reason, count(*) FROM mirror_circuit_canonical_grounding
                    WHERE status = 'unresolved' GROUP BY 1 ORDER BY 2 DESC
                    """
                )
            )
        ).all()
    }
    return {
        "total_grounding_rows": int(row["total"]),
        "grounded": int(row["grounded"]),
        "unresolved": int(row["unresolved"]),
        "unresolved_by_reason": reasons,
        "distinct_canonical_circuits": int(row["distinct_canonical"]),
    }


async def unresolved_report(session: AsyncSession, *, limit: int = 20) -> dict[str, Any]:
    """unresolved 明细报告：按原因分组 + 抽样（含名称与粒度）。"""
    rows = (
        await session.execute(
            text(
                """
                SELECT g.unresolved_reason, g.canonical_name_en, g.granularity_level,
                       g.source_atlas, g.total_region_members, g.grounded_region_members
                FROM mirror_circuit_canonical_grounding g
                WHERE g.status = 'unresolved'
                ORDER BY g.unresolved_reason, g.created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
    ).all()
    return {
        "sample_limit": limit,
        "samples": [
            {
                "reason": r[0],
                "circuit_name": r[1],
                "granularity_level": r[2],
                "source_atlas": r[3],
                "total_region_members": int(r[4]),
                "grounded_region_members": int(r[5]),
            }
            for r in rows
        ],
    }
