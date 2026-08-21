### Task U2: 左栏 ClaimSummaryPanel + 右栏 EvidenceQueuePanel

**Files:**
- Create: `components/ClaimSummaryPanel.tsx`(左栏「当前需要验证的事实」;5 个独立信息块:类型/源脑区/目标脑区/连接关系/方向;每块浅蓝灰 bg+轻 border+8px radius+左侧小图标(tag/location/target/network/arrow,用现有图标体系或 emoji/字符);中文标签蓝/值深色;块间距 10-12px;**由 claim_components 动态生成,按 component_type 映射块,不写死**)
- Modify: `EvidenceCenterPage.tsx`(左栏 candidates 分支渲染 ClaimSummaryPanel 替代 ClaimView;ClaimView 保留或复用为内部实现)
- Create: `components/EvidenceQueuePanel.tsx`(右栏「待处理对象」+ 数量 Badge + Tabs(待审核 N/已完成 N/失败 N)+ ☐只看未处理 + 紧凑 List Item(名称/类型·confidence/证据数/状态)+ 当前项浅蓝选中 + 空态(托盘图标/队列为空/当前没有待处理对象)+ 底部固定[查看全部对象])
- Modify: `EvidenceCandidatesModule.tsx`(左栏 Claim 推送数据适配 ClaimSummaryPanel;右栏队列由页面级渲染 EvidenceQueuePanel 替代 ObjectQueue——检查 ObjectQueue 与 EvidenceQueuePanel 关系:EvidenceQueuePanel 可直接增强/替换 ObjectQueue,确认其他模块(左栏队列)的复用)
- Test: ClaimSummaryPanel 动态块渲染(connection 类型 5 块;其他 target_type 按 components 生成);EvidenceQueuePanel Tabs/只看未处理/空态/选中

**提交:** `feat(evidence-center): 左栏 ClaimSummaryPanel + 右栏 EvidenceQueuePanel`

---

