# Task Report: Ontology Center Inspector UI 优化（六阶段）

## Status: DONE

约束核查：**未修改任何数据逻辑**（ontologyApi / endpoints / 后端零改动），仅布局与信息展示。

---

## Phase 1：统一 Inspector Layout

- `.oc-entity-header` padding `16px 24px` → **16px**（与卡片外边界对齐）
- `.oc-breadcrumb` padding `8px 24px` → **8px 16px**
- `.oc-inspector-body` padding 16px、gap 16 → **12px**（统一 Section 间距，等价 margin-bottom:12px，单点维护）
- `.oc-section-card` 补 `width:100%; box-sizing:border-box`（全局已有 `* {box-sizing:border-box}`，此处按规格显式声明）；radius 8px 不变
- `.oc-section-card-header / -body` 同样补 width/box-sizing；body padding 16px 为唯一 padding 来源，**无任何 section 自写 padding**
- Overview / Hierarchy / Relations / Provenance 全部共用同一 `SectionCard`（核查通过，本已如此）

结果：Header / Properties / Provenance 卡片左右边界完全对齐（全部 16px 起始，全宽一致）。

## Phase 2：Provenance 专业化展示

新增 `detail/ProvenanceField.tsx`（RowList 通用行渲染，Provenance 卡与其他行共用）：

- **普通字段**：直接显示
- **数组字段**（如 `original_connection_ids`，经 JSON.parse 识别纯字符串数组）：显示 `N items` + 逐项 `[ e20a1be7... ]` 预览（16 字符截断，完整值在 title）+ **Expand JSON** 按钮 → 点击展开折叠区（`<pre>` 2 空格缩进 JSON，max-height 240px 内滚动），`aria-expanded` 可达性
- 非数组 JSON（对象等）按普通文本显示；解析失败安全降级

## Phase 3：长文本处理

- 所有 `dd` 值：`max-width:100%; word-break:break-word; overflow-wrap:anywhere`
- code 类值（`mono: true` 行，如 Code 行）：`.oc-detail-value-code` — monospace + 单行 `text-overflow: ellipsis` + hover `title` tooltip 显示完整（`ng:cn:structural_3rd_ventricle_to_...`）
- Header 内 `.oc-entity-code` 同样单行省略 + title（Circuit/Function/Region 三个分支）
- 关系卡 code 行同样省略 + title

## Phase 4：Property Grid 重构

`.oc-detail-row` 从 flex+固定 dt 宽改为 **CSS Grid `120px 1fr`**；dt 支持换行（长 label 如 `directionality_policy`）。四类实体 Detail 共用同一 RowList → 全部生效。

## Phase 5：右侧 Relations 优化

`RelationCard` 重构为四层结构（名称与 code 不再同一行）：

```
[icon] Basal forebrain        ← 名称第一优先，最多两行 clamp，overflow-wrap:anywhere
ng:br:basal_forebrain         ← code 独立一行（mono，单行省略 + tooltip）
[ACTIVE]                      ← 状态独立一行
方向  出向                    ← meta 逐行
```

card padding 16 → **12px**；宽度 `width:100%` 固定填满 420px 右栏（不随内容撑开，box-sizing:border-box）。

## Phase 6：视觉验收（6 项核查）

1. **Provenance 不遮挡** ✓ — 值 max-width 100% + overflow-wrap:anywhere；数组字段预览截断 + 折叠 JSON（240px 内滚动）
2. **所有 Inspector section 左右边界一致** ✓ — header/breadcrumb/body 统一 16px，卡片全宽
3. **长 code 自动省略** ✓ — Code 行 / header code / 关系卡 code 三处 ellipsis + tooltip
4. **点击查看完整 provenance** ✓ — Expand JSON 折叠区（测试覆盖展开/收起）
5. **右侧 Region 名称完整显示** ✓ — 名称独占首行两行 clamp，code/状态分行
6. **四类实体布局一致** ✓ — 共用 SectionCard + RowList grid + ProvenanceField

## 验证

- `npx vitest run`（全量）：**54 files / 453 passed / 1 skipped / 0 failed**（上一任务报告的 evidence 失败用例本次运行通过）
- `npx vitest run src/pages/ontology-center`：10 files / 65 passed
- `npm run build`：✓ built in 2.73s，0 TS 错误（仅既有 chunk/dynamic-import 警告）

## 修改文件

| 文件 | 改动 |
|------|------|
| `detail/ProvenanceField.tsx` | **新增**：数组识别 + Expand JSON + mono code 值 |
| `detail/ProvenanceField.test.tsx` | **新增**：6 用例（普通/对象/mono/数组/展开收起/短数组） |
| `detail/types.ts` | DetailRow + `mono?: boolean` |
| `detail/EntityDetailPanel.tsx` | RowList 接入 ProvenanceField；Code 行 mono；header code 加 title |
| `detail/EntityDetailPanel.test.tsx` | +1 集成用例（数组 provenance 卡内展开） |
| `ui/RelationCard.tsx` | 名称/code/状态/meta 四层分行重构 |
| `src/styles.css` | Phase 1/3/4/5 全部 CSS（统一 padding、grid、省略、provenance 样式） |
