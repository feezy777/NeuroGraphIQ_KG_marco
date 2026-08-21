#!/usr/bin/env python3
"""Allen Mouse Brain Connectivity PoC 2.0 Calibration.

Validates 200 KG connections against Allen Mouse Brain Connectivity Atlas data
with enhanced metrics: pagination, experiment dedup, hierarchy grading,
tiered classification, and persistent PostgreSQL cache.

Usage:
    cd backend
    .venv/Scripts/python.exe run_allen_poc_v2.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import selectors
import statistics
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.database import AsyncSessionLocal
from app.services.allen_connectivity_v2 import (
    REQUEST_TIMEOUT,
    ExperimentData,
    ValidationResult,
    build_http_client_simple,
    get_stats,
    reset_stats,
    validate_connection,
)

_log = logging.getLogger(__name__)

REPORT_PATH = (
    Path(__file__).resolve().parents[1]
    / ".superpowers"
    / "sdd"
    / "tasks"
    / "allen-poc-v2-report.md"
)

POSITIVE_CONTROL_PAIRS: list[tuple[str, str]] = [
    ("cingulate", "caudoputamen"),
    ("cingulate", "striatum"),
    ("hippocamp", "entorhinal"),
    ("motor", "striatum"),
    ("motor", "caudoputamen"),
    ("somatosensory", "thalamus"),
    ("visual", "superior colliculus"),
    ("visual", "thalamus"),
    ("prefrontal", "striatum"),
    ("prefrontal", "caudoputamen"),
    ("amygdala", "hippocamp"),
    ("thalamus", "motor"),
    ("thalamus", "somatosensory"),
    ("barrel", "thalamus"),
    ("barrel", "somatosensory"),
]



# ── Database helpers ──────────────────────────────────────────────────────┐


async def run_migration(session: AsyncSession) -> None:
    """Create/verify v2 tables."""
    ddl_statements = [
        # Cache tables
        """CREATE TABLE IF NOT EXISTS allen_experiments_cache (
            source_allen_id INTEGER PRIMARY KEY,
            total_rows INTEGER, rows_fetched INTEGER, pagination_complete BOOLEAN,
            experiments_json JSONB NOT NULL, retrieved_at TIMESTAMPTZ DEFAULT now()
        )""",
        """CREATE TABLE IF NOT EXISTS allen_unionize_cache (
            experiment_id INTEGER PRIMARY KEY,
            total_rows INTEGER, rows_fetched INTEGER, pagination_complete BOOLEAN,
            unionize_json JSONB NOT NULL, retrieved_at TIMESTAMPTZ DEFAULT now()
        )""",
        # V2 results table
        """CREATE TABLE IF NOT EXISTS allen_connectivity_poc_v2 (
            connection_id UUID PRIMARY KEY,
            source_candidate_id UUID, target_candidate_id UUID,
            source_allen_id INTEGER, target_allen_id INTEGER,
            source_name TEXT, target_name TEXT,
            source_acronym TEXT, target_acronym TEXT,
            source_match_type TEXT,
            matched_source_id INTEGER, matched_source_name TEXT,
            source_hierarchy_distance INTEGER,
            target_match_type TEXT,
            experiment_count INTEGER, positive_experiment_count INTEGER,
            positive_ratio DOUBLE PRECISION,
            source_api_total_rows INTEGER, source_rows_fetched INTEGER,
            source_pagination_complete BOOLEAN,
            density_all_min DOUBLE PRECISION, density_all_median DOUBLE PRECISION,
            density_all_max DOUBLE PRECISION, density_all_p75 DOUBLE PRECISION,
            density_all_p90 DOUBLE PRECISION,
            density_positive_min DOUBLE PRECISION, density_positive_median DOUBLE PRECISION,
            density_positive_max DOUBLE PRECISION, density_positive_p75 DOUBLE PRECISION,
            density_positive_p90 DOUBLE PRECISION,
            energy_all_min DOUBLE PRECISION, energy_all_median DOUBLE PRECISION,
            energy_all_max DOUBLE PRECISION, energy_all_p75 DOUBLE PRECISION,
            energy_all_p90 DOUBLE PRECISION,
            energy_positive_min DOUBLE PRECISION, energy_positive_median DOUBLE PRECISION,
            energy_positive_max DOUBLE PRECISION, energy_positive_p75 DOUBLE PRECISION,
            energy_positive_p90 DOUBLE PRECISION,
            result TEXT, signal_strength TEXT, consistency TEXT,
            source_target_relation TEXT, hemisphere_match_type TEXT,
            reason TEXT, experiments_json JSONB,
            retrieved_at TIMESTAMPTZ DEFAULT now()
        )""",
    ]
    for ddl in ddl_statements:
        await session.execute(text(ddl))
    await session.commit()
    _log.info("Migration 034 applied.")


async def clear_tables(session: AsyncSession) -> None:
    """Clear previous v2 results and old cache (fresh run with new caps)."""
    await session.execute(text("DELETE FROM allen_connectivity_poc_v2"))
    await session.execute(text("DELETE FROM allen_experiments_cache"))
    await session.commit()
    _log.info("Cleared all PoC v2 tables.")


# ── Candidate mapping ─────────────────────────────────────────────────────┐


def extract_allen_id(raw_payload: dict | None) -> int | None:
    """Extract allen_id from a candidate's raw_payload JSONB."""
    if not raw_payload:
        return None
    val = raw_payload.get("allen_id")
    if val is not None:
        try:
            return int(val)
        except (TypeError, ValueError):
            return None
    return None


async def get_original_30_connection_ids(session: AsyncSession) -> list[uuid.UUID]:
    """Get the exact same 30 connection_ids from PoC 1.0."""
    result = await session.execute(
        text("SELECT connection_id FROM allen_connectivity_poc ORDER BY connection_id")
    )
    return [row[0] for row in result.fetchall()]


async def get_connection_details(
    session: AsyncSession, conn_ids: list[uuid.UUID],
) -> list[dict[str, Any]]:
    """Get full connection details for given IDs."""
    if not conn_ids:
        return []
    id_list = ",".join(f"'{cid}'" for cid in conn_ids)
    result = await session.execute(
        text(f"""
            SELECT
                mrc.id AS connection_id,
                mrc.source_region_candidate_id,
                mrc.target_region_candidate_id,
                mrc.source_region_name_en,
                mrc.target_region_name_en,
                mrc.confidence,
                src_c.raw_payload AS src_payload,
                tgt_c.raw_payload AS tgt_payload
            FROM mirror_region_connections mrc
            JOIN candidate_brain_regions src_c ON src_c.id = mrc.source_region_candidate_id
            JOIN candidate_brain_regions tgt_c ON tgt_c.id = mrc.target_region_candidate_id
            WHERE mrc.id IN ({id_list})
        """)
    )
    rows = result.fetchall()
    connections: list[dict] = []
    for row in rows:
        connections.append({
            "connection_id": row[0],
            "source_candidate_id": row[1],
            "target_candidate_id": row[2],
            "source_name_en": row[3] or "",
            "target_name_en": row[4] or "",
            "confidence": float(row[5]) if row[5] is not None else 0.0,
            "src_allen_id": extract_allen_id(row[6]),
            "tgt_allen_id": extract_allen_id(row[7]),
        })
    return connections


def match_positive_control(src_name: str | None, tgt_name: str | None) -> bool:
    """Check if connection matches a positive control pair."""
    if not src_name or not tgt_name:
        return False
    src_lower = src_name.lower()
    tgt_lower = tgt_name.lower()
    for src_pat, tgt_pat in POSITIVE_CONTROL_PAIRS:
        if src_pat in src_lower and tgt_pat in tgt_lower:
            return True
    return False


async def sample_200_connections(
    session: AsyncSession,
    original_30_ids: set[uuid.UUID],
) -> list[dict[str, Any]]:
    """Sample 200 connections from mirror_region_connections (Phase 4)."""
    # Get all eligible connections where both sides have Allen_HBA_2012 source
    all_result = await session.execute(
        text("""
            SELECT
                mrc.id, mrc.source_region_candidate_id, mrc.target_region_candidate_id,
                mrc.source_region_name_en, mrc.target_region_name_en, mrc.confidence,
                src_c.raw_payload AS src_payload, tgt_c.raw_payload AS tgt_payload
            FROM mirror_region_connections mrc
            JOIN candidate_brain_regions src_c ON src_c.id = mrc.source_region_candidate_id
            JOIN candidate_brain_regions tgt_c ON tgt_c.id = mrc.target_region_candidate_id
            WHERE src_c.source_atlas = 'Allen_HBA_2012'
              AND tgt_c.source_atlas = 'Allen_HBA_2012'
              AND src_c.raw_payload->>'allen_id' IS NOT NULL
              AND tgt_c.raw_payload->>'allen_id' IS NOT NULL
            ORDER BY RANDOM()
        """)
    )
    all_rows = all_result.fetchall()
    _log.info("Total eligible Allen→Allen connections: %d", len(all_rows))

    # Build candidates list
    all_candidates: list[dict] = []
    for row in all_rows:
        cid = row[0]
        if cid in original_30_ids:
            continue  # Exclude original 30 (they'll be processed separately)
        all_candidates.append({
            "connection_id": cid,
            "source_candidate_id": row[1],
            "target_candidate_id": row[2],
            "source_name_en": row[3] or "",
            "target_name_en": row[4] or "",
            "confidence": float(row[5]) if row[5] is not None else 0.0,
            "src_allen_id": extract_allen_id(row[6]),
            "tgt_allen_id": extract_allen_id(row[7]),
        })

    # Categorize
    pos_ctrl = [c for c in all_candidates if match_positive_control(c["source_name_en"], c["target_name_en"])]
    remaining = [c for c in all_candidates if c not in pos_ctrl]

    # Get paper evidence connections
    evidence_conn_ids: set[uuid.UUID] = set()
    if remaining:
        batch_ids = [c["connection_id"] for c in remaining[:500]]
        for bid in batch_ids:
            ev_result = await session.execute(
                text("""
                    SELECT 1 FROM mirror_evidence_records
                    WHERE evidence_target_id = :cid
                      AND evidence_target_type = 'mirror_region_connection'
                    LIMIT 1
                """),
                {"cid": bid},
            )
            if ev_result.scalar():
                evidence_conn_ids.add(bid)

    has_evidence = [c for c in remaining if c["connection_id"] in evidence_conn_ids]
    no_evidence = [c for c in remaining if c not in has_evidence]

    sampled: list[dict] = []
    used: set[uuid.UUID] = set()

    def pick(items: list[dict], count: int, label: str):
        added = 0
        for item in items:
            if added >= count:
                break
            cid = item["connection_id"]
            if cid not in used:
                item["category"] = label
                sampled.append(item)
                used.add(cid)
                added += 1
        _log.info("  %s: %d/%d", label, added, count)

    # Target distribution
    pick(pos_ctrl, min(20, len(pos_ctrl)), "positive_control")
    pick(has_evidence, min(10, len(has_evidence)), "paper_evidence")
    pick(no_evidence, 170, "random_sample")

    # Fill remaining if short
    needed = 200 - len(sampled)
    if needed > 0:
        extra_pool = [c for c in all_candidates if c["connection_id"] not in used]
        pick(extra_pool, needed, "fill")

    _log.info("Sampled %d connections total.", len(sampled))
    return sampled


async def store_result_v2(session: AsyncSession, vr: ValidationResult) -> None:
    """Store a v2 validation result."""
    stmt = text("""
        INSERT INTO allen_connectivity_poc_v2 (
            connection_id, source_candidate_id, target_candidate_id,
            source_allen_id, target_allen_id,
            source_name, target_name, source_acronym, target_acronym,
            source_match_type, matched_source_id, matched_source_name,
            source_hierarchy_distance,
            experiment_count, positive_experiment_count, positive_ratio,
            source_api_total_rows, source_rows_fetched, source_pagination_complete,
            density_all_min, density_all_median, density_all_max,
            density_all_p75, density_all_p90,
            density_positive_min, density_positive_median, density_positive_max,
            density_positive_p75, density_positive_p90,
            energy_all_min, energy_all_median, energy_all_max,
            energy_all_p75, energy_all_p90,
            energy_positive_min, energy_positive_median, energy_positive_max,
            energy_positive_p75, energy_positive_p90,
            result, signal_strength, consistency,
            source_target_relation, hemisphere_match_type,
            reason, experiments_json, retrieved_at
        ) VALUES (
            :connection_id, :source_candidate_id, :target_candidate_id,
            :source_allen_id, :target_allen_id,
            :source_name, :target_name, :source_acronym, :target_acronym,
            :source_match_type, :matched_source_id, :matched_source_name,
            :source_hierarchy_distance,
            :experiment_count, :positive_experiment_count, :positive_ratio,
            :source_api_total_rows, :source_rows_fetched, :source_pagination_complete,
            :density_all_min, :density_all_median, :density_all_max,
            :density_all_p75, :density_all_p90,
            :density_positive_min, :density_positive_median, :density_positive_max,
            :density_positive_p75, :density_positive_p90,
            :energy_all_min, :energy_all_median, :energy_all_max,
            :energy_all_p75, :energy_all_p90,
            :energy_positive_min, :energy_positive_median, :energy_positive_max,
            :energy_positive_p75, :energy_positive_p90,
            :result, :signal_strength, :consistency,
            :source_target_relation, :hemisphere_match_type,
            :reason, CAST(:experiments_json AS jsonb), :retrieved_at
        )
        ON CONFLICT (connection_id) DO UPDATE SET
            result = EXCLUDED.result, reason = EXCLUDED.reason,
            retrieved_at = EXCLUDED.retrieved_at
    """)

    # Serialize experiments
    experiments_data = []
    for exp in vr.experiments:
        experiments_data.append({
            "experiment_id": exp.experiment_id,
            "source_match_type": exp.source_match_type,
            "matched_source_id": exp.matched_source_id,
            "source_hierarchy_distance": exp.source_hierarchy_distance,
            "signal_detected": exp.signal_detected,
            "best_density": exp.best_density,
            "best_energy": exp.best_energy,
            "target_row_count": len(exp.target_rows),
            "hemisphere_ids": exp.hemisphere_ids,
        })

    await session.execute(stmt, {
        "connection_id": vr.connection_id,
        "source_candidate_id": vr.source_candidate_id,
        "target_candidate_id": vr.target_candidate_id,
        "source_allen_id": vr.source_allen_id,
        "target_allen_id": vr.target_allen_id,
        "source_name": vr.source_name,
        "target_name": vr.target_name,
        "source_acronym": vr.source_acronym,
        "target_acronym": vr.target_acronym,
        "source_match_type": vr.source_match_type,
        "matched_source_id": vr.matched_source_id,
        "matched_source_name": vr.matched_source_name,
        "source_hierarchy_distance": vr.source_hierarchy_distance,
        "experiment_count": vr.experiment_count,
        "positive_experiment_count": vr.positive_experiment_count,
        "positive_ratio": vr.positive_ratio,
        "source_api_total_rows": vr.source_api_total_rows,
        "source_rows_fetched": vr.source_rows_fetched,
        "source_pagination_complete": vr.source_pagination_complete,
        "density_all_min": vr.density_all_min,
        "density_all_median": vr.density_all_median,
        "density_all_max": vr.density_all_max,
        "density_all_p75": vr.density_all_p75,
        "density_all_p90": vr.density_all_p90,
        "density_positive_min": vr.density_positive_min,
        "density_positive_median": vr.density_positive_median,
        "density_positive_max": vr.density_positive_max,
        "density_positive_p75": vr.density_positive_p75,
        "density_positive_p90": vr.density_positive_p90,
        "energy_all_min": vr.energy_all_min,
        "energy_all_median": vr.energy_all_median,
        "energy_all_max": vr.energy_all_max,
        "energy_all_p75": vr.energy_all_p75,
        "energy_all_p90": vr.energy_all_p90,
        "energy_positive_min": vr.energy_positive_min,
        "energy_positive_median": vr.energy_positive_median,
        "energy_positive_max": vr.energy_positive_max,
        "energy_positive_p75": vr.energy_positive_p75,
        "energy_positive_p90": vr.energy_positive_p90,
        "result": vr.result,
        "signal_strength": vr.signal_strength,
        "consistency": vr.consistency,
        "source_target_relation": vr.source_target_relation,
        "hemisphere_match_type": vr.hemisphere_match_type,
        "reason": vr.reason,
        "experiments_json": json.dumps(experiments_data) if experiments_data else None,
        "retrieved_at": datetime.now(timezone.utc),
    })
    await session.commit()


# ── Report generation ─────────────────────────────────────────────────────┐


async def load_v1_results(session: AsyncSession, conn_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    """Load PoC 1.0 results for before/after comparison."""
    if not conn_ids:
        return {}
    id_list = ",".join(f"'{cid}'" for cid in conn_ids)
    result = await session.execute(
        text(f"""
            SELECT connection_id, result, experiment_count, positive_experiment_count,
                   density_median, source_match_type, source_target_hierarchy
            FROM allen_connectivity_poc
            WHERE connection_id IN ({id_list})
        """)
    )
    mapping: dict[uuid.UUID, dict] = {}
    for row in result.fetchall():
        mapping[row[0]] = {
            "v1_result": row[1],
            "v1_exp_count": row[2],
            "v1_pos_count": row[3],
            "v1_density_median": row[4],
            "v1_source_match": row[5],
            "v1_hierarchy": row[6],
        }
    return mapping


async def generate_report(
    session: AsyncSession,
    original_results: list[ValidationResult],
    new_results: list[ValidationResult],
    original_details: list[dict],
    new_details: list[dict],
) -> None:
    """Generate comprehensive PoC 2.0 report (Phase 5)."""
    stats = get_stats()
    v1_map = await load_v1_results(session, [r.connection_id for r in original_results])

    lines: list[str] = []
    lines.append("# Allen Mouse Brain Connectivity PoC 2.0 Calibration Report\n")
    lines.append(f"**Generated**: {datetime.now(timezone.utc).isoformat()}\n")
    lines.append(f"**Original 30 connections**: re-validated with PoC 2.0 pipeline")
    lines.append(f"**New connections**: {len(new_results)} validated\n")

    # API Metrics
    lines.append("## API Metrics\n")
    cache_total = max(stats["cache_hits"] + stats["db_cache_hits"] + stats["api_requests"], 1)
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| API requests | {stats['api_requests']} |")
    lines.append(f"| In-memory cache hits | {stats['cache_hits']} |")
    lines.append(f"| DB cache hits | {stats['db_cache_hits']} |")
    lines.append(f"| Total cache hit rate | {(stats['cache_hits'] + stats['db_cache_hits']) / cache_total * 100:.1f}% |\n")

    # ── Section 1: Before/After for Original 30 ──
    lines.append("## 1. Before/After: Original 30 Connections\n")
    lines.append("| # | Source | Target | V1 Result | V2 Result | V1 Exp | V2 Exp | V1 Den Med | V2 Den Med | Change |")
    lines.append("|---|--------|--------|-----------|-----------|--------|--------|------------|------------|--------|")

    classification_changes: list[str] = []
    reclassified_count = 0
    for i, vr in enumerate(original_results, 1):
        v1 = v1_map.get(vr.connection_id, {})
        src = (vr.source_name or "?")[:25]
        tgt = (vr.target_name or "?")[:25]
        v1_res = v1.get("v1_result", "?")
        v2_res = vr.result
        v1_exp = v1.get("v1_exp_count", "?")
        v2_exp = vr.experiment_count
        v1_den = f"{v1.get('v1_density_median', 0):.4f}" if v1.get("v1_density_median") else "-"
        v2_den = f"{vr.density_positive_median:.4f}" if vr.density_positive_median is not None else "-"

        change = ""
        if v1_res != v2_res:
            change = f"**{v1_res} → {v2_res}**"
            reclassified_count += 1
            classification_changes.append(
                f"  {i}. {src} → {tgt}: {v1_res} → {v2_res} ({vr.reason[:80]})"
            )

        lines.append(f"| {i} | {src} | {tgt} | {v1_res} | {v2_res} | {v1_exp} | {v2_exp} | {v1_den} | {v2_den} | {change} |")
    lines.append("")

    if classification_changes:
        lines.append(f"### Reclassification Details ({reclassified_count} changed)\n")
        for change in classification_changes:
            lines.append(change)
        lines.append("")

    # ── Section 2: Original 30 Breakdown ──
    lines.append("## 2. Original 30 Re-classification Breakdown\n")
    breakdown_v1: dict[str, int] = {}
    breakdown_v2: dict[str, int] = {}
    for vr in original_results:
        v1 = v1_map.get(vr.connection_id, {})
        v1_res = v1.get("v1_result", "unknown")
        v2_res = vr.result
        breakdown_v1[v1_res] = breakdown_v1.get(v1_res, 0) + 1
        breakdown_v2[v2_res] = breakdown_v2.get(v2_res, 0) + 1

    lines.append("| Classification | V1 Count | V2 Count |")
    lines.append("|----------------|----------|----------|")
    all_classes = sorted(set(list(breakdown_v1.keys()) + list(breakdown_v2.keys())))
    for cls in all_classes:
        lines.append(f"| {cls} | {breakdown_v1.get(cls, 0)} | {breakdown_v2.get(cls, 0)} |")
    lines.append("")

    # ── Section 3: 200 Calibration Breakdown ──
    all_200 = original_results + new_results
    lines.append(f"## 3. 200 Calibration Set Statistics (Total: {len(all_200)})\n")

    # Classification
    cls_200: dict[str, int] = {}
    for vr in all_200:
        cls_200[vr.result] = cls_200.get(vr.result, 0) + 1
    lines.append("### Classification\n")
    lines.append("| Classification | Count | % |")
    lines.append("|----------------|-------|---|")
    for cls in sorted(cls_200.keys()):
        pct = cls_200[cls] / len(all_200) * 100
        lines.append(f"| {cls} | {cls_200[cls]} | {pct:.1f}% |")
    lines.append("")

    # Signal strength distribution
    sig_200: dict[str, int] = {}
    for vr in all_200:
        if vr.signal_strength:
            sig_200[vr.signal_strength] = sig_200.get(vr.signal_strength, 0) + 1
    lines.append("### Signal Strength\n")
    lines.append("| Strength | Count |")
    lines.append("|----------|-------|")
    for sig in ["very_weak", "weak", "moderate", "strong"]:
        lines.append(f"| {sig} | {sig_200.get(sig, 0)} |")
    lines.append("")

    # Consistency
    con_200: dict[str, int] = {}
    for vr in all_200:
        if vr.consistency:
            con_200[vr.consistency] = con_200.get(vr.consistency, 0) + 1
    lines.append("### Consistency\n")
    lines.append("| Consistency | Count |")
    lines.append("|-------------|-------|")
    for con in ["single_experiment", "low_consistency", "moderate_consistency", "high_consistency"]:
        lines.append(f"| {con} | {con_200.get(con, 0)} |")
    lines.append("")

    # Source match grading
    match_200: dict[str, int] = {}
    for vr in all_200:
        match_200[vr.source_match_type] = match_200.get(vr.source_match_type, 0) + 1
    lines.append("### Source Match Distribution\n")
    lines.append("| Match Type | Count |")
    lines.append("|------------|-------|")
    for mt in sorted(match_200.keys()):
        lines.append(f"| {mt} | {match_200[mt]} |")
    lines.append("")

    # Same-structure and hierarchy relations
    hier_200: dict[str, int] = {}
    for vr in all_200:
        hier_200[vr.source_target_relation] = hier_200.get(vr.source_target_relation, 0) + 1
    lines.append("### Hierarchy Relations\n")
    lines.append("| Relation | Count |")
    lines.append("|----------|-------|")
    for rel in sorted(hier_200.keys()):
        lines.append(f"| {rel} | {hier_200[rel]} |")
    lines.append("")

    # ── Section 4: Paper Evidence Comparison ──
    lines.append("## 4. Paper Evidence Comparison\n")
    evidence_v2 = [vr for vr in all_200
                   if any(d.get("category") == "paper_evidence" for d in new_details
                          if d.get("connection_id") == vr.connection_id)]
    if evidence_v2:
        lines.append("| # | Source → Target | V2 Result | Signal | Consistency | Density (median) |")
        lines.append("|---|-----------------|-----------|--------|-------------|------------------|")
        for i, vr in enumerate(evidence_v2, 1):
            src = (vr.source_name or "?")[:25]
            tgt = (vr.target_name or "?")[:25]
            den = f"{vr.density_positive_median:.6f}" if vr.density_positive_median else "-"
            lines.append(f"| {i} | {src} → {tgt} | {vr.result} | {vr.signal_strength} | {vr.consistency} | {den} |")
    else:
        lines.append("*No connections with existing Paper Evidence in sample.*\n")
    lines.append("")

    # ── Section 5: Interesting Cases ──
    lines.append("## 5. Top 10 Interesting Cases (by positive experiment count)\n")
    interesting = sorted(
        [vr for vr in all_200 if vr.positive_experiment_count > 0],
        key=lambda x: x.positive_experiment_count, reverse=True,
    )[:10]
    for i, vr in enumerate(interesting, 1):
        lines.append(f"### {i}. {vr.source_name} → {vr.target_name}\n")
        lines.append(f"- **Result**: {vr.result} | Signal: {vr.signal_strength} | Consistency: {vr.consistency}")
        lines.append(f"- **Source**: Allen ID={vr.source_allen_id} (`{vr.source_acronym}`), Match: {vr.source_match_type} (dist={vr.source_hierarchy_distance})")
        lines.append(f"- **Target**: Allen ID={vr.target_allen_id} (`{vr.target_acronym}`)")
        lines.append(f"- **Experiments**: {vr.positive_experiment_count}/{vr.experiment_count} positive (ratio={vr.positive_ratio:.2f})")
        if vr.density_positive_median is not None:
            lines.append(f"- **Density (positive)**: min={vr.density_positive_min}, median={vr.density_positive_median:.6f}, max={vr.density_positive_max:.6f}")
        lines.append(f"- **Relation**: {vr.source_target_relation} | Hemisphere: {vr.hemisphere_match_type}")
        lines.append(f"- **Pagination**: complete={vr.source_pagination_complete}, fetched={vr.source_rows_fetched}/{vr.source_api_total_rows}")
        lines.append(f"- **Reason**: {vr.reason}")
        lines.append("")

    # ── Section 6: Recommendations ──
    lines.append("## 6. Recommendations for 64K Full Validation\n")
    lines.append("Based on the 200-connection calibration run:\n")

    # Count pagination issues
    api_incomplete_count = cls_200.get("api_incomplete", 0)
    lines.append(f"1. **Pagination**: {api_incomplete_count}/200 connections had incomplete pagination. "
                 f"Ensure all API calls use the page-looping logic from Phase 1.1.")

    # Count same_structure
    same_count = cls_200.get("same_structure_skip", 0)
    lines.append(f"2. **Same-structure filtering**: {same_count} connections were skipped as same-structure. "
                 f"Apply this filter before any Allen validation to avoid wasted API calls.")

    # Positive ratio distribution
    supported = sum(1 for vr in all_200 if vr.result in ("direct_support", "hierarchical_support", "broad_hierarchical_support"))
    not_obs = cls_200.get("atlas_not_observed", 0)
    no_data = cls_200.get("atlas_no_data", 0)
    lines.append(f"3. **Coverage**: {supported}/200 ({supported/len(all_200)*100:.1f}%) connections have Allen support "
                 f"({cls_200.get('direct_support', 0)} direct, {cls_200.get('hierarchical_support', 0)} hierarchical, "
                 f"{cls_200.get('broad_hierarchical_support', 0)} broad). "
                 f"{not_obs} not observed, {no_data} no data.")

    # Signal quality
    very_weak_count = sig_200.get("very_weak", 0)
    lines.append(f"4. **Signal quality**: {very_weak_count} connections had very_weak signal (density < 0.001). "
                 f"Consider raising the minimum density threshold for 'supported' classification.")

    lines.append(f"5. **DB cache effectiveness**: {stats['db_cache_hits']} DB cache hits saved API calls. "
                 f"The persistent cache is critical for the 64K run.")

    lines.append("6. **Concurrency control**: The 200-connection run used sequential processing. "
                 "For 64K, group connections by source structure and use async semaphore with concurrency ~5-10.")

    lines.append("7. **Cost estimation**: At ~{:.0f} API calls for 200 connections, ".format(stats["api_requests"]) +
                 f"64K connections would require ~{stats['api_requests'] * 320:.0f} API calls. "
                 f"With caching by source structure (reuse injection data), "
                 f"actual calls should be significantly lower.")

    # Write
    content = "\n".join(lines) + "\n"
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(content, encoding="utf-8")
    _log.info("Report written to %s", REPORT_PATH)


# ── Progress tracking ─────────────────────────────────────────────────────┐


class ProgressTracker:
    """Track and display progress for long-running validation."""

    def __init__(self, total: int):
        self.total = total
        self.current = 0
        self.results: dict[str, int] = {}
        self.errors = 0

    def update(self, vr: ValidationResult | None, is_error: bool = False):
        self.current += 1
        if is_error:
            self.errors += 1
        if vr:
            self.results[vr.result] = self.results.get(vr.result, 0) + 1

    def summary(self) -> str:
        parts = [f"{self.current}/{self.total}"]
        for cls, count in sorted(self.results.items()):
            parts.append(f"{cls}={count}")
        if self.errors:
            parts.append(f"errors={self.errors}")
        return " | ".join(parts)


# ── Main ──────────────────────────────────────────────────────────────────┐


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    _log.info("=== Allen Mouse Brain Connectivity PoC 2.0 Calibration ===")

    if AsyncSessionLocal is None:
        _log.error("AsyncSessionLocal is None — cannot connect to database")
        return

    reset_stats()

    async with AsyncSessionLocal() as session:
        # Phase 3: Run migration (creates cache + v2 tables)
        _log.info("Phase 3: Running migration...")
        await run_migration(session)

        # Clear v2 results (preserve cache)
        await clear_tables(session)

        # Phase 4 Step 1: Re-run original 30
        _log.info("Phase 4 Step 1: Re-running original 30 connections...")
        original_30_ids = await get_original_30_connection_ids(session)
        _log.info("Found %d original connection IDs.", len(original_30_ids))

        if not original_30_ids:
            _log.error("No original PoC results found — need to run run_allen_poc.py first")
            return

        original_details = await get_connection_details(session, original_30_ids)
        _log.info("Retrieved details for %d connections.", len(original_details))

        progress = ProgressTracker(len(original_details))
        original_results: list[ValidationResult] = []

        async with build_http_client_simple() as client:
            for i, conn in enumerate(original_details):
                _log.info("[%d/%d] %s → %s",
                          i + 1, len(original_details),
                          conn["source_name_en"][:40],
                          conn["target_name_en"][:40])
                try:
                    vr = await validate_connection(
                        client,
                        connection_id=conn["connection_id"],
                        source_candidate_id=conn["source_candidate_id"],
                        target_candidate_id=conn["target_candidate_id"],
                        source_allen_id=conn["src_allen_id"],
                        target_allen_id=conn["tgt_allen_id"],
                        source_name=conn["source_name_en"],
                        target_name=conn["target_name_en"],
                        session=session,
                    )
                except Exception as exc:
                    _log.error("Failed: %s", exc)
                    vr = ValidationResult(
                        connection_id=conn["connection_id"],
                        source_allen_id=conn["src_allen_id"],
                        target_allen_id=conn["tgt_allen_id"],
                        source_name=conn["source_name_en"],
                        target_name=conn["target_name_en"],
                        result="atlas_mapping_uncertain",
                        reason=f"Validation error: {exc}",
                    )
                    progress.update(None, is_error=True)
                else:
                    progress.update(vr)

                original_results.append(vr)
                await store_result_v2(session, vr)
                _log.info("  → %s [%s] (exp=%d, pos=%d)",
                          vr.result, progress.summary(),
                          vr.experiment_count, vr.positive_experiment_count)
                await asyncio.sleep(0.05)

        _log.info("Original 30 complete. Results: %s", progress.summary())

        # Phase 4 Step 2: Sample and validate 170 new connections
        _log.info("Phase 4 Step 2: Sampling 200 new connections...")
        original_ids_set = {c["connection_id"] for c in original_details}
        new_details = await sample_200_connections(session, original_ids_set)
        # Limit to 170 to stay within 200 total
        new_details = new_details[:170]
        _log.info("Sampled %d new connections.", len(new_details))

        new_results: list[ValidationResult] = []
        progress2 = ProgressTracker(len(new_details) + len(original_details))

        async with build_http_client_simple() as client:
            for i, conn in enumerate(new_details):
                total_done = len(original_details) + i + 1
                _log.info("[%d/%d] %s → %s",
                          total_done, len(original_details) + len(new_details),
                          conn["source_name_en"][:40],
                          conn["target_name_en"][:40])
                try:
                    vr = await validate_connection(
                        client,
                        connection_id=conn["connection_id"],
                        source_candidate_id=conn["source_candidate_id"],
                        target_candidate_id=conn["target_candidate_id"],
                        source_allen_id=conn["src_allen_id"],
                        target_allen_id=conn["tgt_allen_id"],
                        source_name=conn["source_name_en"],
                        target_name=conn["target_name_en"],
                        session=session,
                    )
                except Exception as exc:
                    _log.error("Failed: %s", exc)
                    vr = ValidationResult(
                        connection_id=conn["connection_id"],
                        source_allen_id=conn["src_allen_id"],
                        target_allen_id=conn["tgt_allen_id"],
                        source_name=conn["source_name_en"],
                        target_name=conn["target_name_en"],
                        result="atlas_mapping_uncertain",
                        reason=f"Validation error: {exc}",
                    )
                    progress2.update(None, is_error=True)
                else:
                    progress2.update(vr)

                new_results.append(vr)
                await store_result_v2(session, vr)
                _log.info("  → %s [%s] (exp=%d, pos=%d)",
                          vr.result, progress2.summary(),
                          vr.experiment_count, vr.positive_experiment_count)
                await asyncio.sleep(0.05)

        # Phase 5: Generate report
        _log.info("Phase 5: Generating report...")
        await generate_report(session, original_results, new_results,
                              original_details, new_details)

    # Print final summary
    stats = get_stats()
    all_results = original_results + new_results

    print("\n" + "=" * 70)
    print("  Allen Mouse Brain Connectivity PoC 2.0 — Complete")
    print("=" * 70)
    print(f"  Total connections validated: {len(all_results)}")
    print(f"  Original 30: {len(original_results)}")
    print(f"  New: {len(new_results)}")
    print()
    print(f"  Classification breakdown:")
    cls_breakdown: dict[str, int] = {}
    for vr in all_results:
        cls_breakdown[vr.result] = cls_breakdown.get(vr.result, 0) + 1
    for cls, count in sorted(cls_breakdown.items()):
        print(f"    {cls}: {count}")
    print()
    print(f"  API requests: {stats['api_requests']}")
    print(f"  In-memory cache hits: {stats['cache_hits']}")
    print(f"  DB cache hits: {stats['db_cache_hits']}")
    print(f"  Report: {REPORT_PATH}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
