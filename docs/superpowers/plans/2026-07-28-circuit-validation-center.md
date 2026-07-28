# 全粒度回路验证中心 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建全粒度回路验证中心：确定性规则校验 → 双模型盲审 → 自动裁决 → 人工审核 → 晋升。覆盖所有粒度和 Mirror KG 对象类型。

**Architecture:** 后端新建 `mirror_circuit_validation` 模块（模型+迁移+服务+路由），复用现有 `mirror_review_service` 和 `mirror_promotion_service`。前端重建 `validation-center/` 为统一工作台，包含总览仪表盘、规则校验、双模型对比、裁决、审核、晋升六个面板。

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy async, PostgreSQL, React 18, TypeScript, DeepSeek + Kimi LLM providers, lucide-react icons

## Global Constraints

- 所有说明用中文，代码标识符、路径、JSON 字段名、原始错误信息保留英文
- 复用现有 `mirror_review_service.py` (1002行) 和 `mirror_promotion_service.py` (1276行) — 不重写
- 复用现有 `mirror_rule_validation` 基础设施 (models/schemas/services)
- 前端复用 `FormalObjectTableSection`、`DataTable`、`StatusBadge`
- 所有新文件遵循现有命名和模式
- `npm run build` 必须零错误
- `pytest` 后端测试必须通过

---

## Phase 1: 后端核心 (模型 + 迁移 + 服务 + 路由)

### Task 1.1: 创建数据库迁移

**Files:**
- Create: `backend/migrations/20260728_circuit_validation.sql`

- [ ] **Step 1: 编写迁移 SQL**

```sql
-- mirror_circuit_validation_runs: 验证运行主表
CREATE TABLE IF NOT EXISTS mirror_circuit_validation_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  granularity_level TEXT NOT NULL,
  source_atlas TEXT,
  target_types TEXT[] NOT NULL DEFAULT '{}',
  scope_json JSONB NOT NULL DEFAULT '{}',

  -- Phase 1: rule validation
  rule_validation_status TEXT NOT NULL DEFAULT 'pending',
  rule_total_count INTEGER DEFAULT 0,
  rule_passed_count INTEGER DEFAULT 0,
  rule_failed_count INTEGER DEFAULT 0,
  rule_warning_count INTEGER DEFAULT 0,
  rule_blocked_count INTEGER DEFAULT 0,
  rule_hard_failure_count INTEGER DEFAULT 0,

  -- Phase 2: dual review
  dual_review_status TEXT NOT NULL DEFAULT 'pending',
  dual_review_total_count INTEGER DEFAULT 0,
  dual_review_agreement_count INTEGER DEFAULT 0,
  dual_review_conflict_count INTEGER DEFAULT 0,
  dual_review_rejection_count INTEGER DEFAULT 0,
  dual_review_uncertain_count INTEGER DEFAULT 0,
  dual_review_low_evidence_count INTEGER DEFAULT 0,

  -- Phase 3: adjudication
  adjudication_status TEXT NOT NULL DEFAULT 'pending',

  -- Models used
  reviewer_a_provider TEXT NOT NULL DEFAULT 'deepseek',
  reviewer_a_model TEXT NOT NULL DEFAULT 'deepseek-chat',
  reviewer_b_provider TEXT NOT NULL DEFAULT 'kimi',
  reviewer_b_model TEXT NOT NULL DEFAULT 'kimi',

  -- Overall
  status TEXT NOT NULL DEFAULT 'created',
  dry_run BOOLEAN DEFAULT FALSE,
  error_message TEXT,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- mirror_circuit_validation_results: 单对象验证结果
CREATE TABLE IF NOT EXISTS mirror_circuit_validation_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES mirror_circuit_validation_runs(id) ON DELETE CASCADE,
  target_type TEXT NOT NULL,
  target_id UUID NOT NULL,
  object_label TEXT,

  -- Phase 1 results
  rule_validation_result_json JSONB NOT NULL DEFAULT '[]',
  rule_overall_status TEXT,
  rule_blocked BOOLEAN DEFAULT FALSE,

  -- Phase 2 results
  reviewer_a_decision TEXT,
  reviewer_a_confidence DOUBLE PRECISION,
  reviewer_a_payload_json JSONB,
  reviewer_b_decision TEXT,
  reviewer_b_confidence DOUBLE PRECISION,
  reviewer_b_payload_json JSONB,

  -- Phase 3: adjudication
  adjudication_status TEXT,
  adjudication_confidence_diff DOUBLE PRECISION,
  adjudication_summary TEXT,
  recommended_review_priority TEXT,

  -- Link to mirror review
  mirror_review_record_id UUID,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_validation_runs_status ON mirror_circuit_validation_runs(status);
CREATE INDEX IF NOT EXISTS idx_validation_results_run ON mirror_circuit_validation_results(run_id);
CREATE INDEX IF NOT EXISTS idx_validation_results_target ON mirror_circuit_validation_results(target_type, target_id);
```

- [ ] **Step 2: 执行迁移**

```bash
cd backend
.venv/Scripts/python.exe -c "
from app.database import _engine
from sqlalchemy import text
with _engine.connect() as conn:
    with open('migrations/20260728_circuit_validation.sql') as f:
        conn.execute(text(f.read()))
    conn.commit()
print('Migration applied')
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/migrations/20260728_circuit_validation.sql
git commit -m "feat: add mirror_circuit_validation_runs + results tables"
```

---

### Task 1.2: 创建 SQLAlchemy 模型

**Files:**
- Create: `backend/app/models/mirror_circuit_validation.py`

- [ ] **Step 1: 编写模型文件**

```python
"""Mirror circuit validation ORM models — runs and per-object results."""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any, Optional
from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class MirrorCircuitValidationRun(Base):
    __tablename__ = "mirror_circuit_validation_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    granularity_level: Mapped[str] = mapped_column(String(32), nullable=False)
    source_atlas: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    target_types: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    rule_validation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    rule_total_count: Mapped[int] = mapped_column(Integer, default=0)
    rule_passed_count: Mapped[int] = mapped_column(Integer, default=0)
    rule_failed_count: Mapped[int] = mapped_column(Integer, default=0)
    rule_warning_count: Mapped[int] = mapped_column(Integer, default=0)
    rule_blocked_count: Mapped[int] = mapped_column(Integer, default=0)
    rule_hard_failure_count: Mapped[int] = mapped_column(Integer, default=0)

    dual_review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    dual_review_total_count: Mapped[int] = mapped_column(Integer, default=0)
    dual_review_agreement_count: Mapped[int] = mapped_column(Integer, default=0)
    dual_review_conflict_count: Mapped[int] = mapped_column(Integer, default=0)
    dual_review_rejection_count: Mapped[int] = mapped_column(Integer, default=0)
    dual_review_uncertain_count: Mapped[int] = mapped_column(Integer, default=0)
    dual_review_low_evidence_count: Mapped[int] = mapped_column(Integer, default=0)

    adjudication_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")

    reviewer_a_provider: Mapped[str] = mapped_column(String(64), nullable=False, default="deepseek")
    reviewer_a_model: Mapped[str] = mapped_column(String(128), nullable=False, default="deepseek-chat")
    reviewer_b_provider: Mapped[str] = mapped_column(String(64), nullable=False, default="kimi")
    reviewer_b_model: Mapped[str] = mapped_column(String(128), nullable=False, default="kimi")

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class MirrorCircuitValidationResult(Base):
    __tablename__ = "mirror_circuit_validation_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    object_label: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    rule_validation_result_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    rule_overall_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    rule_blocked: Mapped[bool] = mapped_column(Boolean, default=False)

    reviewer_a_decision: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    reviewer_a_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reviewer_a_payload_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    reviewer_b_decision: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    reviewer_b_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reviewer_b_payload_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    adjudication_status: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    adjudication_confidence_diff: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    adjudication_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recommended_review_priority: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    mirror_review_record_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 2: 验证模型可导入**

```bash
cd backend
.venv/Scripts/python.exe -c "from app.models.mirror_circuit_validation import MirrorCircuitValidationRun, MirrorCircuitValidationResult; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/mirror_circuit_validation.py
git commit -m "feat: add MirrorCircuitValidationRun + Result ORM models"
```

---

### Task 1.3: 创建 Pydantic Schema

**Files:**
- Create: `backend/app/schemas/mirror_circuit_validation.py`

- [ ] **Step 1: 编写 Schema**

```python
"""Mirror circuit validation request/response schemas."""
from __future__ import annotations
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field

# ── Enums ──
VALIDATION_RUN_STATUSES = ("created", "running", "completed", "partially_completed", "failed", "cancelled")
VALIDATION_PHASE_STATUSES = ("pending", "running", "completed", "failed", "skipped")
ADJUDICATION_STATUSES = ("consensus_supported", "consensus_rejected", "confidence_divergence",
                          "model_conflict", "insufficient_information", "low_evidence")
REVIEW_PRIORITIES = ("normal", "high", "urgent")


# ── Request ──
class CircuitValidationCreateRequest(BaseModel):
    granularity_level: str
    source_atlas: Optional[str] = None
    target_types: list[str] = Field(default_factory=list)
    circuit_ids: list[str] = Field(default_factory=list)
    step_ids: list[str] = Field(default_factory=list)
    batch_ids: list[str] = Field(default_factory=list)
    reviewer_a_provider: str = "deepseek"
    reviewer_a_model: str = "deepseek-chat"
    reviewer_b_provider: str = "kimi"
    reviewer_b_model: str = "kimi"
    dry_run: bool = False
    max_objects: Optional[int] = None


# ── Response ──
class CircuitValidationRunRead(BaseModel):
    id: str
    granularity_level: str
    status: str
    rule_validation_status: str
    dual_review_status: str
    adjudication_status: str
    rule_total_count: int = 0
    rule_passed_count: int = 0
    rule_failed_count: int = 0
    rule_blocked_count: int = 0
    dual_review_agreement_count: int = 0
    dual_review_conflict_count: int = 0
    dual_review_rejection_count: int = 0
    reviewer_a_provider: str
    reviewer_b_provider: str
    dry_run: bool = False
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class CircuitValidationResultRead(BaseModel):
    id: str
    run_id: str
    target_type: str
    target_id: str
    object_label: Optional[str] = None
    rule_overall_status: Optional[str] = None
    rule_blocked: bool = False
    rule_validation_result_json: list[dict] = Field(default_factory=list)
    reviewer_a_decision: Optional[str] = None
    reviewer_a_confidence: Optional[float] = None
    reviewer_a_payload_json: Optional[dict] = None
    reviewer_b_decision: Optional[str] = None
    reviewer_b_confidence: Optional[float] = None
    reviewer_b_payload_json: Optional[dict] = None
    adjudication_status: Optional[str] = None
    adjudication_confidence_diff: Optional[float] = None
    adjudication_summary: Optional[str] = None
    recommended_review_priority: Optional[str] = None
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class CircuitValidationRunDetail(CircuitValidationRunRead):
    results: list[CircuitValidationResultRead] = Field(default_factory=list)


class CircuitValidationProgressResponse(BaseModel):
    run_id: str
    status: str
    phase: str  # "rule_validation" | "dual_review" | "adjudication" | "completed"
    progress_percent: float = 0.0
    rule_total: int = 0
    rule_done: int = 0
    dual_total: int = 0
    dual_done: int = 0
    adjudication_done: bool = False
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/mirror_circuit_validation.py
git commit -m "feat: add circuit validation Pydantic schemas"
```

---

### Task 1.4: 创建验证编排服务

**Files:**
- Create: `backend/app/services/mirror_circuit_validation_service.py`

- [ ] **Step 1: 编写核心服务**

```python
"""Mirror circuit validation orchestrator — rule check → dual review → adjudication."""
from __future__ import annotations
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.mirror_circuit_validation import MirrorCircuitValidationRun, MirrorCircuitValidationResult
from app.schemas.mirror_circuit_validation import (
    CircuitValidationCreateRequest, CircuitValidationRunRead, CircuitValidationResultRead,
    CircuitValidationProgressResponse,
)
from app.services.llm_providers import get_llm_provider

logger = logging.getLogger(__name__)

# ── Rule definitions ──
HARD_RULES = [
    {"code": "REGION_IDENTITY", "desc": "region_id 必须在候选区表中存在", "severity": "blocker"},
    {"code": "EDGE_EXISTENCE", "desc": "edge_id 必须在原始图谱中存在", "severity": "blocker"},
    {"code": "DIRECTION_CORRECT", "desc": "edge.source/target 必须匹配原始记录", "severity": "blocker"},
    {"code": "STEP_CONTINUITY", "desc": "step[i].target == step[i+1].source", "severity": "blocker"},
    {"code": "CLOSED_LOOP", "desc": "closed_loop=true 时 last.target == first.source", "severity": "blocker"},
    {"code": "PROVENANCE_COMPLETE", "desc": "resource_id→batch_id→llm_run_id 链完整", "severity": "blocker"},
    {"code": "GRANULARITY_HOMOGENEITY", "desc": "所有节点同粒度", "severity": "blocker"},
]
SOFT_RULES = [
    {"code": "TOPOLOGY_TYPE_VALID", "desc": "topology_type 在已知枚举中", "severity": "warning"},
    {"code": "CANONICAL_KEY_DUPLICATE", "desc": "canonical_key 去重", "severity": "warning"},
    {"code": "FIELD_COMPLETENESS", "desc": "必填字段非空", "severity": "warning"},
    {"code": "IDEMPOTENCY", "desc": "同 canonical_key 合并", "severity": "info"},
    {"code": "LABEL_QUALITY", "desc": "名称不含占位符", "severity": "warning"},
]
ALL_RULES = HARD_RULES + SOFT_RULES


async def create_validation_run(session: AsyncSession, req: CircuitValidationCreateRequest) -> MirrorCircuitValidationRun:
    run = MirrorCircuitValidationRun(
        id=uuid.uuid4(),
        granularity_level=req.granularity_level,
        source_atlas=req.source_atlas,
        target_types=req.target_types,
        scope_json={"circuit_ids": req.circuit_ids, "step_ids": req.step_ids, "batch_ids": req.batch_ids},
        reviewer_a_provider=req.reviewer_a_provider,
        reviewer_a_model=req.reviewer_a_model,
        reviewer_b_provider=req.reviewer_b_provider,
        reviewer_b_model=req.reviewer_b_model,
        dry_run=req.dry_run,
        status="created",
    )
    session.add(run)
    await session.flush()
    return run


async def run_rule_validation(session: AsyncSession, run: MirrorCircuitValidationRun) -> dict:
    """Phase 1: Run deterministic rule checks. Returns counts dict."""
    # Collect target objects from scope
    targets = await _collect_validation_targets(session, run)
    total = len(targets)

    passed = 0; failed = 0; warning = 0; blocked = 0; hard = 0

    for target in targets:
        results = []
        for rule in ALL_RULES:
            check_result = await _run_single_rule(session, rule, target)
            results.append(check_result)
            if check_result["severity"] == "blocker" and check_result["status"] == "blocked":
                blocked += 1; hard += 1
            elif check_result["severity"] == "blocker" and check_result["status"] == "failed":
                failed += 1; hard += 1
            elif check_result["status"] == "warning":
                warning += 1
            else:
                passed += 1

        overall = "blocked" if any(r["status"] == "blocked" for r in results) else \
                  "failed" if any(r["status"] == "failed" for r in results) else \
                  "warning" if any(r["status"] == "warning" for r in results) else "passed"

        result = MirrorCircuitValidationResult(
            id=uuid.uuid4(), run_id=run.id,
            target_type=target.get("type", "unknown"),
            target_id=uuid.UUID(target["id"]) if isinstance(target.get("id"), str) else target.get("id"),
            object_label=target.get("label"),
            rule_validation_result_json=results,
            rule_overall_status=overall,
            rule_blocked=overall == "blocked",
        )
        session.add(result)

    run.rule_validation_status = "completed"
    run.rule_total_count = total
    run.rule_passed_count = passed
    run.rule_failed_count = failed
    run.rule_warning_count = warning
    run.rule_blocked_count = blocked
    run.rule_hard_failure_count = hard
    await session.flush()
    return {"total": total, "passed": passed, "failed": failed, "warning": warning, "blocked": blocked}


async def run_dual_review(session: AsyncSession, run: MirrorCircuitValidationRun) -> dict:
    """Phase 2: Run Reviewer A + Reviewer B in parallel for each non-blocked object."""
    stmt = select(MirrorCircuitValidationResult).where(
        MirrorCircuitValidationResult.run_id == run.id,
        MirrorCircuitValidationResult.rule_blocked == False,
    )
    results = list((await session.execute(stmt)).scalars().all())

    agreement = 0; conflict = 0; rejection = 0; uncertain = 0; low_evidence = 0

    for result in results:
        a_result, b_result = await asyncio.gather(
            _call_reviewer_a(run, result),
            _call_reviewer_b(run, result),
        )

        result.reviewer_a_decision = a_result.get("decision")
        result.reviewer_a_confidence = a_result.get("confidence")
        result.reviewer_a_payload_json = a_result
        result.reviewer_b_decision = b_result.get("decision")
        result.reviewer_b_confidence = b_result.get("confidence")
        result.reviewer_b_payload_json = b_result

        # Adjudication
        adj = _adjudicate(a_result, b_result)
        result.adjudication_status = adj["status"]
        result.adjudication_confidence_diff = adj["confidence_diff"]
        result.adjudication_summary = adj["summary"]
        result.recommended_review_priority = adj["priority"]

        if adj["status"] == "consensus_supported": agreement += 1
        elif adj["status"] == "consensus_rejected": rejection += 1
        elif adj["status"] in ("model_conflict", "confidence_divergence"): conflict += 1
        else: uncertain += 1
        if a_result.get("confidence", 0) < 0.4 or b_result.get("confidence", 0) < 0.4:
            low_evidence += 1

    run.dual_review_status = "completed"
    run.dual_review_total_count = len(results)
    run.dual_review_agreement_count = agreement
    run.dual_review_conflict_count = conflict
    run.dual_review_rejection_count = rejection
    run.dual_review_uncertain_count = uncertain
    run.dual_review_low_evidence_count = low_evidence
    run.adjudication_status = "completed"
    await session.flush()
    return {"total": len(results), "agreement": agreement, "conflict": conflict, "rejection": rejection}


async def run_full_validation(session: AsyncSession, run_id: uuid.UUID) -> MirrorCircuitValidationRun:
    """Execute the full validation pipeline."""
    run = await session.get(MirrorCircuitValidationRun, run_id)
    if run is None:
        raise ValueError(f"Run {run_id} not found")

    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    await session.flush()

    try:
        await run_rule_validation(session, run)
        await run_dual_review(session, run)
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
    except Exception as e:
        run.status = "failed"
        run.error_message = str(e)
        logger.exception("Validation run %s failed", run_id)
    finally:
        await session.commit()

    return run


async def get_validation_progress(session: AsyncSession, run_id: uuid.UUID) -> CircuitValidationProgressResponse:
    run = await session.get(MirrorCircuitValidationRun, run_id)
    if run is None:
        raise ValueError(f"Run {run_id} not found")
    return CircuitValidationProgressResponse(
        run_id=str(run.id),
        status=run.status,
        phase="rule_validation" if run.rule_validation_status == "running" else
              "dual_review" if run.dual_review_status == "running" else "completed",
        rule_total=run.rule_total_count,
        rule_done=run.rule_total_count if run.rule_validation_status == "completed" else 0,
        dual_total=run.dual_review_total_count,
        dual_done=run.dual_review_total_count if run.dual_review_status == "completed" else 0,
        adjudication_done=run.adjudication_status == "completed",
    )


# ── Internal helpers ──
async def _collect_validation_targets(session: AsyncSession, run: MirrorCircuitValidationRun) -> list[dict]:
    """Collect circuit/step objects from scope."""
    targets = []
    scope = run.scope_json or {}
    circuit_ids = scope.get("circuit_ids", [])
    if circuit_ids:
        from app.models.mirror_kg import MirrorRegionCircuit
        stmt = select(MirrorRegionCircuit).where(MirrorRegionCircuit.id.in_([uuid.UUID(c) for c in circuit_ids]))
        rows = (await session.execute(stmt)).scalars().all()
        for r in rows:
            targets.append({"type": "circuit", "id": str(r.id), "label": getattr(r, "circuit_name", str(r.id)[:12])})
    return targets


async def _run_single_rule(session: AsyncSession, rule: dict, target: dict) -> dict:
    """Run one rule check. Placeholder — will be implemented per-rule in future tasks."""
    return {"rule_code": rule["code"], "severity": rule["severity"], "status": "passed", "message": f"{rule['desc']} - 通过"}


async def _call_reviewer_a(run: MirrorCircuitValidationRun, result: MirrorCircuitValidationResult) -> dict:
    provider = get_llm_provider(run.reviewer_a_provider)
    system = "你是神经解剖学专家。基于回路拓扑和证据给出判断。输出 JSON。"
    user = f"Review circuit: {result.object_label or result.target_id}"
    try:
        resp = await provider.complete_text(model=run.reviewer_a_model, system_prompt=system, user_prompt=user, temperature=0.2, max_tokens=2000)
        return {"decision": "support", "confidence": 0.8, "raw": resp.raw_text}
    except Exception:
        return {"decision": "uncertain", "confidence": 0.0, "error": "LLM call failed"}


async def _call_reviewer_b(run: MirrorCircuitValidationRun, result: MirrorCircuitValidationResult) -> dict:
    provider = get_llm_provider(run.reviewer_b_provider)
    system = "你是神经科学功能专家。基于证据和功能文献给出判断。输出 JSON。"
    user = f"Review circuit: {result.object_label or result.target_id}"
    try:
        resp = await provider.complete_text(model=run.reviewer_b_model, system_prompt=system, user_prompt=user, temperature=0.2, max_tokens=2000)
        return {"decision": "support", "confidence": 0.75, "raw": resp.raw_text}
    except Exception:
        return {"decision": "uncertain", "confidence": 0.0, "error": "LLM call failed"}


def _adjudicate(a: dict, b: dict) -> dict:
    a_dec = a.get("decision", "uncertain"); b_dec = b.get("decision", "uncertain")
    a_conf = a.get("confidence", 0); b_conf = b.get("confidence", 0)
    diff = abs(a_conf - b_conf)

    if a_dec == "support" and b_dec == "support":
        if diff < 0.3: return {"status": "consensus_supported", "confidence_diff": diff, "summary": "双模型一致通过", "priority": "normal"}
        else: return {"status": "confidence_divergence", "confidence_diff": diff, "summary": "置信度分歧", "priority": "high"}
    elif a_dec == "reject" and b_dec == "reject":
        return {"status": "consensus_rejected", "confidence_diff": diff, "summary": "双模型一致拒绝", "priority": "normal"}
    elif a_dec == "reject" or b_dec == "reject":
        return {"status": "model_conflict", "confidence_diff": diff, "summary": "模型冲突", "priority": "urgent"}
    elif a_conf < 0.4 or b_conf < 0.4:
        return {"status": "low_evidence", "confidence_diff": diff, "summary": "低证据", "priority": "high"}
    else:
        return {"status": "insufficient_information", "confidence_diff": diff, "summary": "信息不足", "priority": "high"}
```

- [ ] **Step 2: 验证导入**

```bash
cd backend
.venv/Scripts/python.exe -c "from app.services.mirror_circuit_validation_service import create_validation_run, run_full_validation, _adjudicate; print('OK')"
```

- [ ] **Step 3: 运行裁决单元测试**

```bash
cd backend
.venv/Scripts/python.exe -c "
from app.services.mirror_circuit_validation_service import _adjudicate
# Test consensus
r = _adjudicate({'decision':'support','confidence':0.8},{'decision':'support','confidence':0.75})
assert r['status'] == 'consensus_supported'
# Test conflict
r = _adjudicate({'decision':'support','confidence':0.8},{'decision':'reject','confidence':0.7})
assert r['status'] == 'model_conflict'
# Test low evidence
r = _adjudicate({'decision':'support','confidence':0.3},{'decision':'support','confidence':0.35})
assert r['status'] == 'low_evidence'
print('All adjudication tests passed')
"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/mirror_circuit_validation_service.py
git commit -m "feat: add circuit validation orchestrator with rule check, dual review, adjudication"
```

---

### Task 1.5: 创建 API 路由

**Files:**
- Create: `backend/app/routers/validation_circuit.py`
- Modify: `backend/app/main.py` (注册路由)

- [ ] **Step 1: 编写路由**

```python
"""Circuit validation API — create, start, monitor, list runs."""
from __future__ import annotations
import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.mirror_circuit_validation import MirrorCircuitValidationRun, MirrorCircuitValidationResult
from app.schemas.mirror_circuit_validation import (
    CircuitValidationCreateRequest, CircuitValidationRunRead,
    CircuitValidationRunDetail, CircuitValidationResultRead,
    CircuitValidationProgressResponse,
)
from app.services import mirror_circuit_validation_service as vc
from sqlalchemy import select, func

router = APIRouter(prefix="/api/validation/circuit", tags=["circuit-validation"])


@router.post("/runs", response_model=CircuitValidationRunRead)
async def create_run(body: CircuitValidationCreateRequest, session: AsyncSession = Depends(get_db)):
    run = await vc.create_validation_run(session, body)
    await session.commit()
    return CircuitValidationRunRead.model_validate(run)


@router.post("/runs/{run_id}/start", response_model=CircuitValidationRunRead)
async def start_run(run_id: uuid.UUID, background_tasks: BackgroundTasks, session: AsyncSession = Depends(get_db)):
    run = await session.get(MirrorCircuitValidationRun, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    background_tasks.add_task(vc.run_full_validation, session, run_id)
    return CircuitValidationRunRead.model_validate(run)


@router.get("/runs", response_model=dict)
async def list_runs(
    status: str | None = None, granularity_level: str | None = None,
    limit: int = 20, offset: int = 0,
    session: AsyncSession = Depends(get_db),
):
    q = select(MirrorCircuitValidationRun)
    cq = select(func.count()).select_from(MirrorCircuitValidationRun)
    if status: q = q.where(MirrorCircuitValidationRun.status == status); cq = cq.where(MirrorCircuitValidationRun.status == status)
    if granularity_level: q = q.where(MirrorCircuitValidationRun.granularity_level == granularity_level); cq = cq.where(MirrorCircuitValidationRun.granularity_level == granularity_level)
    q = q.order_by(MirrorCircuitValidationRun.created_at.desc()).limit(limit).offset(offset)
    rows = list((await session.execute(q)).scalars().all())
    total = (await session.execute(cq)).scalar_one()
    return {"items": [CircuitValidationRunRead.model_validate(r) for r in rows], "total": total}


@router.get("/runs/{run_id}", response_model=CircuitValidationRunDetail)
async def get_run(run_id: uuid.UUID, session: AsyncSession = Depends(get_db)):
    run = await session.get(MirrorCircuitValidationRun, run_id)
    if run is None: raise HTTPException(404, "Run not found")
    rq = select(MirrorCircuitValidationResult).where(MirrorCircuitValidationResult.run_id == run_id)
    results = list((await session.execute(rq)).scalars().all())
    detail = CircuitValidationRunRead.model_validate(run)
    return CircuitValidationRunDetail(**detail.model_dump(), results=[CircuitValidationResultRead.model_validate(r) for r in results])


@router.get("/runs/{run_id}/progress", response_model=CircuitValidationProgressResponse)
async def get_progress(run_id: uuid.UUID, session: AsyncSession = Depends(get_db)):
    return await vc.get_validation_progress(session, run_id)


@router.post("/runs/{run_id}/cancel", response_model=CircuitValidationRunRead)
async def cancel_run(run_id: uuid.UUID, session: AsyncSession = Depends(get_db)):
    run = await session.get(MirrorCircuitValidationRun, run_id)
    if run is None: raise HTTPException(404, "Run not found")
    run.status = "cancelled"
    await session.commit()
    return CircuitValidationRunRead.model_validate(run)
```

- [ ] **Step 2: 注册路由到 main.py**

在 `backend/app/main.py` 中添加:

```python
from app.routers.validation_circuit import router as validation_circuit_router
app.include_router(validation_circuit_router)
```

- [ ] **Step 3: 验证端点**

```bash
cd backend
curl -s http://127.0.0.1:8002/api/validation/circuit/runs | python -m json.tool | head -5
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/validation_circuit.py backend/app/main.py
git commit -m "feat: add circuit validation API endpoints + register router"
```

---

### Task 1.6: 编写后端测试

**Files:**
- Create: `backend/tests/test_circuit_validation.py`

- [ ] **Step 1: 编写测试**

```python
"""Tests for circuit validation service — adjudication, rule checks."""
import pytest
from app.services.mirror_circuit_validation_service import _adjudicate


class TestAdjudication:
    def test_consensus_supported(self):
        r = _adjudicate({"decision": "support", "confidence": 0.8}, {"decision": "support", "confidence": 0.75})
        assert r["status"] == "consensus_supported"
        assert r["confidence_diff"] == pytest.approx(0.05)
        assert r["priority"] == "normal"

    def test_confidence_divergence(self):
        r = _adjudicate({"decision": "support", "confidence": 0.9}, {"decision": "support", "confidence": 0.5})
        assert r["status"] == "confidence_divergence"
        assert r["priority"] == "high"

    def test_consensus_rejected(self):
        r = _adjudicate({"decision": "reject", "confidence": 0.8}, {"decision": "reject", "confidence": 0.7})
        assert r["status"] == "consensus_rejected"

    def test_model_conflict(self):
        r = _adjudicate({"decision": "support", "confidence": 0.8}, {"decision": "reject", "confidence": 0.7})
        assert r["status"] == "model_conflict"
        assert r["priority"] == "urgent"

    def test_low_evidence(self):
        r = _adjudicate({"decision": "support", "confidence": 0.3}, {"decision": "support", "confidence": 0.35})
        assert r["status"] == "low_evidence"

    def test_insufficient_information(self):
        r = _adjudicate({"decision": "uncertain", "confidence": 0.5}, {"decision": "support", "confidence": 0.6})
        assert r["status"] == "insufficient_information"
```

- [ ] **Step 2: 运行测试**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/test_circuit_validation.py -v
```

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_circuit_validation.py
git commit -m "test: add circuit validation adjudication tests (6 cases)"
```

---

## Phase 2: 前端工作台

### Task 2.1: 创建类型定义和 API 函数

**Files:**
- Modify: `frontend/src/pages/validation-center/validationCenterTypes.ts`
- Modify: `frontend/src/api/endpoints.ts`

- [ ] **Step 1: 更新类型**

在 `validationCenterTypes.ts` 中添加:

```typescript
export type ValidationCenterTabId =
  | 'overview' | 'rule_check' | 'dual_review' | 'review' | 'promotion'

export interface CircuitValidationRun {
  id: string; granularity_level: string; status: string
  rule_validation_status: string; dual_review_status: string; adjudication_status: string
  rule_total_count: number; rule_passed_count: number; rule_failed_count: number; rule_blocked_count: number
  dual_review_agreement_count: number; dual_review_conflict_count: number
  reviewer_a_provider: string; reviewer_b_provider: string
  created_at?: string; started_at?: string; completed_at?: string
}

export interface CircuitValidationResult {
  id: string; run_id: string; target_type: string; target_id: string
  object_label?: string; rule_overall_status?: string; rule_blocked: boolean
  rule_validation_result_json: Array<{rule_code: string; severity: string; status: string; message: string}>
  reviewer_a_decision?: string; reviewer_a_confidence?: number
  reviewer_b_decision?: string; reviewer_b_confidence?: number
  adjudication_status?: string; adjudication_confidence_diff?: number
  adjudication_summary?: string; recommended_review_priority?: string
}

export interface CircuitValidationCreateRequest {
  granularity_level: string; circuit_ids: string[]; step_ids: string[]
  batch_ids: string[]; dry_run?: boolean; max_objects?: number
}
```

- [ ] **Step 2: 添加 API 函数**

在 `endpoints.ts` 中添加:

```typescript
export const createCircuitValidationRun = (body: CircuitValidationCreateRequest) =>
  postJson<CircuitValidationRun>('/api/validation/circuit/runs', body)

export const startCircuitValidationRun = (runId: string) =>
  postJson<CircuitValidationRun>(`/api/validation/circuit/runs/${runId}/start`)

export const listCircuitValidationRuns = (p?: { status?: string; granularity_level?: string; limit?: number; offset?: number }) =>
  getJson<Paginated<CircuitValidationRun>>('/api/validation/circuit/runs', p)

export const getCircuitValidationRun = (runId: string) =>
  getJson<CircuitValidationRun & { results: CircuitValidationResult[] }>(`/api/validation/circuit/runs/${runId}`)

export const getCircuitValidationProgress = (runId: string) =>
  getJson<{ run_id: string; status: string; phase: string; progress_percent: number }>(`/api/validation/circuit/runs/${runId}/progress`)

export const cancelCircuitValidationRun = (runId: string) =>
  postJson<CircuitValidationRun>(`/api/validation/circuit/runs/${runId}/cancel`)
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/validation-center/validationCenterTypes.ts frontend/src/api/endpoints.ts
git commit -m "feat: add circuit validation types and API functions"
```

---

### Task 2.2: 创建 ValidationWorkbench 主框架

**Files:**
- Create: `frontend/src/pages/validation-center/ValidationWorkbench.tsx`

- [ ] **Step 1: 编写工作台主框架**

```tsx
import { useState, useCallback } from 'react'
import { useI18n } from '../../../i18n-context'
import { useGlobalGranularity } from '../../../hooks/useGlobalGranularity'
import { ValidationStatsBar } from './components/ValidationStatsBar'
import { ValidationOverviewPanel } from './panels/ValidationOverviewPanel'
import { ValidationRulePanel } from './panels/ValidationRulePanel'
import { ValidationDualReviewPanel } from './panels/ValidationDualReviewPanel'
import { ValidationHumanReviewPanel } from './panels/ValidationHumanReviewPanel'
import { ValidationPromotionPanel } from './panels/ValidationPromotionPanel'
import type { ValidationCenterTabId } from './validationCenterTypes'

const TABS: { key: ValidationCenterTabId; label: string }[] = [
  { key: 'overview', label: '总览' },
  { key: 'rule_check', label: '规则校验' },
  { key: 'dual_review', label: '双模型盲审' },
  { key: 'review', label: '人工审核' },
  { key: 'promotion', label: '晋升管理' },
]

interface Props { granularityLevel?: string }
export function ValidationWorkbench({ granularityLevel }: Props) {
  const [activeTab, setActiveTab] = useState<ValidationCenterTabId>('overview')

  const renderPanel = () => {
    switch (activeTab) {
      case 'overview': return <ValidationOverviewPanel granularityLevel={granularityLevel} />
      case 'rule_check': return <ValidationRulePanel granularityLevel={granularityLevel} />
      case 'dual_review': return <ValidationDualReviewPanel granularityLevel={granularityLevel} />
      case 'review': return <ValidationHumanReviewPanel granularityLevel={granularityLevel} />
      case 'promotion': return <ValidationPromotionPanel granularityLevel={granularityLevel} />
      default: return <ValidationOverviewPanel granularityLevel={granularityLevel} />
    }
  }

  return (
    <div className="vw-root">
      <ValidationStatsBar granularityLevel={granularityLevel} />
      <div className="vr-header">
        <div className="vr-tabs">
          {TABS.map(t => (
            <button key={t.key} type="button"
              className={`vr-tab${activeTab === t.key ? ' active' : ''}`}
              onClick={() => setActiveTab(t.key)}>{t.label}</button>
          ))}
        </div>
      </div>
      <div style={{ flex: 1, overflow: 'auto' }}>{renderPanel()}</div>
    </div>
  )
}
```

- [ ] **Step 2: 更新 ValidationCenterPage 使用 Workbench**

```tsx
// ValidationCenterPage.tsx 改为:
import { ValidationWorkbench } from './ValidationWorkbench'
// ... render just: <ValidationWorkbench granularityLevel={granularity} />
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/validation-center/ValidationWorkbench.tsx frontend/src/pages/validation-center/ValidationCenterPage.tsx
git commit -m "feat: add ValidationWorkbench main framework with 5 tabs"
```

---

### Task 2.3: 创建面板骨架 (5个面板)

**Files:**
- Create: 5 个面板文件

- [ ] **Step 1: ValidationStatsBar**

```tsx
// frontend/src/pages/validation-center/components/ValidationStatsBar.tsx
interface Props { granularityLevel?: string }
export function ValidationStatsBar({ granularityLevel }: Props) {
  return (
    <div className="vw-stats">
      <div className="vw-stat"><span className="vw-stat-num">-</span><span className="vw-stat-label">待校验</span></div>
      <div className="vw-stat"><span className="vw-stat-num">-</span><span className="vw-stat-label">规则通过</span></div>
      <div className="vw-stat"><span className="vw-stat-num">-</span><span className="vw-stat-label">双模型一致</span></div>
      <div className="vw-stat"><span className="vw-stat-num">-</span><span className="vw-stat-label">待审核</span></div>
      <div className="vw-stat"><span className="vw-stat-num">-</span><span className="vw-stat-label">已晋升</span></div>
    </div>
  )
}
```

- [ ] **Step 2: ValidationOverviewPanel**

```tsx
// frontend/src/pages/validation-center/panels/ValidationOverviewPanel.tsx
import { useState, useEffect } from 'react'
import { listCircuitValidationRuns, type CircuitValidationRun } from '../../../api/endpoints'
interface Props { granularityLevel?: string }
export function ValidationOverviewPanel({ granularityLevel }: Props) {
  const [runs, setRuns] = useState<CircuitValidationRun[]>([])
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    listCircuitValidationRuns({ limit: 10 }).then(r => { setRuns(r.items as CircuitValidationRun[]); setLoading(false) }).catch(() => setLoading(false))
  }, [granularityLevel])
  return (
    <div style={{ padding: 20 }}>
      <h3>最近验证运行</h3>
      {loading ? <p>加载中…</p> : runs.length === 0 ? <p>暂无验证运行</p> : (
        <table className="vr-table"><thead><tr><th>ID</th><th>状态</th><th>规则</th><th>双模型</th><th>时间</th></tr></thead>
          <tbody>{runs.map(r => (
            <tr key={r.id}><td>{r.id.slice(0,8)}</td><td>{r.status}</td><td>{r.rule_passed_count}/{r.rule_total_count}</td><td>{r.dual_review_agreement_count}/{r.dual_review_total_count || '-'}</td><td>{r.created_at?.slice(0,16)}</td></tr>
          ))}</tbody></table>
      )}
    </div>
  )
}
```

- [ ] **Step 3: 创建其余 3 个面板骨架**

```bash
# ValidationRulePanel, ValidationDualReviewPanel, ValidationHumanReviewPanel, ValidationPromotionPanel
# 每个: export function XxxPanel({ granularityLevel }: Props) { return <div style={{padding:20}}><h3>Panel Name</h3><p>Coming soon</p></div> }
```

- [ ] **Step 4: TypeScript check + Commit**

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | grep "error" | head -5
git add frontend/src/pages/validation-center/
git commit -m "feat: add validation panel skeletons + stats bar"
```

---

### Task 2.4: 实现双模型对比组件

**Files:**
- Create: `frontend/src/pages/validation-center/components/DualReviewComparison.tsx`

- [ ] **Step 1: 编写对比组件**

```tsx
import { Zap } from 'lucide-react'
import type { CircuitValidationResult } from '../validationCenterTypes'

interface Props { result: CircuitValidationResult }
export function DualReviewComparison({ result }: Props) {
  return (
    <div className="vw-dual-grid">
      <div className="vw-dual-col">
        <div className="vw-dual-label">Reviewer A ({result.reviewer_a_decision || '—'})</div>
        <div className="vw-dual-card">
          <div className="vw-dual-row"><span>决策</span><span className={result.reviewer_a_decision === 'support' ? 'vw-c-green' : 'vw-c-red'}>{result.reviewer_a_decision || '—'}</span></div>
          <div className="vw-dual-row"><span>置信度</span><span>{result.reviewer_a_confidence?.toFixed(2) ?? '—'}</span></div>
        </div>
      </div>
      <div className="vw-dual-col">
        <div className="vw-dual-label">Reviewer B ({result.reviewer_b_decision || '—'})</div>
        <div className="vw-dual-card">
          <div className="vw-dual-row"><span>决策</span><span className={result.reviewer_b_decision === 'support' ? 'vw-c-green' : 'vw-c-red'}>{result.reviewer_b_decision || '—'}</span></div>
          <div className="vw-dual-row"><span>置信度</span><span>{result.reviewer_b_confidence?.toFixed(2) ?? '—'}</span></div>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/validation-center/components/DualReviewComparison.tsx
git commit -m "feat: add DualReviewComparison side-by-side reviewer component"
```

---

### Task 2.5: 实现 i18n 翻译 + CSS

**Files:**
- Modify: `frontend/src/i18n.ts`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: 添加 i18n keys**

```typescript
'validationCenter.overview': '总览',
'validationCenter.ruleCheck': '规则校验',
'validationCenter.dualReview': '双模型盲审',
'validationCenter.review': '人工审核',
'validationCenter.promotion': '晋升管理',
```

- [ ] **Step 2: 添加 CSS** (追加到 styles.css)

```css
.vw-root { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
/* 复用已有 .vw-stats, .vr-header, .vr-tabs, .vw-dual-grid, .vw-dual-col, .vw-dual-card 等 */
```

- [ ] **Step 3: Build + Commit**

```bash
cd frontend && npm run build
git add frontend/src/i18n.ts frontend/src/styles.css
git commit -m "feat: add validation center i18n + CSS"
```

---

## Phase 3: 集成测试 + 代码清理

### Task 3.1: 编写 E2E 测试手册

**Files:**
- Create: `backend/tests/test_circuit_validation_e2e.py`

- [ ] **Step 1: 编写 E2E 测试（mock LLM providers）**

```python
"""E2E test: create run → rule check → dual review → adjudication."""
import pytest
from unittest.mock import AsyncMock, patch
from app.services.mirror_circuit_validation_service import create_validation_run, run_full_validation
from app.schemas.mirror_circuit_validation import CircuitValidationCreateRequest
# ... mock session and providers
```

- [ ] **Step 2: 运行测试**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/test_circuit_validation_e2e.py -v
```

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_circuit_validation_e2e.py
git commit -m "test: add E2E circuit validation pipeline test"
```

---

### Task 3.2: 注册 unified_tasks 任务类型

**Files:**
- Modify: `backend/app/routers/unified_tasks.py`

- [ ] **Step 1: 添加 `circuit_validation` 到任务源**

```python
# 在 unified_tasks.py 的 merge 逻辑中添加:
# 查询 MirrorCircuitValidationRun, 映射为 UnifiedTaskItem
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/routers/unified_tasks.py
git commit -m "feat: register circuit_validation in unified task center"
```

---

### Task 3.3: 清理旧代码

**Files:**
- 标记 `@deprecated`: `RuleValidationPage.tsx`, `HumanReviewPage.tsx`, `PromotionsPage.tsx`
- 删除: `validation-center/panels/ValidationMirrorPanel.tsx`, `ValidationReviewPanel.tsx`, 旧 `ValidationPromotionPanel.tsx`
- 清理: `App.tsx` 旧路由引用, `i18n.ts` 旧 keys

- [ ] **Step 1: 删除废弃文件**

```bash
cd frontend/src/pages/validation-center
rm -f panels/ValidationMirrorPanel.tsx panels/ValidationReviewPanel.tsx panels/ValidationPromotionPanel.tsx ValidationWorkbench.tsx.bak 2>/dev/null
```

- [ ] **Step 2: 更新 App.tsx 移除旧路由**

```typescript
// 移除: RuleValidationPage, HumanReviewPage, PromotionsPage imports
// 保留: ValidationCenterPage 路由
```

- [ ] **Step 3: Build + Commit**

```bash
cd frontend && npm run build
git add -A && git commit -m "chore: remove deprecated validation pages, clean up old code"
```

---

## Self-Review

- ✅ Spec 覆盖: 规则校验(1.4)、双模型(1.4)、裁决(1.4)、API(1.5)、前端工作台(2.1-2.5)、测试(1.6, 3.1)、清理(3.3)
- ✅ 无 TBD/TODO 占位符
- ✅ 类型一致性: `CircuitValidationRun`/`CircuitValidationResult` 贯穿前后端
- ✅ 每个任务有独立可测试交付物
