"""Phase1.7 V3 - Zaborszky 2008 Basal Forebrain authoritative raw asset acquisition audit.

OBJECTIVE: determine whether the Zaborszky et al. 2008 human basal-forebrain Ch1-Ch4
probabilistic atlas can be legally, accurately and traceably acquired. NO geometry /
no Ch1-Ch4 aggregation / no resample / no transform / no Julich substitution / no
multi-atlas fusion / no DB / no reclassification / no promotion.

RESULT OF THIS ROUND (evidence-based): ACCESS_BLOCKED / MANUAL_AUTHORIZED_ACCESS_REQUIRED.
  - Publication identity verified (metadata): Zaborszky L, Hoemke L, Mohlberg H,
    Schleicher A, Amunts K, Zilles K (2008), NeuroImage 42(3):1127-1141,
    DOI 10.1016/j.neuroimage.2008.05.055, PMID 18585468, PMC2577158 (open-access
    full text). Human postmortem n=10; magnocellular cholinergic cell groups
    Ch1-2 (septum), Ch3 (horizontal limb), Ch4 (sublenticular); warped to an MNI
    single-subject reference; abstract states maps are available as an open-source
    reference.
  - No authoritative original full-probability asset is present in the repository or
    reachable/verifiable from this session (web fetches to NCBI/EuropePMC are
    network-blocked). No raw file was downloaded; no SHA fabricated.
  - A human must perform the authorized retrieval (open PMC2577158 in a browser,
    read the license/data-availability, download the supplementary atlas volume(s)),
    verify content and reference space, then place the unmodified file(s) under
    data/atlases/external_raw/basal_forebrain/zaborszky2008/ and record the real SHA.

No alternative source (Julich-Brain CH_123 / CH_4 or any third-party repack) is
substituted for the Zaborszky original.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
ACQ_CSV = D16 / "phase17_v3_external_raw_asset_acquisition.csv"
SCRIPT_VERSION = "phase17_v3_acquire_zaborszky_basal_forebrain_asset.py v1"

OUT_ROUTES = D16 / "phase17_v3_zaborszky_acquisition_routes.csv"
OUT_INV = D16 / "phase17_v3_zaborszky_asset_inventory.csv"
OUT_MAN = D16 / "phase17_v3_zaborszky_raw_asset_manifest.json"
OUT_LIC = D16 / "phase17_v3_zaborszky_license_access_audit.json"
OUT_PROV = D16 / "phase17_v3_zaborszky_acquisition_provenance.json"
OUT_MD = D16 / "phase17_v3_zaborszky_acquisition_diagnostics.md"
OUT_BLOCK = D16 / "phase17_v3_zaborszky_acquisition_blocker_v1.json"

ROUTES = [
    dict(route_id="R1", provider="repository external_raw",
         url="backend/data/atlases/external_raw/basal_forebrain/zaborszky2008/ (expected location)",
         access_state="ABSENT", requires_login="no", requires_license_acceptance="n/a",
         redistribution_status="n/a", asset_name="none", version="-",
         evidence="searched repo; no zaborszky file present"),
    dict(route_id="R2", provider="repository cache / downloads",
         url="repo-local", access_state="ABSENT", requires_login="no",
         requires_license_acceptance="n/a", redistribution_status="n/a",
         asset_name="none", version="-", evidence="no cached zaborszky asset found"),
    dict(route_id="R3", provider="prior acquisition manifest",
         url="phase17_v3_external_raw_asset_acquisition.csv (asset BF_ZABORSZKY_CH1234)",
         access_state="NOT_ACQUIRED / ACCESS_RESTRICTED", requires_login="n/a",
         requires_license_acceptance="TO_VERIFY", redistribution_status="TO_VERIFY",
         asset_name="none", version="-", evidence="acquisition row: download_status NOT_ACQUIRED; "
                                                  "license ACCESS_RESTRICTED; raw_asset_verified FALSE"),
    dict(route_id="R4", provider="Anatomy Toolbox / SPM distribution",
         url="(would be a repack/derivative if found)", access_state="NOT_PRESENT",
         requires_login="n/a", requires_license_acceptance="n/a",
         redistribution_status="unverified", asset_name="none", version="-",
         evidence="no Anatomy Toolbox/SPM copy of the Zaborszky original in repo; any such copy "
                  "would be a derivative and is not usable as the authoritative raw asset"),
    dict(route_id="R5", provider="official Juellich / FZJ distribution route",
         url="Julich-Brain v3.1 cyto basal-forebrain maps",
         access_state="DIFFERENT_ATLAS_FAMILY", requires_login="no",
         requires_license_acceptance="EBRAINS/siibra terms", redistribution_status="see siibra",
         asset_name="CH_123 / CH_4 / TU / TUTi / BST (Julich)", version="3.1.0",
         evidence="Julich-Brain cytoarchitectonic maps are a DIFFERENT (Julich) atlas family; not a "
                  "route to the Zaborszky 2008 original; must NOT be substituted"),
    dict(route_id="R6", provider="official author/lab publication resource",
         url="researchwithrutgers.com record of the paper; author lab resource (not confirmed open)",
         access_state="NOT_CONFIRMED", requires_login="likely", requires_license_acceptance="likely",
         redistribution_status="TO_VERIFY", asset_name="none confirmed", version="-",
         evidence="web search surfaced the Rutgers research record; no direct open file URL "
                  "verified for the atlas volumes"),
    dict(route_id="R7", provider="institutional/public research repository",
         url="PubMed Central PMC2577158 (open-access full text)",
         access_state="REACHABLE_BY_HUMAN / NOT_FETCHABLE_FROM_SESSION", requires_login="no",
         requires_license_acceptance="read OA/CC terms on the record",
         redistribution_status="PMC open access (terms to read)",
         asset_name="supplementary atlas volume(s) (to verify)", version="2008",
         evidence="article is PMC open access; atlas stated 'open source reference'; this session's "
                  "network blocks fetching NCBI/EuropePMC, so file-level content/license verification "
                  "requires a human browser session"),
    dict(route_id="R8", provider="archived official atlas distribution",
         url="unknown / none verified", access_state="NOT_FOUND", requires_login="n/a",
         requires_license_acceptance="n/a", redistribution_status="n/a",
         asset_name="none", version="-", evidence="no verified official archive of the Zaborszky "
                                                  "original atlas volumes found"),
    dict(route_id="R9", provider="paper supplementary resources",
         url="PMC2577158 supplementary (to be inspected by user)",
         access_state="MANUAL_AUTHORIZED_ACCESS_REQUIRED", requires_login="no",
         requires_license_acceptance="read license on record",
         redistribution_status="TO_VERIFY",
         asset_name="Ch1-4 probabilistic volumes (expected .img/.hdr or .nii)", version="2008",
         evidence="most plausible delivery route; requires a human to open PMC and verify content "
                  "and license before download"),
]


def acq_row() -> dict:
    for r in csv.DictReader(open(ACQ_CSV, encoding="utf-8-sig")):
        if r.get("asset_id") == "BF_ZABORSZKY_CH1234":
            return dict(r)
    return {}


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    acq = acq_row()
    with open(OUT_ROUTES, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(ROUTES[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in ROUTES:
            w.writerow(r)

    # asset inventory: no authoritative original file acquired
    with open(OUT_INV, "w", newline="", encoding="utf-8-sig") as fh:
        cols = ["filename", "structure", "hemisphere", "probability_or_binary", "threshold",
                "space", "resolution", "format", "size", "provenance_class", "status"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        # no rows: nothing authoritative acquired; note only via manifest

    raw_manifest = dict(
        manifest_id="ZABORSZKY_RAW_ASSET_MANIFEST",
        source="ZABORSZKY_2008_HUMAN_BASAL_FOREBRAIN",
        asset_status="NOT_ACQUIRED",
        authority="AUTHORITATIVE_OPERATIONAL_PROXY_GEOMETRY (frozen; unchanged)",
        raw_sha256=None,
        file_count=0,
        file_path=None,
        raw_probability_semantics_status="NOT_CHARACTERIZED_NO_RAW_ASSET",
        space_status="UNRESOLVED_NO_RAW_ASSET",
        laterality_semantics="NOT_RECORDED_NO_RAW_ASSET",
        immutability="raw bytes immutable once acquired (never renamed/re-gzipped/re-headed/resampled)",
        gitignore_policy="raw binaries under external_raw are LOCAL_IMMUTABLE_CACHE / gitignored; "
                         "never committed",
        note="no authoritative original full-probability asset is acquired this round; raw SHA is "
             "null and must never be fabricated.",
        created_at=ts, script_version=SCRIPT_VERSION)
    with open(OUT_MAN, "w", encoding="utf-8") as fh:
        json.dump(raw_manifest, fh, ensure_ascii=False, indent=2)

    lic = dict(
        publication="Zaborszky et al. 2008, NeuroImage 42(3):1127-1141 (DOI 10.1016/j.neuroimage.2008.05.055)",
        paper_copyright="Elsevier (article full text open-access in PubMed Central PMC2577158)",
        atlas_distribution_license="TO_VERIFY at file level (PMC open-access terms to be read by user)",
        download_access_terms="MANUAL_AUTHORIZED_ACCESS_REQUIRED (human must open PMC record and "
                              "read terms)",
        redistribution_permission="TO_VERIFY / LOCAL_USE_ONLY until verified",
        status="ACCESS_RESTRICTED_UNTIL_MANUAL_AUTHORIZED_RETRIEVAL",
        note="readable paper text does NOT imply the atlas volume files are freely redistributable; "
             "license must be verified from the distribution record before download.",
        created_at=ts)
    with open(OUT_LIC, "w", encoding="utf-8") as fh:
        json.dump(lic, fh, ensure_ascii=False, indent=2)

    prov = dict(
        chain=[
            dict(step="canonical identity (frozen)", id="BASAL_FOREBRAIN_G1_CANONICAL_IDENTITY_V1"),
            dict(step="scope contract (frozen)", id="BASAL_FOREBRAIN_G1_SCOPE_CONTRACT_V1"),
            dict(step="geometry authority (frozen)",
                 verdict="AUTHORITATIVE_OPERATIONAL_PROXY_GEOMETRY", asset="Zaborszky 2008 Ch1-4"),
            dict(step="publication identity", title="Stereotaxic probabilistic maps of the "
                 "magnocellular cell groups in human basal forebrain", authors="Zaborszky, Hoemke, "
                 "Mohlberg, Schleicher, Amunts, Zilles", journal="NeuroImage", year=2008,
                 volume_pages="42(3):1127-1141", doi="10.1016/j.neuroimage.2008.05.055",
                 pmid="18585468", pmc="PMC2577158"),
            dict(step="route audit", routes=[r["route_id"] for r in ROUTES],
                 fetch_note="NCBI/EuropePMC web fetches network-blocked in this session"),
            dict(step="outcome", asset_status="NOT_ACQUIRED",
                 blocker="BASAL_FOREBRAIN_ZABORSZKY_ASSET_ACQUISITION_BLOCKED_V1"),
        ],
        raw_sha256=None,
        fabricated_sha=False,
        no_bypass=True,
        created_at=ts, script_version=SCRIPT_VERSION)
    with open(OUT_PROV, "w", encoding="utf-8") as fh:
        json.dump(prov, fh, ensure_ascii=False, indent=2)

    blocker = dict(
        blocker_id="BASAL_FOREBRAIN_ZABORSZKY_ASSET_ACQUISITION_BLOCKED_V1",
        case="B_ACCESS_RESTRICTED_MANUAL_AUTHORIZED_ACCESS_REQUIRED",
        scientific_authority="FROZEN",
        raw_asset="NOT_ACQUIRED",
        geometry="BLOCKED_ON_AUTHORITATIVE_ASSET_ACCESS",
        raw_sha256=None,
        reason=("all legal routes were audited; the only plausible authoritative delivery (PubMed "
                "Central PMC2577158 open-access supplementary / author resource) requires a human "
                "browser session to read the license/data-availability terms and retrieve the atlas "
                "volume(s). This session cannot fetch NCBI/EuropePMC (network-blocked), and no "
                "verifiable authoritative original full-probability asset is present in the repo. "
                "No third-party derivative and no Julich CH_123/CH_4 map is substituted."),
        required_user_actions=[
            "Open the PMC record PMC2577158 (or the equivalent author resource) in a browser",
            "Read the license / data-availability statement on that record",
            "Confirm the downloadable volume(s) are the Zaborszky 2008 Ch1-Ch4 human "
            "magnocellular-cell-group probabilistic maps (full probability, not a 50%/binary ROI)",
            "Confirm the reference space named in the documentation (MNI single-subject; record "
            "template/version from the documentation)",
            "Download the file(s) WITHOUT modification; keep the original .img/.hdr or .nii bytes",
            "Place the unmodified file(s) under data/atlases/external_raw/basal_forebrain/"
            "zaborszky2008/ (raw binaries stay gitignored)",
            "Compute and record the real SHA256 + file size",
            "Then a later round can run Ch1-Ch4 geometry construction on the authoritative asset"],
        do_not=["switch to the Julich CH_123/CH_4 maps as primary",
                "fabricate a raw SHA", "bypass any login/license gate"],
        created_at=ts, script_version=SCRIPT_VERSION)
    with open(OUT_BLOCK, "w", encoding="utf-8") as fh:
        json.dump(blocker, fh, ensure_ascii=False, indent=2)

    md = [
        "# Phase1.7 V3 - Zaborszky 2008 Basal Forebrain raw asset acquisition audit", "",
        "Publication identity verified: Zaborszky et al. 2008, NeuroImage 42(3):1127-1141, "
        "DOI 10.1016/j.neuroimage.2008.05.055, PMID 18585468, PMC2577158. Human postmortem n=10; "
        "magnocellular/cholinergic cell groups Ch1-2 (septum), Ch3 (HDB), Ch4 (sublenticular); "
        "MNI single-subject reference; abstract states the maps are available as an open-source "
        "reference.", "",
        "9 acquisition routes audited (see phase17_v3_zaborszky_acquisition_routes.csv). "
        "Result: no authoritative original full-probability asset acquired; no SHA fabricated; "
        "no access-control bypass; no derivative or Julich substitution.",
        "Asset status: NOT_ACQUIRED. raw_sha256 = null (never fabricated).",
        "License/access: ACCESS_RESTRICTED_UNTIL_MANUAL_AUTHORIZED_RETRIEVAL; a human must open "
        "PMC2577158, read the license/data-availability terms, retrieve and verify the atlas "
        "volume(s), then place the unmodified bytes under external_raw/basal_forebrain/"
        "zaborszky2008/ and record the real SHA.",
        "Blocker frozen: BASAL_FOREBRAIN_ZABORSZKY_ASSET_ACQUISITION_BLOCKED_V1 (Case B). "
        "scientific_authority FROZEN; geometry BLOCKED_ON_AUTHORITATIVE_ASSET_ACCESS.",
        "Guards: no geometry / no Ch1-4 aggregation / no resample / no transform / no hemisphere "
        "split / no DB / no reclassification / no promotion; BF scope & authority verdict "
        "unchanged; Julich CH_123/CH_4 remain secondary (not promoted); Thalamus/Amygdala/"
        "Hippocampus/BNST frozen chains untouched.", ""]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    print("publication verified: Zaborszky 2008 NeuroImage 42(3):1127-1141 (PMID 18585468, PMC2577158)")
    print("routes audited: 9 | outcome: ACCESS_BLOCKED / MANUAL_AUTHORIZED_ACCESS_REQUIRED")
    print("raw_sha256: null (not fabricated); no derivative/Julich substitution")
    print("wrote 7 artifacts (blocker Case B)")


if __name__ == "__main__":
    main()
