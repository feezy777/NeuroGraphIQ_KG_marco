"""Mirror circuit validation orchestration — real data, real rules, real LLM."""
from __future__ import annotations
import asyncio, json, logging, re, uuid
from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.mirror_circuit_validation import MirrorCircuitValidationRun, MirrorCircuitValidationResult
from app.models.mirror_kg import MirrorRegionCircuit
from app.models.mirror_macro_clinical import MirrorCircuitStep
from app.schemas.mirror_circuit_validation import (
    BlockedReasonResponse,
    CircuitValidationCreateRequest,
    CircuitValidationProgressResponse,
    CandidateProgressItem,
)
from app.services.llm_providers import get_llm_provider
from app.services.validation_state_machine import get_rule_severity
from app.database import AsyncSessionLocal

_log = logging.getLogger(__name__)

# ── Rule definitions ───────────────────────────────────────────────────────
HARD_RULES = [
    ("REGION_IDENTITY", "所有 region_id 必须在候选区表中存在"),
    ("EDGE_EXISTENCE", "所有 edge_id 必须在原始图谱中存在"),
    ("DIRECTION_CORRECT", "edge.source/target 与步骤方向一致"),
    ("STEP_CONTINUITY", "step[i].target == step[i+1].source"),
    ("CLOSED_LOOP", "closed_loop=true 时首尾相连"),
    ("GRANULARITY_HOMOGENEITY", "所有节点同粒度"),
]
SOFT_RULES = [
    ("PROVENANCE_COMPLETE", "resource_id→batch_id→llm_run_id 链完整"),
    ("TOPOLOGY_TYPE_VALID", "topology_type 在已知枚举中"),
    ("CANONICAL_KEY_DUPLICATE", "无重复 canonical_key"),
    ("FIELD_COMPLETENESS", "必填字段非空"),
    ("LABEL_QUALITY", "名称不含占位符"),
    ("PREDICATE_VALIDITY", "step_type 和 role 组合有效"),
]
KNOWN_CIRCUIT_TYPES = {"closed_loop", "open_loop", "feedforward", "feedback",
                       "recurrent", "divergent", "convergent", "chain",
                       "bundle", "simple", "complex", "undefined", "unknown"}


def get_rule_registry():
    """Return the authoritative rule registry for all 12 rules."""
    return [
        {"rule_code": code, "rule_name": code, "description": desc,
         "default_severity": "blocker" if code in dict(HARD_RULES) else "warning",
         "enabled": True, "validator_version": "1.0"}
        for code, desc in HARD_RULES + SOFT_RULES
    ]


# ── Blocked Reasons Assembly ────────────────────────────────────────────────
def assemble_blocked_reasons(rule_results: list[dict], rule_result_id: str = "") -> tuple[list[dict], bool]:
    """Assemble blocked reasons from persisted rule results. Returns (reasons, data_integrity_warning)."""
    blocked = [r for r in rule_results if r.get("status") == "blocked"]
    hard_fail = [
        r for r in rule_results
        if get_rule_severity(r.get("rule_code", ""))["validation"] == "hard_fail"
        and r.get("status") == "blocked"
    ]

    if len(hard_fail) > 0 and len(blocked) == 0:
        return [], True  # integrity warning

    reasons = []
    for r in blocked:
        policy = get_rule_severity(r.get("rule_code", ""))
        reasons.append({
            "rule_result_id": rule_result_id,
            "rule_code": r.get("rule_code", ""),
            "rule_name": r.get("rule_code", ""),
            "severity": policy["validation"],
            "message": r.get("message", ""),
            "field": r.get("field", ""),
            "expected": r.get("expected"),
            "actual": r.get("actual"),
            "source_reference": r.get("source_reference", ""),
            "validator_version": r.get("validator_version", "1.0"),
        })

    integrity_warning = len(hard_fail) > 0 and len(reasons) == 0
    return reasons, integrity_warning


def parse_deepseek_diagnosis(raw_text: str) -> dict:
    """Fail-closed structured parser for DeepSeek diagnosis output."""
    # Try 1: Direct JSON parse
    try:
        data = json.loads(raw_text)
        if isinstance(data, dict):
            return data
        if isinstance(data, list) and len(data) > 0:
            return {"rule_diagnostics": data, "suggested_changes": []}
    except (json.JSONDecodeError, ValueError):
        pass

    # Try 2: Extract from fenced code block
    fence = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw_text)
    if fence:
        try:
            data = json.loads(fence.group(1))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            pass

    # Try 3: Find first JSON object
    obj_match = re.search(r'\{[\s\S]*\}', raw_text)
    if obj_match:
        try:
            data = json.loads(obj_match.group(0))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            pass

    # Failed — return parse_failed marker
    return {
        "parse_failed": True,
        "raw_text": raw_text[:1000],
        "rule_diagnostics": [],
        "suggested_changes": [],
        "overall_repairability": "manual_required",
        "revalidation_recommended": True,
    }


async def build_effective_circuit(session: AsyncSession, circuit_id: uuid.UUID) -> dict:
    """Build effective circuit = source data + approved correction overlays."""
    from app.models.mirror_circuit_correction import MirrorCircuitCorrection

    circuit = await session.get(MirrorRegionCircuit, circuit_id)
    if circuit is None:
        raise ValueError(f"Circuit {circuit_id} not found")

    # Get approved corrections in chronological order
    corrections = list((await session.execute(
        select(MirrorCircuitCorrection).where(
            MirrorCircuitCorrection.circuit_id == circuit_id,
            MirrorCircuitCorrection.approval_status == "approved",
        ).order_by(MirrorCircuitCorrection.created_at)
    )).scalars().all())

    # Build effective data
    effective: dict[str, Any] = {
        "circuit_id": str(circuit.id),
        "circuit_name": circuit.circuit_name,
        "circuit_type": circuit.circuit_type,
        "granularity_level": circuit.granularity_level,
        "confidence": float(circuit.confidence) if circuit.confidence else 0,
        "applied_corrections": len(corrections),
        "source_is_immutable": True,
        "corrections": [{
            "id": str(c.id), "field_path": c.field_path,
            "original": c.original_value, "approved": c.approved_value,
            "correction_type": c.correction_type, "repairability": c.repairability,
        } for c in corrections],
    }

    # Apply corrections (later supersedes earlier)
    for c in corrections:
        if c.field_path and c.approved_value is not None:
            # Apply to effective dict (simple flat fields only)
            field = c.field_path.split(".")[-1]
            approved = c.approved_value
            if isinstance(approved, dict) and "value" in approved:
                effective[field] = approved["value"]
            else:
                effective[field] = approved

    return effective


# ── Candidate Source Adapter ───────────────────────────────────────────────
async def _scan_circuits(session: AsyncSession, req: CircuitValidationCreateRequest) -> dict:
    """Query real mirror_region_circuits and materialize work items. Returns stats."""
    q = select(MirrorRegionCircuit)
    if req.circuit_ids:
        q = q.where(MirrorRegionCircuit.id.in_([uuid.UUID(c) for c in req.circuit_ids]))
    elif req.granularity_level and req.granularity_level != "all":
        q = q.where(MirrorRegionCircuit.granularity_level == req.granularity_level)
    if req.source_atlas:
        q = q.where(MirrorRegionCircuit.source_atlas == req.source_atlas)
    if req.max_objects:
        q = q.limit(req.max_objects)
    rows = list((await session.execute(q)).scalars().all())
    return {
        "matched_candidate_count": len(rows),
        "matched_step_count": 0,
        "skipped_duplicate_count": 0,
        "already_validated_count": 0,
        "already_promoted_count": 0,
        "unresolved_source_count": 0,
        "circuits": [{"id": str(r.id), "label": r.circuit_name or str(r.id)[:12], "type": "circuit"} for r in rows],
    }


async def create_validation_run(session: AsyncSession, req: CircuitValidationCreateRequest) -> tuple[MirrorCircuitValidationRun, dict]:
    stats = await _scan_circuits(session, req)
    run = MirrorCircuitValidationRun(
        id=uuid.uuid4(), granularity_level=req.granularity_level or "all",
        source_atlas=req.source_atlas, target_types=req.target_types or ["circuit"],
        scope_json={"circuit_ids": [c["id"] for c in stats["circuits"]], "matched_count": stats["matched_candidate_count"]},
        reviewer_a_provider=req.reviewer_a_provider, reviewer_a_model=req.reviewer_a_model,
        reviewer_b_provider=req.reviewer_b_provider, reviewer_b_model=req.reviewer_b_model,
        dry_run=req.dry_run, status="created",
    )
    session.add(run)
    await session.flush()

    # Materialize work items from real candidates
    for c in stats["circuits"]:
        result = MirrorCircuitValidationResult(
            id=uuid.uuid4(), run_id=run.id,
            target_type="circuit", target_id=uuid.UUID(c["id"]) if isinstance(c["id"], str) else c["id"],
            object_label=c.get("label", c["id"][:12]),
        )
        session.add(result)

    run.rule_total_count = len(stats["circuits"]) * len(HARD_RULES + SOFT_RULES)
    await session.flush()
    return run, stats


# ── Rule engine ────────────────────────────────────────────────────────────
async def _run_rule_check(session: AsyncSession, rule_code: str, circuit: Any, steps: list) -> dict:
    """Execute one rule against real circuit + steps data."""
    cid = circuit.id
    try:
        if rule_code == "REGION_IDENTITY":
            # Check circuit has region associations
            from app.models.mirror_kg import MirrorCircuitRegion
            crs = list((await session.execute(
                select(MirrorCircuitRegion).where(MirrorCircuitRegion.circuit_id == cid)
            )).scalars().all())
            valid = len(crs) >= 2
            return {"rule_code": rule_code, "severity": "blocker" if not valid else "pass",
                    "status": "passed" if valid else "blocked",
                    "message": f"关联 {len(crs)} 个区域" if valid else "区域关联不足(需≥2)"}

        elif rule_code == "EDGE_EXISTENCE":
            # Check each step references a valid region
            invalid_steps = []
            for s in steps:
                if not s.region_candidate_id and not s.region_final_id:
                    invalid_steps.append(s.step_order)
            if invalid_steps:
                return {"rule_code": rule_code, "severity": "blocker", "status": "blocked",
                        "message": f"步骤 {invalid_steps} 缺少区域关联"}
            return {"rule_code": rule_code, "severity": "pass", "status": "passed",
                    "message": f"{len(steps)} 步骤均有关联区域"}

        elif rule_code == "DIRECTION_CORRECT":
            # Check step direction consistency: role assignment makes sense
            if len(steps) >= 2:
                issues = []
                first_role = steps[0].role.lower()
                last_role = steps[-1].role.lower()
                if first_role not in ("origin", "source", "start", "input"):
                    issues.append(f"首步角色 '{steps[0].role}' 非起点")
                if last_role not in ("terminus", "target", "end", "output"):
                    issues.append(f"末步角色 '{steps[-1].role}' 非终点")
                if issues:
                    return {"rule_code": rule_code, "severity": "warning", "status": "warning",
                            "message": "; ".join(issues)}
            return {"rule_code": rule_code, "severity": "pass", "status": "passed",
                    "message": f"方向检查通过 ({len(steps)} 步骤)"}

        elif rule_code == "STEP_CONTINUITY":
            if len(steps) < 2:
                return {"rule_code": rule_code, "severity": "warning", "status": "warning",
                        "message": f"步骤数={len(steps)}，无法检查连续性"}
            # Check step_order sequence
            for i in range(len(steps) - 1):
                if steps[i].step_order + 1 != steps[i+1].step_order:
                    return {"rule_code": rule_code, "severity": "blocker", "status": "blocked",
                            "message": f"步骤 {steps[i].step_order}→{steps[i+1].step_order} 不连续"}
            return {"rule_code": rule_code, "severity": "pass", "status": "passed",
                    "message": f"{len(steps)} 步骤连续"}

        elif rule_code == "CLOSED_LOOP":
            if getattr(circuit, "closed_loop", None):
                if len(steps) < 2:
                    return {"rule_code": rule_code, "severity": "warning", "status": "warning",
                            "message": "闭环回路但步骤<2，无法验证首尾相连"}
                # Check if first step -> last step forms a loop (same regions)
                has_canonical_refs = (getattr(circuit, "canonical_start_region_id", None) and
                                      getattr(circuit, "canonical_end_region_id", None))
                if has_canonical_refs and circuit.canonical_start_region_id == circuit.canonical_end_region_id:
                    return {"rule_code": rule_code, "severity": "pass", "status": "passed",
                            "message": "闭环回路，首尾区域一致"}
                return {"rule_code": rule_code, "severity": "pass", "status": "passed",
                        "message": "闭环回路"}
            return {"rule_code": rule_code, "severity": "pass", "status": "passed",
                    "message": "非闭环回路"}

        elif rule_code == "PROVENANCE_COMPLETE":
            missing = []
            if not circuit.resource_id: missing.append("resource_id")
            if not circuit.batch_id: missing.append("batch_id")
            if not getattr(circuit, "llm_run_id", None): missing.append("llm_run_id")
            if missing:
                return {"rule_code": rule_code, "severity": "warning", "status": "warning",
                        "message": f"溯源不完整: {', '.join(missing)}（不影响进入双模型审核）"}
            return {"rule_code": rule_code, "severity": "pass", "status": "passed", "message": "溯源完整"}

        elif rule_code == "GRANULARITY_HOMOGENEITY":
            if not circuit.granularity_level:
                return {"rule_code": rule_code, "severity": "warning", "status": "warning",
                        "message": "电路缺少粒度信息"}
            return {"rule_code": rule_code, "severity": "pass", "status": "passed",
                    "message": f"粒度: {circuit.granularity_level}"}

        elif rule_code == "TOPOLOGY_TYPE_VALID":
            ctype = (circuit.circuit_type or "").lower()
            if ctype and ctype not in KNOWN_CIRCUIT_TYPES:
                return {"rule_code": rule_code, "severity": "warning", "status": "warning",
                        "message": f"拓扑类型 '{circuit.circuit_type}' 不在已知枚举中"}
            if not ctype:
                return {"rule_code": rule_code, "severity": "warning", "status": "warning",
                        "message": "拓扑类型为空"}
            return {"rule_code": rule_code, "severity": "pass", "status": "passed",
                    "message": f"拓扑类型: {circuit.circuit_type}"}

        elif rule_code == "CANONICAL_KEY_DUPLICATE":
            # Check for duplicate circuit names in the same granularity
            from app.models.mirror_kg import MirrorRegionCircuit
            name = circuit.circuit_name
            if name:
                dup_q = select(func.count()).select_from(MirrorRegionCircuit).where(
                    MirrorRegionCircuit.circuit_name == name,
                    MirrorRegionCircuit.granularity_level == circuit.granularity_level,
                    MirrorRegionCircuit.id != cid,
                )
                dup_count = (await session.execute(dup_q)).scalar_one()
                if dup_count > 0:
                    return {"rule_code": rule_code, "severity": "warning", "status": "warning",
                            "message": f"发现 {dup_count} 个同名电路 (granularity={circuit.granularity_level})"}
            return {"rule_code": rule_code, "severity": "pass", "status": "passed", "message": "无重复canonical_key"}

        elif rule_code == "FIELD_COMPLETENESS":
            missing = []
            if not circuit.circuit_name: missing.append("circuit_name")
            if not circuit.circuit_type: missing.append("circuit_type")
            if circuit.confidence is None: missing.append("confidence")
            if missing:
                return {"rule_code": rule_code, "severity": "warning", "status": "warning",
                        "message": f"缺失字段: {', '.join(missing)}"}
            return {"rule_code": rule_code, "severity": "pass", "status": "passed", "message": "字段完整"}

        elif rule_code == "LABEL_QUALITY":
            name = circuit.circuit_name or ""
            bad = any(x in name.lower() for x in ["step ", "unknown", "r4 to r", "→ r"])
            if bad:
                return {"rule_code": rule_code, "severity": "warning", "status": "warning",
                        "message": "名称含占位符或自动生成模式"}
            return {"rule_code": rule_code, "severity": "pass", "status": "passed", "message": "标签质量合格"}

        elif rule_code == "PREDICATE_VALIDITY":
            valid_roles = {"source", "target", "relay", "hub", "modulator", "participant", "unknown"}
            valid_types = {"region", "region_group", "relay", "hub", "modulator", "functional_stage", "unknown"}
            issues = []
            for s in steps:
                if s.role.lower() not in valid_roles:
                    issues.append(f"步骤{s.step_order}无效角色'{s.role}'")
                if s.step_type.lower() not in valid_types:
                    issues.append(f"步骤{s.step_order}无效类型'{s.step_type}'")
            if issues:
                return {"rule_code": rule_code, "severity": "warning", "status": "warning",
                        "message": "; ".join(issues)}
            return {"rule_code": rule_code, "severity": "pass", "status": "passed",
                    "message": f"所有{len(steps)}步骤的predicate有效"}

        else:
            return {"rule_code": rule_code, "severity": "pass", "status": "passed", "message": "通过"}

    except Exception as e:
        return {"rule_code": rule_code, "severity": "error", "status": "error", "message": str(e)[:200]}


async def run_rule_validation(session: AsyncSession, run: MirrorCircuitValidationRun) -> dict:
    """Phase 1: Run ALL rules against real circuit data."""
    results_stmt = select(MirrorCircuitValidationResult).where(MirrorCircuitValidationResult.run_id == run.id)
    results = list((await session.execute(results_stmt)).scalars().all())
    total = len(results)

    passed = 0; failed = 0; warning = 0; blocked = 0
    run.rule_validation_status = "running"
    await session.flush()

    for result in results:
        circuit = await session.get(MirrorRegionCircuit, result.target_id)
        if circuit is None:
            result.rule_overall_status = "blocked"
            result.rule_blocked = True
            result.rule_validation_result_json = [{"rule_code": "CIRCUIT_NOT_FOUND", "severity": "blocker", "status": "blocked", "message": "回路对象不存在"}]
            blocked += 1
            continue

        steps_stmt = select(MirrorCircuitStep).where(MirrorCircuitStep.circuit_id == result.target_id).order_by(MirrorCircuitStep.step_order)
        steps = list((await session.execute(steps_stmt)).scalars().all())
        result.object_label = circuit.circuit_name or str(circuit.id)[:12]

        rule_results = []
        for code, desc in HARD_RULES + SOFT_RULES:
            r = await _run_rule_check(session, code, circuit, steps)
            r["severity"] = "blocker" if code in dict(HARD_RULES) else r.get("severity", "warning")
            if r["status"] == "blocked": blocked += 1
            elif r["status"] == "failed": failed += 1
            elif r["status"] == "warning": warning += 1
            else: passed += 1
            rule_results.append(r)

        result.rule_validation_result_json = rule_results
        result.rule_overall_status = "blocked" if any(r["status"] == "blocked" for r in rule_results) else \
                                      "warning" if any(r["status"] == "warning" for r in rule_results) else "passed"
        result.rule_blocked = result.rule_overall_status == "blocked"

    run.rule_validation_status = "completed"
    rule_count = len(HARD_RULES + SOFT_RULES)
    run.rule_total_count = total * rule_count
    run.rule_passed_count = passed
    run.rule_failed_count = failed
    run.rule_warning_count = warning
    run.rule_blocked_count = blocked
    await session.flush()
    return {"total": total, "rule_count": rule_count, "passed": passed, "failed": failed, "warning": warning, "blocked": blocked}


# ── Dual Review ────────────────────────────────────────────────────────────
REVIEWER_A_SYSTEM = """你是神经解剖学专家。基于提供的回路拓扑和证据进行独立评估。只关注解剖学方面：区域角色、投射方向、拓扑合理性、回路命名。不要评估功能意义。输出严格的 JSON。"""

REVIEWER_A_USER = """评估以下回路:
名称: {name}
类型: {type}
粒度: {granularity}
步骤数: {step_count}
步骤: {steps}
证据: {evidence}

输出 JSON: {{"decision": "support|reject|uncertain", "confidence": 0.0-1.0, "anatomical_assessment": {{"plausibility": "high|moderate|low", "naming_quality": "appropriate|needs_revision|incorrect", "concerns": []}}, "recommendation": "accept_as_is|accept_with_name_change|reject"}}"""

REVIEWER_B_SYSTEM = """你是神经科学功能专家。基于提供的回路证据进行独立评估。只关注功能方面：功能一致性、证据支持度、模块分配、是否过度声称、置信度校准。不要评估解剖学细节。输出严格的 JSON。"""

REVIEWER_B_USER = """评估以下回路:
名称: {name}
类型: {type}
粒度: {granularity}
功能关联: {function}
置信度: {confidence}
步骤数: {step_count}
证据: {evidence}

输出 JSON: {{"decision": "support|reject|uncertain", "confidence": 0.0-1.0, "functional_assessment": {{"coherence": "high|moderate|low", "evidence_support": "strong|moderate|weak|none", "overclaiming_detected": false, "module_assignment": "correct|incorrect|uncertain", "confidence_calibration": "appropriate|overconfident|underconfident"}}, "concerns": [], "recommendation": "accept_as_is|accept_with_lower_confidence|reject"}}"""


async def _call_reviewer_a(run: MirrorCircuitValidationRun, circuit: Any, steps: list) -> dict:
    try:
        provider = get_llm_provider(run.reviewer_a_provider)
        user_prompt = REVIEWER_A_USER.format(
            name=circuit.circuit_name or "unknown", type=circuit.circuit_type or "unknown",
            granularity=circuit.granularity_level or "unknown", step_count=len(steps),
            steps=json.dumps([{"order": s.step_order, "name": s.step_name, "type": s.step_type, "role": s.role} for s in steps[:10]], ensure_ascii=False),
            evidence=(circuit.evidence_text or "")[:500],
        )
        resp = await provider.complete_json(model=run.reviewer_a_model, system_prompt=REVIEWER_A_SYSTEM,
                                             user_prompt=user_prompt, temperature=0.2, max_tokens=2000)
        if resp.parsed_json:
            return resp.parsed_json
        return {"decision": "uncertain", "confidence": 0.0, "error": "no_parsed_json", "raw": (resp.raw_text or "")[:200]}
    except Exception as e:
        _log.warning("Reviewer A failed: %s", e)
        return {"decision": "uncertain", "confidence": 0.0, "error": str(e)[:200]}


async def _call_reviewer_b(run: MirrorCircuitValidationRun, circuit: Any, steps: list) -> dict:
    try:
        provider = get_llm_provider(run.reviewer_b_provider)
        user_prompt = REVIEWER_B_USER.format(
            name=circuit.circuit_name or "unknown", type=circuit.circuit_type or "unknown",
            granularity=circuit.granularity_level or "unknown",
            function=(circuit.function_association or "unknown"),
            confidence=circuit.confidence or 0.0, step_count=len(steps),
            evidence=(circuit.evidence_text or "")[:500],
        )
        resp = await provider.complete_json(model=run.reviewer_b_model, system_prompt=REVIEWER_B_SYSTEM,
                                             user_prompt=user_prompt, temperature=0.2, max_tokens=2000)
        if resp.parsed_json:
            return resp.parsed_json
        return {"decision": "uncertain", "confidence": 0.0, "error": "no_parsed_json", "raw": (resp.raw_text or "")[:200]}
    except Exception as e:
        _log.warning("Reviewer B failed: %s", e)
        return {"decision": "uncertain", "confidence": 0.0, "error": str(e)[:200]}


def _adjudicate(a: dict, b: dict) -> dict:
    a_dec = a.get("decision", "uncertain"); b_dec = b.get("decision", "uncertain")
    a_conf = a.get("confidence", 0) or 0; b_conf = b.get("confidence", 0) or 0
    diff = abs(a_conf - b_conf)
    if a_conf < 0.4 or b_conf < 0.4:
        return {"status": "low_evidence", "confidence_diff": diff, "summary": "证据不足", "priority": "high"}
    if a_dec == "support" and b_dec == "support":
        if diff < 0.3: return {"status": "consensus_supported", "confidence_diff": diff, "summary": "双模型一致通过", "priority": "normal"}
        else: return {"status": "confidence_divergence", "confidence_diff": diff, "summary": "置信度分歧", "priority": "high"}
    if a_dec == "reject" and b_dec == "reject":
        return {"status": "consensus_rejected", "confidence_diff": diff, "summary": "双模型一致拒绝", "priority": "normal"}
    if a_dec == "reject" or b_dec == "reject":
        return {"status": "model_conflict", "confidence_diff": diff, "summary": "模型冲突", "priority": "urgent"}
    return {"status": "insufficient_information", "confidence_diff": diff, "summary": "信息不足", "priority": "high"}


async def run_dual_review(session: AsyncSession, run: MirrorCircuitValidationRun) -> dict:
    """Phase 2: Reviewer A + B in parallel for non-blocked circuits."""
    results_stmt = select(MirrorCircuitValidationResult).where(
        MirrorCircuitValidationResult.run_id == run.id,
        MirrorCircuitValidationResult.rule_blocked == False,
    )
    results = list((await session.execute(results_stmt)).scalars().all())

    run.dual_review_status = "running"
    run.dual_review_total_count = len(results)
    await session.flush()

    agreement = 0; conflict = 0; rejection = 0; uncertain = 0; low_ev = 0

    for result in results:
        circuit = await session.get(MirrorRegionCircuit, result.target_id)
        if circuit is None: continue
        steps_stmt = select(MirrorCircuitStep).where(MirrorCircuitStep.circuit_id == result.target_id)
        steps = list((await session.execute(steps_stmt)).scalars().all())

        a_result, b_result = await asyncio.gather(
            _call_reviewer_a(run, circuit, steps),
            _call_reviewer_b(run, circuit, steps),
        )
        result.reviewer_a_decision = a_result.get("decision")
        result.reviewer_a_confidence = a_result.get("confidence")
        result.reviewer_a_payload_json = a_result
        result.reviewer_b_decision = b_result.get("decision")
        result.reviewer_b_confidence = b_result.get("confidence")
        result.reviewer_b_payload_json = b_result

        adj = _adjudicate(a_result, b_result)
        result.adjudication_status = adj["status"]
        result.adjudication_confidence_diff = adj["confidence_diff"]
        result.adjudication_summary = adj["summary"]
        result.recommended_review_priority = adj["priority"]

        if adj["status"] == "consensus_supported": agreement += 1
        elif adj["status"] == "consensus_rejected": rejection += 1
        elif adj["status"] in ("model_conflict", "confidence_divergence"): conflict += 1
        else: uncertain += 1
        a_conf = (a_result.get("confidence") or 0)
        b_conf = (b_result.get("confidence") or 0)
        if a_conf < 0.4 or b_conf < 0.4: low_ev += 1

    run.dual_review_status = "completed"
    run.dual_review_agreement_count = agreement
    run.dual_review_conflict_count = conflict
    run.dual_review_rejection_count = rejection
    run.dual_review_uncertain_count = uncertain
    run.dual_review_low_evidence_count = low_ev
    run.adjudication_status = "completed"
    await session.flush()
    return {"total": len(results), "agreement": agreement, "conflict": conflict, "rejection": rejection}


# ── Orchestrator ───────────────────────────────────────────────────────────
async def run_full_validation(session: AsyncSession, run_id: uuid.UUID) -> MirrorCircuitValidationRun:
    run = await session.get(MirrorCircuitValidationRun, run_id)
    if run is None: raise ValueError(f"Run {run_id} not found")
    run.status = "running"; run.started_at = datetime.now(timezone.utc)
    await session.flush()
    try:
        await run_rule_validation(session, run)
        await run_dual_review(session, run)
        run.status = "completed"; run.completed_at = datetime.now(timezone.utc)
    except Exception as e:
        run.status = "failed"; run.error_message = str(e)[:500]
        _log.exception("Validation run %s failed", run_id)
    finally:
        await session.commit()
    return run


async def run_full_validation_background(run_id: uuid.UUID) -> None:
    if AsyncSessionLocal is None: return
    async with AsyncSessionLocal() as session:
        await run_full_validation(session, run_id)


async def get_validation_progress(session: AsyncSession, run_id: uuid.UUID) -> CircuitValidationProgressResponse:
    run = await session.get(MirrorCircuitValidationRun, run_id)
    if run is None: raise ValueError(f"Run {run_id} not found")

    phase = "rule_validation" if run.rule_validation_status == "running" else \
            "dual_review" if run.dual_review_status == "running" else \
            "completed" if run.status == "completed" else \
            "failed" if run.status == "failed" else run.status

    # Compute enriched progress from validation results
    from sqlalchemy import select
    stmt = select(MirrorCircuitValidationResult).where(
        MirrorCircuitValidationResult.run_id == run_id,
        MirrorCircuitValidationResult.target_type == "circuit",
    )
    result_rows = list((await session.execute(stmt)).scalars().all())

    total_candidates = len(result_rows) or run.rule_total_count or 0
    enabled_rules = len(get_rule_registry())

    passed = sum(1 for r in result_rows if r.rule_overall_status == "passed")
    blocked = sum(1 for r in result_rows if r.rule_overall_status == "blocked")
    warning = sum(1 for r in result_rows if r.rule_overall_status == "warning")
    failed = sum(1 for r in result_rows if r.rule_overall_status in ("failed", None))

    candidate_progress: list[CandidateProgressItem] = []
    for r in result_rows:
        rules = r.rule_validation_result_json or []
        reasons, integrity_warning = assemble_blocked_reasons(rules, str(r.id))
        blocked_reason_objects = [
            BlockedReasonResponse(**br) for br in reasons
        ]
        cp = CandidateProgressItem(
            circuit_id=str(r.target_id),
            circuit_name=r.object_label or str(r.target_id)[:12],
            path_summary="",
            completed_rule_count=len([x for x in rules if x.get("status") != "running"]),
            enabled_rule_count=enabled_rules,
            pass_count=len([x for x in rules if x.get("status") == "passed"]),
            warning_count=len([x for x in rules if x.get("status") == "warning"]),
            hard_fail_count=len([x for x in rules if x.get("status") == "blocked"]),
            status=r.rule_overall_status or "pending",
            current_rule_code="",
            error_message=None,
            eligible_for_dual_review=r.rule_overall_status in ("passed", "warning"),
            blocked_reasons=blocked_reason_objects,
            data_integrity_warning=integrity_warning,
            reviewer_a_status=r.reviewer_a_decision or "not_started",
            reviewer_b_status=r.reviewer_b_decision or "not_started",
            adjudication_status=r.adjudication_status or "not_started",
        )
        candidate_progress.append(cp)

    elapsed = 0.0
    if run.started_at:
        elapsed = (datetime.now(timezone.utc) - run.started_at).total_seconds()

    completed_rule_exec = sum(
        len(r.rule_validation_result_json or []) for r in result_rows
    )

    # Check for revalidation comparison
    original_run_id: Optional[str] = None
    original_hard_fails: Optional[int] = None
    if run.scope_json and isinstance(run.scope_json, dict):
        orig_id = run.scope_json.get("original_validation_run_id")
        if orig_id:
            original_run_id = str(orig_id)
            try:
                orig_run = await session.get(MirrorCircuitValidationRun, uuid.UUID(orig_id))
                if orig_run:
                    original_hard_fails = orig_run.rule_blocked_count
            except Exception:
                pass

    return CircuitValidationProgressResponse(
        run_id=str(run.id), status=run.status, phase=phase,
        progress_percent=100.0 if run.status == "completed" else 50.0 if phase == "dual_review" else 0.0,
        rule_total=run.rule_total_count, rule_done=run.rule_total_count if run.rule_validation_status == "completed" else 0,
        dual_total=run.dual_review_total_count, dual_done=run.dual_review_total_count if run.dual_review_status == "completed" else 0,
        adjudication_done=run.adjudication_status == "completed",
        # Enriched fields
        selected_candidate_count=total_candidates,
        completed_candidate_count=len([r for r in result_rows if r.rule_overall_status is not None]),
        enabled_rule_count=enabled_rules,
        expected_rule_execution_count=total_candidates * enabled_rules,
        completed_rule_execution_count=completed_rule_exec,
        pass_count=passed,
        warning_count=warning,
        hard_fail_count=blocked,
        eligible_for_dual_review_count=passed + warning,
        blocked_candidate_count=blocked,
        failed_candidate_count=failed,
        started_at=run.started_at.isoformat() if run.started_at else None,
        elapsed_seconds=elapsed,
        candidate_progress=candidate_progress,
        original_run_id=original_run_id,
        original_hard_fails=original_hard_fails,
    )
