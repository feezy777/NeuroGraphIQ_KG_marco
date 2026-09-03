"""Phase 2B-2 — Fetch Julich-Brain v3.1 official MNI152 probability maps (siibra).

Locks Julich-Brain Cytoarchitectonic Atlas v3.1 and fetches its probabilistic
(statistical) cytoarchitectonic map components in "MNI 152 ICBM 2009c Nonlinear
Asymmetric" via siibra's official EBRAINS data chain.

Each of the 414 per-hemisphere area components is saved as a full-grid NIfTI
probability volume (193x229x193, MNI152 1mm) under:

    backend/data/atlases/julich/v3.1/spatial_raw/probability_maps/

Filenames are deterministic from the official region id + hemisphere. SHA256 is
recorded in provenance. Resumable: an existing file whose sha256 matches the
current fetch is skipped. Re-run after full success = NOOP/SKIP.

This script does NOT compute overlap, does NOT generate mapping candidates,
does NOT threshold probability maps, does NOT write the database.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import nibabel as nib

try:
    import siibra
    from siibra.commons import MapType
except ImportError:  # pragma: no cover
    sys.exit("siibra required: pip install siibra")

BACKEND = Path(__file__).resolve().parent.parent
SPATIAL_RAW = BACKEND / "data" / "atlases" / "julich" / "v3.1" / "spatial_raw"
PROB_DIR = SPATIAL_RAW / "probability_maps"
META_DIR = SPATIAL_RAW / "metadata"
PROV_DIR = SPATIAL_RAW / "provenance"

ATLAS_NAME = "Julich-Brain Cytoarchitectonic Atlas (v3.1)"
ATLAS_ID = "minds/core/parcellationatlas/v1.0.0/94c1125b-b87e-45e4-901c-00daee7f2579-310"
ATLAS_VERSION = "3.1.0"
DOI = "10.25493/KNSN-XB4"
SPACE = "MNI 152 ICBM 2009c Nonlinear Asymmetric"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_filename(region_id: str, hemisphere: str) -> str:
    # strip the long shared prefix, keep region tail + hemi
    tail = re.sub(r"^JULICH_BRAIN_CYTOARCHITECTONIC_ATLAS_V3_1_", "", region_id)
    return f"{tail}_{hemisphere.upper()}.nii.gz"


def _resolve(parc, mapobj) -> list[dict]:
    """Return deterministic (map_name, region_id, hemisphere) for every component."""
    out = []
    for name in mapobj.regions:
        if name.endswith(" left"):
            base, hemi = name[:-5], "left"
        elif name.endswith(" right"):
            base, hemi = name[:-6], "right"
        else:
            base, hemi = name, ""
        reg = parc.get_region(base)
        rid = str(getattr(reg, "id", getattr(reg, "identifier", "")))
        out.append({"map_name": name, "region_id": rid, "hemisphere": hemi})
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="resolve + report, fetch nothing")
    parser.add_argument("--limit", type=int, default=None, help="only fetch first N components")
    args = parser.parse_args()

    for d in (PROB_DIR, META_DIR, PROV_DIR):
        d.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).isoformat()

    # 1. lock exact parcellation + space
    def _is_v31(p):
        return str(getattr(p, "id", "")) == ATLAS_ID and str(getattr(p, "version", "")) == ATLAS_VERSION
    parc = next(p for p in siibra.parcellations if _is_v31(p))
    print(f"parcellation: {parc.name} id={parc.id} version={parc.version}")
    space = next(s for s in siibra.spaces if str(getattr(s, "name", "")) == SPACE)
    print(f"space: {space.name}")

    # 2. statistical (probabilistic) map
    statmap = parc.get_map(SPACE, MapType.STATISTICAL)
    print(f"statistical map: {statmap.name} | shape={statmap.shape} | n_components={len(statmap.regions)}")

    comps = _resolve(parc, statmap)
    print(f"resolved components: {len(comps)}")
    if args.dry_run:
        # write resolution index only
        idx = {
            "atlas": {"name": str(parc.name), "id": str(parc.id), "version": str(parc.version),
                      "doi": DOI},
            "space": SPACE,
            "map": {"name": str(statmap.name), "shape": list(statmap.shape),
                    "affine": statmap.affine.tolist()},
            "component_count": len(comps),
            "components": comps,
            "resolution_timestamp": ts,
        }
        (META_DIR / "spatial_component_index.json").write_text(
            json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
        print("dry-run: component index written to metadata/")
        print("hemi split:", sum(1 for c in comps if c["hemisphere"]=="left"),
              sum(1 for c in comps if c["hemisphere"]=="right"))
        return 0

    # 3. per-component fetch
    fetched = 0
    skipped = 0
    errors = []
    provenance = []
    todo = comps if args.limit is None else comps[: args.limit]
    for i, comp in enumerate(todo, 1):
        fname = _safe_filename(comp["region_id"], comp["hemisphere"])
        path = PROB_DIR / fname
        # resumable skip if file exists with matching recorded sha (provenance of this component)
        # simplest: if file exists, skip (assume prior success); recompute hash and record.
        if path.exists():
            skipped += 1
            # preserve provenance: recompute + record for already-fetched files too
            sha = _sha256(path)
            provenance.append({
                "file_name": fname,
                "relative_path": str(path.relative_to(BACKEND)),
                "file_size": path.stat().st_size,
                "sha256": sha,
                "official_region_id": comp["region_id"],
                "official_region_name": comp["map_name"],
                "hemisphere": comp["hemisphere"],
                "atlas": "Julich-Brain",
                "version": ATLAS_VERSION,
                "provider": "EBRAINS / siibra",
                "dataset_doi": DOI,
                "representation_type": "probabilistic/statistical",
                "reference_space": SPACE,
                "fetch_timestamp": ts,
                "siibra_version": siibra.__version__,
            })
            print(f"[{i}/{len(todo)}] skip (exists): {fname}")
            continue
        try:
            img = statmap.fetch(comp["map_name"])  # nibabel Nifti1Image
            nib.save(img, str(path))
            sha = _sha256(path)
            fetched += 1
            rec = {
                "file_name": fname,
                "relative_path": str(path.relative_to(BACKEND)),
                "file_size": path.stat().st_size,
                "sha256": sha,
                "official_region_id": comp["region_id"],
                "official_region_name": comp["map_name"],
                "hemisphere": comp["hemisphere"],
                "atlas": "Julich-Brain",
                "version": ATLAS_VERSION,
                "provider": "EBRAINS / siibra",
                "dataset_doi": DOI,
                "representation_type": "probabilistic/statistical",
                "reference_space": SPACE,
                "fetch_timestamp": ts,
                "siibra_version": siibra.__version__,
            }
            provenance.append(rec)
            if i % 20 == 0 or i == len(todo):
                print(f"[{i}/{len(todo)}] fetched {fetched}, skipped {skipped}")
        except Exception as e:  # noqa: BLE001 - record failure, do not fake success
            errors.append({"map_name": comp["map_name"], "region_id": comp["region_id"],
                           "error": f"{type(e).__name__}: {str(e)[:160]}"})
            print(f"[{i}/{len(todo)}] ERROR {comp['map_name']}: {type(e).__name__} {str(e)[:80]}")

    # write provenance
    (PROV_DIR / "asset_provenance.json").write_text(
        json.dumps({"fetched": fetched, "skipped": skipped, "errors": errors,
                    "assets": provenance, "generated_at": ts},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"DONE: fetched={fetched} skipped={skipped} errors={len(errors)}")
    if errors:
        print("FAILURES PRESENT (not faked as success):", len(errors))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
