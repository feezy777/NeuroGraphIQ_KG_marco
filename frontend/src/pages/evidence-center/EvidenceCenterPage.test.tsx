import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { EvidenceCenterPage } from './EvidenceCenterPage'

describe('EvidenceCenterPage', () => {
  afterEach(() => { cleanup(); window.location.hash = '' })

  it('渲染五模块导航与默认说明句', () => {
    window.location.hash = '#/evidence-center'
    render(<EvidenceCenterPage />)
    expect(screen.getByText('佐证任务')).toBeTruthy()
    expect(screen.getByText('论文库')).toBeTruthy()
    expect(screen.getByText('证据候选')).toBeTruthy()
    expect(screen.getByText('人工审核')).toBeTruthy()
    expect(screen.getByText('证据晋升')).toBeTruthy()
  })

  it('模块导航切换更新 URL 与内容区', async () => {
    window.location.hash = '#/evidence-center'
    render(<EvidenceCenterPage />)
    fireEvent.click(screen.getByText('论文库'))
    await waitFor(() => expect(window.location.hash).toContain('module=papers'))
    expect(screen.getByText('管理系统已经获取和解析的真实论文资源。')).toBeTruthy()
    fireEvent.click(screen.getByText('返回数据中心'))
    await waitFor(() => expect(window.location.hash).toContain('/data-center'))
  })
})
