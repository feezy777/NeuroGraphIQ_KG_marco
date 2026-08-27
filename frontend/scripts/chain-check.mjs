import { chromium } from 'playwright'
async function w(page, sel){ return page.evaluate(s=>{const e=document.querySelector(s); if(!e) return null; const cs=getComputedStyle(e); return {w:cs.width, display:cs.display, displayType:cs.display, grid:cs.gridTemplateColumns, flex:cs.flex}}, sel) }
const browser = await chromium.launch({ headless:true, executablePath:'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe' })
const page = await browser.newPage({ viewport:{width:1680,height:1050} })
await page.goto('http://localhost:5173/#/validation-center?tab=paper_evidence', {waitUntil:'networkidle'})
await page.waitForSelector('.evidence-module-btn')
await page.getByText('论文库', {exact:true}).first().click()
await page.waitForSelector('.paper-library-container')
await page.waitForTimeout(500)
const report = {
  page: await page.evaluate(()=>window.innerWidth),
  evidenceCenter: await w(page, '.evidence-center'),
  layout: await w(page, '.evidence-center-layout'),
  layoutFull: await page.evaluate(()=>!!document.querySelector('.evidence-center-layout-full')),
  main: await w(page, '.evidence-main'),
  paperModule: await w(page, '.paper-library-container'),
  navVisible: await page.evaluate(()=>{const n=document.querySelector('.evidence-module-nav'); return n?getComputedStyle(n).display:'none'}),
}
report.layoutClass = await page.evaluate(()=>document.querySelector('.evidence-center-layout')?.className ?? null)
console.log(JSON.stringify(report,null,2))
await browser.close()
