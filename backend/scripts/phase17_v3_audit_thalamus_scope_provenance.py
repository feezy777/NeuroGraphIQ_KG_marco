"""Phase1.7 V3 - Thalamus Scope Contract Provenance Continuity audit (READ-ONLY).

Verifies the repository-level chain

    V2 (THALAMUS_G1_SCOPE_CONTRACT_V2)
      -> supersedes
    V1 (THALAMUS_G1_SCOPE_CONTRACT_V1)
      -> generated_from
    phase17_v3_resolve_thalamus_g1_ontology_scope.py  (scope-resolution generator)
      -> source inputs (frozen mapping CSVs + BNA authoritative + Macro96)

Two distinct status tiers are reported so no claim is overstated:

  A. repository_chain_verified (TRUE/FALSE)
     = V1 and V2 are git-tracked AND V2.supersedes == V1.contract_id AND the
       recorded SHA256s match the on-disk files. This level is reproducible from
       a clean clone of this commit (no external/local dependency).

  B. generator_reproducibility
     = VERIFIED_LOCAL / NOT_RERUNNABLE. Re-running the V1 generator requires
       source data CSVs (g3_to_g1 manifest, BNA authoritative subregions) that
       are entangled in a wider data relocation and may not be present in a clean
       clone of this round. When present, the generator is rerun to a temp dir
       and its output is semantically compared (timestamps stripped) against the
       stored V1; that evidence is recorded but does NOT gate status A.

No V1/V2 scientific content is modified by this audit.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
V1 = D16 / "phase17_v3_thalamus_g1_scope_contract.json"
V2 = D16 / "phase17_v3_thalamus_g1_scope_contract_v2.json"
V1_GEN = BACKEND / "scripts" / "phase17_v3_resolve_thalamus_g1_ontology_scope.py"
V1_SIDE = D16 / "phase17_v3_thalamus_g1_scope_contract_v1_provenance.json"
LINEAGE = D16 / "phase17_v3_thalamus_scope_contract_lineage.json"

# generator source inputs (may live under the wider relocation)
G3_MANIFEST = BACKEND / "data" / "integration" / "g3_to_g1" / "g3_to_g1_full_decision_coverage_manifest.csv"
BNA_SUBREG = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "brainnetome_bna246_subregions_authoritative.csv"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def repo_rel(p: Path) -> str:
    return str(p.relative_to(BACKEND.parent)).replace("\\", "/")


def git_tracked(p: Path) -> bool:
    # TRUE if present in HEAD or in the staged index (i.e. will be in this commit)
    r = subprocess.run(["git", "ls-files", "--error-unmatch", str(p)],
                       cwd=BACKEND.parent, capture_output=True)
    return r.returncode == 0


def load_json(p: Path):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _strip_ts(o):
    if isinstance(o, dict):
        return {k: _strip_ts(v) for k, v in o.items()
                if k not in ("created_at", "run_timestamp", "construction_timestamp")}
    if isinstance(o, list):
        return [_strip_ts(x) for x in o]
    return o


def _generator_rerun(v1) -> str:
    """Best-effort generator reproducibility. Returns a status string only; never
    gates repository_chain_verified (source CSVs may be absent in a clean clone)."""
    if not (G3_MANIFEST.exists() and BNA_SUBREG.exists()):
        return "NOT_RERUNNABLE"
    try:
        import importlib.util
        with tempfile.TemporaryDirectory() as td:
            spec = importlib.util.spec_from_file_location("res_scope_prov", V1_GEN)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            for name in ("OUT_SRC", "OUT_DEC", "OUT_CON", "OUT_MD"):
                setattr(mod, name, Path(td) / Path(getattr(mod, name)).name)
            mod.main()
            regen = load_json(Path(td) / V1.name)
            return "VERIFIED_LOCAL" if _strip_ts(regen) == _strip_ts(v1) else "MISMATCH"
    except Exception as exc:  # pragma: no cover
        return f"ERROR:{type(exc).__name__}"


def main() -> dict:
    checks = {}
    v1_sha = sha256(V1)
    v2_sha = sha256(V2)
    gen_sha = sha256(V1_GEN)

    checks["v1_file_exists"] = V1.exists()
    checks["v1_git_tracked"] = git_tracked(V1)
    checks["v2_git_tracked"] = git_tracked(V2)
    checks["v1_generator_git_tracked"] = git_tracked(V1_GEN)
    checks["v1_sidecar_git_tracked"] = git_tracked(V1_SIDE)
    checks["lineage_git_tracked"] = git_tracked(LINEAGE)

    v1 = load_json(V1)
    v2 = load_json(V2)
    v1_name = v1["contract"]["contract_name"]
    v2_name = v2["contract_v2"]["contract_id"]
    checks["v1_contract_name"] = v1_name
    checks["v2_contract_id"] = v2_name
    checks["v2_supersedes"] = v2["contract_v2"]["supersedes"]
    checks["supersedes_id_match"] = (v1_name == v2["contract_v2"]["supersedes"])
    checks["v1_verdict"] = v1["verdict"]
    checks["v2_verdict"] = v2["verdict"]

    lin = load_json(LINEAGE)
    checks["lineage_v1_sha_matches"] = lin["v1_sha256"] == v1_sha
    checks["lineage_v2_sha_matches"] = lin["v2_sha256"] == v2_sha
    checks["lineage_gen_sha_matches"] = lin["v1_generator_sha256"] == gen_sha
    checks["lineage_v1_git_tracked_flag"] = lin["v1_git_tracked"]
    checks["lineage_supersedes_id_match"] = lin["supersedes_id_match"]
    checks["lineage_repository_chain_verified"] = lin["repository_chain_verified"]

    side = load_json(V1_SIDE)
    checks["sidecar_snapshot_sha_matches"] = side["snapshot_sha256"] == v1_sha
    checks["sidecar_generator_sha_matches"] = side["generator_sha256"] == gen_sha

    # ---- Tier A: repository chain (clean-clone reproducible) ----
    tier_a = (
        checks["v1_git_tracked"] and checks["v2_git_tracked"]
        and checks["v1_generator_git_tracked"]
        and checks["supersedes_id_match"]
        and checks["lineage_v1_sha_matches"] and checks["lineage_v2_sha_matches"]
        and checks["lineage_gen_sha_matches"]
        and checks["sidecar_snapshot_sha_matches"] and checks["sidecar_generator_sha_matches"]
    )
    # ---- Tier B: generator reproducibility (best-effort, local-only) ----
    tier_b = _generator_rerun(v1)

    out = dict(
        v1_snapshot_authenticity=("VERIFIED" if tier_a else "UNVERIFIED"),
        repository_provenance_chain_complete=tier_a,
        generator_reproducibility=tier_b,
        checks=checks,
        v1=dict(path=repo_rel(V1), sha256=v1_sha),
        v2=dict(path=repo_rel(V2), sha256=v2_sha),
        generator=dict(path=repo_rel(V1_GEN), sha256=gen_sha),
        status_definition=(
            "Tier A repository_chain_verified = V1+V2+generator git-tracked, "
            "V2.supersedes==V1.contract_id, recorded SHA256s match on-disk. "
            "Clean-clone reproducible from this commit. "
            "Tier B generator_reproducibility is a separate best-effort rerun "
            "that needs source data CSVs (g3 manifest, BNA authoritative) which "
            "may live in the wider data relocation; it does not gate Tier A."),
        note="read-only provenance audit; no V1/V2 content modified",
    )
    out_path = D16 / "phase17_v3_thalamus_scope_provenance_audit.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print("v1_authenticity", out["v1_snapshot_authenticity"],
          "chain_complete", tier_a, "generator_reproducibility", tier_b)
    return out


if __name__ == "__main__":
    sys.exit(0 if main()["repository_provenance_chain_complete"] else 2)
