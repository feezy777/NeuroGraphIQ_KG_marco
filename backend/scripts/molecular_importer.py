"""Molecular importer (idempotent) — GTEx v10 brain expression → registry + alignments.

Molecular entities are NEVER BrainRegions: genes go to
molecular_entity_registry (ng:mol:* codes) and align to canonical regions via
region_molecular_alignment (evidence_type='expression').

Run from backend/:
    .venv/Scripts/python.exe scripts/molecular_importer.py

Data:
- data/atlases/gtex/gene_median_tpm_v10.gct.gz — GTEx v10
  GTEx_Analysis_v10_RNASeQCv2.4.2_gene_median_tpm.gct.gz (official release,
  adult-gtex storage bucket). One median-TPM column per tissue; 13 brain tissues.
- Top-10 expressed genes (by median TPM) per brain tissue become molecular
  entities; each gets a region_molecular_alignment to the matching canonical
  region. Tissues without a clear 1:1 canonical region (hypothalamus, spinal
  cord, substantia nigra) are reported as unaligned — not fabricated.
- Allen HBA: the existing molecular_attr family (allen_hba_expression) is kept
  as-is per BR3; its demo alignments already carry source 'Allen HBA expression'.
"""

from __future__ import annotations

import asyncio
import gzip
import heapq
import re
import selectors
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.canonical_region import CanonicalBrainRegion
from app.models.multiscale import MolecularEntityRegistry, RegionMolecularAlignment

GCT_PATH = BACKEND_DIR / "data" / "atlases" / "gtex" / "gene_median_tpm_v10.gct.gz"
TOP_N = 10

# GTEx brain column -> canonical region (None = documented as unaligned)
TISSUE_REGION: dict[str, str | None] = {
    "Brain_Amygdala": "ng:br:amygdala",
    "Brain_Anterior_cingulate_cortex_BA24": "ng:br:rostral_anterior_cingulate",
    "Brain_Caudate_basal_ganglia": "ng:br:caudate",
    "Brain_Cerebellar_Hemisphere": "ng:br:cerebellum",
    "Brain_Cerebellum": "ng:br:cerebellum",
    "Brain_Cortex": "ng:br:cerebrum",
    "Brain_Frontal_Cortex_BA9": "ng:br:dlpfc",
    "Brain_Hippocampus": "ng:br:hippocampus",
    "Brain_Hypothalamus": None,
    "Brain_Nucleus_accumbens_basal_ganglia": "ng:br:accumbens_area",
    "Brain_Putamen_basal_ganglia": "ng:br:putamen",
    "Brain_Spinal_cord_cervical_c-1": None,
    "Brain_Substantia_nigra": None,
}

_CODE_RE = re.compile(r"[^a-z0-9]+")


def normalize_code(symbol: str) -> str:
    return _CODE_RE.sub("_", symbol.lower()).strip("_")


def parse_gct(path: Path) -> dict[str, list[tuple[float, str, str]]]:
    """Returns {tissue: top-N [(median_tpm, symbol, gene_id), ...]}."""
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        handle.readline()  # version
        handle.readline()  # dims
        headers = handle.readline().rstrip("\n").split("\t")
        brain_idx = {i: c for i, c in enumerate(headers) if c in TISSUE_REGION}
        # accumulator: per tissue list of all (tpm, symbol, gene_id) — 59k genes × 13, fine in memory
        accum: dict[str, list[tuple[float, str, str]]] = {c: [] for c in brain_idx.values()}
        for line in handle:
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 3:
                continue
            gene_id, symbol = fields[0], fields[1].strip()
            if not symbol:
                continue
            for i, tissue in brain_idx.items():
                if i >= len(fields):
                    continue
                try:
                    tpm = float(fields[i])
                except ValueError:
                    continue
                if tpm > 0:
                    accum[tissue].append((tpm, symbol, gene_id))
    return {t: heapq.nlargest(TOP_N, rows) for t, rows in accum.items()}


async def _region_by_code(session, code: str) -> CanonicalBrainRegion | None:
    return (
        await session.execute(
            select(CanonicalBrainRegion).where(CanonicalBrainRegion.region_code == code)
        )
    ).scalar_one_or_none()


async def import_expression(session) -> dict[str, int]:
    stats = {"entities_created": 0, "alignments_created": 0, "unaligned_genes": 0}
    cache: dict[str, int] = {}
    top_by_tissue = parse_gct(GCT_PATH)

    for tissue, rows in top_by_tissue.items():
        region_code = TISSUE_REGION[tissue]
        if region_code is None:
            stats["unaligned_genes"] += len(rows)
            print(f"  unaligned (no canonical): {tissue} ({len(rows)} genes)")
            continue
        region = await _region_by_code(session, region_code)
        if region is None:
            print(f"  !! canonical missing: {region_code} (tissue {tissue}) — skipped")
            continue

        for rank, (tpm, symbol, gene_id) in enumerate(rows, start=1):
            code = f"ng:mol:{normalize_code(symbol)}"
            entity_id = cache.get(code)
            if entity_id is None:
                existing = (
                    await session.execute(
                        select(MolecularEntityRegistry).where(
                            MolecularEntityRegistry.entity_code == code
                        )
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    entity_id = existing.id
                else:
                    row = MolecularEntityRegistry(
                        entity_code=code,
                        entity_type="gene",
                        canonical_name_en=symbol,
                        canonical_name_cn=None,
                        external_iri=None,  # GTEx file carries symbols, not HGNC ids
                        species="human",
                        description=(
                            f"{symbol} — top-{TOP_N} expressed gene in {tissue} "
                            "(GTEx v10 median TPM)."
                        ),
                        provenance={
                            "importer": "molecular_importer",
                            "gene_id": gene_id,
                            "note": "HGNC id not present in the GTEx release file",
                        },
                    )
                    session.add(row)
                    await session.flush()
                    entity_id = row.id
                    stats["entities_created"] += 1
                cache[code] = entity_id

            dup = (
                await session.execute(
                    select(RegionMolecularAlignment).where(
                        RegionMolecularAlignment.region_id == region.id,
                        RegionMolecularAlignment.molecular_entity_id == entity_id,
                        RegionMolecularAlignment.evidence_type == "expression",
                    )
                )
            ).scalar_one_or_none()
            if dup is not None:
                continue
            session.add(
                RegionMolecularAlignment(
                    region_id=region.id,
                    molecular_entity_id=entity_id,
                    entity_type="gene",
                    evidence_type="expression",
                    confidence=0.9,
                    source="GTEx v10 brain tissue median TPM",
                    provenance={
                        "importer": "molecular_importer",
                        "tissue": tissue,
                        "median_tpm": round(tpm, 2),
                        "rank": rank,
                    },
                )
            )
            stats["alignments_created"] += 1
    return stats


async def main() -> None:
    if not GCT_PATH.exists():
        print(f"ERROR: GTEx data file missing: {GCT_PATH}")
        raise SystemExit(1)
    async with AsyncSessionLocal() as session:
        stats = await import_expression(session)
        await session.commit()
    print("MOLECULAR IMPORT RESULT")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print("OK")


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
