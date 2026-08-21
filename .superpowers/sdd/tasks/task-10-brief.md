### Task 10: 数据中心入口切换 + EvidenceReviewModal 兼容壳

**Files:**
- Modify: `frontend/src/pages/data-center/FormalObjectTableSection.tsx`(或实际承载「论文佐证」按钮的组件——grep `EvidenceReviewModal` 调用点)
- Modify: `frontend/src/pages/data-center/EvidenceReviewModal.tsx`(改为兼容壳:仅跳转)
- Modify: `frontend/src/pages/data-center/EvidenceReviewModal.test.tsx`(改为壳跳转断言 + 删除依赖已迁移组件的旧断言;业务覆盖由新模块测试承接)
- Test: `frontend/src/pages/data-center/EvidenceReviewModal.test.tsx`(改造后)

- [ ] **Step 1: grep 调用点**

Run: `cd frontend/src && grep -rn "EvidenceReviewModal" pages/ components/`
Expected: 找出所有打开弹窗的位置(至少 FormalObjectTableSection / MirrorKgPanel)

- [ ] **Step 2: 改造入口**

每个调用点:原本 `setModalOpen(true)` + initialItems → 改为 `window.location.hash = buildEvidenceUrl({ module: 'candidates', taskId: initialTaskId ?? null, targetType: items[0]?.target_type ?? null, targetId: items[0]?.target_id ?? null, paperId: null })`;multi-target 场景用 sessionStorage `evidence-center.initial-queue` 存 { items } 供候选模块队列恢复。

- [ ] **Step 3: EvidenceReviewModal 改造为兼容壳**

```tsx
export function EvidenceReviewModal({ open, onClose, initialItems, initialTaskId }: {...}) {
  useEffect(() => {
    if (!open) return
    if (initialItems?.length) {
      sessionStorage.setItem('evidence-center.initial-queue', JSON.stringify({ items: initialItems, taskId: initialTaskId ?? null }))
    }
    const first = initialItems?.[0]
    window.location.hash = buildEvidenceUrl({
      module: 'candidates',
      taskId: initialTaskId ?? null,
      targetType: first?.target_type ?? null,
      targetId: first?.target_id ?? null,
      paperId: null,
    })
    onClose()
  }, [open, initialItems, initialTaskId, onClose])
  return null
}
```
删除全部业务 import(原 24 个测试大部分删除,保留入口跳转测试);import `buildEvidenceUrl` from `../evidence-center/evidenceCenterUrl`。

- [ ] **Step 4: 改造测试**

`EvidenceReviewModal.test.tsx` 重写为:
1. open 时跳转 hash 含 `/evidence-center`
2. 带 initialItems 时 sessionStorage 写入 initial-queue
3. onClose 被调用
(原五步流程/提取/审核/attach 的业务断言删除——由 EvidenceCenter 模块测试承接,见 Task 5-9)

- [ ] **Step 5: 运行全部前端测试 + build**

Run: `cd frontend && npx vitest run && npm run build`
Expected: 全绿 + build 通过

- [ ] **Step 6: 提交**

```bash
git commit -am "feat(evidence-center): 数据中心入口切换 + EvidenceReviewModal 兼容壳"
```

---

