### Task 5: 回归验证

**Files:**
- 无新文件

**Interfaces:**
- Consumes: 全部前序任务

- [ ] **Step 1: 后端全量**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: 全部通过(仅既有 6 个基线失败)

- [ ] **Step 2: 实测一篇提取(计时 + 片段质量)**

Run(临时脚本,调 `extract_candidate_for_paper` 对一篇真实论文计时):

```bash
cd backend && ./.venv/Scripts/python.exe -c "
import asyncio, time
from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.services import paper_evidence_service as pes
async def main():
    sem_fetch = asyncio.Semaphore(2); sem_llm = asyncio.Semaphore(2)
    async with AsyncSessionLocal() as s:
        row = (await s.execute(text(\"SELECT id, target_id::text FROM paper_evidence_task_items WHERE status='awaiting_review' AND jsonb_array_length(COALESCE(candidate_papers,'[]'::jsonb))>0 ORDER BY updated_at DESC LIMIT 1\"))).first()
        cp = (await s.execute(text('SELECT candidate_papers FROM paper_evidence_task_items WHERE id=:iid'), {'iid': row[0]})).first()[0]
        ctx = await pes.build_retrieval_context(s, 'connection', row[1], mode='existence')
        t0 = time.monotonic()
        env = await pes.extract_candidate_for_paper(s, context=ctx, paper=cp[0], sem_fetch=sem_fetch, sem_deepseek=sem_llm, mode='existence')
        print('TOTAL %.1fs status=%s passages=%d dir=%s' % (time.monotonic()-t0, env.get('status'), len((env.get('candidate') or {}).get('passages') or []), (env.get('candidate') or {}).get('model_direction')))
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
"
```

Expected: 完成且 passage 方向/内容合理(相对旧流程,共现噪声段应减少)。

- [ ] **Step 3: 冒烟**

前后端 dev 服务运行中;佐证任务页创建/手动提取一个对象,确认无报错。
