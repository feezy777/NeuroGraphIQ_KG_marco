#!/usr/bin/env python3
"""Allen Mouse Brain Connectivity Reverse Validation PoC.

Validates ~30 KG connections against Allen Mouse Brain Connectivity Atlas data.

Usage:
    cd backend
    .venv/Scripts/python.exe run_allen_poc.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
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

# Ensure backend/ is on path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.database import AsyncSessionLocal
from app.services.allen_connectivity import (
    build_http_client,
    find_injection_experiments,
    get_all_projections_for_experiments,
    get_projections_to_target,
    get_structures,
    get_stats,
    reset_stats,
)

_log = logging.getLogger(__name__)

REPORT_PATH = Path(__file__).resolve().parents[1] / ".superpowers" / "sdd" / "tasks" / "allen-poc-report.md"

# Well-known mouse brain projection pairs (source_name_en contains → target_name_en contains)
# These are canonical projections from the literature
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


def match_positive_control(
    src_name: str | None, tgt_name: str | None
) -> bool:
    """Check if a connection's source/target names match a positive control pair."""
    if not src_name or not tgt_name:
        return False
    src_lower = src_name.lower()
    tgt_lower = tgt_name.lower()
    for src_pat, tgt_pat in POSITIVE_CONTROL_PAIRS:
        if src_pat in src_lower and tgt_pat in tgt_lower:
            return True
    return False


def determine_hierarchy(
    source_struct: dict, target_struct: dict
) -> tuple[str, dict | None]:
    """Determine hierarchy relation between source and target structures.

    Returns (relation_type, info_dict)
    relation_type: same_structure | source_parent_of_target | target_parent_of_source |
                   source_descendant_of_target | target_descendant_of_source |
                   sibling | unrelated
    """
    src_id = source_struct.get("id")
    tgt_id = target_struct.get("id")
    src_path = source_struct.get("structure_id_path", "")
    tgt_path = target_struct.get("structure_id_path", "")

    if src_id == tgt_id:
        return "same_structure", {"src_id": src_id, "tgt_id": tgt_id}

    # Convert paths to lists of ints
    src_ids = [int(x) for x in str(src_path).split("/") if x]
    tgt_ids = [int(x) for x in str(tgt_path).split("/") if x]

    if src_id in tgt_ids:
        return "target_parent_of_source", {
            "src_id": src_id, "tgt_id": tgt_id,
            "src_path": src_path, "tgt_path": tgt_path,
        }
    if tgt_id in src_ids:
        return "source_parent_of_target", {
            "src_id": src_id, "tgt_id": tgt_id,
            "src_path": src_path, "tgt_path": tgt_path,
        }

    # Check for common ancestry (sibling check)
    common_parent = None
    for pid in reversed(src_ids):
        if pid in tgt_ids:
            common_parent = pid
            break

    if common_parent:
        return "sibling", {
            "src_id": src_id, "tgt_id": tgt_id,
            "common_parent_id": common_parent,
        }

    return "unrelated", {"src_id": src_id, "tgt_id": tgt_id}


async def create_table(session: AsyncSession) -> None:
    """Create allen_connectivity_poc table if not exists."""
    ddl = text("""
        CREATE TABLE IF NOT EXISTS allen_connectivity_poc (
            connection_id UUID,
            source_candidate_id UUID, target_candidate_id UUID,
            source_allen_id INTEGER, target_allen_id INTEGER,
            source_name TEXT, target_name TEXT,
            source_acronym TEXT, target_acronym TEXT,
            source_match_type TEXT,
            experiment_count INTEGER, positive_experiment_count INTEGER,
            density_min DOUBLE PRECISION, density_median DOUBLE PRECISION, density_max DOUBLE PRECISION,
            energy_min DOUBLE PRECISION, energy_median DOUBLE PRECISION, energy_max DOUBLE PRECISION,
            result TEXT, reason TEXT,
            source_target_hierarchy TEXT,
            hemisphere_info JSONB,
            experiments_json JSONB,
            retrieved_at TIMESTAMPTZ DEFAULT now(),
            PRIMARY KEY (connection_id)
        );
    """)
    await session.execute(ddl)
    await session.commit()
    _log.info("Table allen_connectivity_poc created/verified.")


async def clear_table(session: AsyncSession) -> None:
    """Clear all previous PoC results."""
    await session.execute(text("DELETE FROM allen_connectivity_poc"))
    await session.commit()
    _log.info("Cleared previous PoC results.")


async def get_allen_candidate_map(session: AsyncSession) -> dict[uuid.UUID, int]:
    """Build mapping: candidate_brain_regions.id -> allen_id from raw_payload."""
    result = await session.execute(
        text("""
            SELECT id, raw_payload
            FROM candidate_brain_regions
            WHERE source_atlas = 'Allen_HBA_2012'
              AND raw_payload->>'allen_id' IS NOT NULL
        """)
    )
    rows = result.fetchall()
    mapping: dict[uuid.UUID, int] = {}
    for row in rows:
        cid = row[0]
        aid = extract_allen_id(row[1])
        if aid is not None:
            mapping[cid] = aid
    _log.info("Built allen_id mapping for %d candidates.", len(mapping))
    return mapping


async def sample_connections(
    session: AsyncSession,
    allen_map: dict[uuid.UUID, int],
) -> list[dict[str, Any]]:
    """Sample 30 connections from mirror_region_connections.

    Categories:
    - 10 high confidence (>0.5)
    - 10 low confidence (<0.3)
    - 5 with existing Paper Evidence
    - 5 positive controls (well-known projections)
    """
    # Get all connections where both source and target have allen_ids
    all_conns_result = await session.execute(
        text("""
            SELECT
                mrc.id AS connection_id,
                mrc.source_region_candidate_id,
                mrc.target_region_candidate_id,
                mrc.source_region_name_en,
                mrc.target_region_name_en,
                mrc.confidence,
                mrc.mirror_status,
                src_c.raw_payload AS src_payload,
                tgt_c.raw_payload AS tgt_payload,
                src_c.en_name AS src_en_name,
                tgt_c.en_name AS tgt_en_name
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
    all_conns = all_conns_result.fetchall()

    _log.info("Total Allen→Allen connections available: %d", len(all_conns))

    if not all_conns:
        _log.warning("No connections found with valid Allen IDs on both sides. "
                     "Checking for connections with at least one side...")
        all_conns_result = await session.execute(
            text("""
                SELECT
                    mrc.id AS connection_id,
                    mrc.source_region_candidate_id,
                    mrc.target_region_candidate_id,
                    mrc.source_region_name_en,
                    mrc.target_region_name_en,
                    mrc.confidence,
                    mrc.mirror_status,
                    src_c.raw_payload AS src_payload,
                    tgt_c.raw_payload AS tgt_payload,
                    src_c.en_name AS src_en_name,
                    tgt_c.en_name AS tgt_en_name
                FROM mirror_region_connections mrc
                JOIN candidate_brain_regions src_c ON src_c.id = mrc.source_region_candidate_id
                JOIN candidate_brain_regions tgt_c ON tgt_c.id = mrc.target_region_candidate_id
                WHERE src_c.source_atlas = 'Allen_HBA_2012'
                  AND tgt_c.source_atlas = 'Allen_HBA_2012'
                ORDER BY RANDOM()
            """)
        )
        all_conns = all_conns_result.fetchall()
        _log.info("Total Allen→Allen connections (with or without allen_id): %d", len(all_conns))

    # Build candidates
    candidates: list[dict] = []
    for row in all_conns:
        src_name = (row[3] or row[9] or "")
        tgt_name = (row[4] or row[10] or "")
        candidates.append({
            "connection_id": row[0],
            "source_candidate_id": row[1],
            "target_candidate_id": row[2],
            "source_name_en": src_name,
            "target_name_en": tgt_name,
            "confidence": float(row[5]) if row[5] is not None else 0.0,
            "mirror_status": row[6],
            "src_allen_id": extract_allen_id(row[7]),
            "tgt_allen_id": extract_allen_id(row[8]),
        })

    # Categorize
    high_conf = [c for c in candidates if c["confidence"] > 0.5]
    low_conf = [c for c in candidates if c["confidence"] < 0.3]
    pos_ctrl = [c for c in candidates if match_positive_control(c["source_name_en"], c["target_name_en"])]

    # Find connections with existing paper evidence
    conn_ids = [c["connection_id"] for c in candidates]
    evidence_conns = []
    if conn_ids:
        # Check in batches for evidence records
        for conn_id in conn_ids[:500]:  # Limit random check
            evidence_result = await session.execute(
                text("""
                    SELECT 1 FROM mirror_evidence_records
                    WHERE evidence_target_id = :cid
                      AND evidence_target_type = 'mirror_region_connection'
                    LIMIT 1
                """),
                {"cid": conn_id},
            )
            if evidence_result.scalar():
                evidence_conns.append(conn_id)

    has_evidence = [c for c in candidates if c["connection_id"] in evidence_conns]

    sampled: list[dict] = []
    used_ids: set = set()

    def add_unique(items: list[dict], count: int, label: str):
        nonlocal sampled
        added = 0
        for item in items:
            if added >= count:
                break
            cid = item["connection_id"]
            if cid not in used_ids:
                item["category"] = label
                sampled.append(item)
                used_ids.add(cid)
                added += 1
        _log.info("Added %d/%d from category '%s'", added, count, label)
        return added

    add_unique(high_conf, 10, "high_confidence")
    add_unique(low_conf, 10, "low_confidence")
    add_unique(has_evidence, 5, "has_paper_evidence")
    add_unique(pos_ctrl, 5, "positive_control")

    # If any category is short, pad with random connections
    total_needed = 30
    if len(sampled) < total_needed:
        remaining = [c for c in candidates if c["connection_id"] not in used_ids]
        add_unique(remaining, total_needed - len(sampled), "random_fill")

    _log.info("Sampled %d connections total.", len(sampled))
    for s in sampled:
        _log.info("  [%s] %s -> %s (conf=%.2f, src_id=%s, tgt_id=%s)",
                  s["category"], s["source_name_en"][:40],
                  s["target_name_en"][:40], s["confidence"],
                  s["src_allen_id"], s["tgt_allen_id"])

    return sampled


async def validate_one_connection(
    client: httpx.AsyncClient,
    conn: dict[str, Any],
    struct_cache_global: dict[int, dict],
) -> dict[str, Any]:
    """Run the Allen pipeline for one connection."""
    src_aid = conn["src_allen_id"]
    tgt_aid = conn["tgt_allen_id"]
    result: dict[str, Any] = {
        "connection_id": conn["connection_id"],
        "source_candidate_id": conn["source_candidate_id"],
        "target_candidate_id": conn["target_candidate_id"],
        "source_allen_id": src_aid,
        "target_allen_id": tgt_aid,
        "source_name": conn["source_name_en"],
        "target_name": conn["target_name_en"],
        "source_acronym": "",
        "target_acronym": "",
        "source_match_type": "unknown",
        "experiment_count": 0,
        "positive_experiment_count": 0,
        "density_min": None,
        "density_median": None,
        "density_max": None,
        "energy_min": None,
        "energy_median": None,
        "energy_max": None,
        "result": "atlas_no_data",
        "reason": "",
        "source_target_hierarchy": "",
        "hemisphere_info": None,
        "experiments_json": None,
    }

    # Resolve structure metadata for source and target
    ids_to_fetch = [aid for aid in (src_aid, tgt_aid) if aid is not None]
    if not ids_to_fetch:
        result["result"] = "atlas_mapping_uncertain"
        result["reason"] = "No Allen IDs available for source or target"
        return result

    try:
        structures = await get_structures(client, ids_to_fetch)
    except Exception as exc:
        result["result"] = "atlas_mapping_uncertain"
        result["reason"] = f"Failed to fetch structure metadata: {exc}"
        return result

    src_struct = structures.get(src_aid, {}) if src_aid else {}
    tgt_struct = structures.get(tgt_aid, {}) if tgt_aid else {}

    result["source_name"] = src_struct.get("name") or conn["source_name_en"] or f"id:{src_aid}"
    result["target_name"] = tgt_struct.get("name") or conn["target_name_en"] or f"id:{tgt_aid}"
    result["source_acronym"] = src_struct.get("acronym", "")
    result["target_acronym"] = tgt_struct.get("acronym", "")

    # Get injection experiments for source — walk up hierarchy if needed
    if src_aid is None:
        result["result"] = "atlas_mapping_uncertain"
        result["reason"] = "Source candidate has no Allen ID"
        return result

    try:
        sds_ids, match_type, matched_src_id = await find_injection_experiments(
            client, src_aid
        )
    except Exception as exc:
        result["result"] = "atlas_mapping_uncertain"
        result["reason"] = f"Failed to fetch injection experiments: {exc}"
        return result

    result["source_match_type"] = match_type
    result["experiment_count"] = len(sds_ids)

    if not sds_ids:
        result["result"] = "atlas_no_data"
        result["reason"] = (
            f"No injection experiments found for source structure {src_aid} "
            f"({result['source_name']}) or any ancestor in hierarchy"
        )
        return result

    # Get projections to target structure from these SectionDataSets
    try:
        target_projections = await get_projections_to_target(
            client, sds_ids, tgt_aid if tgt_aid else 0
        )
    except Exception as exc:
        result["result"] = "atlas_mapping_uncertain"
        result["reason"] = f"Failed to fetch projection data: {exc}"
        return result

    # Aggregate metrics — group by experiment
    densities = []
    energies = []
    positive_exp_ids: set[int] = set()
    for proj in target_projections:
        density = proj.get("projection_density")
        energy = proj.get("projection_energy")
        eid = proj.get("section_data_set_id")
        if density is not None:
            densities.append(float(density))
        if energy is not None:
            energies.append(float(energy))
        if eid is not None:
            positive_exp_ids.add(int(eid))

    result["positive_experiment_count"] = len(positive_exp_ids)

    if densities:
        result["density_min"] = min(densities)
        result["density_median"] = statistics.median(densities)
        result["density_max"] = max(densities)
    if energies:
        result["energy_min"] = min(energies)
        result["energy_median"] = statistics.median(energies)
        result["energy_max"] = max(energies)

    # Determine hierarchy
    if src_struct and tgt_struct:
        hierarchy, hier_info = determine_hierarchy(src_struct, tgt_struct)
        result["source_target_hierarchy"] = hierarchy
    else:
        result["source_target_hierarchy"] = "unknown"

    # Extract hemisphere info
    if tgt_struct:
        result["hemisphere_info"] = {
            "hemisphere_id": tgt_struct.get("hemisphere_id"),
            "graph_order": tgt_struct.get("graph_order"),
            "structure_id_path": tgt_struct.get("structure_id_path"),
        }

    # Store experiment summary
    result["experiments_json"] = {
        "total_section_datasets": len(sds_ids),
        "target_projection_rows": len(target_projections),
        "positive_experiment_ids": len(positive_exp_ids),
        "source_match_type": result["source_match_type"],
        "matched_structure_id": matched_src_id,
        "source_structure_id": src_aid,
    }

    # Classification
    hierarchy = result["source_target_hierarchy"]
    if hierarchy == "same_structure" and result["positive_experiment_count"] == 0:
        result["result"] = "atlas_mapping_uncertain"
        result["reason"] = "Source and target are same structure -- self-connection validation not applicable"
    elif result["positive_experiment_count"] == 0:
        result["result"] = "atlas_not_observed"
        result["reason"] = (
            f"{len(sds_ids)} injection experiments in {result['source_name']} "
            f"(matched at {match_type}, struct_id={matched_src_id}), "
            f"no projection signal found for {result['target_name']} (structure_id={tgt_aid})"
        )
    elif result["positive_experiment_count"] > 0:
        # Compare distinct experiments with projection vs total
        if result["positive_experiment_count"] < len(sds_ids) and len(sds_ids) > 1:
            result["result"] = "atlas_supported_candidate"
            result["reason"] = (
                f"{result['positive_experiment_count']}/{len(sds_ids)} experiments show projection "
                f"from {result['source_name']} (matched={match_type}, struct_id={matched_src_id}) "
                f"to {result['target_name']} "
                f"(density median={result['density_median']}, total projection rows={len(target_projections)})"
            )
        else:
            result["result"] = "atlas_supported_candidate"
            result["reason"] = (
                f"{result['positive_experiment_count']}/{len(sds_ids)} experiments show projection "
                f"from {result['source_name']} (matched={match_type}, struct_id={matched_src_id}) "
                f"to {result['target_name']} "
                f"(density median={result['density_median']}, total projection rows={len(target_projections)})"
            )

    if hierarchy in ("source_parent_of_target", "target_parent_of_source"):
        result["reason"] += f" | Hierarchy note: {hierarchy}"

    return result


async def store_result(session: AsyncSession, result: dict[str, Any]) -> None:
    """Insert or update a single PoC result."""
    stmt = text("""
        INSERT INTO allen_connectivity_poc (
            connection_id, source_candidate_id, target_candidate_id,
            source_allen_id, target_allen_id,
            source_name, target_name,
            source_acronym, target_acronym,
            source_match_type,
            experiment_count, positive_experiment_count,
            density_min, density_median, density_max,
            energy_min, energy_median, energy_max,
            result, reason,
            source_target_hierarchy,
            hemisphere_info,
            experiments_json,
            retrieved_at
        ) VALUES (
            :connection_id, :source_candidate_id, :target_candidate_id,
            :source_allen_id, :target_allen_id,
            :source_name, :target_name,
            :source_acronym, :target_acronym,
            :source_match_type,
            :experiment_count, :positive_experiment_count,
            :density_min, :density_median, :density_max,
            :energy_min, :energy_median, :energy_max,
            :result, :reason,
            :source_target_hierarchy,
            CAST(:hemisphere_info AS jsonb),
            CAST(:experiments_json AS jsonb),
            :retrieved_at
        )
        ON CONFLICT (connection_id) DO UPDATE SET
            source_allen_id = EXCLUDED.source_allen_id,
            target_allen_id = EXCLUDED.target_allen_id,
            source_name = EXCLUDED.source_name,
            target_name = EXCLUDED.target_name,
            source_acronym = EXCLUDED.source_acronym,
            target_acronym = EXCLUDED.target_acronym,
            source_match_type = EXCLUDED.source_match_type,
            experiment_count = EXCLUDED.experiment_count,
            positive_experiment_count = EXCLUDED.positive_experiment_count,
            density_min = EXCLUDED.density_min,
            density_median = EXCLUDED.density_median,
            density_max = EXCLUDED.density_max,
            energy_min = EXCLUDED.energy_min,
            energy_median = EXCLUDED.energy_median,
            energy_max = EXCLUDED.energy_max,
            result = EXCLUDED.result,
            reason = EXCLUDED.reason,
            source_target_hierarchy = EXCLUDED.source_target_hierarchy,
            hemisphere_info = EXCLUDED.hemisphere_info,
            experiments_json = EXCLUDED.experiments_json,
            retrieved_at = EXCLUDED.retrieved_at
    """)
    await session.execute(
        stmt,
        {
            "connection_id": result["connection_id"],
            "source_candidate_id": result["source_candidate_id"],
            "target_candidate_id": result["target_candidate_id"],
            "source_allen_id": result["source_allen_id"],
            "target_allen_id": result["target_allen_id"],
            "source_name": result["source_name"],
            "target_name": result["target_name"],
            "source_acronym": result["source_acronym"],
            "target_acronym": result["target_acronym"],
            "source_match_type": result["source_match_type"],
            "experiment_count": result["experiment_count"],
            "positive_experiment_count": result["positive_experiment_count"],
            "density_min": result["density_min"],
            "density_median": result["density_median"],
            "density_max": result["density_max"],
            "energy_min": result["energy_min"],
            "energy_median": result["energy_median"],
            "energy_max": result["energy_max"],
            "result": result["result"],
            "reason": result["reason"],
            "source_target_hierarchy": result["source_target_hierarchy"],
            "hemisphere_info": json.dumps(result["hemisphere_info"]) if result["hemisphere_info"] else None,
            "experiments_json": json.dumps(result["experiments_json"]) if result["experiments_json"] else None,
            "retrieved_at": datetime.now(timezone.utc),
        },
    )
    await session.commit()


async def generate_report(session: AsyncSession, sampled: list[dict], results: list[dict]) -> None:
    """Generate the PoC report markdown file."""
    stats = get_stats()
    breakdown: dict[str, int] = {}
    for r in results:
        key = r["result"]
        breakdown[key] = breakdown.get(key, 0) + 1

    conf_breakdown: dict[str, dict[str, int]] = {}
    for r, c in zip(results, sampled):
        cat = c.get("category", "unknown")
        if cat not in conf_breakdown:
            conf_breakdown[cat] = {}
        key = r["result"]
        conf_breakdown[cat][key] = conf_breakdown[cat].get(key, 0) + 1

    lines: list[str] = []
    lines.append("# Allen Mouse Brain Connectivity Reverse Validation PoC Report\n")
    lines.append(f"**Generated**: {datetime.now(timezone.utc).isoformat()}\n")
    lines.append(f"**Connections processed**: {len(results)}\n")

    # API metrics
    lines.append("## API Metrics\n")
    lines.append(f"- **Total API requests**: {stats['api_requests']}")
    lines.append(f"- **Cache hits**: {stats['cache_hits']}")
    lines.append(f"- **Cache hit rate**: {stats['cache_hits'] / max(stats['cache_hits'] + stats['api_requests'], 1) * 100:.1f}%\n")

    # Summary table
    lines.append("## Summary Table\n")
    lines.append("| # | Source | Target | Result | Experiments | Density (median) | Category |")
    lines.append("|---|--------|--------|--------|-------------|------------------|----------|")
    for i, (r, c) in enumerate(zip(results, sampled), 1):
        src_name = (r["source_name"] or "N/A")[:30]
        tgt_name = (r["target_name"] or "N/A")[:30]
        result_str = r["result"]
        exp_count = r["experiment_count"]
        density = f"{r['density_median']:.4f}" if r["density_median"] is not None else "-"
        category = c.get("category", "-")
        lines.append(f"| {i} | {src_name} | {tgt_name} | {result_str} | {exp_count} | {density} | {category} |")
    lines.append("")

    # Breakdown by classification
    lines.append("## Classification Breakdown\n")
    lines.append("| Classification | Count |")
    lines.append("|----------------|-------|")
    for key in ["atlas_supported_candidate", "atlas_not_observed", "atlas_no_data",
                "atlas_mapping_uncertain", "atlas_conflicting_experiments"]:
        count = breakdown.get(key, 0)
        lines.append(f"| {key} | {count} |")
    lines.append("")

    # Breakdown by original confidence level
    lines.append("## Breakdown by Original Category\n")
    lines.append("| Category | Total | Supported | Not Observed | No Data | Uncertain | Conflicting |")
    lines.append("|----------|-------|-----------|-------------|---------|-----------|-------------|")
    for cat in ["high_confidence", "low_confidence", "has_paper_evidence", "positive_control", "random_fill"]:
        cb = conf_breakdown.get(cat, {})
        total = sum(cb.values())
        if total == 0:
            continue
        lines.append(
            f"| {cat} | {total} | "
            f"{cb.get('atlas_supported_candidate', 0)} | "
            f"{cb.get('atlas_not_observed', 0)} | "
            f"{cb.get('atlas_no_data', 0)} | "
            f"{cb.get('atlas_mapping_uncertain', 0)} | "
            f"{cb.get('atlas_conflicting_experiments', 0)} |"
        )
    lines.append("")

    # Interesting cases (top 5 by most experiments with projection signal)
    lines.append("## 5 Interesting Cases\n")
    interesting = sorted(
        [r for r in results if r["positive_experiment_count"] is not None and r["positive_experiment_count"] > 0],
        key=lambda x: x["positive_experiment_count"],
        reverse=True,
    )[:5]

    if not interesting:
        # Fallback: show any supported or conflicting
        interesting = [r for r in results if r["result"] in ("atlas_supported_candidate", "atlas_conflicting_experiments")][:5]

    for i, r in enumerate(interesting, 1):
        lines.append(f"### Case {i}: {r['source_name']} -> {r['target_name']}\n")
        lines.append(f"- **Result**: {r['result']}")
        lines.append(f"- **Source**: {r['source_name']} (Allen ID: {r['source_allen_id']}, `{r['source_acronym']}`)")
        lines.append(f"- **Target**: {r['target_name']} (Allen ID: {r['target_allen_id']}, `{r['target_acronym']}`)")
        lines.append(f"- **Experiments**: {r['experiment_count']} total, {r['positive_experiment_count']} with projection signal")
        if r["density_median"] is not None:
            lines.append(f"- **Density**: min={r['density_min']}, median={r['density_median']}, max={r['density_max']}")
        if r["energy_median"] is not None:
            lines.append(f"- **Energy**: min={r['energy_min']}, median={r['energy_median']}, max={r['energy_max']}")
        lines.append(f"- **Hierarchy**: {r['source_target_hierarchy']}")
        lines.append(f"- **Match Type**: {r['source_match_type']}")
        lines.append(f"- **Reason**: {r['reason']}")
        lines.append("")

    # Paper Evidence comparison
    lines.append("## Paper Evidence Comparison\n")
    paper_ev = [c for c in sampled if c.get("category") == "has_paper_evidence"]
    if paper_ev:
        lines.append(f"| # | Source → Target | Paper Evidence | Allen Result |")
        lines.append(f"|---|-----------------|---------------|-------------|")
        for i, c in enumerate(paper_ev, 1):
            r = next((r for r in results if r["connection_id"] == c["connection_id"]), None)
            src = (c["source_name_en"] or "?")[:25]
            tgt = (c["target_name_en"] or "?")[:25]
            allen_result = r["result"] if r else "?"
            lines.append(f"| {i} | {src} → {tgt} | (existing evidence) | {allen_result} |")
    else:
        lines.append("No connections with existing Paper Evidence were found in the sample.\n")

    # Recommendations
    lines.append("## Recommendations for 64K Full Validation\n")
    lines.append("1. **Caching strategy**: The module-level cache works well for a single run. "
                 "For 64K connections, consider a persistent cache (Redis or SQLite) to avoid redundant API calls.")
    lines.append("2. **Rate limiting**: Allen API has rate limits. The current retry logic handles 429s, "
                 "but for 64K connections, concurrency control (semaphore) and backpressure are needed.")
    lines.append("3. **Structure hierarchy resolution**: Many connections may be between parent/child structures "
                 "in the Allen ontology. Add logic to aggregate projection signal at the appropriate hierarchy level.")
    lines.append("4. **Batch processing**: Group connections by source structure to minimize API calls "
                 "(injection experiments only need to be queried once per source).")
    lines.append("5. **Mapping quality**: The `source_match_type` field already tracks whether the injection "
                 "is exactly primary or at a descendant level. This helps filter low-quality mappings.")
    lines.append("6. **Signal thresholds**: Consider adding minimum density/energy thresholds for 'supported' "
                 "classification (e.g., density > 0.01). Currently any non-zero signal counts.")
    lines.append("7. **Hemisphere awareness**: Allen projections are hemisphere-specific. "
                 "Connections between left and right sides should account for this.")

    content = "\n".join(lines) + "\n"
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(content, encoding="utf-8")
    _log.info("Report written to %s", REPORT_PATH)


async def main() -> None:
    """Main entry point for the PoC."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    _log.info("=== Allen Mouse Brain Connectivity PoC ===")

    if AsyncSessionLocal is None:
        _log.error("AsyncSessionLocal is None — cannot connect to database")
        return

    reset_stats()

    async with AsyncSessionLocal() as session:
        # Step 0: Create table
        await create_table(session)
        await clear_table(session)

        # Step 1: Build allen_id map
        allen_map = await get_allen_candidate_map(session)

        # Step 2: Sample 30 connections
        sampled = await sample_connections(session, allen_map)
        if not sampled:
            _log.error("No connections sampled — cannot continue")
            return

        # Step 3: Run pipeline
        results: list[dict] = []
        async with await build_http_client() as client:
            for i, conn in enumerate(sampled):
                _log.info("Processing %d/%d: %s -> %s",
                          i + 1, len(sampled),
                          conn.get("source_name_en", "?")[:40],
                          conn.get("target_name_en", "?")[:40])
                try:
                    result = await validate_one_connection(client, conn, {})
                except Exception as exc:
                    _log.error("Failed to validate connection %s: %s", conn["connection_id"], exc)
                    result = {
                        "connection_id": conn["connection_id"],
                        "source_candidate_id": conn["source_candidate_id"],
                        "target_candidate_id": conn["target_candidate_id"],
                        "source_allen_id": conn["src_allen_id"],
                        "target_allen_id": conn["tgt_allen_id"],
                        "source_name": conn.get("source_name_en", ""),
                        "target_name": conn.get("target_name_en", ""),
                        "source_acronym": "",
                        "target_acronym": "",
                        "source_match_type": "unknown",
                        "experiment_count": 0,
                        "positive_experiment_count": 0,
                        "density_min": None,
                        "density_median": None,
                        "density_max": None,
                        "energy_min": None,
                        "energy_median": None,
                        "energy_max": None,
                        "result": "atlas_mapping_uncertain",
                        "reason": f"Validation error: {exc}",
                        "source_target_hierarchy": "unknown",
                        "hemisphere_info": None,
                        "experiments_json": None,
                    }
                results.append(result)
                await store_result(session, result)

                # Brief pause between connections to respect rate limits
                await asyncio.sleep(0.3)

        # Step 4: Generate report
        await generate_report(session, sampled, results)

    # Print summary
    stats = get_stats()
    breakdown: dict[str, int] = {}
    for r in results:
        key = r["result"]
        breakdown[key] = breakdown.get(key, 0) + 1

    print("\n" + "=" * 60)
    print("  Allen Mouse Brain Connectivity PoC — Complete")
    print("=" * 60)
    print(f"  Connections processed: {len(results)}")
    print(f"  Classification breakdown:")
    for key, count in sorted(breakdown.items()):
        print(f"    {key}: {count}")
    print(f"  API requests: {stats['api_requests']}")
    print(f"  Cache hits: {stats['cache_hits']}")
    print(f"  Report: {REPORT_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
