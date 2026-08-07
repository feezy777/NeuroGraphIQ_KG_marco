import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const DIR = join(process.cwd(), 'src', 'pages', 'data-center')

const FILES = [
  'EvidenceReviewModal.tsx',
  'PaperEvidenceColumn.tsx',
  'PaperEvidencePanel.tsx',
  'FormalObjectDetailDrawer.tsx',
]

describe('论文佐证相关页面禁用原生弹窗', () => {
  it.each(FILES)('%s 不包含 window.prompt / window.confirm / alert', file => {
    const content = readFileSync(join(DIR, file), 'utf8')
    expect(content).not.toMatch(/window\.(prompt|confirm)\s*\(/)
    expect(content).not.toMatch(/\balert\s*\(/)
  })
})
