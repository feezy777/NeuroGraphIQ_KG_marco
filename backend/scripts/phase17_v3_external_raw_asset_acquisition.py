"""Phase1.7 V3 - External Raw G1 geometry asset acquisition audit (READ-ONLY freeze).

This round actually downloads / locates the already-selected external authoritative
G1 geometry raw assets under backend/data/atlases/external_raw/, then freezes for
each asset: provenance, atlas/version, DOI, license, download source, sha256, real
NIfTI header (shape/spacing/affine/orientation/qform/sform/datatype/min-max/
nonzero voxels), and its coordinate relation to the Julich MNI152NLin2009cAsym
reference (193x229x193, 1 mm).

No geometry construction, no label merge, no threshold/binarize, no resampling,
no registration, no surface->volume bridge, no overlap, no reclassification,
no promotion, no DB writes, no commit.

Statuses:
  PENDING_EXTERNAL      -> not yet fetched (license/access gated)
  RAW_ASSET_ACQUIRED    -> bytes present on disk (immutable), sha256 recorded
  RAW_ASSET_VERIFIED    -> sha256 + real header + provenance + license all frozen
  SUBJECT_SPECIFIC_ONLY -> aseg (never a group gold-standard)

coordinate_relation_to_julich:
  EXACT_GRID_MATCH | SAME_TEMPLATE_DIFFERENT_GRID | SYMMETRIC_VS_ASYMMETRIC_TEMPLATE
  | RESAMPLING_REQUIRED | NONLINEAR_TEMPLATE_TRANSFORM_REQUIRED | SPACE_PROVENANCE_INCOMPLETE
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import nibabel as nib
import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
RAW = BACKEND / "data" / "atlases" / "external_raw"
OUTCSV = D16 / "phase17_v3_external_raw_asset_acquisition.csv"
OUTJSON = D16 / "phase17_v3_external_raw_asset_summary.json"
OUTMD = D16 / "phase17_v3_external_raw_asset_diagnostics.md"
JULICH_REF = (BACKEND / "data" / "atlases" / "julich" / "v3.1" / "spatial_raw"
              / "probability_maps" / "AREA_44_IFG_LEFT.nii.gz")

# --------------------------------------------------------------------------
# asset registry
# --------------------------------------------------------------------------
# key: asset_id; fields documented at commit time in manifest; downloads done
# this round are real HTTP fetches; access-restricted ones are metadata-only.
A = dict(
    # ---- P0 FreeSurfer ICBM 2009c (SYMMETRIC) group probability atlases ----
    FS_SUBFIELD_HIPPO=dict(structure="Hippocampus",
        source="surfer.nmr.mgh.harvard.edu/fswiki/SubfieldAtlasesICBMspace",
        publication="Iglesias et al. 2015 NeuroImage (hippocampal subfields)",
        doi="10.1016/j.neuroimage.2015.03.035",
        license="FS license (research; attribution required)",
        redistribution="LOCAL_USE_ONLY",
        license_status="LICENSE_VERIFIED_LOCAL_USE_ONLY",
        space="ICBM152 2009c SYMMETRIC (MNI-ICBM152 2009c sym; 0.25 mm)",
        template_variant="2009cSym (not Asym)", kind="prob",
        files=["freesurfer_icbm2009c/hippocampus/HippoAmygProbs.MNIsymSpace.left.nii.gz",
               "freesurfer_icbm2009c/hippocampus/HippoAmygProbs.MNIsymSpace.right.nii.gz"]),
    FS_AMYG_NUCLEI=dict(structure="Amygdala",
        source="surfer.nmr.mgh.harvard.edu/fswiki/SubfieldAtlasesICBMspace",
        publication="Saygin/Kliemann et al. 2017 NeuroImage (amygdala nuclei)",
        doi="10.1016/j.neuroimage.2016.10.046",
        license="FS license (research; attribution required)",
        redistribution="LOCAL_USE_ONLY",
        license_status="LICENSE_VERIFIED_LOCAL_USE_ONLY",
        space="ICBM152 2009c SYMMETRIC (0.25 mm)",
        template_variant="2009cSym (not Asym)", kind="prob",
        files=["freesurfer_icbm2009c/hippocampus/HippoAmygProbs.MNIsymSpace.left.nii.gz",
               "freesurfer_icbm2009c/hippocampus/HippoAmygProbs.MNIsymSpace.right.nii.gz"]),
    FS_THAL_ICBM=dict(structure="Thalamus",
        source="surfer.nmr.mgh.harvard.edu/fswiki/SubfieldAtlasesICBMspace",
        publication="Iglesias et al. 2018 NeuroImage (thalamic nuclei)",
        doi="10.1016/j.neuroimage.2018.08.012",
        license="FS license (research; attribution required)",
        redistribution="LOCAL_USE_ONLY",
        license_status="LICENSE_VERIFIED_LOCAL_USE_ONLY",
        space="ICBM152 2009c SYMMETRIC (0.5 mm)",
        template_variant="2009cSym (not Asym)", kind="prob",
        files=["freesurfer_icbm2009c/thalamus/ThalamusProbs.MNIsymSpace.nii.gz"]),
    # ---- P0 CIT168 NAC ----
    CIT168_NAcc=dict(structure="Nucleus Accumbens",
        source="OSF node jkzwp / CIT168_Reinf_Learn_v1.1.0 / MNI152-Nonlin-Asym-2009c",
        publication="Pauli, Nili & Tyszka 2018 Sci Data 5:180063",
        doi="10.1038/sdata.2018.63",
        license="MIT License, Copyright (c) 2017 California Institute of Technology "
                "(LICENSE.md in jmtyszka/CIT168-SubCorticalAtlas@master; OSF node jkzwp)",
        redistribution="REDISTRIBUTABLE",
        license_status="LICENSE_VERIFIED_REDISTRIBUTABLE",
        space="MNI152NLin2009cAsym res01 (author transform; EXACT vs Julich grid)",
        template_variant="2009cAsym", kind="prob+dseg",
        files=["cit168/CIT168toMNI152-2009c_det.nii.gz",
               "cit168/CIT168toMNI152-2009c_prob.nii.gz",
               "cit168/CIT168toMNI152-NLin6Asym_det.nii.gz"]),
    # ---- P1 Basal Forebrain (Zaborszky) ----
    BF_ZABORSZKY_CH1234=dict(structure="Basal Forebrain",
        source="JuBrain / AnatomyToolbox (EBRAINS) - not downloaded (access gated)",
        publication="Zaborszky et al. 2008 NeuroImage 42(3):1127-1141",
        doi="10.1016/j.neuroimage.2008.05.055",
        license="EBRAINS AnatomyToolbox terms; academic; redistribution unclear",
        redistribution="TO_VERIFY",
        license_status="ACCESS_RESTRICTED",
        space="MNI152 (variant verify); no binary this round",
        template_variant="UNKNOWN", kind="prob",
        files=[]),
    # ---- P1 BST Blackford (PRIMARY whole-BNST) ----
    BST_BLACKFORD_WHOLE=dict(structure="BST (whole BNST)",
        source="NeuroVault collection 2017 / image 39103 (Blackford lab)",
        publication="Theiss, Ridgewell, McHugo, Heckers & Blackford 2017 NeuroImage",
        doi="10.1016/j.neuroimage.2016.11.047",
        license="NeuroVault CC0 1.0 (public domain)",
        redistribution="REDISTRIBUTABLE",
        license_status="LICENSE_VERIFIED_REDISTRIBUTABLE",
        space="MNI152 (FSL 6th-gen grid 182x218x182; NOT 2009c)",
        template_variant="MNI152NLin6 (grid, not 2009c)", kind="prob",
        files=["bnst/blackford/Blackford_BNST_3T.nii.gz"]),
    # ---- P1 BST Sibbach (secondary) ----
    BST_SIBBACH_DV=dict(structure="BST (dBNST/vBNST)",
        source="Sibbach et al. 2024 BSF 229:273-283 - data availability not public URL located",
        publication="Sibbach et al. 2024 Brain Struct Funct",
        doi="10.1007/s00429-023-02713-z",
        license="paper data availability unclear; no repo URL found",
        redistribution="TO_VERIFY",
        license_status="LICENSE_UNCLEAR",
        space="MNI (7T); metadata only",
        template_variant="UNKNOWN", kind="prob",
        files=[]),
    # ---- P1 BST Brandstetter (cyto secondary) ----
    BST_CYTO_10BRAIN=dict(structure="BST (BSTC/D/M/P cyto)",
        source="Brandstetter et al. 2026 Imaging Neuroscience (Juelich) - HBM/EBRAINS gated",
        publication="Brandstetter et al. 2026 Imaging Neuroscience",
        doi="10.1162/IMAG.a.1260",
        license="open (EBRAINS/HBM terms); record gated this round",
        redistribution="TO_VERIFY",
        license_status="ACCESS_RESTRICTED",
        space="Colin-27 / ICBM-152 (not 2009cAsym); metadata only",
        template_variant="Colin27/ICBM152", kind="prob",
        files=[]),
    # aseg is never a group standard
    FS_ASEG_SUBJECT=dict(structure="Accumbens/Amygdala/Hippocampus/Thalamus",
        source="FreeSurfer aseg subject segmentation",
        publication="Fischl et al. 2002 Neuron",
        doi="10.1016/S0896-6273(02)00569-X",
        license="FS license",
        redistribution="LOCAL_USE_ONLY",
        license_status="SUBJECT_SPECIFIC_ONLY",
        space="subject native",
        template_variant="subject", kind="segmentation",
        files=[]),
)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def julich_ref():
    im = nib.load(JULICH_REF)
    h = im.header
    d = np.asanyarray(im.dataobj)
    return dict(
        shape=list(im.shape), zooms=[float(x) for x in h.get_zooms()],
        affine=[float(x) for x in im.affine.ravel()],
        qform=[float(x) for x in h.get_qform().ravel()],
        sform=[float(x) for x in h.get_sform().ravel()],
        qform_code=int(h["qform_code"]), sform_code=int(h["sform_code"]),
        orientation="".join(nib.aff2axcodes(im.affine)),
        affine_summary="tpl-MNI152NLin2009cAsym res01 (193x229x193, 1mm, origin -96/-132/-78)",
    )


def inspect(p: Path):
    """Real-header read of one raw NIfTI volume. Probability files may be 4-D;
    report full array extrema/nonzero and the time-axis shape."""
    im = nib.load(p)
    h = im.header
    d = np.asanyarray(im.dataobj)
    lo, hi = float(np.nanmin(d)), float(np.nanmax(d))
    return dict(
        local_path=str(p.relative_to(BACKEND)),
        shape=[int(x) for x in im.shape],
        zooms=[float(x) for x in h.get_zooms()],
        affine=[float(x) for x in im.affine.ravel()],
        qform=[float(x) for x in h.get_qform().ravel()],
        sform=[float(x) for x in h.get_sform().ravel()],
        qform_code=int(h["qform_code"]), sform_code=int(h["sform_code"]),
        orientation="".join(nib.aff2axcodes(im.affine)),
        datatype=int(h["datatype"]), dtype=str(d.dtype),
        value_range=[round(lo, 6), round(hi, 6)],
        nonzero=int(np.count_nonzero(np.isfinite(d) & (d != 0))),
        affine_summary=_affine_summary(im.affine),
    )


def _affine_summary(aff):
    a = np.asarray(aff, float)
    t = a[:3, 3]
    z = np.sqrt((a[:3, :3] ** 2).sum(axis=0))
    return "translate=(%.1f,%.1f,%.1f) zoom=(%.4f,%.4f,%.4f)" % (
        t[0], t[1], t[2], z[0], z[1], z[2])


def coordinate_relation(j, insp, declared_sym):
    """Header-driven (not name-driven) relation of one asset volume to Julich ref.

    Rules (measured header only):
      * EXACT: spatial shape == Julich [193,229,193], 1mm zoom, affine grid equal.
      * 182x218x182 @1mm is the MNI152 6th-gen/FSL 1mm grid (NLin6 / avg152) -
        physically NOT the 2009c grid -> a nonlinear template transform is needed
        to reach MNI152NLin2009cAsym.  (Determined by measured shape, not label.)
      * Fine-grid (0.25/0.5 mm) maps on the 2009c SYMMETRIC template ->
        SYMMETRIC_VS_ASYMMETRIC_TEMPLATE vs Julich 2009cAsym.
    """
    sh3 = insp["shape"][:3]
    z3 = insp["zooms"][:3]
    if sh3 == list(j["shape"][:3]) and all(abs(a - 1.0) < 1e-6 for a in z3) \
            and _same_grid(insp["affine"], j["affine"]):
        return "EXACT_GRID_MATCH"
    if sh3 == [182, 218, 182] and all(abs(a - 1.0) < 1e-6 for a in z3):
        return "NONLINEAR_TEMPLATE_TRANSFORM_REQUIRED"
    if declared_sym:
        return "SYMMETRIC_VS_ASYMMETRIC_TEMPLATE"
    return "RESAMPLING_REQUIRED"


def _same_grid(a, b, tol=1e-3):
    return all(abs(x - y) < tol for x, y in zip(a, b))


def _load_prior_checksums():
    """Load the frozen per-file checksums from the last run, if present."""
    if not OUTJSON.exists():
        return {}
    try:
        return {rel: m["sha256"] for rel, m in json.loads(OUTJSON.read_text(encoding="utf-8")).get("files", {}).items()}
    except Exception:
        return {}


def main():
    ref = julich_ref()
    prior = _load_prior_checksums()
    mismatches = []
    rows = []
    per_asset = {}
    for asset_id, meta in A.items():
        files = meta.get("files") or []
        if not files:
            status = ("SUBJECT_SPECIFIC_ONLY" if asset_id == "FS_ASEG_SUBJECT"
                      else "PENDING_EXTERNAL")
            rows.append(dict(asset_id=asset_id, structure=meta["structure"],
                             source_status=meta["license_status"],
                             download_status="NOT_ACQUIRED",
                             license_status=meta["license_status"],
                             redistribution_allowed=meta["redistribution"],
                             file_count=0, sha256="", local_path="", file_size=0,
                             coordinate_space=meta["space"], template_variant=meta["template_variant"],
                             shape="", spacing="", orientation="", affine_summary="",
                             qform="", sform="",
                             value_range="", nonzero_voxels="", coordinate_relation_to_julich="",
                             resampling_required="", transform_required="",
                             probabilistic_or_discrete=meta.get("kind", ""),
                             raw_asset_verified="FALSE", notes=meta.get("note", "")))
            per_asset[asset_id] = status
            continue
        lic = meta["license_status"]
        allok = True
        file_rows = []
        for rel in files:
            p = RAW / rel
            if not p.exists():
                allok = False
                file_rows.append(dict(asset_id=asset_id, structure=meta["structure"],
                                      file=rel, present="MISSING", sha256="", file_size=0,
                                      download_status="FAIL_RAW_ASSET_MISSING",
                                      coord="SPACE_PROVENANCE_INCOMPLETE"))
                continue
            fsz = p.stat().st_size
            s = sha256(p)
            # immutable freeze check FIRST: bytes must match the previously frozen checksum
            if rel in prior and prior[rel] != s:
                mismatches.append((asset_id, rel, prior[rel], s))
                file_rows.append(dict(asset_id=asset_id, structure=meta["structure"], file=rel,
                                      present="YES", sha256=s, file_size=fsz,
                                      download_status="FAIL_RAW_ASSET_CHANGED", coord="",
                                      insp={}))
                per_asset[asset_id] = "FAIL_RAW_ASSET_CHANGED"
                continue
            try:
                insp = inspect(p)
                ok = True
            except Exception as e:  # corrupt/unreadable but present -> fail, never verify
                file_rows.append(dict(asset_id=asset_id, structure=meta["structure"], file=rel,
                                      present="YES", sha256=s, file_size=fsz,
                                      download_status="FAIL_RAW_ASSET_UNREADABLE", coord="",
                                      insp={}, err=str(e)[:120]))
                per_asset[asset_id] = "FAIL_RAW_ASSET_UNREADABLE"
                allok = False
                continue
            relc = coordinate_relation(ref, insp, "Sym" in meta["template_variant"])
            download_status = "RAW_ASSET_VERIFIED" if lic != "LICENSE_UNCLEAR" and lic != "ACCESS_RESTRICTED" \
                else "RAW_ASSET_ACQUIRED"
            file_rows.append(dict(asset_id=asset_id, structure=meta["structure"], file=rel,
                                  present="YES", sha256=s, file_size=fsz,
                                  download_status=download_status, coord=relc,
                                  insp=insp))
            per_asset[asset_id] = download_status
        # aggregate one summary row per asset
        present = [f for f in file_rows if f.get("present") == "YES"]
        failed_kinds = {f.get("download_status") for f in file_rows
                        if str(f.get("download_status", "")).startswith("FAIL")}
        if failed_kinds:
            status = sorted(failed_kinds)[0]  # e.g. FAIL_RAW_ASSET_CHANGED
        elif present and len(present) == len(file_rows) and allok:
            if lic in ("LICENSE_VERIFIED_REDISTRIBUTABLE", "LICENSE_VERIFIED_ATTRIBUTION_REQUIRED",
                       "LICENSE_VERIFIED_LOCAL_USE_ONLY"):
                status = "RAW_ASSET_VERIFIED"
            else:
                status = "RAW_ASSET_ACQUIRED"
        else:
            status = "RAW_ASSET_PARTIAL"
        per_asset[asset_id] = status
        coords = [f["coord"] for f in present]
        # relation flags relative to Julich 2009cAsym grid
        exact = any(c == "EXACT_GRID_MATCH" for c in coords)
        sym_vs_asym = any(c == "SYMMETRIC_VS_ASYMMETRIC_TEMPLATE" for c in coords)
        nonlinear = any(c == "NONLINEAR_TEMPLATE_TRANSFORM_REQUIRED" for c in coords)
        rows.append(dict(asset_id=asset_id, structure=meta["structure"],
                         source_status=meta["license_status"],
                         download_status=status,
                         license_status=meta["license_status"],
                         redistribution_allowed=meta["redistribution"],
                         file_count=len(file_rows),
                         sha256=(present[0]["sha256"] if present else ""),
                         local_path="; ".join(f["file"] for f in file_rows if f.get("present") == "YES"),
                         file_size=sum(f["file_size"] for f in file_rows),
                         coordinate_space=meta["space"], template_variant=meta["template_variant"],
                         shape="; ".join(str(f["insp"]["shape"]) for f in present if f.get("insp")),
                         spacing="; ".join(str(f["insp"]["zooms"][:3]) for f in present if f.get("insp")),
                         orientation="; ".join(f["insp"]["orientation"] for f in present if f.get("insp")),
                         affine_summary="; ".join(f["insp"]["affine_summary"] for f in present if f.get("insp")),
                         qform="; ".join(str(f["insp"]["qform_code"]) for f in present if f.get("insp")),
                         sform="; ".join(str(f["insp"]["sform_code"]) for f in present if f.get("insp")),
                         probabilistic_or_discrete=meta.get("kind", ""),
                         value_range="; ".join(str(f["insp"]["value_range"]) for f in present if f.get("insp")),
                         nonzero_voxels="; ".join(str(f["insp"]["nonzero"]) for f in present if f.get("insp")),
                         coordinate_relation_to_julich="; ".join(coords),
                         resampling_required="NO" if (present and exact and not sym_vs_asym and not nonlinear) else "YES",
                         transform_required="YES" if (sym_vs_asym or nonlinear) else "NO",
                         raw_asset_verified=("TRUE" if status == "RAW_ASSET_VERIFIED" else "FALSE"),
                         notes=(";".join(sorted(failed_kinds)) if failed_kinds else "")))
    # status tallies from per_asset (single source of truth)
    verified = sum(1 for v in per_asset.values() if v == "RAW_ASSET_VERIFIED")
    acquired = sum(1 for v in per_asset.values() if v == "RAW_ASSET_ACQUIRED")
    pending = sum(1 for v in per_asset.values() if v in ("PENDING_EXTERNAL", "SUBJECT_SPECIFIC_ONLY"))
    failed = sum(1 for v in per_asset.values() if str(v).startswith("FAIL"))
    # write acquisition CSV
    cols = ["asset_id", "structure", "source_status", "download_status", "license_status",
            "redistribution_allowed", "file_count", "sha256", "local_path", "file_size",
            "coordinate_space", "template_variant", "shape", "spacing", "orientation",
            "affine_summary", "qform", "sform", "probabilistic_or_discrete", "value_range",
            "nonzero_voxels", "coordinate_relation_to_julich", "resampling_required",
            "transform_required", "raw_asset_verified", "notes"]
    with open(OUTCSV, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    archives = {}
    for rel in ["freesurfer_icbm2009c/hippocampus/_original/HippoAmyg.zip",
                "freesurfer_icbm2009c/thalamus/_original/Thalamus.zip",
                "_ref/mni_icbm152_nlin_sym_09c_nifti.zip"]:
        p = RAW / rel
        if p.exists():
            archives[rel] = dict(sha256=sha256(p), file_size=p.stat().st_size)
    # per-file registry (every raw file present under external_raw managed set)
    # frozen checksum is preserved; a live mismatch is recorded, never overwritten.
    files = {}
    asset_ids = {}
    for asset_id, meta in A.items():
        for rel in meta.get("files") or []:
            asset_ids.setdefault(rel, []).append(asset_id)
    for rel, aids in sorted(asset_ids.items()):
        p = RAW / rel
        if not p.exists():
            continue
        live = sha256(p)
        frozen = prior.get(rel)
        try:
            ins = inspect(p)
            shape, zooms, vrange, nz = ins["shape"], ins["zooms"], ins["value_range"], ins["nonzero"]
        except Exception:
            shape, zooms, vrange, nz = [], [], [], 0
        if frozen is not None and frozen != live:
            files[rel] = dict(asset_ids=";".join(aids), sha256=frozen, live_sha256=live,
                              file_size=p.stat().st_size, shape=shape, zooms=zooms,
                              value_range=vrange, nonzero=nz, status="FAIL_RAW_ASSET_CHANGED")
        else:
            files[rel] = dict(asset_ids=";".join(aids), sha256=live,
                              file_size=p.stat().st_size, shape=shape, zooms=zooms,
                              value_range=vrange, nonzero=nz, status="OK")
    summary = dict(julich_reference=ref, asset_count=len(rows),
                   raw_asset_verified_count=verified, raw_asset_acquired_count=acquired,
                   pending_metadata_count=pending, failed_count=failed,
                   original_archives=archives, files=files,
                   immutable_mismatches=[dict(asset_id=a, file=r, prior=p_, live=l)
                                         for (a, r, p_, l) in mismatches],
                   per_asset=per_asset,
                   note="no downloads of gated assets; no resampling/transform/geometry; "
                        "symmetric(2009cSym) != asymmetric(2009cAsym) enforced by header, not name")
    with open(OUTJSON, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    files_md = [
        f"- {rel} sha256={m['sha256']} size={m['file_size']} "
        f"shape={m['shape']} zooms={m['zooms']} range={m['value_range']} nonzero={m['nonzero']}"
        for rel, m in sorted(files.items())]
    md = ["# Phase1.7 V3 External Raw G1 asset acquisition audit", "",
          f"Julich reference: {ref['affine_summary']}",
          "assets=" + str(len(rows)),
          "acquisition per asset: " + json.dumps(per_asset, ensure_ascii=False),
          f"RAW_ASSET_VERIFIED={verified} RAW_ASSET_ACQUIRED={acquired} "
          f"pending/metadata={pending} FAILED={failed}",
          "original_archives(sha256): " + json.dumps(archives, ensure_ascii=False),
          "EXACT grid match vs Julich: CIT168 2009cAsym det+prob (193x229x193,1mm,origin -96/-132/-78).",
          "FreeSurfer subfield atlases are on ICBM152 2009c SYMMETRIC template (0.25/0.5mm):",
          "  SYMMETRIC_VS_ASYMMETRIC_TEMPLATE relative to Julich 2009cAsym - resampling+transform required.",
          "Blackford whole-BNST is on the FSL MNI152 6th-gen 1mm grid (182x218x182):",
          "  NOT 2009c - nonlinear template transform to NLin2009cAsym required.",
          "BF/BST separation preserved (BST never merged into Zaborszky Ch atlas).",
          "aseg stays SUBJECT_SPECIFIC_ONLY (never group gold standard).",
          "immutable_mismatches=" + (json.dumps(summary["immutable_mismatches"])
                                     if summary["immutable_mismatches"] else "NONE"),
          "", "## raw file registry (sha256 of every present file)"] + files_md + [""]
    with open(OUTMD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    # sync manifest acquisition_status + backfill verified header facts
    mpath = D16 / "phase17_v3_external_g1_asset_manifest.csv"
    mrows = list(csv.DictReader(open(mpath, encoding="utf-8-sig")))
    fieldnames = list(mrows[0].keys())
    # per-asset first-present-file header facts (immutable raw)
    # NB: FAIL_RAW_ASSET_CHANGED assets are NOT re-backfilled - the frozen
    # checksum/header columns are preserved, never overwritten by tampered bytes.
    header_facts = {}
    for r in rows:
        if not r.get("local_path") or str(r.get("download_status", "")).startswith("FAIL"):
            continue
        first = r["local_path"].split("; ")[0]
        p = RAW / first
        if not p.exists():
            continue
        ins = inspect(p)
        # grid-in-sync means spatial shape+affine exactly on Julich 2009cAsym grid
        coord = coordinate_relation(ref, ins, "Sym" in r["template_variant"])
        header_facts[r["asset_id"]] = dict(
            resolution=",".join("%g" % z for z in ins["zooms"][:3]),
            shape="x".join(str(x) for x in ins["shape"][:3]) +
                  ("+" + str(ins["shape"][3]) if len(ins["shape"]) > 3 else ""),
            voxel_spacing=",".join("%g" % z for z in ins["zooms"][:3]),
            affine_summary=ins["affine_summary"],
            orientation=ins["orientation"],
            file_size=p.stat().st_size,
            checksum=sha256(p),
            local_raw_path="data/atlases/external_raw/" + first,
            exact_voxel_grid_match=("TRUE" if coord == "EXACT_GRID_MATCH" else "FALSE/UNKNOWN(not same Julich 2009cAsym grid)"),
        )
    # Explicit license + redistribution for the assets managed by this audit
    # (CIT168 verified as MIT per the author repository LICENSE.md).
    license_overrides = {
        "CIT168_NAcc": ("MIT License, Copyright (c) 2017 California Institute of "
                        "Technology (LICENSE.md in jmtyszka/CIT168-SubCorticalAtlas@master; "
                        "OSF node jkzwp)", "REDISTRIBUTABLE"),
        "BST_BLACKFORD_WHOLE": ("CC0 1.0 (NeuroVault collection 2017 / image 39103)", "REDISTRIBUTABLE"),
        "FS_SUBFIELD_HIPPO": ("FreeSurfer license (research use; attribution required; see "
                              "surfer.nmr.mgh.harvard.edu terms)", "LOCAL_USE_ONLY"),
        "FS_AMYG_NUCLEI": ("FreeSurfer license (research use; attribution required; see "
                           "surfer.nmr.mgh.harvard.edu terms)", "LOCAL_USE_ONLY"),
        "FS_THAL_ICBM": ("FreeSurfer license (research use; attribution required; see "
                         "surfer.nmr.mgh.harvard.edu terms)", "LOCAL_USE_ONLY"),
    }
    for r in mrows:
        aid = r["asset_id"]
        if aid in per_asset:
            r["acquisition_status"] = per_asset[aid]
        facts = header_facts.get(aid)
        if facts:
            r["resolution"] = facts["resolution"]
            r["shape"] = facts["shape"]
            r["voxel_spacing"] = facts["voxel_spacing"]
            r["affine_summary"] = facts["affine_summary"]
            r["orientation"] = facts["orientation"]
            r["file_size"] = str(facts["file_size"])
            r["checksum"] = facts["checksum"]
            r["local_raw_path"] = facts["local_raw_path"]
            r["exact_voxel_grid_match"] = facts["exact_voxel_grid_match"]
        lic_ov = license_overrides.get(aid)
        if lic_ov:
            r["license"] = lic_ov[0]
            r["redistribution_status"] = lic_ov[1]
    with open(mpath, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in mrows:
            w.writerow(r)
    print("assets", len(rows), "verified", verified, "acquired", acquired,
          "pending", pending, "failed", failed)
    print("per_asset", per_asset)


if __name__ == "__main__":
    main()
