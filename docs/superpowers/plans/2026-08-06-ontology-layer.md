# 本体层（Phase A）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建成本体层（词汇表 + 术语注册表 + 锚定），让功能术语可校验、可追溯，并接入选校/生成链路。

**Architecture:** 5 张 PostgreSQL 表（`ontology_vocabularies`、`ontology_terms`、`ontology_term_synonyms`、`ontology_term_external_mappings`、`ontology_term_groundings`）+ 业务表 `term_id` 挂接 + FastAPI 服务层 + 只读覆盖率 API。校验规则 `ONT_*` 接入 mirror 校验，提取/补全改读注册表。

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy async / psycopg3 / Pydantic v2 / React 18 + Vite + TS。

## Global Constraints

- 设计依据：`docs/superpowers/specs/2026-08-05-ontology-design.md`（用户已批准，Q1–Q12）；
- 迁移必须幂等（`IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` / `DROP CONSTRAINT IF EXISTS`）；
- 只移除 4 个 CHECK：`chk_mirror_function_category`、`chk_mirror_function_relation_type`、`chk_mirror_projection_function_category`、`chk_mirror_projection_function_relation_type`；
- 业务表 `function_term*` 原文保留；`term_id` 用真外键；category/relation_type 保留 TEXT 不加 FK；
- LLM 只能创建 `proposed` 词，绝不自动激活；
- 新代码遵循现有模式：模型放 `app/models/`、schema 放 `app/schemas/`、服务放 `app/services/`、路由放 `app/routers/`、测试放 `backend/tests/test_*.py`；
- 所有服务函数必须可 mock（不直接依赖网络/LLM）。

## File Structure

- Create `backend/migrations/20260805_ontology_layer.sql` — 建表 + 种子 + 回填 + 去 CHECK
- Create `backend/app/models/ontology.py` — 5 个 ORM 模型
- Modify `backend/app/models/mirror_kg.py` — MirrorRegionFunction.term_id
- Modify `backend/app/models/mirror_macro_clinical.py` — MirrorCircuitFunction / MirrorProjectionFunction.term_id
- Modify `backend/app/models/candidate.py` — CandidateBrainRegion uberon_iri / nifstd_iri / alignment_status
- Create `backend/app/schemas/ontology.py` — Pydantic 模型
- Create `backend/app/services/ontology_service.py` — 业务逻辑
- Create `backend/app/routers/ontology.py` — REST API
- Modify `backend/app/main.py` — 注册 `/api/ontology`
- Create `backend/tests/test_ontology.py` — 单元测试
- 后续任务：`llm_function_extraction_service.py` / `llm_projection_function_extraction_service.py`（改读注册表）、`mirror_rule_validation_service.py`（ONT_* 规则）、前端（覆盖率卡片 + proposed 列表）、`backend/scripts/term_panorama_report.py`（全景报告）、`backend/scripts/ground_existing_terms.py`（存量对齐）

---

### Task 1: 迁移文件并应用

**Files:**
- Create: `backend/migrations/20260805_ontology_layer.sql`

**Interfaces:**
- Produces: 5 张新表 + 4 个业务表 `term_id` 列 + candidate 3 列 + 词汇种子 + 4 个 CHECK 移除

- [ ] **Step 1: 编写迁移 SQL**

```sql
-- 20260805_ontology_layer.sql (idempotent)
CREATE TABLE IF NOT EXISTS ontology_vocabularies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(128) NOT NULL,
    vocab_type VARCHAR(32) NOT NULL,
    label_cn VARCHAR(256),
    label_en VARCHAR(256),
    description TEXT,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    seq INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_ontology_vocab_code_type UNIQUE (code, vocab_type)
);

CREATE TABLE IF NOT EXISTS ontology_terms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    term_code VARCHAR(128) NOT NULL UNIQUE,
    canonical_term_en VARCHAR(512) NOT NULL,
    canonical_term_cn VARCHAR(512),
    term_type VARCHAR(32) NOT NULL DEFAULT 'function',
    category VARCHAR(128),
    domain VARCHAR(128),
    role VARCHAR(128),
    effect_type VARCHAR(128),
    description TEXT,
    status VARCHAR(16) NOT NULL DEFAULT 'proposed',
    created_by VARCHAR(64) NOT NULL DEFAULT 'manual',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ontology_terms_status ON ontology_terms (status);

CREATE TABLE IF NOT EXISTS ontology_term_synonyms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    term_id UUID NOT NULL REFERENCES ontology_terms(id) ON DELETE CASCADE,
    synonym_text VARCHAR(512) NOT NULL,
    lang VARCHAR(8) NOT NULL DEFAULT 'en',
    match_type VARCHAR(16) NOT NULL,
    confidence NUMERIC,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    CONSTRAINT uq_ontology_synonym UNIQUE (term_id, synonym_text, lang)
);

CREATE TABLE IF NOT EXISTS ontology_term_external_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    term_id UUID NOT NULL REFERENCES ontology_terms(id) ON DELETE CASCADE,
    external_system VARCHAR(64) NOT NULL,
    external_iri VARCHAR(512) NOT NULL,
    match_type VARCHAR(16) NOT NULL,
    confidence NUMERIC,
    verified_by VARCHAR(64),
    CONSTRAINT uq_ontology_external UNIQUE (term_id, external_system, external_iri)
);

CREATE TABLE IF NOT EXISTS ontology_term_groundings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_type VARCHAR(32) NOT NULL,
    target_id UUID NOT NULL,
    term_id UUID REFERENCES ontology_terms(id) ON DELETE SET NULL,
    grounded_by VARCHAR(16) NOT NULL,
    confidence NUMERIC,
    created_by VARCHAR(64),
    grounded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_ontology_grounding_target UNIQUE (target_type, target_id)
);

ALTER TABLE mirror_circuit_functions ADD COLUMN IF NOT EXISTS term_id UUID REFERENCES ontology_terms(id);
ALTER TABLE mirror_projection_functions ADD COLUMN IF NOT EXISTS term_id UUID REFERENCES ontology_terms(id);
ALTER TABLE mirror_region_functions ADD COLUMN IF NOT EXISTS term_id UUID REFERENCES ontology_terms(id);
CREATE INDEX IF NOT EXISTS idx_mirror_circuit_functions_term ON mirror_circuit_functions (term_id);
CREATE INDEX IF NOT EXISTS idx_mirror_projection_functions_term ON mirror_projection_functions (term_id);
CREATE INDEX IF NOT EXISTS idx_mirror_region_functions_term ON mirror_region_functions (term_id);

ALTER TABLE candidate_brain_regions ADD COLUMN IF NOT EXISTS uberon_iri VARCHAR(512);
ALTER TABLE candidate_brain_regions ADD COLUMN IF NOT EXISTS nifstd_iri VARCHAR(512);
ALTER TABLE candidate_brain_regions ADD COLUMN IF NOT EXISTS alignment_status VARCHAR(32) NOT NULL DEFAULT 'not_aligned';

INSERT INTO ontology_vocabularies (code, vocab_type, label_en, seq) VALUES
('involved_in','relation_type','involved_in',10),
('associated_with','relation_type','associated_with',20),
('necessary_for','relation_type','necessary_for',30),
('modulates','relation_type','modulates',40),
('participates_in','relation_type','participates_in',50),
('uncertain_association','relation_type','uncertain_association',60),
('unknown','relation_type','unknown',70),
('motor','category','motor',10),
('sensory','category','sensory',20),
('visual','category','visual',30),
('auditory','category','auditory',40),
('language','category','language',50),
('memory','category','memory',60),
('emotion','category','emotion',70),
('executive_control','category','executive_control',80),
('attention','category','attention',90),
('autonomic','category','autonomic',100),
('default_mode','category','default_mode',110),
('salience','category','salience',120),
('reward','category','reward',130),
('cognitive','category','cognitive',140),
('unknown','category','unknown',150),
('structurally_connects_to','predicate','structurally_connects_to',10),
('functionally_connects_to','predicate','functionally_connects_to',20),
('effectively_connects_to','predicate','effectively_connects_to',30),
('projects_to','predicate','projects_to',40),
('associated_with','predicate','associated_with',50),
('coactivates_with','predicate','coactivates_with',60),
('has_uncertain_connection_to','predicate','has_uncertain_connection_to',70),
('has_participant_region','predicate','has_participant_region',80),
('has_ordered_participant','predicate','has_ordered_participant',90),
('instance_of_circuit_type','predicate','instance_of_circuit_type',100),
('associated_with_function','predicate','associated_with_function',110),
('involved_in_function','predicate','involved_in_function',120),
('necessary_for_function','predicate','necessary_for_function',130),
('modulates_function','predicate','modulates_function',140),
('participates_in_process','predicate','participates_in_process',150),
('close_match','predicate','close_match',160),
('partial_match','predicate','partial_match',170),
('related_to','predicate','related_to',180),
('not_same_as','predicate','not_same_as',190),
('supported_by_evidence','predicate','supported_by_evidence',200),
('generated_by_llm_run','predicate','generated_by_llm_run',210),
('confirmed_by_reviewer','predicate','confirmed_by_reviewer',220)
ON CONFLICT (code, vocab_type) DO NOTHING;

UPDATE mirror_region_functions SET function_category='unknown' WHERE function_category NOT IN ('motor','sensory','visual','auditory','language','memory','emotion','executive_control','attention','autonomic','default_mode','salience','reward','cognitive','unknown');
UPDATE mirror_region_functions SET relation_type='unknown' WHERE relation_type NOT IN ('involved_in','associated_with','necessary_for','modulates','participates_in','uncertain_association','unknown');
UPDATE mirror_projection_functions SET function_category='unknown' WHERE function_category NOT IN ('motor','sensory','visual','auditory','language','memory','emotion','executive_control','attention','autonomic','default_mode','salience','reward','cognitive','unknown');
UPDATE mirror_projection_functions SET relation_type='unknown' WHERE relation_type NOT IN ('involved_in','associated_with','necessary_for','modulates','participates_in','uncertain_association','unknown');

ALTER TABLE mirror_region_functions DROP CONSTRAINT IF EXISTS chk_mirror_function_category;
ALTER TABLE mirror_region_functions DROP CONSTRAINT IF EXISTS chk_mirror_function_relation_type;
ALTER TABLE mirror_projection_functions DROP CONSTRAINT IF EXISTS chk_mirror_projection_function_category;
ALTER TABLE mirror_projection_functions DROP CONSTRAINT IF EXISTS chk_mirror_projection_function_relation_type;
```

- [ ] **Step 2: 应用迁移（python + SQLAlchemy 执行，幂等可重跑）**

Run: `python backend/scripts/apply_migration_file.py`（临时脚本，一次执行后删除）或直接 python 内联执行 SQL 文件。
Expected: 输出 `applied 20260805_ontology_layer.sql`，无异常。

- [ ] **Step 3: 验证表存在**

Run: `SELECT COUNT(*) FROM ontology_vocabularies;` Expected: `>= 43`；`\d mirror_projection_functions` 含 `term_id`。

- [ ] **Step 4: Commit**

```bash
git add backend/migrations/20260805_ontology_layer.sql
git commit -m "feat(ontology): migration for vocabulary/term registry"
```

---

### Task 2: ORM 模型

**Files:**
- Create: `backend/app/models/ontology.py`
- Modify: `backend/app/models/mirror_kg.py`（MirrorRegionFunction 加 term_id）
- Modify: `backend/app/models/mirror_macro_clinical.py`（MirrorCircuitFunction / MirrorProjectionFunction 加 term_id）
- Modify: `backend/app/models/candidate.py`（CandidateBrainRegion 加 3 列）

**Interfaces:**
- Produces: `OntologyVocabulary`、`OntologyTerm`、`OntologyTermSynonym`、`OntologyTermExternalMapping`、`OntologyTermGrounding`（字段名与迁移一致）

- [ ] **Step 1: 写模型代码**（照抄 spec 4.x 字段，SQLAlchemy 2.0 `Mapped` 风格，见 `app/models/connection_pool.py`）
- [ ] **Step 2: 业务表加列**

```python
# mirror_kg.py MirrorRegionFunction
term_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ontology_terms.id"), nullable=True)
# mirror_macro_clinical.py MirrorCircuitFunction / MirrorProjectionFunction 同上
# candidate.py CandidateBrainRegion
uberon_iri: Mapped[str | None] = mapped_column(String(512), nullable=True)
nifstd_iri: Mapped[str | None] = mapped_column(String(512), nullable=True)
alignment_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_aligned")
```

- [ ] **Step 3: 验证 import**

Run: `python -c "from app.models.ontology import OntologyTerm; from app.models.mirror_macro_clinical import MirrorProjectionFunction; print('ok')"` Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/ontology.py backend/app/models/mirror_kg.py backend/app/models/mirror_macro_clinical.py backend/app/models/candidate.py
git commit -m "feat(ontology): ORM models for registry and term_id columns"
```

---

### Task 3: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/ontology.py`

**Interfaces:**
- Produces: `VocabularyRead`、`VocabularyCreateRequest`、`VocabularyListResponse`、`TermRead`、`TermCreateRequest`、`TermListResponse`、`GroundingRead`、`CoverageResponse`、`PanoramaItem`、`PanoramaResponse`

- [ ] **Step 1: 写 schema 代码**（`model_config = {"from_attributes": True}`，风格见 `app/schemas/connection_pool.py`）
- [ ] **Step 2: import 验证**（`python -c "from app.schemas.ontology import CoverageResponse; print('ok')"`）
- [ ] **Step 3: Commit**

---

### Task 4: 服务层

**Files:**
- Create: `backend/app/services/ontology_service.py`

**Interfaces:**
- Produces:
  - `normalize_term_key(text: str) -> str`
  - `list_vocabularies(session, vocab_type=None, status=None) -> list[OntologyVocabulary]`
  - `create_vocabulary(session, *, code, vocab_type, label_cn=None, label_en=None, description=None, seq=0) -> OntologyVocabulary`
  - `get_active_codes(session, vocab_type) -> list[str]`
  - `list_terms(session, *, status=None, q=None, limit=100, offset=0) -> tuple[list[OntologyTerm], int]`
  - `propose_term(session, *, canonical_term_en, canonical_term_cn=None, term_type="function", category=None, domain=None, role=None, effect_type=None, description=None, created_by="llm") -> OntologyTerm`
  - `activate_term(session, term_id) -> OntologyTerm`
  - `deprecate_term(session, term_id) -> OntologyTerm`
  - `merge_term(session, source_id, target_id) -> OntologyTerm`
  - `add_synonym(session, *, term_id, synonym_text, lang="en", match_type="synonym", confidence=None) -> OntologyTermSynonym`
  - `ground_deterministic(session, *, target_type, target_id, term_text, created_by="system") -> OntologyTermGrounding`
  - `run_deterministic_grounding_batch(session, target_type, limit=500) -> dict`
  - `coverage(session) -> dict`
  - `term_panorama(session, target_type, limit=5000) -> list[dict]`

- [ ] **Step 1: 写失败测试**（`backend/tests/test_ontology.py`：normalize、propose 去重、状态转换、coverage 聚合、deterministic grounding 匹配）
- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现服务**（纯函数 + session 操作；mock 友好）
- [ ] **Step 4: 跑测试确认通过**
- [ ] **Step 5: Commit**

---

### Task 5: REST API + 注册

**Files:**
- Create: `backend/app/routers/ontology.py`
- Modify: `backend/app/main.py`（注册 `/api/ontology`）

**Interfaces:**
- Produces: `GET /api/ontology/vocabularies`、`POST /api/ontology/vocabularies`、`GET /api/ontology/terms`、`POST /api/ontology/terms`、`POST /api/ontology/terms/{id}/activate|deprecate`、`POST /api/ontology/terms/{id}/merge`、`GET /api/ontology/coverage`、`GET /api/ontology/groundings`、`POST /api/ontology/groundings/run`、`GET /api/ontology/report/term-panorama`

- [ ] **Step 1: 写路由**（模式见 `app/routers/connection_pool.py`：try/except ValueError → 400，commit/rollback）
- [ ] **Step 2: 注册到 main.py**
- [ ] **Step 3: 集成测试**（TestClient + mock service，验证状态码与响应结构）
- [ ] **Step 4: Commit**

---

### Task 6: 提取/补全改读注册表

**Files:**
- Modify: `backend/app/services/llm_function_extraction_service.py`
- Modify: `backend/app/services/llm_projection_function_extraction_service.py`
- Modify: `backend/app/services/field_completion_registry.py`

**Interfaces:**
- Consumes: `ontology_service.get_active_codes(session, vocab_type)`

- [ ] **Step 1: 写测试**（mock `get_active_codes`，断言 prompt 值来自注册表）
- [ ] **Step 2: 实现**（frozenset 删除；有 session 处读取注册表，无 session 处保留默认值兜底）
- [ ] **Step 3: 跑既有相关测试**（`test_llm_function_extraction.py`、`test_llm_projection_function_extraction.py`、`test_llm_field_completion.py`）
- [ ] **Step 4: Commit**

---

### Task 7: 校验规则 ONT_*

**Files:**
- Modify: `backend/app/services/mirror_rule_validation_service.py`

- [ ] **Step 1: 写测试**（ONT_TERM_UNGROUNDED / ONT_PREDICATE_UNKNOWN / ONT_ENUM_INVALID / ONT_REGION_ALIGNMENT_MISSING）
- [ ] **Step 2: 实现**（3 硬 1 软，规则码与 spec 第 8 节一致）
- [ ] **Step 3: 跑测试 + Commit**

---

### Task 8: 本体中心独立页面（跟随全局颗粒度）

> 设计变更（2026-08-06 用户确认）：不再在数据中心放混合颗粒度的覆盖卡；新建独立「本体中心」页面，数据直接跟随系统顶部的颗粒度切换器（`useGlobalGranularity`），页面内不加自己的颗粒度筛选。待用户确认的两个开放点：页面是否含管理操作（激活/合并）、空态展示方式。

**Files:**
- Create: `frontend/src/pages/ontology-center/OntologyCenterPage.tsx`
- Modify: `frontend/src/api/endpoints.ts`（`getOntologyCoverage` 支持 `granularity_level` 参数）
- Modify: `frontend/src/App.tsx`（注册 `/ontology-center`）
- Modify: `frontend/src/layout/WorkbenchLayout.tsx`（侧边栏「本体中心」）
- Modify: `frontend/src/i18n.ts`（`nav.ontologyCenter`）
- Delete: `frontend/src/pages/data-center/OntologyCoverageCard.tsx`（并移除 DataCenterOverview 引用）
- Modify: `backend/app/services/ontology_service.py`（`coverage` / `term_panorama` 支持可选 `granularity_level`）
- Modify: `backend/app/routers/ontology.py`（`/coverage`、`/report/term-panorama` 接收 `granularity_level`）

- [ ] **Step 1: 后端 coverage/panorama 增加可选 granularity_level 过滤 + 路由参数**
- [ ] **Step 2: endpoints 增加参数透传**
- [ ] **Step 3: 创建 OntologyCenterPage**（跟随全局颗粒度；覆盖率卡片 + proposed 词列表 + 搜索/分页）
- [ ] **Step 4: 注册路由 + 侧边栏入口 + i18n**
- [ ] **Step 5: 移除数据中心旧卡**
- [ ] **Step 6: `npm run build` 通过 + 后端测试通过**
- [ ] **Step 7: Commit**

### Task 11: 实体与关系本体化（范围待确认，2026-08-06 用户提出）

> 现状：当前本体只覆盖功能术语；脑区仅有 UBERON/NIFSTD 空字段；回路/连接/步骤是实例没有术语锚定；
> connection_type / directionality / circuit_type / role / step_type / triple scope/subject/object 仍是
> DDL CHECK + Python 枚举双份硬编码，校验读代码常量而非注册表。

**待确认决策（grill-me 第 2 轮）：**
- 实体范围：脑区进术语注册表并做 UBERON/NIFSTD 对齐；回路/连接/步骤按“实例 + 类型约束”处理（推荐）；
- 关系/枚举迁移：connection_type / directionality / circuit_type / role / step_type / triple 类型全部迁入
  `ontology_vocabularies`，移除对应 CHECK，校验读注册表；
- 脑区对齐方式：核心图谱（Macro96 + AAL3）半自动 + 人工确认先行；
- 约束级别：实体/关系类型不合法 = blocker，脑区未对齐 = warning。

- [ ] **Step 1: 扩展 ontology_vocabularies 种子（connection_type/directionality/circuit_type/role/step_type/triple types）**
- [ ] **Step 2: 移除对应 CHECK（先回填非法值）**
- [ ] **Step 3: 校验器从注册表读取 VALID_* 替代代码常量**
- [ ] **Step 4: 脑区对齐（核心图谱）**
- [ ] **Step 5: ONT_* 规则覆盖实体/关系**
- [ ] **Step 6: 本体中心页面增加实体/关系 Tab**

---

### Task 9: 术语全景报告 + 存量对齐

**Files:**
- Create: `backend/scripts/term_panorama_report.py`
- Create: `backend/scripts/ground_existing_terms.py`
- Create: `backend/data/synonym_dictionary.json`（300–600 条高频映射）

- [ ] **Step 1: 全景报告脚本**（distinct lower term + count + 样例，输出 Markdown/JSON）
- [ ] **Step 2: 交付全景报告给用户过目**
- [ ] **Step 3: deterministic grounding 全量跑**
- [ ] **Step 4: LLM 残差对齐（用户确认成本后）**
- [ ] **Step 5: 验收（≥95% 锚定）**

---

### Task 10: 验收

- [ ] 运行 spec 第 13 节 5 条验收
- [ ] 运行全量相关测试套件
