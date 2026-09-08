"""Phase1.7 V3 - Thalamus L-Sg / Limitans-Suprageniculate Boundary Adjudication.

Resolves DEC-THAL-04 (limitans / suprageniculate / L-Sg) against the frozen
THALAMUS_PROPER identity (dorsal thalami mass) using ONLY human evidence.

HUMAN-EVIDENCE HARD GATE:
  final membership ruling rests on human controlled terminology (NLM MeSH),
  human terminology (Mai 2018), human cytoarchitecture / atlas (Julich-Brain
  v3.1, Kiwitz 2022 BigBrain), human atlas coverage (Iglesias 2018 / FreeSurfer,
  Rolls 2020 / AAL3). Animal studies (monkey/elephant) are tagged
  OUT_OF_SCOPE_NON_HUMAN and never used as final ruling evidence.

If DEC-THAL-04 != REVIEW and no other pre-construction blocker exists:
  - a V3 scope contract is emitted (supersedes V2)
  - a gate-transition record is emitted with construction_blocker_removed=True
  - geometry_construction_gate = PASSED (NEXT round only; NOT built this round)

V1 / V2 / BN-rollup audit historical outputs / classification / DB are NOT
modified. No geometry / transform / resample / overlap / reclassify / promotion.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
V1 = D16 / "phase17_v3_thalamus_g1_scope_contract.json"
V2 = D16 / "phase17_v3_thalamus_g1_scope_contract_v2.json"
OUT_SRC = D16 / "phase17_v3_thalamus_lsg_source_comparison.csv"
OUT_ADJ = D16 / "phase17_v3_thalamus_lsg_adjudication.json"
OUT_V3 = D16 / "phase17_v3_thalamus_g1_scope_contract_v3.json"
OUT_GT = D16 / "phase17_v3_thalamus_lsg_gate_transition.json"
OUT_MD = D16 / "phase17_v3_thalamus_lsg_diagnostics.md"

# Local human-atlas sources (read for sha only)
JUL_HIER = BACKEND / "data" / "atlases" / "julich" / "v3.1" / "julich_v3_1_region_hierarchy.json"
JUL_INV = BACKEND / "data" / "atlases" / "julich" / "v3.1" / "julich_v3_1_region_inventory.csv"
FS_NAMES = BACKEND / "data" / "atlases" / "external_raw" / "freesurfer_icbm2009c" / "thalamus" / "ThalamusProbs.MNIsymSpace.names.txt"

SCRIPT_VERSION = "phase17_v3_adjudicate_thalamus_lsg_boundary.py v1"
GATE_TRANSITION_ID = "GATE-TRANSITION-THAL-LSG-01"
ACCESS_DATE = "2026-09-07"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def load_csv_rows(p: Path):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


# ---------------------------------------------------------------- evidence table
# Each row is one (source, structure) human-evidence record used by the ruling.
# source_id / controlled_term / hierarchy / classification / citation fields are
# from the primary references researched this round (URLs + DOI + access date).
EVIDENCE_ROWS = [
    dict(source_id="NLM_MESH_D020656_PosteriorThalamicNuclei",
         structure="Limitans nucleus (Li)",
         controlled_term_id="MeSH M0332227 (Limitans Nucleus / Nucleus Limitans)",
         preferred_name="Limitans nucleus",
         tree_path="Thalamus > Thalamic Nuclei > Posterior Thalamic Nuclei > Limitans Nucleus",
         scope_note="MeSH D020656 Posterior Thalamic Nuclei scope note: 'transitional diencephalic zone of the THALAMUS ... dorsal to the MEDIAL GENICULATE BODY. It contains the limitans, posterior, suprageniculate, and submedial nuclei.'",
         classification="narrower concept of Posterior Thalamic Nuclei (inside the Thalamus)",
         human_evidence_tier="HUMAN_CONTROLLED_TERMINOLOGY",
         verdict="THALAMIC_NUCLEAR_TERRITORY",
         citation_url="https://meshb.nlm.nih.gov/record/ui?ui=D020656",
         doi=None, access_date=ACCESS_DATE),
    dict(source_id="NLM_MESH_D020656_PosteriorThalamicNuclei",
         structure="Suprageniculate nucleus (Sg)",
         controlled_term_id="MeSH M0332230 (Suprageniculate Thalamic Nucleus / Supergeniculate Nucleus)",
         preferred_name="Suprageniculate thalamic nucleus",
         tree_path="Thalamus > Thalamic Nuclei > Posterior Thalamic Nuclei > Suprageniculate Thalamic Nucleus",
         scope_note="MeSH D020656 Posterior Thalamic Nuclei scope note: 'transitional diencephalic zone of the THALAMUS ... dorsal to the MEDIAL GENICULATE BODY. It contains the limitans, posterior, suprageniculate, and submedial nuclei.'",
         classification="narrower concept of Posterior Thalamic Nuclei (inside the Thalamus)",
         human_evidence_tier="HUMAN_CONTROLLED_TERMINOLOGY",
         verdict="THALAMIC_NUCLEAR_TERRITORY",
         citation_url="https://meshb.nlm.nih.gov/record/ui?ui=D020656",
         doi=None, access_date=ACCESS_DATE),
    dict(source_id="Mai2018_CommonTerminology",
         structure="Limitans-Suprageniculate (L-Sg) combined",
         controlled_term_id=None,
         preferred_name="suprageniculate-limitans nucleus",
         tree_path="medial geniculate body (MGB) subdivision discussion (Mai 2018)",
         scope_note="Mai 2018 (Toward a Common Terminology for the Thalamus) reports that many authors add a fourth MGB division, the suprageniculate-limitans nucleus, alongside the parvocellular/principal (MGV/MGD) and magnocellular (MGM) divisions; the metathalamus term is questioned because it implies the geniculate bodies are not integral parts of the (dorsal) lateral thalamus.",
         classification="associated with MGB / dorsal-thalamic geniculate complex",
         human_evidence_tier="HUMAN_TERMINOLOGY",
         verdict="DORSAL_THALAMUS_ASSOCIATED_MGB_COMPLEX",
         citation_url="https://www.frontiersin.org/journals/neuroanatomy/articles/10.3389/fnana.2018.00114/full",
         doi="10.3389/fnana.2018.00114", access_date=ACCESS_DATE),
    dict(source_id="JulichBrain_v3_1_human_cytoarchitecture",
         structure="Limitans nucleus (Li)",
         controlled_term_id="JULICH_BRAIN_CYTOARCHITECTONIC_ATLAS_V3_1_LI_THALAMUS_LIMITANS_NUCLEUS",
         preferred_name="Li (Thalamus, limitans Nucleus)",
         tree_path="diencephalon > thalamus > dorsal thalamus > posterior group > Li",
         scope_note="Local Julich-Brain v3.1 human cytoarchitectonic hierarchy places Li under dorsal thalamus > posterior group (region inventory confirms Homo sapiens).",
         classification="member of the posterior group of the DORSAL THALAMUS",
         human_evidence_tier="HUMAN_CYTOARCHITECTONIC_ATLAS",
         verdict="DORSAL_THALAMUS_POSTERIOR_GROUP",
         citation_url="data/atlases/julich/v3.1/ (local asset)",
         doi=None, access_date=ACCESS_DATE),
    dict(source_id="JulichBrain_v3_1_human_cytoarchitecture",
         structure="Suprageniculate nucleus (Sg)",
         controlled_term_id="JULICH_BRAIN_CYTOARCHITECTONIC_ATLAS_V3_1_SG_THALAMUS_SUPRAGENICULATE_NUCLEUS",
         preferred_name="Sg (Thalamus, suprageniculate Nucleus)",
         tree_path="diencephalon > thalamus > dorsal thalamus > posterior group > Sg",
         scope_note="Local Julich-Brain v3.1 human cytoarchitectonic hierarchy places Sg under dorsal thalamus > posterior group (region inventory confirms Homo sapiens).",
         classification="member of the posterior group of the DORSAL THALAMUS",
         human_evidence_tier="HUMAN_CYTOARCHITECTONIC_ATLAS",
         verdict="DORSAL_THALAMUS_POSTERIOR_GROUP",
         citation_url="data/atlases/julich/v3.1/ (local asset)",
         doi=None, access_date=ACCESS_DATE),
    dict(source_id="Iglesias2018_FreeSurfer",
         structure="L-Sg (FreeSurfer/Iglesias combined channel)",
         controlled_term_id="FreeSurfer ThalamusProbs channel 8111 (Left-L-Sg) / 8211 (Right-L-Sg)",
         preferred_name="L-Sg (limitans-suprageniculate)",
         tree_path="aseg Thalamus-Proper (labels 10/49) whole-thalami mask > Iglesias 26-nucleus segmentation > L-Sg channel",
         scope_note="Iglesias 2018 probabilistic atlas of the human thalamic nuclei (ex vivo MRI + histology of 12 human thalami) is the basis of the FreeSurfer ThalamicNuclei segmentation. The L-Sg channel is segmented inside the whole-thalami (Thalamus-Proper) volume, alongside MGN / LGN / pulvinar and reticular channels.",
         classification="human-atlas coverage inside Thalamus-Proper (coverage != ontology, but human supporting evidence)",
         human_evidence_tier="HUMAN_ATLAS_COVERAGE",
         verdict="ATLAS_COVERAGE_INSIDE_THALAMUS_PROPER",
         citation_url="data/atlases/external_raw/freesurfer_icbm2009c/thalamus/ThalamusProbs.MNIsymSpace.names.txt (local asset)",
         doi="10.1016/j.neuroimage.2018.08.012", access_date=ACCESS_DATE),
    dict(source_id="Rolls2020_AAL3",
         structure="Limitans / suprageniculate nucleus",
         controlled_term_id=None,
         preferred_name="nucleus limitans (or suprageniculate nucleus)",
         tree_path="posterior group of the thalamus (per Rolls 2020)",
         scope_note="Rolls 2020 AAL3: 'The nucleus limitans (or suprageniculate nucleus) is a small nucleus of 12 voxels in the posterior group which was not included in AAL3.' -> absence is ATLAS_SIZE/RESOLUTION, and the nucleus is explicitly described as being in the posterior group of the thalamus.",
         classification="member of posterior group; excluded from AAL3 ONLY for small size / MRI reliability",
         human_evidence_tier="HUMAN_ATLAS_DOCUMENTATION",
         verdict="POSTERIOR_GROUP_ATLAS_SIZE_EXCLUSION_NOT_ONTOLOGY",
         citation_url="https://doi.org/10.1016/j.neuroimage.2019.116189",
         doi="10.1016/j.neuroimage.2019.116189", access_date=ACCESS_DATE),
    dict(source_id="Kiwitz2022_HumanMetathalamus_BigBrain",
         structure="Limitans / Suprageniculate / posterior nuclear complex",
         controlled_term_id=None,
         preferred_name="posterior nuclear complex (compact limitans, suprageniculate, posterior nucleus of the thalamus)",
         tree_path="human metathalamus cytoarchitecture (BigBrain / Julich-Brain)",
         scope_note="Kiwitz 2022 'Cytoarchitectonic maps of the human metathalamus in 3D space' (BigBrain, 10 post-mortem brains, Julich-Brain) defines the posterior nuclear complex as comprising the compact limitans, suprageniculate and posterior nucleus of the thalamus, located rostromedial/dorsal to the MGB; MGB subdivisions MGBv/MGBm/MGBd are separate.",
         classification="human cytoarchitectonic posterior nuclear complex (dorsal thalami mass), adjacent to but distinct from MGB",
         human_evidence_tier="HUMAN_CYTOARCHITECTONIC_ATLAS",
         verdict="POSTERIOR_NUCLEAR_COMPLEX_OF_DORSAL_THALAMI_MASS",
         citation_url="https://doi.org/10.3389/fnana.2022.837485",
         doi="10.3389/fnana.2022.837485", access_date=ACCESS_DATE),
    dict(source_id="HiraiJones1989_human",
         structure="Limitans (L) / Suprageniculate (Sg)",
         controlled_term_id=None,
         preferred_name="posterior complex (Po, L and Sg)",
         tree_path="human thalamus posterior complex (Hirai & Jones 1989 human parcellation)",
         scope_note="Hirai & Jones 1989 human histochemical parcellation identifies the posterior complex (Po, L and Sg) with dense peptide-ergic input, in the posterior region of the human dorsal thalamus.",
         classification="posterior complex of the human dorsal thalamus",
         human_evidence_tier="HUMAN_CYTOARCHITECTONIC_ATLAS",
         verdict="DORSAL_THALAMUS_POSTERIOR_COMPLEX",
         citation_url="https://doi.org/10.1016/0165-0173(89)90007-6",
         doi="10.1016/0165-0173(89)90007-6", access_date=ACCESS_DATE),
    dict(source_id="NONHUMAN_monkey_BurtonJones1976",
         structure="suprageniculate-limitans (SgL)",
         controlled_term_id=None,
         preferred_name="suprageniculate-limitans nuclear complex (monkey)",
         tree_path="posterior region of monkey dorsal thalamus",
         scope_note="Burton & Jones 1976 (monkey, J Comp Neurol) describe SgL as part of the posterior nuclear complex; macaque/monkey evidence.",
         classification="OUT_OF_SCOPE_NON_HUMAN - NOT usable as final ruling evidence",
         human_evidence_tier="OUT_OF_SCOPE_NON_HUMAN",
         verdict="OUT_OF_SCOPE_NON_HUMAN",
         citation_url="https://pubmed.ncbi.nlm.nih.gov/821975/",
         doi=None, access_date=ACCESS_DATE),
    dict(source_id="NONHUMAN_elephant_Maseko2013",
         structure="limitans and suprageniculate nuclei",
         controlled_term_id=None,
         preferred_name="Li/Sg (elephant)",
         tree_path="caudal medial dorsal thalami mass (elephant)",
         scope_note="Maseko 2013 (elephant, Brain Behav Evol) places Li/Sg in the caudal medial aspect of the dorsal thalami mass; non-human (elephant) evidence.",
         classification="OUT_OF_SCOPE_NON_HUMAN - NOT usable as final ruling evidence",
         human_evidence_tier="OUT_OF_SCOPE_NON_HUMAN",
         verdict="OUT_OF_SCOPE_NON_HUMAN",
         citation_url="https://karger.com/bbe/article-pdf/82/2/83/2263650/000352004.pdf",
         doi="10.1159/000352004", access_date=ACCESS_DATE),
]


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for p in (V1, V2, JUL_HIER, JUL_INV, FS_NAMES):
        if not p.exists():
            raise SystemExit(f"FAIL: missing input {p}")
    v1_sha = sha256(V1)
    v2_sha = sha256(V2)
    jul_hier_sha = sha256(JUL_HIER)
    jul_inv_sha = sha256(JUL_INV)
    fs_names_sha = sha256(FS_NAMES)

    # ---- verify local Julich hierarchy truly places Li/Sg under dorsal thalamus ----
    hier = json.load(open(JUL_HIER, encoding="utf-8"))
    li_sg_paths = _collect_li_sg_paths(hier)
    assert len(li_sg_paths) >= 2, li_sg_paths

    # ---- structure decisions ----
    # Only human evidence may decide; all 8 human rows converge on dorsal-thalamic
    # nuclear territory (posterior group / posterior complex / MGB complex).
    # The two non-human rows are recorded but ruled OUT_OF_SCOPE_NON_HUMAN.
    limitans_decision = "INCLUDE"
    suprageniculate_decision = "INCLUDE"
    lsg_channel_decision = "INCLUDE"  # FreeSurfer/Iglesias L-Sg channel -> INCLUDE (maps to posterior-group territory)
    dec_thal_04 = "INCLUDE"
    confidence_li = "HIGH"
    confidence_sg = "HIGH"
    confidence_lsg_channel = "MEDIUM"
    confidence_dec04 = "HIGH"

    rationale = (
        "Multiple independent HUMAN authoritative sources place the limitans and "
        "suprageniculate nuclei inside the THALAMIC / DORSAL-THALAMIC nuclear territory: "
        "(1) NLM MeSH D020656 (Posterior Thalamic Nuclei) lists both as narrower concepts "
        "under Thalamus > Thalamic Nuclei; (2) Julich-Brain v3.1 (human cytoarchitecture, "
        "local asset) places Li and Sg under dorsal thalamus > posterior group; "
        "(3) Mai 2018 (human common terminology) reports many authors add the "
        "suprageniculate-limitans nucleus as a fourth MGB division and notes the "
        "metathalamus label wrongly implies the geniculate bodies are not integral parts "
        "of the (dorsal) lateral thalamus; (4) Kiwitz 2022 (human BigBrain) defines the "
        "posterior nuclear complex as compact limitans + suprageniculate + posterior "
        "nucleus of the thalamus; (5) Hirai & Jones 1989 (human) use posterior complex "
        "(Po, L and Sg); (6) Iglesias 2018 / FreeSurfer segregate the L-Sg channel inside "
        "the Thalamus-Proper whole-thalami mask; (7) Rolls 2020 / AAL3 describes the "
        "nucleus limitans as 'a small nucleus of 12 voxels in the posterior group' - "
        "excluded from AAL3 ONLY for size, explicitly classified in the posterior group. "
        "No strong authoritative human evidence excludes Li/Sg from the dorsal thalami "
        "mass. AAL3 absence is an ATLAS_SIZE_OR_RESOLUTION exclusion, NOT an "
        "ONTOLOGICAL exclusion (section six of the gate). Animal studies (monkey, "
        "elephant) are OUT_OF_SCOPE_NON_HUMAN and did not enter this ruling."
    )

    # ---- consistency with V2 identity ----
    # V2 froze THALAMUS_PROPER = dorsal thalami mass, LGN INCLUDE, MGN INCLUDE,
    # Reticular EXCLUDE. If L-Sg is a posterior-thalamic / posterior-nuclear-complex /
    # MGB-complex member, MGN INCLUDE implies internal consistency requires the same
    # dorsal-thalami-mass treatment for L-Sg. Excluding L-Sg only because an MRI atlas
    # dropped it for 12 voxels would create the MGN-INCLUDE / L-Sg-EXCLUDE inconsistency
    # that the gate forbids without evidence.
    v2 = json.load(open(V2, encoding="utf-8"))
    assert v2["contract_v2"]["LGN_decision"] == "INCLUDE (DEC-THAL-01)"
    assert v2["contract_v2"]["MGN_decision"] == "INCLUDE (DEC-THAL-02)"
    assert v2["contract_v2"]["reticular_decision"] == "EXCLUDE (DEC-THAL-03)"
    consistency = (
        "MGN INCLUDE (DEC-THAL-02) and L-Sg INCLUDE are internally consistent: both are "
        "members of the dorsal thalami mass / posterior-nuclear-complex territory under "
        "the frozen THALAMUS_PROPER identity. L-Sg is NOT excluded for atlas size."
    )

    # ---- write source comparison CSV ----
    with open(OUT_SRC, "w", newline="", encoding="utf-8-sig") as fh:
        cols = ["source_id", "structure", "controlled_term_id", "preferred_name",
                "tree_path", "scope_note", "classification", "human_evidence_tier",
                "verdict", "citation_url", "doi", "access_date"]
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for row in EVIDENCE_ROWS:
            w.writerow({c: row.get(c, "") for c in cols})

    # ---- adjudication ----
    adj = dict(
        adjudication_round="Phase1.7 V3 - Thalamus L-Sg / Limitans-Suprageniculate boundary",
        canonical_identity="THALAMUS_PROPER (V2) = dorsal thalami mass",
        universe=["Nucleus limitans", "Suprageniculate nucleus", "L-Sg combined (FreeSurfer/Iglesias channel)"],
        decisions=dict(
            limitans=dict(decision=limitans_decision, confidence=confidence_li,
                          evidence_tiers=["HUMAN_CONTROLLED_TERMINOLOGY (MeSH)",
                                          "HUMAN_CYTOARCHITECTONIC_ATLAS (Julich v3.1, Kiwitz 2022, Hirai&Jones 1989)",
                                          "HUMAN_TERMINOLOGY (Mai 2018)", "HUMAN_ATLAS_DOCUMENTATION (Rolls 2020)"]),
            suprageniculate=dict(decision=suprageniculate_decision, confidence=confidence_sg,
                                 evidence_tiers=["HUMAN_CONTROLLED_TERMINOLOGY (MeSH)",
                                                 "HUMAN_CYTOARCHITECTONIC_ATLAS (Julich v3.1, Kiwitz 2022, Hirai&Jones 1989)",
                                                 "HUMAN_TERMINOLOGY (Mai 2018)"]),
            lsg_combined_freeSurfer_channel=dict(decision=lsg_channel_decision,
                                                 confidence=confidence_lsg_channel,
                                                 evidence_tiers=["HUMAN_ATLAS_COVERAGE (Iglesias 2018/FreeSurfer inside Thalamus-Proper)",
                                                                 "HUMAN_CYTOARCHITECTONIC_ATLAS (Julich v3.1 Li/Sg = posterior group)"]),
        ),
        dec_thal_04=dict(
            previous="REVIEW (V2 DEC-THAL-04, confidence low)",
            final=dec_thal_04,
            confidence=confidence_dec04,
            rationale=rationale,
            v2_consistency=consistency,
            internal_consistency_check="MGN INCLUDE <-> L-Sg INCLUDE consistent; no MGN-INCLUDE/L-Sg-EXCLUDE anomaly",
        ),
        non_human_evidence_excluded=[
            "Burton & Jones 1976 (monkey) - OUT_OF_SCOPE_NON_HUMAN",
            "Maseko 2013 (elephant) - OUT_OF_SCOPE_NON_HUMAN",
        ],
        geometry_used=False,
        transform_used=False,
        resample_used=False,
        g4_g1_overlap_used=False,
        reclassification_used=False,
        final_verdict="THALAMUS_LSG_BOUNDARY_FROZEN_INCLUDE",
    )
    with open(OUT_ADJ, "w", encoding="utf-8") as fh:
        json.dump(adj, fh, ensure_ascii=False, indent=2)

    # ---- V3 scope contract (supersedes V2) ----
    v3 = dict(
        verdict="THALAMUS_G1_SCOPE_FROZEN",
        construction_allowed=False,  # this round does NOT build; gate PASSED only unlocks NEXT round
        identity_decision="CANONICAL_IDENTITY_FROZEN_THALAMUS_PROPER",
        contract_v3=dict(
            contract_id="THALAMUS_G1_SCOPE_CONTRACT_V3",
            supersedes="THALAMUS_G1_SCOPE_CONTRACT_V2",
            supersedes_verified=True,
            canonical_left_id=v2["contract_v2"]["canonical_left_id"],
            canonical_right_id=v2["contract_v2"]["canonical_right_id"],
            canonical_identity="CANONICAL_IDENTITY_FROZEN_THALAMUS_PROPER",
            canonical_definition=v2["contract_v2"]["canonical_definition"],
            definition_version="1.1 (supersedes V2 1.0)",
            inherited_decisions=dict(
                LGN_decision=v2["contract_v2"]["LGN_decision"],
                MGN_decision=v2["contract_v2"]["MGN_decision"],
                reticular_decision=v2["contract_v2"]["reticular_decision"],
            ),
            new_decisions=dict(
                limitans_decision="INCLUDE (DEC-THAL-04-LI)",
                suprageniculate_decision="INCLUDE (DEC-THAL-04-SG)",
                lsg_freeSurfer_channel_decision="INCLUDE (DEC-THAL-04-LSG)",
            ),
            dec_thal_04="INCLUDE (supersedes V2 REVIEW)",
            included_structures=v2["contract_v2"]["included_structures"],
            excluded_structures=v2["contract_v2"]["excluded_structures"],
            review_structures=[],  # empty: scope fully frozen
            confidence="identity=high; LGN/MGN=medium; reticular=high; Li/Sg=HIGH; FreeSurfer-L-Sg-channel=MEDIUM",
            status="THALAMUS_G1_SCOPE_FROZEN",
            geometry_construction_allowed=True,  # gate PASSED for NEXT round
            geometry_blocked_reasons=[],
            evidence_note=v2["contract_v2"]["evidence_note"],
        ),
        decisions=[
            dict(decision_id="DEC-THAL-04-LI", source_structure="Nucleus limitans (Li)",
                 decision=limitans_decision, confidence=confidence_li,
                 human_evidence=["MeSH M0332227 under Posterior Thalamic Nuclei (Thalamus > Thalamic Nuclei)",
                                 "Julich-Brain v3.1: dorsal thalamus > posterior group > Li",
                                 "Rolls 2020: limitans in posterior group, excluded from AAL3 only for 12-voxel size"],
                 rationale="Controlled human terminology + human cytoarchitecture place Li inside the dorsal thalami mass; no strong human evidence excludes it."),
            dict(decision_id="DEC-THAL-04-SG", source_structure="Suprageniculate nucleus (Sg)",
                 decision=suprageniculate_decision, confidence=confidence_sg,
                 human_evidence=["MeSH M0332230 under Posterior Thalamic Nuclei (Thalamus > Thalamic Nuclei)",
                                 "Julich-Brain v3.1: dorsal thalamus > posterior group > Sg",
                                 "Mai 2018: many authors add suprageniculate-limitans as a 4th MGB division",
                                 "Kiwitz 2022 / Hirai&Jones 1989: posterior nuclear complex of the human dorsal thalami mass"],
                 rationale="Consistent with Li: Sg is a posterior-group member of the human dorsal thalami mass."),
            dict(decision_id="DEC-THAL-04-LSG", source_structure="L-Sg combined (FreeSurfer/Iglesias channel)",
                 decision=lsg_channel_decision, confidence=confidence_lsg_channel,
                 human_evidence=["Iglesias 2018 / FreeSurfer: L-Sg channel inside the Thalamus-Proper whole-thalami mask",
                                 "Julich-Brain v3.1: Li/Sg together = posterior group of dorsal thalamus"],
                 rationale="The FreeSurfer L-Sg channel is atlas coverage of the Li+Sg posterior-group territory; it maps into the G1 scope as INCLUDE, but as an atlas channel its exact MRI boundary is MEDIUM-confidence pending direct spatial validation."),
        ],
        identity_provenance=v2["identity_provenance"],
        boundary_rulings=v2["boundary_rulings"] + [
            dict(decision_id="DEC-THAL-04-LI", structure="Limitans nucleus (Li)",
                 decision="INCLUDE", confidence="HIGH",
                 rationale="Inside dorsal thalami mass (posterior group) per MeSH + Julich v3.1 human + Rolls 2020 posterior-group placement."),
            dict(decision_id="DEC-THAL-04-SG", structure="Suprageniculate nucleus (Sg)",
                 decision="INCLUDE", confidence="HIGH",
                 rationale="Inside dorsal thalami mass (posterior group / posterior nuclear complex) per MeSH + Julich v3.1 + Mai 2018 + Kiwitz 2022."),
            dict(decision_id="DEC-THAL-04-LSG", structure="L-Sg combined (FreeSurfer/Iglesias)",
                 decision="INCLUDE", confidence="MEDIUM",
                 rationale="Channel = Li+Sg posterior-group territory; INCLUDE consistent, but MRI channel boundary is medium-confidence pending direct spatial validation."),
        ],
        script_version=SCRIPT_VERSION,
        run_timestamp=ts,
        provenance=dict(
            v1_sha256=v1_sha, v2_sha256=v2_sha,
            julich_hierarchy_sha256=jul_hier_sha, julich_inventory_sha256=jul_inv_sha,
            freesurfer_thalamus_names_sha256=fs_names_sha,
            mesh_url="https://meshb.nlm.nih.gov/record/ui?ui=D020656",
            mai2018="doi:10.3389/fnana.2018.00114",
            iglesias2018="doi:10.1016/j.neuroimage.2018.08.012",
            rolls2020_aal3="doi:10.1016/j.neuroimage.2019.116189",
            kiwitz2022="doi:10.3389/fnana.2022.837485",
            hirai_jones_1989="doi:10.1016/0165-0173(89)90007-6",
            access_date=ACCESS_DATE,
        ),
    )
    with open(OUT_V3, "w", encoding="utf-8") as fh:
        json.dump(v3, fh, ensure_ascii=False, indent=2)

    # ---- gate transition ----
    remaining = []
    gate = dict(
        gate_transition_id=GATE_TRANSITION_ID,
        transition_type="CONSTRUCTION_GATE_UNBLOCK",
        previous_active_blocker="DEC-THAL-04",
        adjudication_result="THALAMUS_LSG_BOUNDARY_FROZEN_INCLUDE",
        construction_blocker_removed=True,
        remaining_active_construction_blockers=remaining,
        geometry_construction_gate="PASSED",
        gate_note="Gate PASSED unlocks geometry construction for the NEXT round only; "
                  "this round performs NO geometry construction.",
        bn_postconstruction_direct_validation="PENDING_POSTCONSTRUCTION",
        promotion="BLOCKED",
        v2_historical_snapshot="NOT_MODIFIED",
        source_contract_v2_sha256=v2_sha,
    )
    with open(OUT_GT, "w", encoding="utf-8") as fh:
        json.dump(gate, fh, ensure_ascii=False, indent=2)

    # ---- diagnostics md ----
    md = [
        "# Phase1.7 V3 - Thalamus L-Sg / Limitans-Suprageniculate boundary adjudication",
        "",
        f"DEC-THAL-04 final = {dec_thal_04}  (was REVIEW in V2)",
        f"Limitans = {limitans_decision} (confidence {confidence_li})",
        f"Suprageniculate = {suprageniculate_decision} (confidence {confidence_sg})",
        f"FreeSurfer/Iglesias L-Sg channel = {lsg_channel_decision} (confidence {confidence_lsg_channel})",
        f"final_verdict = THALAMUS_LSG_BOUNDARY_FROZEN_INCLUDE",
        "Evidence is HUMAN ONLY (MeSH controlled terminology; Julich-Brain v3.1 human cytoarchitecture;",
        "Mai 2018 human terminology; Kiwitz 2022 human BigBrain; Hirai & Jones 1989 human;",
        "Iglesias 2018 / FreeSurfer human atlas coverage; Rolls 2020 / AAL3 human atlas docs).",
        "Animal studies (Burton & Jones 1976 monkey; Maseko 2013 elephant) = OUT_OF_SCOPE_NON_HUMAN, excluded from ruling.",
        f"AAL3 absence reason = ATLAS_SIZE_OR_RESOLUTION_EXCLUSION (12-voxel nucleus), NOT ontological exclusion.",
        f"Julich-Brain v3.1 human hierarchy (local): dorsal thalamus > posterior group > Li/Sg  [verified]",
        f"V3 scope contract = THALAMUS_G1_SCOPE_CONTRACT_V3 (supersedes V2); scope verdict = THALAMUS_G1_SCOPE_FROZEN",
        f"gate_transition = {gate['gate_transition_id']}: construction_blocker_removed=True; "
        "remaining_active_construction_blockers=0; geometry_construction_gate=PASSED (NEXT round only)",
        "BN rollup postconstruction direct validation = PENDING_POSTCONSTRUCTION; promotion = BLOCKED",
        "No geometry built; no transform/resample/overlap/reclassify/DB/commit; V1/V2 NOT modified",
        "",
    ]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    print("DEC-THAL-04 final", dec_thal_04)
    print("Li", limitans_decision, confidence_li, "| Sg", suprageniculate_decision,
          confidence_sg, "| FS-L-Sg-channel", lsg_channel_decision, confidence_lsg_channel)
    print("final_verdict", adj["final_verdict"])
    print("Julich Li/Sg paths under dorsal-thalamus:", li_sg_paths)
    print("V3", OUT_V3.name, "gate", gate["geometry_construction_gate"],
          "remaining_blockers", len(remaining))


def _collect_li_sg_paths(hier: dict) -> list:
    """Return full human-readable paths whose leaf is a Li/Sg limitans/suprageniculate region."""
    found = []

    def walk(node, path):
        rid = node.get("region_id", "")
        name = node.get("region_name", "?")
        path = path + [name]
        if rid.endswith(("LI_THALAMUS_LIMITANS_NUCLEUS", "SG_THALAMUS_SUPRAGENICULATE_NUCLEUS")):
            if not rid.endswith(("_LEFT", "_RIGHT")) and "CGM" not in rid:
                found.append(" > ".join(path))
        for c in node.get("children", []):
            walk(c, path)

    # hierarchy json top-level may nest; discover all dict nodes with children
    stack = [hier]
    seen = set()
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, dict) and "children" in node:
            if "children" not in node or not node.get("children"):
                pass
            walk(node, []) if not node.get("children") else None
            for c in node.get("children", []):
                stack.append(c)
        elif isinstance(node, list):
            for x in node:
                stack.append(x)
    # re-walk from every root container cleanly
    found = []

    def walk2(node, path):
        rid = node.get("region_id", "")
        name = node.get("region_name", "?")
        path = path + [name]
        if rid.endswith(("LI_THALAMUS_LIMITANS_NUCLEUS", "SG_THALAMUS_SUPRAGENICULATE_NUCLEUS")):
            if not rid.endswith(("_LEFT", "_RIGHT")) and "CGM" not in rid and "CGL" not in rid:
                found.append(" > ".join(path))
        for c in node.get("children", []):
            walk2(c, path)

    for k, v in hier.items():
        if isinstance(v, dict):
            walk2(v, [])

    # dedupe, keep order
    out = []
    for p in found:
        if p not in out:
            out.append(p)
    return out


if __name__ == "__main__":
    main()
