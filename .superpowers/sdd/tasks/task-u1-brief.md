### Task U1: 页面骨架视觉重构(ModuleNav / ContextBar / Stepper / 三栏背景)

**Files:**
- Modify: `pages/evidence-center/EvidenceCenterPage.tsx`(三栏 grid 240/640/340 + 背景 #f5f7fa + 栏内白底 Card 化)
- Modify: `pages/evidence-center/EvidenceCenterHeader.tsx`(模块导航胶囊:选中蓝实底白字/未选浅灰深字/圆角偏大紧凑)
- Create: `components/EvidenceModuleNav.tsx`(从 Header 拆出导航)
- Modify: `components/ContextBar.tsx`(整行浅蓝灰背景;左侧:状态 Badge「等待处理对象」+ 一句完整事实「需要验证:xxx 存在投射连接(方向性:directed)」;右侧 [刷新](白底描边)[返回数据中心](蓝主);不拆散字段)
- Modify: `components/StepPills.tsx`(圆数字+文字+虚线连接;当前蓝/完成绿/未完成浅灰;紧凑)
- Modify: `styles.css`(.evidence-center-* 背景/栏 Card/间距 12-16/gap)

**测试:** 导航选中态;ContextBar 事实句渲染;Stepper 三态;三栏背景类

**提交:** `style(evidence-center): 骨架视觉重构(模块导航/ContextBar/Stepper/三栏背景)`

---

