### Task 8: 全量验收

**Files:**
- 无新文件

**Interfaces:**
- Consumes: 全部前序任务

- [ ] **Step 1: 后端全量**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: 全部通过(含 6 个既有无关失败)

- [ ] **Step 2: 前端全量 + 构建**

Run: `cd frontend && npx vitest run && npm run build`
Expected: 通过(仅既有无关 WIP 失败)+ 0 错误

- [ ] **Step 3: 端到端冒烟**

1. 后端已重启(`cd backend && ./.venv/Scripts/python.exe run_server.py` 后台)。
2. 前端 dev server 运行中(`cd frontend && npm run dev` 后台)。
3. 打开佐证任务页:含「脑室/脑脊液」靶标的任务卡显示「结构性不存在」徽章;点击进入证据佐证页显示提示条,不自动搜索。
4. 创建一个普通连接任务:正常流程;选一个无结果对象,观察反向检索日志(后端日志出现 negative query)。
5. 干跑清理脚本统计(不删除),确认 final 库状态。

- [ ] **Step 4: 提交(如有冒烟修复)**

```bash
git add <修复文件>
git commit -m "fix(evidence): smoke-test fixes"
```
