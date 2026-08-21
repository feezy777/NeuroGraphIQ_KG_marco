### Task U6: 全量回归 + 分辨率验收

**Files:** 无新增
**行为:**
- `npx vitest run` 全绿 + `npm run build` + `npx tsc --noEmit`
- 浏览器人工验收(implementer 无浏览器时,用 Playwright/curl 不可行则检查布局 CSS 数值 + 报告):
  - 1920×1080 / 1600×900 / 1366×768:无横向滚动;中栏不被压窄;按钮可见;独立滚动;Empty 态;有结果态;长 Claim/标题换行;审核右栏 sticky;console 无错误
  - 至少:构建产物检查 + 报告分辨率适配结论(基于 CSS 媒体查询/数值推理)

**提交:** 如无修复不提交

---

