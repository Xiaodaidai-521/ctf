import { chromium } from 'file:///C:/Users/29681/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs'
import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'
import path from 'node:path'

const base = process.env.LOGIC_BROWSER_URL || 'http://127.0.0.1:5188'
const root = process.cwd()
const report = { boundary: 'Real Chrome, API fixtures only; no real login, database writes or model calls.', cases: [], pageErrors: [], petRequests: [] }
const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true })
const image = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZQAAAABJRU5ErkJggg==', 'base64')
const user = { id: 9001, role: 'student', username: 'synthetic_browser_student', nickname: '回归学生' }
const resource = { id: 9101, title: '回归图片资料', resource_type: 'document', resource_type_display: '文档', status: 'approved', category: '基础',
  file_type: '.png', file_name: 'resource-9101.png', file_size: image.length, file_url: base + '/api/resources/9101/download/',
  tags_list: [], uploader_info: { username: '回归教师' }, protection: { file: { storage: 'encrypted' } } }

try {
  for (const [size, viewport] of [['desktop', { width: 1440, height: 960 }], ['mobile', { width: 390, height: 844 }]]) {
    const context = await browser.newContext({ viewport })
    await context.addInitScript(value => localStorage.setItem('userInfo', JSON.stringify(value)), user)
    await context.route('**/api/**', async route => {
      const endpoint = new URL(route.request().url()).pathname
      if (!endpoint.startsWith('/api/')) return route.continue()
      let data = { results: [], count: 0 }
      if (endpoint === '/api/users/profile/') data = user
      else if (endpoint === '/api/resources/') data = { results: [resource], count: 1 }
      else if (endpoint === '/api/resources/9101/') data = resource
      else if (endpoint === '/api/resources/9101/download/') return route.fulfill({ status: 200, contentType: 'image/png', body: image })
      else if (endpoint === '/api/content/9102/') {
        assert.equal(new URL(route.request().url()).searchParams.get('content_type'), 'quiz')
        data = { id: 9102, content_type: 'quiz', title: '回归测验', difficulty: 'easy', question_count: 1,
          questions: [{ question: '选择正确答案', question_type: 'single_choice', options: ['A', 'B'], correct_answer: 'A', explanation: '回归解释' }] }
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) })
    })
    const page = await context.newPage()
    page.on('pageerror', error => report.pageErrors.push({ size, message: error.message }))
    page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/pets/')) report.petRequests.push(request.url()) })
    await page.goto(base + '/guide')
    await page.locator('.guide-shortcuts').waitFor()
    assert.equal(await page.locator('.pet-launcher, .tutor-pet, #platform-pet').count(), 0)
    assert.equal(await page.getByRole('button', { name: /继续导学对话/ }).count(), 1)
    report.cases.push({ name: `teaching-entry-and-pet-removal-${size}`, passed: true })

    await page.goto(base + '/resources?resource=9101')
    await page.locator('.resource-modal .resource-title').waitFor()
    assert.equal(await page.locator('.resource-modal .resource-title').innerText(), resource.title)
    const preview = page.getByRole('button', { name: '预览资源' })
    assert.equal(await preview.isEnabled(), true)
    await preview.click()
    await page.locator('.preview-image img').waitFor()
    await page.waitForFunction(() => { const img = document.querySelector('.preview-image img'); return img?.complete && img.naturalWidth > 0 })
    await page.screenshot({ path: path.join(root, `artifacts/logic-fix-resource-preview-${size}-20261113.png`), fullPage: true })
    report.cases.push({ name: `document-image-preview-${size}`, passed: true })

    await page.goto(base + '/content/9102?content_type=quiz')
    await page.getByText('回归测验', { exact: true }).waitFor()
    report.cases.push({ name: `typed-generated-content-${size}`, passed: true })
    await context.close()
  }
  assert.equal(report.pageErrors.length, 0)
  assert.equal(report.petRequests.length, 0)
} catch (error) {
  report.failure = error.message
  process.exitCode = 1
} finally {
  await browser.close()
  await writeFile(path.join(root, 'artifacts/logic-fix-browser-smoke-20261113.json'), JSON.stringify(report, null, 2) + '\n')
  process.stdout.write(JSON.stringify(report, null, 2) + '\n')
}
