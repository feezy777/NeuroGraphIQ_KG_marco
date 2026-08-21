### Task 7: 前端任务卡徽章 + 证据佐证页提示条

**Files:**
- Modify: `frontend/src/pages/evidence-center/components/taskStatus.ts`(状态徽章)
- Modify: `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx`(任务卡徽章)
- Modify: `frontend/src/pages/evidence-center/modules/EvidenceCandidatesModule.tsx`(提示条,替换候选工作区)
- Modify: `frontend/src/styles.css`(chip 样式)

**Interfaces:**
- Consumes: item 的 `preprocess_outcome`(前端通过 `listPaperEvidenceTaskItems` 的 `preprocess_outcome` 字段获得;任务卡则需后端任务列表带该字段——若任务列表不含,任务卡徽章可用 `display_name` 兜底判断?不——任务列表需要新增字段。检查 `PaperEvidenceTask` 是否有 `preprocess_outcome`;无则列表接口补上,或任务卡徽章仅在有该字段时显示)

- [ ] **Step 1: 确认数据通路**

Run: `grep -n "preprocess_outcome" frontend/src/api/endpoints.ts | head -3`(item 类型已有);`grep -n "preprocess_outcome" backend/app/services/paper_evidence_service.py | grep list_paper_evidence_tasks -A3`(任务列表是否返回该字段;若否,Task 2 的 item 标记需经列表接口暴露——`list_paper_evidence_tasks` 的 enrich 已查 items(snap),可在输出补 `preprocess_outcome`)。

若任务列表接口未返回 `preprocess_outcome`:在 `_enrich_task_display` 的 items 查询(snap 查询)追加该列并输出到任务字典。

- [ ] **Step 2: 写失败测试(前端)**

`frontend/src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx` 追加:

```tsx
  it('非神经靶标任务卡显示「结构性不存在」徽章', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({
      items: [makeTask({ id: 't-nn', target_id: 'c1', display_name_cn: '右旁中央 → 右侧脑室', work_status: 'awaiting_review', preprocess_outcome: 'non_neural_target' })],
      total: 1,
    })
    renderModule()
    const card = await screen.findByTestId('evidence-task-card-t-nn')
    expect(within(card).getByText(/结构性不存在/)).toBeTruthy()
  })
```

(若任务列表不返回 preprocess_outcome,则此测试揭示字段缺失 → Step 1 补后端。)

- [ ] **Step 3: 实现(前端)**

`taskStatus.ts` 增加:

```typescript
/** 预处理结果中文标签(对象卡/任务卡徽章) */
export const PREPROCESS_OUTCOME_LABELS: Record<string, string> = {
  non_neural_target: '结构性不存在:靶标为非神经结构',
  evidence_negated: '证据否定',
  no_evidence_found: '无证据',
}
```

`EvidenceTasksModule.tsx` TaskCard:在 meta 行后、有 `task.preprocess_outcome` 且为治理类时渲染徽章:

```tsx
      {(task.preprocess_outcome === 'non_neural_target' || task.preprocess_outcome === 'evidence_negated') && (
        <div className="evidence-task-chip evidence-task-chip-bad" data-testid={`evidence-task-outcome-${task.id}`}>
          {PREPROCESS_OUTCOME_LABELS[task.preprocess_outcome]}
        </div>
      )}
```

`EvidenceCandidatesModule.tsx`:current 存在且 `preprocess_outcome === 'non_neural_target'` 时,替代候选工作区渲染提示条:

```tsx
  const nonNeuralTarget = current?.preprocess_outcome === 'non_neural_target'
  // …在渲染候选工作区的条件处:
  {nonNeuralTarget ? (
    <div className="ontology-page-message evidence-non-neural-banner" data-testid="evidence-non-neural-banner">
      该对象靶标为非神经结构(脑室/脑脊液等),解剖学上不存在投射连接,已标记为不存在。
    </div>
  ) : manualTarget ? ( /* 原候选工作区 */ ) : ( /* 原空态 */ )}
```

(具体插入点以实际 JSX 结构为准:在 `manualTarget && (<PaperSearchPanel …>` 之前拦截,或在外层条件分支。)

`styles.css` 追加:

```css
.evidence-non-neural-banner {
  margin-bottom: 12px;
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx src/pages/evidence-center/modules/EvidenceCandidatesModule.test.tsx src/pages/evidence-center/EvidenceCenterPage.test.tsx`
Expected: 全部通过(含新增用例)

- [ ] **Step 5: 类型与构建**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json && npm run build`
Expected: 0 错误

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/evidence-center/components/taskStatus.ts frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx frontend/src/pages/evidence-center/modules/EvidenceCandidatesModule.tsx frontend/src/styles.css frontend/src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx
git commit -m "feat(evidence-ui): structurally-impossible badge on task cards + banner on evidence page"
```

---

