"""Macro Connection canonical consolidation v1 — 核心聚类逻辑(纯函数,无 DB 依赖)。

Pipeline: Mirror Connection → Connection Cluster → Canonical Connection(本阶段只做 Cluster)

* cluster key = (src canonical id, tgt canonical id, connection_type, directionality, modality_norm, species)
* 完全一致的 mirror 行合并为同一 cluster;cluster 内按 hemisphere pattern 分组,
  left-left / right-right 等侧别保留(hemisphere-specific,不简单合并)。
* 证据聚合:mirror ids、evidence_text、llm_run_id、confidence 分布全保留。
* 质量守恒:sum(cluster.evidence_count) + self_loop + unresolved == 输入行数。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

# modality 归一化:structural_connection/diffusion_tensor → structural,functional_connection → functional
MODALITY_NORM = {
    "structural_connection": "structural",
    "diffusion_tensor": "structural",
    "functional_connection": "functional",
    "other": "other",
    None: "other",
}

MERGE_REASON_DUPLICATE = "duplicate_evidence"    # 同 hemisphere pattern 多条证据合并
MERGE_REASON_HEMISPHERE = "hemisphere_specific"  # 同一 canonical pair 下多个 hemisphere pattern 并存
MERGE_REASON_SINGLE = "single_evidence"          # 唯一证据
MERGE_REASON_SELF_LOOP = "self_loop"             # source == target,不聚类
MERGE_REASON_UNRESOLVED = "unresolved"           # 无法 grounding,不聚类


def side_of(name: str) -> str:
    """从镜像名称提取侧别:left/right 前缀 → left/right,否则 bilateral。"""
    n = (name or "").strip().lower()
    if n.startswith("left "):
        return "left"
    if n.startswith("right "):
        return "right"
    return "bilateral"


def norm_modality(modality) -> str:
    return MODALITY_NORM.get(modality, "other")


def cluster_key(src_id, tgt_id, ctype, direction, modality, species: str = "human") -> str:
    return f"{src_id}:{tgt_id}:{ctype}:{direction}:{norm_modality(modality)}:{species}"


@dataclass
class EvidenceItem:
    """单条 mirror 证据(聚类聚合单位)。"""
    mirror_id: str
    pattern: str                      # hemisphere pattern,如 "left-left"
    confidence: float | None = None
    evidence_text: str | None = None
    llm_run_id: str | None = None
    modality_original: str | None = None
    directionality: str | None = None
    source_name: str | None = None
    target_name: str | None = None


@dataclass
class Cluster:
    """canonical cluster:同一 canonical key 的 mirror 证据集合(含 hemisphere 分组)。"""
    key: str
    source_region_id: int
    target_region_id: int
    source_region_name: str
    target_region_name: str
    connection_type: str
    directionality: str
    modality_norm: str
    species: str = "human"
    evidence: list[EvidenceItem] = field(default_factory=list)

    # ---- 聚合结果 ----
    @property
    def evidence_count(self) -> int:
        return len(self.evidence)

    @property
    def hemisphere_groups(self) -> list[dict]:
        """按 hemisphere pattern 分组(保留左右侧别)。"""
        groups: dict[str, list[EvidenceItem]] = defaultdict(list)
        for ev in self.evidence:
            groups[ev.pattern].append(ev)
        return [
            {
                "pattern": pattern,
                "evidence_count": len(items),
                "mirror_connection_ids": [ev.mirror_id for ev in items],
            }
            for pattern, items in sorted(groups.items())
        ]

    @property
    def merge_reason(self) -> str:
        if len(self.hemisphere_groups) > 1:
            return MERGE_REASON_HEMISPHERE
        if self.evidence_count > 1:
            return MERGE_REASON_DUPLICATE
        return MERGE_REASON_SINGLE

    @property
    def confidence_distribution(self) -> dict:
        confs = [ev.confidence for ev in self.evidence if ev.confidence is not None]
        if not confs:
            return {"count": 0}
        buckets: Counter = Counter(round(c * 10) / 10 for c in confs)
        return {
            "count": len(confs),
            "min": min(confs),
            "max": max(confs),
            "avg": round(sum(confs) / len(confs), 4),
            "buckets": {f"{k:.1f}": v for k, v in sorted(buckets.items())},
        }

    @property
    def provenance(self) -> dict:
        llm_runs = sorted({ev.llm_run_id for ev in self.evidence if ev.llm_run_id})
        texts = [ev.evidence_text for ev in self.evidence if ev.evidence_text]
        return {
            "llm_run_ids": llm_runs,
            "evidence_texts": [t[:200] for t in texts[:10]],
            "evidence_text_total": len(texts),
            "source_versions": [],  # mirror 表无 source_version(全 None)
            "modality_original": sorted({ev.modality_original for ev in self.evidence if ev.modality_original}),
            "directionality_original": sorted({ev.directionality for ev in self.evidence if ev.directionality}),
        }

    def to_row(self) -> dict:
        return {
            "cluster_key": self.key,
            "source_region_id": self.source_region_id,
            "target_region_id": self.target_region_id,
            "source_region_name": self.source_region_name,
            "target_region_name": self.target_region_name,
            "connection_type": self.connection_type,
            "directionality": self.directionality,
            "modality_norm": self.modality_norm,
            "modality_original": self.provenance["modality_original"],
            "species": self.species,
            "hemisphere_groups": self.hemisphere_groups,
            "mirror_connection_ids": [ev.mirror_id for ev in self.evidence],
            "evidence_count": self.evidence_count,
            "merge_reason": self.merge_reason,
            "confidence_distribution": self.confidence_distribution,
            "provenance": self.provenance,
            "status": "preview",
        }


@dataclass
class ConsolidationResult:
    clusters: list[Cluster]
    self_loop_rows: list[dict]
    unresolved_rows: list[dict]

    @property
    def stats(self) -> dict:
        reasons = Counter(c.merge_reason for c in self.clusters)
        total_evidence = sum(c.evidence_count for c in self.clusters)
        return {
            "total_input_rows": (total_evidence + len(self.self_loop_rows) + len(self.unresolved_rows)),
            "clusters": len(self.clusters),
            "evidence_rows_in_clusters": total_evidence,
            "self_loop_rows": len(self.self_loop_rows),
            "unresolved_rows": len(self.unresolved_rows),
            "clusters_by_reason": dict(reasons),
        }


def build_clusters(rows: list[dict]) -> ConsolidationResult:
    """从 mirror 行列表构建 clusters。

    rows 需含:source_region_name_en/target_region_name_en、connection_type、directionality、
    modality、confidence、evidence_text、llm_run_id、source_region_candidate_id、
    target_region_candidate_id、src_canonical_id/tgt_canonical_id、src_canonical_name/tgt_canonical_name、
    g_status、unresolved_reason。
    """
    clusters: dict[str, Cluster] = {}
    self_loops: list[dict] = []
    unresolved: list[dict] = []

    for r in rows:
        ev = EvidenceItem(
            mirror_id=str(r["id"]),
            pattern=f"{side_of(r['source_region_name_en'])}-{side_of(r['target_region_name_en'])}",
            confidence=float(r["confidence"]) if r.get("confidence") is not None else None,
            evidence_text=r.get("evidence_text"),
            llm_run_id=str(r["llm_run_id"]) if r.get("llm_run_id") is not None else None,
            modality_original=r.get("modality"),
            directionality=r.get("directionality"),
            source_name=r.get("source_region_name_en"),
            target_name=r.get("target_region_name_en"),
        )
        if r.get("g_status") != "grounded":
            unresolved.append({"mirror_id": ev.mirror_id, "reason": r.get("unresolved_reason"),
                               "source": ev.source_name, "target": ev.target_name})
            continue
        src_id, tgt_id = r["src_canonical_id"], r["tgt_canonical_id"]
        if src_id == tgt_id or (r.get("src_canonical_name") or "").lower() == (r.get("tgt_canonical_name") or "").lower():
            self_loops.append({"mirror_id": ev.mirror_id, "source": ev.source_name, "target": ev.target_name})
            continue
        key = cluster_key(src_id, tgt_id, r["connection_type"], r["directionality"],
                          r["modality"], "human")
        cl = clusters.get(key)
        if cl is None:
            cl = Cluster(
                key=key,
                source_region_id=src_id,
                target_region_id=tgt_id,
                source_region_name=r["src_canonical_name"],
                target_region_name=r["tgt_canonical_name"],
                connection_type=r["connection_type"],
                directionality=r["directionality"],
                modality_norm=norm_modality(r["modality"]),
            )
            clusters[key] = cl
        cl.evidence.append(ev)

    return ConsolidationResult(
        clusters=list(clusters.values()),
        self_loop_rows=self_loops,
        unresolved_rows=unresolved,
    )
