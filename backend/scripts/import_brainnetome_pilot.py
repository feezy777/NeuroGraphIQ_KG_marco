"""Gate 8A — Brainnetome BNA246 pilot importer (production DB, rerun-safe).

Chain written (PostgreSQL canonical 32-table schema, no schema changes):
    Scientific Source (Human Brainnetome Atlas / BNA246)
      -> Atlas entity
      -> ExternalRegion (per pilot parcel, G3_MESO_FINE)
      -> proposed canonical BrainRegion (record_status=proposed)
      -> Alias (atlas label) + Xref (Brainnetome numeric code)
      -> RegionMapping (exact canonicalization)

Authoritative source:
    backend/data/atlases/brainnetome/BNA246_regions_circos.tsv
    Official Human Brainnetome Atlas circos band file (atlas.brainnetome.org),
    BNA246 (2016), Homo sapiens, 246 bands = 123 left + 123 right.

Pilot selection (reproducible):
    For PILOT_GYRI, take the minimal-idx band of each hemisphere.
    For PILOT_SUBCORTICAL_EXTRA, take the minimal-idx LEFT band.
    Total = 9*2 + 2 = 20 parcels (left/right + cortical/subcortical + lobe spread).

Usage:
    python scripts/import_brainnetome_pilot.py [--plan|--apply] [--db neurographiq_human_brain_v1]
    Default is --plan (read-only; no IDs burned).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

try:
    import psycopg
except ImportError:
    print("ERROR: psycopg (psycopg3) required")
    sys.exit(2)

BACKEND_DIR = Path(__file__).resolve().parents[1]
TSV = BACKEND_DIR / "data" / "atlases" / "brainnetome" / "BNA246_regions_circos.tsv"

DB_DEFAULT = "neurographiq_human_brain_v1"

ATLAS_NAME_EN = "Human Brainnetome Atlas"
ATLAS_NAME_ZH = "人类脑连接组图谱"
ATLAS_VERSION = "BNA246 (2016)"
ATLAS_URL = "http://atlas.brainnetome.org"
ATLAS_FAMILY = "Brainnetome"
SOURCE_PROVIDER = "Brainnetome Center, Institute of Automation, Chinese Academy of Sciences (CASIA)"
SOURCE_CITATION = (
    "Fan L, Li H, Zhuo J, et al.\n"
    "The Human Brainnetome Atlas: A New Brain Atlas Based on Connectional Architecture.\n"
    "Cerebral Cortex. 2016;26(8):3508-3526.\n"
    "doi:10.1093/cercor/bhw157"
)
SPECIES_HUMAN = "Homo sapiens (NCBI:9606)"
SPECIES_TAXON = "9606"
GRANULARITY_LEVEL = "G3_MESO_FINE"
GRANULARITY_BASIS = "multimodal_parcellation"
XREF_DATABASE = "Brainnetome"
REGION_COUNT = 246

_BAND_RE = re.compile(r"^(?P<gyrus>[A-Za-z0-9]+)_(?P<hemi>[LR])_(?P<n>\d+)_(?P<idx>\d+)$")

# circos lobe key -> lobe name (from the 14 `chr - lobeN ...` header rows)
_LOBE_NAMES = {
    "lobe1": "frontal", "lobe2": "insular", "lobe3": "limbic", "lobe4": "temporal",
    "lobe5": "parietal", "lobe6": "occipital", "lobe7": "subcortical",
    "lobe8": "subcortical", "lobe9": "occipital", "lobe10": "parietal",
    "lobe11": "temporal", "lobe12": "limbic", "lobe13": "insular", "lobe14": "frontal",
}

# gyrus abbr -> (full EN name, full CN name) — curated in-repo BNA abbreviation map
# (also present in legacy scripts/brainnetome_importer.py GYRUS_PARENT).
_GYRUS_NAMES = {
    "SFG": ("Superior frontal gyrus", "额上回"),
    "IFG": ("Inferior frontal gyrus", "额下回"),
    "STG": ("Superior temporal gyrus", "颞上回"),
    "MTG": ("Middle temporal gyrus", "颞中回"),
    "SPL": ("Superior parietal lobule", "顶上小叶"),
    "IPL": ("Inferior parietal lobule", "顶下小叶"),
    "Cun": ("Medioventral occipital cortex", "腹内侧枕叶皮层"),
    "Ins": ("Insular gyrus", "岛回"),
    "Hipp": ("Hippocampus", "海马"),
    "Str": ("Striatum (basal ganglia)", "纹状体"),
    "Th": ("Thalamus", "丘脑"),
}

_LATERALITY_CN = {"L": "左", "R": "右"}
_HEMI = {"L": "left", "R": "right"}

MAPPING_SOURCE = "brainnetome_direct"


def _canonical_names(b: dict) -> tuple[str, str]:
    """Canonical BrainRegion display name (Priority 2 stable constructed form).

    The BNA246 circos source carries only native codes (e.g. SFG_L_7_1) + gyrus
    abbreviation + lobe — no official English parcel subdivision names. So the
    canonical name is a stable constructed form that carries the hemisphere
    explicitly:  '<Left|Right> <gyrus anatomical name>, Brainnetome <n>_<idx>'.
    name_en_source='normalized' / name_zh_source='translated_human' (constructed,
    NOT authoritative Brainnetome subdivision names). source_name_original stays
    the source-native code.
    """
    hemi_en = "Left" if b["hemi"] == "L" else "Right"
    hemi_zh = "左侧" if b["hemi"] == "L" else "右侧"
    gyrus_en, gyrus_cn = _GYRUS_NAMES[b["gyrus"]]
    name_en = f"{hemi_en} {gyrus_en}, Brainnetome {b['n']}_{b['idx']}"
    name_zh = f"{hemi_zh}{gyrus_cn}（Brainnetome {b['n']}-{b['idx']}）"
    return name_en, name_zh


def _mapping_rationale(b: dict) -> str:
    return (
        f"Direct canonicalization of BNA246 parcel {b['native_name']} into its proposed "
        f"canonical BrainRegion (same parcel identity under deterministic rule; "
        f"not fuzzy atlas matching)."
    )

# Pilot selection (reproducible): minimal-idx band per hemisphere for these gyri,
# plus minimal-idx left band of the two extra subcortical gyri.
PILOT_GYRI = ["SFG", "IFG", "STG", "MTG", "SPL", "IPL", "Cun", "Ins", "Hipp"]
PILOT_SUBCORTICAL_EXTRA = ["Str", "Th"]


def _redact(secret: str | None) -> str:
    return "<REDACTED>" if secret else "<EMPTY>"


def _parse_bands() -> list[dict]:
    """Parse circos band rows -> list of parcel dicts (all 246)."""
    bands = []
    for line in TSV.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if not fields or fields[0] != "band":
            continue
        lobe_key, band_id, native_name = fields[1], int(fields[2]), fields[3]
        m = _BAND_RE.match(native_name)
        if m is None:
            continue
        bands.append({
            "band_id": band_id,
            "native_name": native_name,
            "gyrus": m.group("gyrus"),
            "hemi": m.group("hemi"),
            "n": int(m.group("n")),
            "idx": int(m.group("idx")),
            "lobe": _LOBE_NAMES.get(lobe_key, "unknown"),
        })
    return bands


def _select_pilot(bands: list[dict]) -> list[dict]:
    """Deterministic pilot selection: min-idx band per hemisphere for PILOT_GYRI;
    min-idx left band for PILOT_SUBCORTICAL_EXTRA."""
    selected: list[dict] = []
    for gyrus in PILOT_GYRI:
        gbands = [b for b in bands if b["gyrus"] == gyrus]
        for hemi in ("L", "R"):
            cand = [b for b in gbands if b["hemi"] == hemi]
            if cand:
                selected.append(min(cand, key=lambda b: b["idx"]))
    for gyrus in PILOT_SUBCORTICAL_EXTRA:
        cand = [b for b in bands if b["gyrus"] == gyrus and b["hemi"] == "L"]
        if cand:
            selected.append(min(cand, key=lambda b: b["idx"]))
    # deterministic order: by band_id
    selected.sort(key=lambda b: b["band_id"])
    return selected


def _connect(args):
    return psycopg.connect(
        host=args.host, port=args.port, user=args.user,
        password=args.password, dbname=args.db, autocommit=False,
    )


def _row(cur, sql, *params):
    cur.execute(sql, params)
    r = cur.fetchone()
    return r[0] if r else None


def _src_exists(cur) -> tuple[int | None, str | None]:
    cur.execute("SELECT source_pk, source_id FROM sources WHERE name_en=%s AND version=%s",
                (ATLAS_NAME_EN, ATLAS_VERSION))
    r = cur.fetchone()
    return (r[0], r[1]) if r else (None, None)


def _atlas_exists(cur) -> tuple[int | None, str | None]:
    cur.execute(
        "SELECT e.entity_pk, e.entity_id FROM kg_entities e"
        " JOIN atlases a ON a.entity_pk = e.entity_pk"
        " WHERE e.entity_type='atlas' AND e.name_en=%s AND a.atlas_version=%s",
        (ATLAS_NAME_EN, ATLAS_VERSION),
    )
    r = cur.fetchone()
    return (r[0], r[1]) if r else (None, None)


def _external_region_exists(cur, atlas_pk: int, native_name: str) -> int | None:
    cur.execute(
        "SELECT e.entity_pk FROM kg_entities e"
        " JOIN external_regions x ON x.entity_pk = e.entity_pk"
        " WHERE e.entity_type='external_region' AND x.atlas_pk=%s AND x.source_region_id=%s",
        (atlas_pk, native_name),
    )
    r = cur.fetchone()
    return r[0] if r else None


def _brain_region_exists(cur, source_name_original: str) -> int | None:
    cur.execute(
        "SELECT entity_pk FROM kg_entities"
        " WHERE entity_type='brain_region' AND source_name_original=%s",
        (source_name_original,),
    )
    r = cur.fetchone()
    return r[0] if r else None


def _mapping_exists(cur, xpk: int, bpk: int) -> int | None:
    cur.execute(
        "SELECT e.entity_pk FROM kg_entities e"
        " JOIN region_mappings rm ON rm.entity_pk = e.entity_pk"
        " WHERE e.entity_type='region_mapping' AND rm.external_region_pk=%s AND rm.brain_region_pk=%s",
        (xpk, bpk),
    )
    r = cur.fetchone()
    return r[0] if r else None


def _alias_exists(cur, entity_pk: int, alias_text: str) -> bool:
    cur.execute(
        "SELECT 1 FROM entity_aliases WHERE entity_pk=%s AND alias_text=%s AND alias_type='atlas_label'",
        (entity_pk, alias_text),
    )
    return cur.fetchone() is not None


def _xref_exists(cur, entity_pk: int, external_id: str) -> bool:
    cur.execute(
        "SELECT 1 FROM entity_xrefs WHERE entity_pk=%s AND source_database=%s AND external_id=%s",
        (entity_pk, XREF_DATABASE, external_id),
    )
    return cur.fetchone() is not None


def _plan(args) -> int:
    bands = _parse_bands()
    pilot = _select_pilot(bands)
    conn = _connect(args)
    try:
        cur = conn.cursor()
        src_pk, src_id = _src_exists(cur)
        atlas_pk, atlas_id = _atlas_exists(cur)

        print("=== Gate 8A Brainnetome Pilot PLAN ===")
        print(f"  source: {ATLAS_NAME_EN} / {ATLAS_VERSION} ({SPECIES_HUMAN})")
        print(f"  source file: {TSV}  (246 bands)")
        print(f"  pilot size: {len(pilot)} (rule: min-idx per hemisphere for {PILOT_GYRI} + left {PILOT_SUBCORTICAL_EXTRA})")
        print(f"  scientific source present: {src_id or 'NO (will create)'}")
        print(f"  atlas present: {atlas_id or 'NO (will create)'}")
        print()
        n_ext = n_br = n_map = 0
        n_br_update = n_map_update = 0
        for b in pilot:
            name_en, _name_zh = _canonical_names(b)
            xpk = _external_region_exists(cur, atlas_pk, b["native_name"]) if atlas_pk else None
            bpk = _brain_region_exists(cur, b["native_name"])
            mpk = _mapping_exists(cur, xpk, bpk) if (xpk and bpk) else None
            if not xpk:
                n_ext += 1
            if not bpk:
                n_br += 1
            else:
                cur.execute("SELECT name_en, name_zh_source FROM kg_entities WHERE entity_pk=%s", (bpk,))
                r = cur.fetchone()
                if r[0] != name_en or r[1] != "normalized":
                    n_br_update += 1
            if not mpk:
                n_map += 1  # mapping will be created after xpk+bpk are ensured
            else:
                cur.execute("SELECT mapping_source, overall_confidence FROM region_mappings WHERE entity_pk=%s", (mpk,))
                r = cur.fetchone()
                if r[0] != MAPPING_SOURCE or r[1] is not None:
                    n_map_update += 1
            print(f"  {b['band_id']:>3}  {b['native_name']:<12} gyrus={b['gyrus']:<4} "
                  f"{b['hemi']} lobe={b['lobe']:<10} ext={'exists' if xpk else 'CREATE'} "
                  f"br={'exists' if bpk else 'CREATE'} map={'exists' if mpk else 'CREATE'}")
        print()
        print(f"  would CREATE: external_regions={n_ext} brain_regions={n_br} region_mappings={n_map}")
        print(f"  would UPDATE: canonical names={n_br_update} mapping provenance={n_map_update} "
              f"+ source/atlas/aliases/xrefs as needed")
        print("  (plan mode — nothing written, no NGIQ IDs burned)")
        return 0
    finally:
        conn.rollback()
        conn.close()


def _apply(args) -> int:
    bands = _parse_bands()
    pilot = _select_pilot(bands)
    conn = _connect(args)
    try:
        cur = conn.cursor()
        stats = {"source": 0, "atlas": 0, "external_region": 0, "brain_region": 0,
                 "brain_region_updated": 0, "region_mapping": 0, "mapping_updated": 0,
                 "alias": 0, "xref": 0}

        # 1. Scientific Source (reuse if present; repair provenance if missing)
        src_pk, src_id = _src_exists(cur)
        if src_pk is None:
            src_id = _row(cur, "SELECT infra.next_ngiq_id('source')")
            cur.execute(
                "INSERT INTO sources (source_id, name_en, name_zh, abbreviation, source_type,"
                " version, species_scope, url, provider, citation_text, last_checked_at, record_status)"
                " VALUES (%s,%s,%s,%s,'atlas',%s,%s,%s,%s,%s,NOW(),'active')",
                (src_id, ATLAS_NAME_EN, ATLAS_NAME_ZH, "BNA", ATLAS_VERSION,
                 SPECIES_HUMAN, ATLAS_URL, SOURCE_PROVIDER, SOURCE_CITATION),
            )
            cur.execute("SELECT source_pk FROM sources WHERE source_id=%s", (src_id,))
            src_pk = cur.fetchone()[0]
            stats["source"] = 1
        else:
            cur.execute("SELECT provider FROM sources WHERE source_pk=%s", (src_pk,))
            if cur.fetchone()[0] is None:
                cur.execute(
                    "UPDATE sources SET provider=%s, citation_text=%s, last_checked_at=NOW()"
                    " WHERE source_pk=%s",
                    (SOURCE_PROVIDER, SOURCE_CITATION, src_pk),
                )
                stats["source"] += 1  # provenance backfilled
        print(f"  source: {src_id}")

        # 2. Atlas entity (reuse if present)
        atlas_pk, atlas_id = _atlas_exists(cur)
        if atlas_pk is None:
            atlas_id = _row(cur, "SELECT infra.next_ngiq_id('atlas')")
            cur.execute(
                "INSERT INTO kg_entities (entity_id, entity_type, name_en, name_zh,"
                " source_name_original, name_en_source, name_zh_source, record_status, metadata_json)"
                " VALUES (%s,'atlas',%s,%s,%s,'source','translated_human','active',%s)",
                (atlas_id, ATLAS_NAME_EN, ATLAS_NAME_ZH, ATLAS_NAME_EN,
                 f'{{"scientific_source":"{src_id}","version":"{ATLAS_VERSION}"}}'),
            )
            cur.execute("SELECT entity_pk FROM kg_entities WHERE entity_id=%s", (atlas_id,))
            atlas_pk = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO atlases (entity_pk, atlas_family, atlas_version, species,"
                " parcellation_method, reference_space, map_type, region_count,"
                " publisher_or_institution, source_url)"
                " VALUES (%s,%s,%s,%s,%s,%s,'label',%s,%s,%s)",
                (atlas_pk, ATLAS_FAMILY, ATLAS_VERSION, SPECIES_HUMAN,
                 "multimodal connectivity parcellation", "MNI152", REGION_COUNT,
                 "Institute of Automation, Chinese Academy of Sciences", ATLAS_URL),
            )
            stats["atlas"] = 1
        print(f"  atlas: {atlas_id}")

        # 3-7. Per parcel
        for b in pilot:
            native = b["native_name"]
            name_en, name_zh = _canonical_names(b)
            gyrus_en, gyrus_cn = _GYRUS_NAMES[b["gyrus"]]
            hemi = _HEMI[b["hemi"]]
            map_entity_en = f"{ATLAS_NAME_EN} {native} → {name_en}"
            map_entity_zh = f"{native} → {name_zh}"

            # ExternalRegion (identity-only — unchanged policy)
            xpk = _external_region_exists(cur, atlas_pk, native)
            if xpk is None:
                xid = _row(cur, "SELECT infra.next_ngiq_id('external_region')")
                cur.execute(
                    "INSERT INTO kg_entities (entity_id, entity_type, name_en, name_zh,"
                    " source_name_original, name_en_source, name_zh_source, record_status)"
                    " VALUES (%s,'external_region',%s,%s,%s,'source','translated_human','active')",
                    (xid, native, f"{gyrus_cn} {b['n']}-{b['idx']}（{_LATERALITY_CN[b['hemi']]}）",
                     native),
                )
                cur.execute("SELECT entity_pk FROM kg_entities WHERE entity_id=%s", (xid,))
                xpk = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO external_regions (entity_pk, atlas_pk, source_region_id, label_index,"
                    " hemisphere, granularity_level, granularity_basis)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (xpk, atlas_pk, native, b["band_id"], hemi,
                     GRANULARITY_LEVEL, GRANULARITY_BASIS),
                )
                stats["external_region"] += 1

            # proposed canonical BrainRegion — create or repair canonical display name
            bpk = _brain_region_exists(cur, native)
            if bpk is None:
                bid = _row(cur, "SELECT infra.next_ngiq_id('brain_region')")
                cur.execute(
                    "INSERT INTO kg_entities (entity_id, entity_type, name_en, name_zh,"
                    " source_name_original, name_en_source, name_zh_source, record_status)"
                    " VALUES (%s,'brain_region',%s,%s,%s,'normalized','normalized','proposed')",
                    (bid, name_en, name_zh, native),
                )
                cur.execute("SELECT entity_pk FROM kg_entities WHERE entity_id=%s", (bid,))
                bpk = cur.fetchone()[0]
                category = "subcortical_region" if b["lobe"] == "subcortical" else "cortical_parcel"
                cur.execute(
                    "INSERT INTO brain_regions (entity_pk, region_category, hemisphere,"
                    " granularity_level, species_taxon_id)"
                    " VALUES (%s,%s,%s,%s,%s)",
                    (bpk, category, hemi, GRANULARITY_LEVEL, SPECIES_TAXON),
                )
                stats["brain_region"] += 1
            else:
                # idempotent repair: keep entity_pk/entity_id; update canonical display name + sources.
                # name_en_source/name_zh_source='normalized' (deterministic construction from the
                # in-repo BNA name dictionary — NOT per-entity human translation).
                cur.execute("SELECT name_en, name_zh_source FROM kg_entities WHERE entity_pk=%s", (bpk,))
                r = cur.fetchone()
                if r[0] != name_en or r[1] != "normalized":
                    cur.execute(
                        "UPDATE kg_entities SET name_en=%s, name_zh=%s, name_en_source='normalized',"
                        " name_zh_source='normalized' WHERE entity_pk=%s",
                        (name_en, name_zh, bpk),
                    )
                    stats["brain_region_updated"] += 1

            # Alias: atlas-native label (not the numeric code — that goes to xref).
            # Ensured whenever the brain region exists (rerun-safe / partial-state repair).
            if not _alias_exists(cur, bpk, native):
                cur.execute(
                    "INSERT INTO entity_aliases (alias_id, entity_pk, alias_text,"
                    " alias_type, source_pk) VALUES (%s,%s,%s,'atlas_label',%s)",
                    (_row(cur, "SELECT infra.next_ngiq_id('alias')"), bpk, native, src_pk),
                )
                stats["alias"] += 1
            # Xref: Brainnetome numeric code
            if not _xref_exists(cur, bpk, str(b["band_id"])):
                cur.execute(
                    "INSERT INTO entity_xrefs (xref_id, entity_pk, source_database, external_id,"
                    " match_type, is_primary, source_version)"
                    " VALUES (%s,%s,%s,%s,'exact',true,%s)",
                    (_row(cur, "SELECT infra.next_ngiq_id('xref')"), bpk, XREF_DATABASE,
                     str(b["band_id"]), ATLAS_VERSION),
                )
                stats["xref"] += 1

            # RegionMapping: external parcel -> its proposed canonical candidate (canonicalization)
            mpk = _mapping_exists(cur, xpk, bpk)
            if mpk is None:
                mid = _row(cur, "SELECT infra.next_ngiq_id('region_mapping')")
                cur.execute(
                    "INSERT INTO kg_entities (entity_id, entity_type, name_en, name_zh,"
                    " source_name_original, name_en_source, name_zh_source, record_status, review_status)"
                    " VALUES (%s,'region_mapping',%s,%s,%s,'normalized','translated_human','active','pending')",
                    (mid, map_entity_en, map_entity_zh, native),
                )
                cur.execute("SELECT entity_pk FROM kg_entities WHERE entity_id=%s", (mid,))
                mpk = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO region_mappings (entity_pk, external_region_pk, brain_region_pk,"
                    " mapping_type, mapping_method, overall_confidence, review_status, mapping_source,"
                    " evidence_summary_en)"
                    " VALUES (%s,%s,%s,'exact','automatic',NULL,'pending',%s,%s)",
                    (mpk, xpk, bpk, MAPPING_SOURCE, _mapping_rationale(b)),
                )
                stats["region_mapping"] += 1
            else:
                # idempotent repair: provenance + confidence + display name (identity unchanged).
                # overall_confidence stays NULL: direct canonicalization is a deterministic
                # identity/canonicalization rule, not a probabilistic mapping model.
                cur.execute("SELECT mapping_source, overall_confidence FROM region_mappings WHERE entity_pk=%s", (mpk,))
                r = cur.fetchone()
                if r[0] != MAPPING_SOURCE or r[1] is not None:
                    cur.execute(
                        "UPDATE region_mappings SET mapping_source=%s, evidence_summary_en=%s,"
                        " overall_confidence=NULL WHERE entity_pk=%s",
                        (MAPPING_SOURCE, _mapping_rationale(b), mpk),
                    )
                    stats["mapping_updated"] += 1
                cur.execute("SELECT name_en FROM kg_entities WHERE entity_pk=%s", (mpk,))
                if cur.fetchone()[0] != map_entity_en:
                    cur.execute(
                        "UPDATE kg_entities SET name_en=%s, name_zh=%s WHERE entity_pk=%s",
                        (map_entity_en, map_entity_zh, mpk),
                    )
                    stats["mapping_updated"] += 1

            print(f"  {b['band_id']:>3} {native:<12} ext={xpk} br={bpk} map={mpk}")

        # 8. aggregation mappings must stay 0
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings")
        agg = cur.fetchone()[0]

        conn.commit()
        print("\n=== Gate 8A Brainnetome Pilot APPLY RESULT ===")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        print(f"  brain_region_aggregation_mappings: {agg} (must stay 0)")
        print("OK — committed.")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Gate 8A Brainnetome BNA246 pilot importer")
    p.add_argument("--plan", action="store_true", help="dry-run (default)")
    p.add_argument("--apply", action="store_true", help="write to DB in a transaction")
    p.add_argument("--db", default=os.environ.get("PGDATABASE", DB_DEFAULT))
    p.add_argument("--host", default=os.environ.get("PGHOST", "127.0.0.1"))
    p.add_argument("--port", default=os.environ.get("PGPORT", "5432"))
    p.add_argument("--user", default=os.environ.get("PGUSER", "postgres"))
    p.add_argument("--password", default=os.environ.get("PGPASSWORD", "postgres"))
    return p.parse_args()


def main() -> int:
    if not TSV.exists():
        print("ERROR: MISSING_AUTHORITATIVE_BRAINNETOME_SOURCE:", TSV)
        return 2
    args = _parse_args()
    print(f"  target: {args.db}  conn: {args.user}@{args.host}:{args.port} (password {_redact(args.password)})")
    if args.apply and not args.plan:
        return _apply(args)
    return _plan(args)


if __name__ == "__main__":
    sys.exit(main())
