### Task 8: 前端 API 类型(endpoints.ts)

**Files:**
- Modify: `frontend/src/api/endpoints.ts`(`PaperEvidenceTask`,约 5677-5711 行;`createPaperEvidenceBatch` 返回类型,约 5713-5730 行)

**Interfaces:**
- Produces: `PaperEvidenceTask` 新字段(前端 Task 9/10 使用);`createPaperEvidenceBatch` 返回 `task_ids`

- [ ] **Step 1: 修改类型**

`PaperEvidenceTask` 接口在 `confidence_lt: number | null` 之后追加:

```typescript
  /** 对象身份(一对一任务);旧任务迁移前为 null */
  target_id: string | null
  /** 任务级对象展示名(中文;镜像行实时,缺失回退快照/兜底) */
  display_name_cn: string | null
  /** 任务级对象展示名(英文;仅镜像行实时) */
  display_name_en: string | null
  /** 任务级展示置信度(实时 → 快照 → null=未评分) */
  display_confidence: number | null
  display_name_source: 'mirror_live' | 'task_snapshot' | 'fallback' | 'missing'
  display_confidence_source: 'mirror_live' | 'task_snapshot' | 'missing'
```

`createPaperEvidenceBatch` 返回类型改为:

```typescript
) => postJson<{ task_id: string; task_ids: string[]; target_count: number; skipped_active_targets: number; auto_started: boolean }>(
```

- [ ] **Step 2: 类型检查**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: 0 errors(仅类型扩展,无调用方受影响)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/endpoints.ts
git commit -m "feat(evidence-ui): task display fields + task_ids types"
```

---

