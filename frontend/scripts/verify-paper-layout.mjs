/**
 * Paper Library 三栏布局真实浏览器验证(Playwright,只读)。
 *
 * 流程: v5 dev server → #/validation-center?tab=paper_evidence → 「论文库」Tab
 *  → 采集三栏 computed style → 点击论文卡 → 详情/右栏 → 截图 → JSON 报告。
 */
import { chromium } from 'playwright'
import fs from 'node:fs'

const BASE = 'http://localhost:5173'
const OUT = 'C:/Users/ADMINI~1/AppData/Local/Temp'

async function computed(page, selector) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel)
    if (!el) return null
    const cs = getComputedStyle(el)
    return {
      width: cs.width,
      minWidth: cs.minWidth,
      display: cs.display,
      flex: cs.flex,
      flexDirection: cs.flexDirection,
      overflowY: cs.overflowY,
      overflowX: cs.overflowX,
      borderLeft: cs.borderLeftWidth,
      exists: true,
    }
  }, selector)
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe',
  })
  const page = await browser.newPage({ viewport: { width: 1680, height: 1050 } })
  await page.goto(`${BASE}/#/validation-center?tab=paper_evidence`, { waitUntil: 'networkidle' })
  await page.waitForSelector('.evidence-module-btn', { timeout: 15000 })
  await page.screenshot({ path: `${OUT}/paperlib-0-before-tab.png`, fullPage: false })

  // 进入论文库
  await page.getByText('论文库', { exact: true }).first().click()
  await page.waitForSelector('.paper-library-container', { timeout: 15000 })
  await page.waitForTimeout(600) // 列表加载
  await page.screenshot({ path: `${OUT}/paperlib-1-library-empty-detail.png` })

  const report = {
    container: await computed(page, '.paper-library-container'),
    body: await computed(page, '.paper-library-body'),
    sidebar: await computed(page, '.paper-library-sidebar'),
    detail: await computed(page, '.paper-detail-panel'),
    relation: await computed(page, '.paper-relation-panel'),
    // 空态文案
    emptyState: await page.evaluate(() => document.body.innerText.includes('请选择论文查看详情')),
    // 横向滚动检查
    scroll: await page.evaluate(() => ({
      bodyScrollWidth: document.body.scrollWidth,
      innerWidth: window.innerWidth,
      containerScrollWidth: document.querySelector('.paper-library-container')?.scrollWidth ?? null,
      containerClientWidth: document.querySelector('.paper-library-container')?.clientWidth ?? null,
    })),
  }

  // 点第一张卡 → 详情
  const card = page.locator('.paper-card').first()
  if (await card.count() > 0) {
    await card.click()
    await page.waitForTimeout(800)
    await page.screenshot({ path: `${OUT}/paperlib-2-detail-selected.png`, fullPage: false })
    report.detailContent = await page.evaluate(() => ({
      hasPaperInfo: !!Array.from(document.querySelectorAll('h4')).find(h => h.textContent === 'Paper Information'),
      abstractVisible: document.body.innerText.includes('Abstract'),
      relationStats: !!document.querySelector('.paper-relation-stats'),
    }))
  } else {
    report.cardCount = 0
    await page.screenshot({ path: `${OUT}/paperlib-1b-no-cards.png` })
  }
  await page.screenshot({ path: `${OUT}/paperlib-3-final.png`, fullPage: false })

  console.log(JSON.stringify(report, null, 2))
  await browser.close()
}

main().catch(e => { console.error('VERIFY_FAILED', e); process.exit(1) })
