"""CN1 canonical grounding — Mirror Connection → Canonical Connection.

服务职责（只读分析 + 幂等分批构建，绝不修改 mirror_region_connections）：

  * ``analyze_mirror_connection_data`` — 只读数据分析：总数量、端点
    grounding 状态、命名一致性、未解析 region 数量（按 atlas 分）、
    duplicate、自环、connection_type / directionality 词表覆盖率。
  * ``resolve_region_by_name`` — 分层名称解析：canonical en/cn 精确 →
    alias 精确 → 归一化精确。跨物种 atlas（Allen 小鼠）直接拒绝，
    不进入 human canonical 池（BR3 跨物种守卫同源语义）。
  * ``build_connection_grounding`` — 分批构建 grounding 表（每批 500-1000，
    幂等）：回填 canonical_connections.provenance 已覆盖的 mirror ids；
    未覆盖行做 candidate grounded / 名称解析 → 复用或新建
    canonical_connection（复用 frozen mapping rules，provenance 保留）；
    失败行写 unresolved + 原因。
  * ``grounding_stats`` / ``unresolved_report`` — 聚合统计输出。

约束：不执行 roll-up / inference / Final promotion；不修改既有
canonical_connections 行与 mirror 行。
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_connection import (
    CanonicalConnection,
    MirrorConnectionCanonicalGrounding,
)
from app.schemas.canonical_connection import CanonicalConnectionCreate
from app.services import canonical_connection_service as ccs
from app.services.connection_mapping_service import (
    build_connection_provenance,
    map_connection_type,
    map_directionality_policy,
)

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #

DEFAULT_BATCH_SIZE = 500
MIN_BATCH_SIZE = 500
MAX_BATCH_SIZE = 1000
GROUNDING_SOURCE = "cn1_connection_grounding_v1"

# 跨物种 atlas：端点名称属于不同物种（小鼠），与 human canonical 池
# 不可直接匹配（BR3 跨物种守卫语义），统一标注 species_mismatch。
_CROSS_SPECIES_ATLASES = {"Allen_HBA_2012"}

# resolution method 取值
_RM_CANDIDATE = "candidate_grounded"
_RM_CANONICAL = "name_canonical_exact"
_RM_ALIAS = "name_alias_exact"
_RM_NORMALIZED = "name_normalized_exact"
_RM_UNRESOLVED = "unresolved"

# unresolved reason 取值
_RR_SPECIES = "species_mismatch"
_RR_NO_NAME = "no_name_match"
_RR_SELF_LOOP = "self_loop"
_RR_MAPPING = "mapping_error"

_NORMALIZE_RE = re.compile(r"[^a-z0-9一-鿿 ]+")


def _normalize(name: str) -> str:
    """归一化名称用于最后一层匹配：casefold + 去标点 + 压缩空白。"""
    return " ".join(_NORMALIZE_RE.sub(" ", name.casefold()).split())


def _resolve_name_sync(
    cn: str | None, en: str | None, index: dict[str, Any]
) -> tuple[str | None, str | None]:
    """同步名称解析（内存索引，无 IO）→ (canonical_region_id, method)。

    匹配层：canonical en 精确 → canonical cn 精确 → alias 精确 →
    归一化精确（大小写/标点不敏感）。跨物种已在调用方拦截。
    """
    for raw, table, method in (
        (en, "en_exact", _RM_CANONICAL),
        (cn, "cn_exact", _RM_CANONICAL),
        (en, "en_norm", _RM_NORMALIZED),
        (cn, "cn_norm", _RM_NORMALIZED),
    ):
        if not raw:
            continue
        if table.startswith("en"):
            key = raw.casefold() if table == "en_exact" else _normalize(raw)
        else:
            key = raw if table == "cn_exact" else _normalize(raw)
        rid = index[table].get(key)
        if rid:
            return rid, method
    for raw in (en, cn):
        if raw:
            rid = index["alias"].get(raw.casefold())
            if rid:
                return rid, _RM_ALIAS
    return None, None


# --------------------------------------------------------------------------- #
# 只读数据分析
# --------------------------------------------------------------------------- #


async def analyze_mirror_connection_data(session: AsyncSession) -> dict[str, Any]:
    """只读统计当前 Mirror Connection 数据全景（不写任何表）。"""
    row = (
        await session.execute(
            text(
                """
                WITH base AS (
                  SELECT mrc.id,
                         mrc.source_region_candidate_id,
                         mrc.target_region_candidate_id,
                         s.canonical_region_id AS src_canon,
                         t.canonical_region_id AS tgt_canon,
                         mrc.source_region_name_cn, mrc.source_region_name_en,
                         mrc.target_region_name_cn, mrc.target_region_name_en,
                         mrc.source_atlas
                  FROM mirror_region_connections mrc
                  LEFT JOIN candidate_brain_regions s ON s.id = mrc.source_region_candidate_id
                  LEFT JOIN candidate_brain_regions t ON t.id = mrc.target_region_candidate_id
                )
                SELECT
                  (SELECT count(*) FROM mirror_region_connections) AS total,
                  count(*) FILTER (WHERE src_canon IS NOT NULL AND tgt_canon IS NOT NULL) AS both_grounded,
                  count(*) FILTER (WHERE src_canon IS NULL OR tgt_canon IS NULL) AS any_ungrounded,
                  count(*) FILTER (WHERE source_region_candidate_id IS NULL
                                    OR target_region_candidate_id IS NULL) AS candidate_missing,
                  count(*) FILTER (WHERE source_region_candidate_id IS NOT NULL
                                    AND source_region_candidate_id = target_region_candidate_id) AS same_candidate,
                  count(*) FILTER (WHERE source_region_name_cn IS NULL) AS src_cn_missing,
                  count(*) FILTER (WHERE source_region_name_en IS NULL) AS src_en_missing,
                  count(*) FILTER (WHERE target_region_name_cn IS NULL) AS tgt_cn_missing,
                  count(*) FILTER (WHERE target_region_name_en IS NULL) AS tgt_en_missing,
                  (SELECT count(DISTINCT connection_type) FROM mirror_region_connections) AS distinct_types,
                  (SELECT count(DISTINCT directionality) FROM mirror_region_connections) AS distinct_dirs,
                  (SELECT count(*) FROM canonical_connections) AS canonical_total
                FROM base
                """
            )
        )
    ).mappings().first()

    unresolved_by_atlas = {
        r[0]: int(r[1])
        for r in (
            await session.execute(
                text(
                    """
                    SELECT mrc.source_atlas, count(*) FROM mirror_region_connections mrc
                    LEFT JOIN candidate_brain_regions s ON s.id = mrc.source_region_candidate_id
                    LEFT JOIN candidate_brain_regions t ON t.id = mrc.target_region_candidate_id
                    WHERE s.canonical_region_id IS NULL OR t.canonical_region_id IS NULL
                    GROUP BY 1 ORDER BY 2 DESC
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
                  SELECT s.canonical_region_id, t.canonical_region_id, mrc.connection_type, count(*) n
                  FROM mirror_region_connections mrc
                  JOIN candidate_brain_regions s ON s.id = mrc.source_region_candidate_id
                  JOIN candidate_brain_regions t ON t.id = mrc.target_region_candidate_id
                  WHERE s.canonical_region_id IS NOT NULL AND t.canonical_region_id IS NOT NULL
                  GROUP BY 1, 2, 3 HAVING count(*) > 1
                ) x
                """
            )
        )
    ).mappings().first()

    return {
        "total_mirror_connections": int(row["total"]),
        "endpoint_grounding": {
            "both_candidate_grounded": int(row["both_grounded"]),
            "any_ungrounded": int(row["any_ungrounded"]),
            "candidate_missing": int(row["candidate_missing"]),
        },
        "naming": {
            "source_cn_filled": int(row["total"]) - int(row["src_cn_missing"]),
            "source_en_filled": int(row["total"]) - int(row["src_en_missing"]),
            "target_cn_filled": int(row["total"]) - int(row["tgt_cn_missing"]),
            "target_en_filled": int(row["total"]) - int(row["tgt_en_missing"]),
            "total": int(row["total"]),
        },
        "unresolved_by_atlas": unresolved_by_atlas,
        "duplicates": {
            "groups": int(dup["groups"]) if dup else 0,
            "extra_rows": int(dup["extra_rows"]) if dup else 0,
        },
        "self_loops": int(row["same_candidate"]),
        "type_coverage": {
            "mirror_distinct": int(row["distinct_types"]),
            "canonical_enum": sorted(ccs._VALID_CONNECTION_TYPES),
        },
        "direction_coverage": {
            "mirror_distinct": int(row["distinct_dirs"]),
            "canonical_enum": sorted(ccs._VALID_DIRECTIONALITY_POLICIES),
        },
        "canonical_connections_existing": int(row["canonical_total"]),
    }


# --------------------------------------------------------------------------- #
# 名称索引 + 分层解析
# --------------------------------------------------------------------------- #


async def _load_name_index(session: AsyncSession) -> dict[str, Any]:
    """加载 canonical 区域名称索引（小表，全内存）。

    返回:
      * en_exact / cn_exact / en_norm / cn_norm: {key: region_id}
      * alias: {alias_casefold: region_id}
    """
    index: dict[str, Any] = {"en_exact": {}, "cn_exact": {}, "en_norm": {}, "cn_norm": {}, "alias": {}}
    regions = (
        await session.execute(
            text("SELECT id, canonical_name_en, canonical_name_cn FROM canonical_brain_regions")
        )
    ).all()
    for rid, en, cn in regions:
        sid = str(rid)
        if en:
            index["en_exact"][en.casefold()] = sid
            index["en_norm"][_normalize(en)] = sid
        if cn:
            index["cn_exact"][cn] = sid
            index["cn_norm"][_normalize(cn)] = sid
    aliases = (
        await session.execute(
            text("SELECT alias, region_id FROM canonical_region_aliases WHERE alias IS NOT NULL")
        )
    ).all()
    for alias, rid in aliases:
        index["alias"].setdefault(alias.casefold(), str(rid))
    return index


async def resolve_region_by_name(
    session: AsyncSession,
    *,
    cn: str | None,
    en: str | None,
    atlas: str | None,
    index: dict[str, Any] | None = None,
    cross_species_atlases: set[str] | None = None,
) -> tuple[str | None, str | None]:
    """分层名称解析 → (canonical_region_id, resolution_method)。

    跨物种 atlas（Allen 小鼠）恒为 (None, None) —— 调用方据此标注
    species_mismatch，绝不让小鼠精细区域落入 human canonical 池。
    cross_species_atlases 可覆盖默认集合（测试隔离用）。
    """
    cross_species = cross_species_atlases if cross_species_atlases is not None else _CROSS_SPECIES_ATLASES
    if atlas in cross_species:
        return None, None
    idx = index if index is not None else await _load_name_index(session)
    return _resolve_name_sync(cn, en, idx)


# --------------------------------------------------------------------------- #
# grounding 构建
# --------------------------------------------------------------------------- #


async def _load_existing_grounding(
    session: AsyncSession, atlas_filter: str | None = None
) -> set[str]:
    """已 grounded 的 mirror ids；atlas_filter 非空时只统计该 atlas 的行。"""
    sql = (
        "SELECT g.mirror_connection_id::text "
        "FROM mirror_connection_canonical_grounding g "
        "JOIN mirror_region_connections mrc ON mrc.id = g.mirror_connection_id "
        "WHERE mrc.source_atlas = :atlas"
        if atlas_filter
        else "SELECT mirror_connection_id::text FROM mirror_connection_canonical_grounding"
    )
    rows = (await session.execute(text(sql), {"atlas": atlas_filter} if atlas_filter else {})).scalars().all()
    return set(rows)


async def _load_provenance_coverage(session: AsyncSession) -> dict[str, str]:
    """canonical_connections.provenance 已覆盖的 mirror ids → canonical id。"""
    rows = (
        await session.execute(
            text(
                "SELECT id, jsonb_array_elements_text(provenance_json->'original_connection_ids') "
                "FROM canonical_connections "
                "WHERE provenance_json->'original_connection_ids' IS NOT NULL"
            )
        )
    ).all()
    return {mid: str(cc_id) for cc_id, mid in rows}


async def _load_canonical_keys(session: AsyncSession) -> dict[tuple[str, str, str], str]:
    rows = (
        await session.execute(
            text(
                "SELECT id::text, source_region_id::text, target_region_id::text, connection_type "
                "FROM canonical_connections"
            )
        )
    ).all()
    return {(src, tgt, ctype): cc_id for cc_id, src, tgt, ctype in rows}


async def _load_candidate_grounding(session: AsyncSession) -> dict[str, str]:
    rows = (
        await session.execute(
            text(
                "SELECT id::text, canonical_region_id::text FROM candidate_brain_regions "
                "WHERE canonical_region_id IS NOT NULL"
            )
        )
    ).all()
    return dict(rows)


def _plan_row(
    row: Any,
    *,
    candidate_grounded: dict[str, str],
    name_index: dict[str, Any],
    canonical_keys: dict[tuple[str, str, str], str],
    created_canonical: dict[tuple[str, str, str], str],
    cross_species_atlases: set[str] | None = None,
) -> dict[str, Any]:
    """为单条 mirror 行做 grounding 计划（纯内存，不写库）。

    返回:
      * grounded — 复用既有 canonical_connection
      * create  — 需要新建 canonical_connection
      * unresolved — 失败 + reason（species_mismatch / no_name_match /
        self_loop / mapping_error）
    """
    mid = str(row[0])
    src_cand = str(row[1]) if row[1] else None
    tgt_cand = str(row[2]) if row[2] else None
    src_cn, src_en = row[3], row[4]
    tgt_cn, tgt_en = row[5], row[6]
    atlas = row[7]
    raw_type, raw_dir = row[8], row[9]
    confidence = float(row[10]) if row[10] is not None else None

    cross_species = cross_species_atlases if cross_species_atlases is not None else _CROSS_SPECIES_ATLASES

    # 自环（candidate 层同 id）
    if src_cand and src_cand == tgt_cand:
        return {"kind": "unresolved", "mirror_id": mid, "reason": _RR_SELF_LOOP}

    src_id = candidate_grounded.get(src_cand) if src_cand else None
    tgt_id = candidate_grounded.get(tgt_cand) if tgt_cand else None
    src_method = _RM_CANDIDATE if src_id else None
    tgt_method = _RM_CANDIDATE if tgt_id else None

    # 未 grounded 端点走名称解析（跨物种 atlas 直接跳过）
    if not src_id and atlas not in cross_species:
        src_id, src_method = _resolve_name_sync(src_cn, src_en, name_index)
    if not tgt_id and atlas not in cross_species:
        tgt_id, tgt_method = _resolve_name_sync(tgt_cn, tgt_en, name_index)

    if src_id is None or tgt_id is None:
        reason = _RR_SPECIES if atlas in cross_species else _RR_NO_NAME
        return {"kind": "unresolved", "mirror_id": mid, "reason": reason}

    # 解析后自环（不同 candidate 落到同一 canonical region）
    if src_id == tgt_id:
        return {"kind": "unresolved", "mirror_id": mid, "reason": _RR_SELF_LOOP}

    try:
        conn_type = map_connection_type(raw_type)
        direction = map_directionality_policy(raw_dir)
    except Exception:
        return {"kind": "unresolved", "mirror_id": mid, "reason": _RR_MAPPING}

    key = (src_id, tgt_id, conn_type)
    existing = canonical_keys.get(key) or created_canonical.get(key)
    if existing:
        return {
            "kind": "grounded",
            "mirror_id": mid,
            "canonical_id": existing,
            "src_id": src_id,
            "tgt_id": tgt_id,
            "src_method": src_method or _RM_UNRESOLVED,
            "tgt_method": tgt_method or _RM_UNRESOLVED,
            "conn_type": conn_type,
            "direction": direction,
            "confidence": confidence,
        }
    return {
        "kind": "create",
        "mirror_id": mid,
        "src_id": src_id,
        "tgt_id": tgt_id,
        "src_method": src_method or _RM_UNRESOLVED,
        "tgt_method": tgt_method or _RM_UNRESOLVED,
        "conn_type": conn_type,
        "direction": direction,
        "confidence": confidence,
        "raw_type": raw_type,
        "raw_dir": raw_dir,
    }


def _plan_from_coverage(row: Any, cc_id: str, candidate_grounded: dict[str, str]) -> dict[str, Any]:
    """回填计划：provenance 已覆盖的行 → 直接 grounded（region id 反查）。"""
    src_cand = str(row[1]) if row[1] else None
    tgt_cand = str(row[2]) if row[2] else None
    return {
        "kind": "grounded",
        "mirror_id": str(row[0]),
        "canonical_id": cc_id,
        "src_id": candidate_grounded.get(src_cand) if src_cand else None,
        "tgt_id": candidate_grounded.get(tgt_cand) if tgt_cand else None,
        "src_method": _RM_CANDIDATE,
        "tgt_method": _RM_CANDIDATE,
        "conn_type": None,
        "direction": None,
        "confidence": float(row[10]) if row[10] is not None else None,
    }


async def _write_grounding_rows(
    session: AsyncSession,
    plans: list[dict[str, Any]],
    *,
    created_by: str,
    created_canonical: dict[tuple[str, str, str], str],
) -> None:
    """写入一批 grounding 行；create 计划的先建 canonical_connection。"""
    for plan in plans:
        canonical_id: str | None = plan.get("canonical_id")
        if plan["kind"] == "create":
            key = (plan["src_id"], plan["tgt_id"], plan["conn_type"])
            canonical_id = created_canonical.get(key)
            if canonical_id is None:
                cc = await ccs.create_canonical_connection(
                    session,
                    CanonicalConnectionCreate(
                        source_region_id=uuid.UUID(plan["src_id"]),
                        target_region_id=uuid.UUID(plan["tgt_id"]),
                        connection_type=plan["conn_type"],
                        directionality_policy=plan["direction"],
                        confidence=plan["confidence"],
                        provenance_json=build_connection_provenance(
                            [plan["mirror_id"]],
                            [plan["raw_type"] or "unknown"],
                            [plan["confidence"]],
                            mapping_method="cn1_connection_grounding_v1",
                            endpoint_grounding={
                                "source": plan["src_method"],
                                "target": plan["tgt_method"],
                            },
                        ),
                    ),
                )
                await session.flush()
                canonical_id = str(cc.id)
                created_canonical[key] = canonical_id
        elif canonical_id is None and plan.get("_deferred_key"):
            # 批内合并计划：解析本批首个 create 创建的 canonical id
            canonical_id = created_canonical.get(plan["_deferred_key"])
        session.add(MirrorConnectionCanonicalGrounding(
            mirror_connection_id=uuid.UUID(plan["mirror_id"]),
            canonical_connection_id=uuid.UUID(canonical_id) if canonical_id else None,
            source_region_id=uuid.UUID(plan["src_id"]) if plan.get("src_id") else None,
            target_region_id=uuid.UUID(plan["tgt_id"]) if plan.get("tgt_id") else None,
            source_resolution_method=plan.get("src_method", _RM_UNRESOLVED),
            target_resolution_method=plan.get("tgt_method", _RM_UNRESOLVED),
            connection_type=plan.get("conn_type"),
            directionality_policy=plan.get("direction"),
            status="grounded" if plan["kind"] in ("grounded", "create") else "unresolved",
            unresolved_reason=plan.get("reason"),
            confidence=plan.get("confidence"),
            created_by=created_by,
        ))


async def build_connection_grounding(
    session: AsyncSession,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    dry_run: bool = False,
    created_by: str = GROUNDING_SOURCE,
    atlas_filter: str | None = None,
    cross_species_atlases: set[str] | None = None,
) -> dict[str, Any]:
    """分批构建 Mirror → Canonical grounding 表（幂等）。

    batch_size 必须落在 [500, 1000]；dry_run=True 只预测不写入。
    重跑时已有 grounding 行全部跳过，新行按同规则补建。
    atlas_filter 只处理指定 source_atlas 的行（None=全量，生产默认）；
    cross_species_atlases 覆盖默认跨物种集合（测试隔离用）。
    """
    if not (MIN_BATCH_SIZE <= batch_size <= MAX_BATCH_SIZE):
        raise ValueError(
            f"batch_size must be within [{MIN_BATCH_SIZE}, {MAX_BATCH_SIZE}], got {batch_size}"
        )

    existing = await _load_existing_grounding(session, atlas_filter=atlas_filter)
    coverage = await _load_provenance_coverage(session)
    canonical_keys = await _load_canonical_keys(session)
    candidate_grounded = await _load_candidate_grounding(session)
    name_index = await _load_name_index(session)

    created_canonical: dict[tuple[str, str, str], str] = {}
    counts = {
        "total_mirror_rows": 0,
        "already_grounded_rows": len(existing),
        "grounded": {"reused_existing_canonical": 0, "created_new_canonical": 0},
        "new_canonical_connections": 0,
        "unresolved": {
            _RR_SPECIES: 0,
            _RR_NO_NAME: 0,
            _RR_SELF_LOOP: 0,
            _RR_MAPPING: 0,
        },
        "duplicate_mirror_rows_merged": 0,
    }
    seen_canonical_keys: dict[tuple[str, str, str], int] = {}

    # keyset 分页扫描 mirror rows（可选按 source_atlas 过滤）
    last_id: uuid.UUID | None = None
    where_atlas = "WHERE source_atlas = :atlas" if atlas_filter else ""
    where_both = "WHERE source_atlas = :atlas AND id > :last_id" if atlas_filter else "WHERE id > :last_id"
    while True:
        sql = (
            f"""
            SELECT id, source_region_candidate_id, target_region_candidate_id,
                   source_region_name_cn, source_region_name_en,
                   target_region_name_cn, target_region_name_en,
                   source_atlas, connection_type, directionality, confidence
            FROM mirror_region_connections
            {where_both if last_id is not None else where_atlas}
            ORDER BY id LIMIT :limit
            """
        )
        params: dict[str, Any] = {"limit": batch_size}
        if last_id is not None:
            params["last_id"] = last_id
        if atlas_filter:
            params["atlas"] = atlas_filter
        rows = (await session.execute(text(sql), params)).all()
        if not rows:
            break

        plans: list[dict[str, Any]] = []
        # 本批内已计划 create 的 key：同批后续同 key 行降级为 grounded（引用同一 canonical）
        planned_create_keys: set[tuple[str, str, str]] = set()
        for row in rows:
            mid = str(row[0])
            counts["total_mirror_rows"] += 1
            if mid in existing:
                continue
            cc_id = coverage.get(mid)
            if cc_id:
                plan = _plan_from_coverage(row, cc_id, candidate_grounded)
            else:
                plan = _plan_row(
                    row,
                    candidate_grounded=candidate_grounded,
                    name_index=name_index,
                    canonical_keys=canonical_keys,
                    created_canonical=created_canonical,
                    cross_species_atlases=cross_species_atlases,
                )
            if plan["kind"] in ("grounded", "create"):
                key = (plan["src_id"], plan["tgt_id"], plan["conn_type"])
                if plan["kind"] == "create":
                    if key in planned_create_keys:
                        # 批内同 key 重复 → 合并引用（canonical id 写阶段解析）
                        plan["kind"] = "grounded"
                        plan["canonical_id"] = None
                        plan["_deferred_key"] = key
                        counts["grounded"]["reused_existing_canonical"] += 1
                    else:
                        planned_create_keys.add(key)
                        counts["grounded"]["created_new_canonical"] += 1
                        counts["new_canonical_connections"] += 1
                else:
                    counts["grounded"]["reused_existing_canonical"] += 1
                seen_canonical_keys[key] = seen_canonical_keys.get(key, 0) + 1
            else:
                counts["unresolved"][plan["reason"]] += 1
            plans.append(plan)

        if plans and not dry_run:
            await _write_grounding_rows(
                session, plans, created_by=created_by, created_canonical=created_canonical
            )
            await session.commit()
        for plan in plans:
            existing.add(plan["mirror_id"])
        last_id = rows[-1][0]

    counts["duplicate_mirror_rows_merged"] = sum(
        n - 1 for n in seen_canonical_keys.values() if n > 1
    )
    counts["dry_run"] = dry_run
    return counts


# --------------------------------------------------------------------------- #
# 聚合统计 / unresolved report
# --------------------------------------------------------------------------- #


async def grounding_stats(session: AsyncSession) -> dict[str, Any]:
    """从 grounding 表聚合输出（总/成功/失败/duplicate/canonical 数）。"""
    row = (
        await session.execute(
            text(
                """
                SELECT count(*) AS total,
                       count(*) FILTER (WHERE status = 'grounded') AS grounded,
                       count(*) FILTER (WHERE status = 'unresolved') AS unresolved,
                       count(DISTINCT canonical_connection_id) AS distinct_canonical,
                       count(DISTINCT source_region_id) AS distinct_source_regions,
                       count(DISTINCT target_region_id) AS distinct_target_regions
                FROM mirror_connection_canonical_grounding
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
                    SELECT unresolved_reason, count(*) FROM mirror_connection_canonical_grounding
                    WHERE status = 'unresolved' GROUP BY 1 ORDER BY 2 DESC
                    """
                )
            )
        ).all()
    }
    methods = {
        r[0]: int(r[1])
        for r in (
            await session.execute(
                text(
                    """
                    SELECT source_resolution_method, count(*) FROM mirror_connection_canonical_grounding
                    GROUP BY 1 ORDER BY 2 DESC
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
        "source_resolution_methods": methods,
        "distinct_canonical_connections": int(row["distinct_canonical"]),
        "distinct_source_regions": int(row["distinct_source_regions"]),
        "distinct_target_regions": int(row["distinct_target_regions"]),
    }


async def unresolved_report(session: AsyncSession, *, limit: int = 20) -> dict[str, Any]:
    """unresolved 明细报告：按原因分组 + 抽样（含原始名称）。"""
    rows = (
        await session.execute(
            text(
                """
                SELECT g.unresolved_reason,
                       mrc.source_region_name_cn, mrc.source_region_name_en,
                       mrc.target_region_name_cn, mrc.target_region_name_en,
                       mrc.source_atlas
                FROM mirror_connection_canonical_grounding g
                JOIN mirror_region_connections mrc ON mrc.id = g.mirror_connection_id
                WHERE g.status = 'unresolved'
                ORDER BY g.unresolved_reason, mrc.created_at DESC
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
                "source_atlas": r[5],
                "source_name": r[1] or r[2],
                "target_name": r[3] or r[4],
            }
            for r in rows
        ],
    }
