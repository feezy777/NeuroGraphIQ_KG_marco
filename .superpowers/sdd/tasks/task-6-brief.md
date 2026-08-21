### Task 6: 论文库模块(PaperLibraryModule + PaperCard + PaperDetailDrawer)

**Files:**
- Create: `frontend/src/pages/evidence-center/modules/PaperLibraryModule.tsx`
- Create: `frontend/src/pages/evidence-center/components/PaperCard.tsx`
- Create: `frontend/src/pages/evidence-center/components/PaperDetailDrawer.tsx`
- Modify: `frontend/src/api/endpoints.ts`(加 `listEvidencePapers`/`getEvidencePaperDetail`)
- Test: `frontend/src/pages/evidence-center/modules/PaperLibraryModule.test.tsx`

**Interfaces:**
- Produces(endpoints.ts):
  - `listEvidencePapers(p?: { search?; oa?; year?; has_fulltext?; page?; page_size? }) => Promise<{ items: EvidencePaperItem[]; total: number }>`
  - `getEvidencePaperDetail(paperId: string) => Promise<EvidencePaperDetail>`
  - `interface EvidencePaperItem { id; pmid; pmcid; doi; title; journal; publication_year; is_oa; abstract_available; fulltext_available; paragraph_count; evidence_count }`
  - `interface EvidencePaperDetail { paper: EvidencePaperItem; paragraphs: Array<{ paragraph_id; section_title; paragraph_index; passage_text; source_scope }>; evidence_count; targets: Array<{ target_type; target_id }> }`

- [ ] **Step 1: endpoints.ts 增加封装**

```ts
export interface EvidencePaperItem {
  id: string; pmid: string | null; pmcid: string | null; doi: string | null
  title: string | null; journal: string | null; publication_year: number | null
  is_oa: boolean; abstract_available: boolean; fulltext_available: boolean
  paragraph_count: number; evidence_count: number
}
export interface EvidencePaperParagraph { paragraph_id: string; section_title: string | null; paragraph_index: number; passage_text: string; source_scope: string }
export interface EvidencePaperDetail {
  paper: EvidencePaperItem
  paragraphs: EvidencePaperParagraph[]
  evidence_count: number
  targets: Array<{ target_type: string; target_id: string }>
}
export const listEvidencePapers = (p?: Record<string, string | number | boolean | undefined>) =>
  getJson<{ items: EvidencePaperItem[]; total: number }>('/api/ontology/evidence/papers', p)
export const getEvidencePaperDetail = (paperId: string) =>
  getJson<EvidencePaperDetail>(`/api/ontology/evidence/papers/${paperId}`)
```

- [ ] **Step 2: 写失败测试**(mock `listEvidencePapers`/`getEvidencePaperDetail`)

关键断言:
1. 列表渲染 title/journal/年份/OA 徽章/段落数
2. 搜索框输入 + 点击搜索 → 携带 search 参数重新请求
3. 点击 PaperCard → PaperDetailDrawer 显示 metadata + abstract 段落 + section 结构
4. 论文库不渲染 Reviewer/Attach/Coverage 控件(断言 `queryByText(/确认晋升|Reviewer/)` 为 null)

- [ ] **Step 3: 实现三组件**

`PaperLibraryModule.tsx`:搜索行(search 输入 + OA checkbox + 年份 select + 已解析全文 checkbox)+ 分页列表(PaperCard)+ 选中 → PaperDetailDrawer(state: selectedPaperId)。
`PaperCard.tsx`:title 加粗、journal(year)、PMID/PMCID/DOI、OA 徽章、摘要可用/全文可用徽章、段落数、证据数;整卡可点。
`PaperDetailDrawer.tsx`:右侧抽屉(复用 `ontology-modal-overlay` 样式类或新增 `.evidence-drawer`):metadata 行 + abstract 段落 + section 分组段落列表(折叠,默认展开 abstract)+ 关联 Evidence 数 + targets 列表(点击 target → `openTarget`)。

- [ ] **Step 4: 测试通过 + build + 提交**

---

