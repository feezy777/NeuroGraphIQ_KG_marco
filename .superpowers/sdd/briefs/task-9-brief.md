### Task 9: taskStatus 卡片标题工具 + 测试

**Files:**
- Modify: `frontend/src/pages/evidence-center/components/taskStatus.ts`
- Test: `frontend/src/pages/evidence-center/components/taskStatus.test.ts`(新建)

**Interfaces:**
- Produces: `objectCardTitle(cn: string | null | undefined, en: string | null | undefined, fallback: string): string`(Task 10 使用)

- [ ] **Step 1: 写失败测试**

创建 `taskStatus.test.ts`:

```typescript
import { describe, expect, it } from 'vitest'
import { objectCardTitle } from './taskStatus'

describe('objectCardTitle(中文为主+英文括号)', () => {
  it('中英皆有:中文 (英文)', () => {
    expect(objectCardTitle('杏仁核 → 海马', 'Amygdala → Hippocampus', '兜底')).toBe('杏仁核 → 海马 (Amygdala → Hippocampus)')
  })
  it('仅中文:只显示中文', () => {
    expect(objectCardTitle('默认模式网络', null, '兜底')).toBe('默认模式网络')
  })
  it('仅英文:只显示英文', () => {
    expect(objectCardTitle(null, 'Amygdala → Hippocampus', '兜底')).toBe('Amygdala → Hippocampus')
  })
  it('中英相同:不重复括号', () => {
    expect(objectCardTitle('R1→R2', 'R1→R2', '兜底')).toBe('R1→R2')
  })
  it('皆空/空白:回退兜底', () => {
    expect(objectCardTitle(null, null, '连接 #abc12345')).toBe('连接 #abc12345')
    expect(objectCardTitle('  ', '', '连接 #abc12345')).toBe('连接 #abc12345')
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/pages/evidence-center/components/taskStatus.test.ts`
Expected: FAIL(`objectCardTitle is not a function`)

- [ ] **Step 3: 实现**

在 `taskStatus.ts` 的 `taskTitle` 函数之后新增:

```typescript
/** 对象卡片标题:中文 (英文);中文缺失只用英文;中英相同不重复;皆空回退兜底名 */
export function objectCardTitle(
  cn: string | null | undefined,
  en: string | null | undefined,
  fallback: string,
): string {
  const c = cn?.trim() || ''
  const e = en?.trim() || ''
  if (!c && !e) return fallback
  if (!c) return e
  if (!e || e === c) return c
  return `${c} (${e})`
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/pages/evidence-center/components/taskStatus.test.ts`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/evidence-center/components/taskStatus.ts frontend/src/pages/evidence-center/components/taskStatus.test.ts
git commit -m "feat(evidence-ui): objectCardTitle cn-first-with-en-parens helper"
```

---

