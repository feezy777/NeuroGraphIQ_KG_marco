# 验证中心 Mirror KG 三操作 Tab 改造计划

**目标：** Mirror KG 页面去掉字段补全，前面加 3 个操作 Tab（规则校验、人工审核、双模型校验），后面保留数据浏览 Tab。

---

## 新结构

```
验证中心
├── Mirror KG (默认)
│   ├── 规则校验     ← 🆕 带 rule status + batch validate
│   ├── 人工审核     ← 🆕 带 review status + batch approve/reject
│   ├── 双模型校验   ← 🆕 带 dual-model consensus + 对比
│   ├── 连接         ← 纯浏览（去字段补全）
│   ├── 功能         ← 纯浏览
│   ├── 回路         ← 纯浏览
│   ├── 三元组       ← 纯浏览
│   └── 证据         ← 纯浏览
├── 晋升管理
├── Macro Clinical
└── Final KG
```

## 三个操作 Tab 详情

### Tab 1：规则校验

| 列 | 说明 |
|---|---|
| ☐ | 勾选 |
| 类型 | 连接/回路/功能 |
| 名称 | display_label |
| Mirror状态 | StatusBadge |
| 置信度 | 0.00-1.00 |
| 规则校验 | 🚫阻塞数 / ⚠警告数 / ✓通过 |
| 👁 | 打开详情弹窗 |

**底部操作栏：** [执行规则校验]

**弹窗：** 对象数据 + 校验结果逐条展示（规则名、严重度、消息）+ [重新校验此对象]

**数据源：** `listMirrorReviewQueue`（全部 target_types）

---

### Tab 2：人工审核

| 列 | 说明 |
|---|---|
| ☐ | 勾选 |
| 类型 | 连接/回路/功能 |
| 名称 | display_label |
| 审核状态 | StatusBadge |
| 置信度 | 0.00-1.00 |
| 问题 | B/W 计数 |
| 👁 | 打开详情弹窗 |

**底部操作栏：** [✓ 批准] [✕ 拒绝]

**弹窗：** 对象数据 + 校验结果 + 审核历史 + 批准/拒绝按钮

**数据源：** `listMirrorReviewQueue`（filter: review_status=pending）

---

### Tab 3：双模型校验

| 列 | 说明 |
|---|---|
| ☐ | 勾选 |
| 类型 | 连接/回路/功能 |
| 名称 | display_label |
| 共识状态 | 🤝一致 / ⚡冲突 / 🔄未验证 |
| DeepSeek置信度 | 0.00 |
| Kimi置信度 | 0.00 |
| 👁 | 打开详情弹窗 |

**底部操作栏：** [触发双模型验证]

**弹窗：** DeepSeek vs Kimi 并排对比卡片 + 共识状态 + [触发双模型验证]

**数据源：** `listMirrorReviewQueue`（filter: review_status=approved）

---

### 数据浏览 Tab（连接/功能/回路/三元组/证据）

纯数据浏览，无字段补全按钮，无批量操作栏。点击行打开简化的详情弹窗（只读 JSON + 证据）。

**数据源：** `listMirrorReviewQueue`（按 target_type 过滤）

---

## 文件变更

| 文件 | 动作 |
|---|---|
| `validationCenterTypes.ts` | MirrorKgSubTab 改为 8 个值 |
| `ValidationMirrorPanel.tsx` | 完全重写：不再委托 MirrorKgPanel，全部自建 |
| `ValidationReviewPanel.tsx` | 删除（人工审核已并入 Mirror KG） |
| `ValidationCenterPage.tsx` | 去掉 human-review tab |
| `ValidationCenterTabBar.tsx` | 去掉 human-review 入口 |
| `styles.css` | 追加 `vw-*` CSS |
| `i18n.ts` | 追加/调整 key |

---

## 关键决策

1. **去字段补全**：不再委托 `MirrorKgPanel`，改用 `listMirrorReviewQueue` 自建表格
2. **去人工审核独立 Tab**：审核功能合入 Mirror KG Tab 2
3. **Tab 1/2/3 共用 `ValidationSubTab` 组件**：传参控制列和操作按钮
4. **数据浏览 Tab 用简化表格**：只有类型/名称/状态/置信度 + 只读弹窗
5. **弹窗复用 `vr-modal` CSS**：三个操作 Tab 的弹窗共用一个 Modal 组件

---

## 任务

### Task 1: 更新类型和 TabBar
- `validationCenterTypes.ts`: MirrorKgSubTab 增加 'rule_check', 'review', 'dual_model'，移除 'validation'
- `ValidationCenterTabBar.tsx`: 移除 'human-review'
- `ValidationCenterPage.tsx`: 移除 human-review case，移除 ValidationReviewPanel import

### Task 2: 重写 ValidationMirrorPanel
- 不再委托 MirrorKgPanel
- 8 个子 Tab 全部自建表格
- Tab 1-3 有操作列 + 批量按钮
- Tab 4-8 纯浏览
- 所有 Tab 共用 `listMirrorReviewQueue` 数据源
- 弹窗通用：数据 + 证据 + 校验结果 + 操作按钮

### Task 3: CSS + i18n + 构建验证
- 检查并补充 CSS
- 更新 i18n key
- `npm run build` 确认零错误
- 清理无用文件（ValidationReviewPanel 等）
