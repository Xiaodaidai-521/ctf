// Actual browser interactions only; never record cookies, credentials or request bodies.
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import fs from 'node:fs/promises'
import path from 'node:path'
import { pathToFileURL } from 'node:url'
import { createServer } from '../../frontend/node_modules/vite/dist/node/index.js'

const [privateDir, backendPort, frontendPort, executablePath, playwrightPath, evidence, label] = process.argv.slice(2)
const { chromium } = await import(pathToFileURL(playwrightPath).href)
const root = process.cwd()
const base = `http://127.0.0.1:${frontendPort}`
const backend = `http://127.0.0.1:${backendPort}`
const checks = {}
const network = []
const previews = []
let step = 'launch'
let browser
let server
let credentials = {}
try {
  credentials = JSON.parse(await fs.readFile(path.join(privateDir, 'credentials.json'), 'utf8'))
  const deadline = Date.now() + 30000
  while (true) {
    try {
      const response = await fetch(`${backend}/api/users/csrf/`)
      if (response.status === 200) break
    } catch {}
    assert.ok(Date.now() < deadline, 'BACKEND_READINESS_TIMEOUT')
    await new Promise(resolve => setTimeout(resolve, 150))
  }
  server = await createServer({ root: path.join(root, 'frontend'),
    configFile: path.join(root, 'frontend/vite.config.js'), logLevel: 'silent',
    server: { host: '127.0.0.1', port: Number(frontendPort), strictPort: true,
      proxy: { '/api': { target: backend, changeOrigin: true }, '/media': { target: backend, changeOrigin: true } } } })
  await server.listen()
  step = 'browser-launch'
  // Use the immutable image policy required by this installed browser; never a writable substitute.
  const policyPath = '/var/lib/hatch-browser/rootfs-base/usr/share/hatch/chromium/webgl-allowed-domains.txt'
  const policyHash = createHash('sha256').update(await fs.readFile(policyPath)).digest('hex')
  browser = await chromium.launch({ executablePath, headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', `--hatch-webgl-allowed-domains-file=${policyPath}`,
      `--hatch-webgl-allowed-domains-sha256=${policyHash}`] })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'zh-CN' })
  const external = []
  await context.route('**/*', route => {
    const url = new URL(route.request().url())
    if (url.origin === base || url.protocol === 'data:' || url.protocol === 'blob:') return route.continue()
    external.push(url.protocol)
    return route.abort()
  })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.name))
  page.on('response', response => {
    const url = new URL(response.url())
    if (url.pathname.startsWith('/api/data-security/')) network.push({ path: url.pathname, status: response.status() })
  })
  step = 'admin-login-navigation'
  await page.goto(`${base}/login`)
  step = 'admin-login-fields'
  await page.getByPlaceholder('请输入用户名').fill(credentials.admin.username)
  await page.getByPlaceholder('请输入密码').fill(credentials.admin.password)
  const login = page.waitForResponse(response => response.url().endsWith('/api/users/login/') && response.request().method() === 'POST')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  assert.equal((await login).status(), 200)
  await page.waitForFunction(() => localStorage.getItem('userInfo') !== null)
  step = 'policy-page'
  const loaded = page.waitForResponse(response => response.url().endsWith('/api/data-security/policies/'))
  await page.goto(`${base}/admin/data-security`)
  const metadataResponse = await loaded
  assert.equal(metadataResponse.status(), 200)
  const metadata = await metadataResponse.json()
  assert.deepEqual(Object.keys(metadata).sort(), ['keys', 'policy', 'preview_source', 'reveal_enabled'])
  assert.equal(metadata.reveal_enabled, false)
  assert.equal(metadata.preview_source, 'server-synthetic-only')
  assert.equal(metadata.policy.status, 'approved')
  assert.equal(metadata.keys.length, 4)
  for (const key of metadata.keys) assert.deepEqual(Object.keys(key).sort(), ['key_ref', 'purpose', 'schema_version', 'status', 'version'])
  checks.admin_metadata_is_reference_only = true
  await page.getByText('已批准', { exact: true }).waitFor()
  assert.equal(await page.locator('.security-page input, .security-page textarea').count(), 0)
  checks.no_free_text_or_hidden_raw_controls = true
  await page.getByText('密钥引用信息', { exact: true }).click()
  for (const sample of ['email', 'ipv4', 'card', 'mixed']) {
    step = 'preview-' + sample
    await page.locator('#sample-case').selectOption(sample)
    const replied = page.waitForResponse(response => response.url().endsWith('/api/data-security/preview/'))
    await page.getByRole('button', { name: '预览保护结果', exact: true }).click()
    const response = await replied
    assert.equal(response.status(), 200)
    assert.equal(response.headers()['cache-control'], 'no-store')
    assert.deepEqual(response.request().postDataJSON(), { case: sample })
    const result = await response.json()
    assert.deepEqual(Object.keys(result).sort(), ['output', 'policy_version', 'synthetic_only'])
    assert.equal(result.synthetic_only, true)
    for (const original of ['Student@Example.invalid', '192.0.2.42', '4111111111111111']) assert.ok(!result.output.includes(original))
    assert.equal(await page.locator('.security-page pre').textContent(), result.output)
    previews.push({ case: sample, status: response.status(), output_characters: result.output.length, body_is_case_label_only: true })
  }
  checks.four_synthetic_previews_protected = true
  await page.screenshot({ path: path.join(evidence, label + '-desktop.png'), fullPage: true })
  step = 'mobile-layout'
  await page.setViewportSize({ width: 390, height: 844 })
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
  await page.locator('#preview-title').scrollIntoViewIfNeeded()
  await page.screenshot({ path: path.join(evidence, label + '-mobile.png'), fullPage: true })
  checks.mobile_no_horizontal_document_overflow = true
  step = 'invalid-body-refusal'
  const invalid = await page.evaluate(async () => {
    const csrf = document.cookie.split('; ').find(item => item.startsWith('csrftoken=')).split('=')[1]
    const statuses = []
    for (const body of [{ case: 'email', text: 'RejectedBody@example.invalid' }, { case: 'email', context: { role: 'admin' } }, { case: 'unknown' }]) {
      const response = await fetch('/api/data-security/preview/', { method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify(body) })
      statuses.push({ status: response.status, code: (await response.json()).code })
    }
    return statuses
  })
  assert.deepEqual(invalid, Array(3).fill({ status: 400, code: 'INVALID_VALUE' }))
  checks.arbitrary_body_and_forged_context_rejected = true
  const rawRoute = await page.evaluate(async () => {
    const response = await fetch('/api/data-security/keys/data_root/v1/')
    return response.status
  })
  assert.equal(rawRoute, 404)
  checks.key_reference_has_no_secret_route = true
  assert.equal(await page.evaluate(() => Object.keys(localStorage).sort().join(',')), 'userInfo')
  assert.equal(await page.evaluate(() => sessionStorage.length), 0)
  checks.preview_not_persisted_in_browser_storage = true
  assert.equal(errors.length, 0)
  checks.policy_page_javascript_errors = 0
  await context.close()
  for (const role of ['anonymous', 'teacher', 'student']) {
    step = 'denial-' + role
    const restricted = await browser.newContext()
    await restricted.route('**/*', route => new URL(route.request().url()).origin === base ? route.continue() : route.abort())
    const view = await restricted.newPage()
    await view.goto(`${base}/login`)
    if (role !== 'anonymous') {
      await view.getByPlaceholder('请输入用户名').fill(credentials[role].username)
      await view.getByPlaceholder('请输入密码').fill(credentials[role].password)
      const replied = view.waitForResponse(response => response.url().endsWith('/api/users/login/') && response.request().method() === 'POST')
      await view.getByRole('button', { name: '登录', exact: true }).click()
      assert.equal((await replied).status(), 200)
      await view.waitForFunction(() => localStorage.getItem('userInfo') !== null)
    }
    const status = await view.evaluate(async () => {
      await fetch('/api/users/csrf/')
      const csrf = document.cookie.split('; ').find(item => item.startsWith('csrftoken=')).split('=')[1]
      const policies = await fetch('/api/data-security/policies/')
      const preview = await fetch('/api/data-security/preview/', { method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify({ case: 'mixed' }) })
      return [policies.status, preview.status]
    })
    assert.ok(status.every(code => code === 401 || code === 403))
    checks[role + '_metadata_and_preview_denied'] = status
    await view.goto(`${base}/admin/data-security`)
    await view.waitForFunction(() => location.pathname !== '/admin/data-security')
    assert.equal(await view.locator('#policy-title').count(), 0)
    checks[role + '_admin_page_denied'] = true
    await restricted.close()
  }
  assert.equal(external.length, 0)
  checks.external_browser_requests = 0
  console.log(JSON.stringify({ checks, previews, network,
    browser_version: browser.version(), ui_mode: 'actual Vite application; unchanged routes and components',
    screenshots: [label + '-desktop.png', label + '-mobile.png'] }))
} catch (error) {
  let message = error.message.split('\n')[0]
  for (const user of Object.values(credentials)) message = message.replaceAll(user.password, '[OMITTED]')
  console.log(JSON.stringify({ failure_step: step, error_type: error.name, message, checks, previews, network }))
  process.exitCode = 1
} finally {
  if (browser) await browser.close()
  if (server) await server.close()
}
