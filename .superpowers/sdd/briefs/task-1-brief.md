### Task 1: 迁移 SQL — paper_evidence_tasks 增加 target_id

**Files:**
- Create: `backend/migrations/20260817_evidence_tasks_target_id.sql`

**Interfaces:**
- Produces: `paper_evidence_tasks.target_id UUID NULL`(Task 3/5/7 使用)

- [ ] **Step 1: 写迁移文件**

```sql
-- 佐证任务一对一:任务行即对象。
-- target_id = 对象身份;新建任务必填,旧行为 NULL(由拆分迁移回填)。
ALTER TABLE paper_evidence_tasks ADD COLUMN IF NOT EXISTS target_id UUID;
CREATE INDEX IF NOT EXISTS idx_paper_evidence_tasks_target ON paper_evidence_tasks (target_type, target_id);
```

- [ ] **Step 2: 应用迁移(当前开发库)**

Run:

```bash
cd backend && ./.venv/Scripts/python.exe -c "
import asyncio
from sqlalchemy import text
from app.database import AsyncSessionLocal
async def main():
    sql = open('migrations/20260817_evidence_tasks_target_id.sql', encoding='utf-8').read()
    async with AsyncSessionLocal() as s:
        await s.execute(text(sql))
        await s.commit()
    print('migration applied')
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
"
```

Expected: prints `migration applied`(重跑也安全,`IF NOT EXISTS`)。

- [ ] **Step 3: 验证列存在**

Run:

```bash
cd backend && ./.venv/Scripts/python.exe -c "
import asyncio
from sqlalchemy import text
from app.database import AsyncSessionLocal
async def main():
    async with AsyncSessionLocal() as s:
        r = await s.execute(text(\"SELECT column_name FROM information_schema.columns WHERE table_name='paper_evidence_tasks' AND column_name='target_id'\"))
        print('target_id column:', r.scalar_one_or_none())
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
"
```

Expected: `target_id column: target_id`

- [ ] **Step 4: Commit**

```bash
git add backend/migrations/20260817_evidence_tasks_target_id.sql
git commit -m "feat(evidence): add paper_evidence_tasks.target_id for 1:1 object tasks"
```

---

