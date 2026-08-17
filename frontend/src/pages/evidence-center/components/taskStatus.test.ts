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
