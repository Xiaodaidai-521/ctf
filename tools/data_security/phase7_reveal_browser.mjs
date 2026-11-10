// Actual built Vue application with synthetic HTTP responses; no backend or credentials.
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import fs from 'node:fs/promises'
import path from 'node:path'
import { preview } from '../../frontend/node_modules/vite/dist/node/index.js'
import { chromium } from '/opt/hatch/skills/spaces/ts-runtime/dist/node_modules/playwright/index.mjs'

const [evidence, label] = process.argv.slice(2)
const checks = {}
const screenshots = []
const network = []
const external = []
const errors = []
const consoleErrors = []
const submitted = []
const decisions = []
const lookups = []
let step = 'launch'
let browser
let server
let page
let listMode = 'normal'
let statisticsMode = 'normal'
let denyDecision = false
let denySource = false
const reason = '核对合成材料 browser-reason@example.invalid'
const protectedReason = '核对合成材料 [邮箱已遮蔽]'
const user = { id: 41, username: 'synthetic-admin', nickname: '合成管理员', role: 'admin' }
const fixture = {
  id: 'reveal-request-ui-1', requested_by: 'user/7', course_id: 1,
  object_ref: '00000000-0000-4000-8000-000000000007', object_version: 'v2',
  fields: [['email', 'users.ctfuser/email']], purpose: 'investigation',
  reason: '核对资料 [内容已遮蔽]', requested_at: '2026-11-10T00:00:00+00:00',
  state: 'pending', decided_by: null, decided_at: null, expires_at: null,
}
let items = [fixture, { ...fixture, id: 'reveal-request-ui-2', requested_by: 'user/8',
  object_ref: '00000000-0000-4000-8000-000000000008', state: 'approved',
  decided_by: 'user/9', decided_at: '2026-11-10T00:01:00+00:00', expires_at: '2026-11-10T00:16:00+00:00' }]
const statisticsReport = {
  id: 901, integrity: 'verified', reason: null, created_at: '2026-11-10T00:00:00+00:00',
  environment: 'evaluation', source_trust: 'synthetic', rescan_state: 'complete',
  versions: { asset: 'asset/statistics-browser-v1', report: 'ds.mask-report.v1',
    policy_binding: { protection_version: 'policy-browser.v1', risk_version: 'risk-browser.v1', contract_version: 'ds.m0.v1' },
    algorithms: ['replace.v1'], adapter: 'adapter-browser.v1', source: 'source-browser.v1',
    audit_key: { version: 'audit-browser.v1' } },
  measurements: [
    { stage: 'processing', unit: 'cell', total: 4, eligible: 3, processed: 3, excluded: 1,
      failed: 0, unknown: 0, unscanned: 0, numerator: 3, denominator: 3, ratio: 1,
      zero_reason: null, version: 'coverage-browser.v1' },
    { stage: 'rescan', unit: 'field', total: 2, eligible: 2, processed: 2, excluded: 0,
      failed: 0, unknown: 0, unscanned: 0, numerator: 2, denominator: 2, ratio: 1,
      zero_reason: null, version: 'coverage-browser.v1' },
  ],
}
const statisticsItems = [statisticsReport,
  { ...statisticsReport, id: 902, versions: { ...statisticsReport.versions, asset: 'asset/statistics-browser-v2' },
    measurements: statisticsReport.measurements.map(metric => ({ ...metric, total: 4, eligible: 0, processed: 0,
      excluded: 4, numerator: 0, denominator: 0, ratio: null, zero_reason: 'NO_ELIGIBLE_UNITS', version: 'coverage-browser.v2' })) },
  { id: 903, integrity: 'unknown', reason: 'REPORT_MISMATCH', measurements: [], versions: null },
]
const statisticsPage = {
  state: 'enabled-unverified', scope: 'retained-report-page', observed_at: '2026-11-10T01:00:00+00:00',
  capabilities: [{ capability: 'text-rag', state: 'enabled-unverified' }, { capability: 'private-files', state: 'disabled' }],
  unknown_sources: [
    { source: 'field-protection', unit: 'field', reason: 'COVERAGE_NOT_RECORDED' },
    { source: 'text-rag', unit: 'text', reason: 'COVERAGE_NOT_RECORDED' },
    { source: 'enabled-outlets', unit: 'outlet', reason: 'BASELINE_UNVERIFIED' },
  ].map(item => ({ ...item, numerator: null, denominator: null, ratio: null, zero_reason: null, version: null })),
}

try {
  server = await preview({ root: path.join(process.cwd(), 'frontend'), configFile: false,
    logLevel: 'silent', preview: { host: '127.0.0.1', port: 0, strictPort: true } })
  const base = `http://127.0.0.1:${server.httpServer.address().port}`
  const policyPath = '/var/lib/hatch-browser/rootfs-base/usr/share/hatch/chromium/webgl-allowed-domains.txt'
  const policyHash = createHash('sha256').update(await fs.readFile(policyPath)).digest('hex')
  browser = await chromium.launch({ executablePath: '/opt/meta-chromium/chrome', headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', `--hatch-webgl-allowed-domains-file=${policyPath}`,
      `--hatch-webgl-allowed-domains-sha256=${policyHash}`] })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'zh-CN', serviceWorkers: 'block' })
  await context.addInitScript(value => localStorage.setItem('userInfo', JSON.stringify(value)), user)
  await context.route('**/*', async route => {
    const request = route.request()
    const url = new URL(request.url())
    if (url.origin !== base) {
      external.push(url.protocol)
      return route.abort()
    }
    if (!url.pathname.startsWith('/api/')) return route.continue()
    let status = 200
    let body
    if (url.pathname === '/api/data-security/policies/') {
      body = { policy: { version: 'phase7-ui-synthetic.v1', status: 'approved', content_hash: 'a'.repeat(64),
        effective_at: '2026-11-10T00:00:00+00:00', expires_at: '2026-11-11T00:00:00+00:00',
        rules: [{ category: 'email_address', outlet: 'api', role: 'admin', purpose: 'investigation', action: { algorithm: 'replace' } }] },
        keys: [], reveal_enabled: true, reveal_state: 'enabled-unverified', preview_source: 'server-synthetic-only' }
    } else if (url.pathname === '/api/data-security/stats/' && request.method() === 'GET') {
      if (['disabled', 'unavailable', 'forbidden'].includes(statisticsMode)) {
        status = statisticsMode === 'forbidden' ? 403 : 503
        body = { code: { disabled: 'POLICY_NOT_APPROVED', unavailable: 'AUDIT_UNAVAILABLE', forbidden: 'AUTHORIZATION_DENIED' }[statisticsMode],
          state: statisticsMode === 'disabled' ? 'disabled' : 'unknown', detail: 'do-not-render-statistics-detail' }
      } else {
        const offset = Number(url.searchParams.get('offset'))
        const available = statisticsMode === 'pagination'
          ? Array.from({ length: 21 }, (_, i) => ({ ...statisticsReport, id: 1000 + i }))
          : statisticsMode === 'empty' ? [] : statisticsItems
        const visible = available.slice(offset, offset + 20)
        body = { ...statisticsPage, items: visible, offset, limit: 20,
          next_offset: available.length > offset + 20 ? offset + 20 : null,
          unknown_records: visible.filter(item => item.integrity === 'unknown').length }
      }
    } else if (url.pathname === '/api/data-security/reveal-source/' && request.method() === 'GET') {
      lookups.push(Object.fromEntries(url.searchParams))
      if (denySource) {
        status = 403
        body = { code: 'AUTHORIZATION_DENIED', detail: 'do-not-render-source-detail' }
      } else {
        body = { object_ref: '00000000-0000-4000-8000-000000000041', object_version: 'v3',
          fields: [['email', 'users.ctfuser/email']] }
      }
    } else if (url.pathname === '/api/data-security/reveal-requests/' && request.method() === 'GET') {
      const offset = Number(url.searchParams.get('offset'))
      const limit = Number(url.searchParams.get('limit'))
      if (listMode === 'disabled') {
        status = 503
        body = { code: 'POLICY_NOT_APPROVED', state: 'disabled' }
      } else if (listMode === 'unavailable') {
        status = 503
        body = { code: 'AUDIT_UNAVAILABLE' }
      } else {
        const visible = listMode === 'pagination' ? Array.from({ length: 21 }, (_, i) => ({ ...fixture, id: `reveal-request-page-${i}` })) : items
        body = { items: visible.slice(offset, offset + limit), offset, limit, state: 'enabled-unverified' }
      }
    } else if (url.pathname === '/api/data-security/reveal-requests/' && request.method() === 'POST') {
      const data = request.postDataJSON()
      submitted.push(data)
      body = { ...fixture, ...data, id: 'reveal-request-ui-submitted', requested_by: 'user/41', reason: protectedReason }
      items = [body, ...items]
      status = 201
    } else if (/\/reveal-requests\/[^/]+\/(approve|reject|revoke)\/$/.test(url.pathname)) {
      const [, id, action] = url.pathname.match(/\/reveal-requests\/([^/]+)\/([^/]+)\/$/)
      decisions.push({ id, action, body: request.postDataJSON() })
      if (denyDecision) {
        status = 403
        body = { code: 'AUTHORIZATION_DENIED', detail: 'do-not-render-private-detail' }
      } else {
        const index = items.findIndex(item => item.id === id)
        items[index] = { ...items[index], state: { approve: 'approved', reject: 'rejected', revoke: 'revoked' }[action],
          decided_by: 'user/41', decided_at: '2026-11-10T00:02:00+00:00',
          expires_at: action === 'approve' ? '2026-11-10T00:17:00+00:00' : items[index].expires_at }
        body = items[index]
      }
    } else if (url.pathname.startsWith('/api/announcements/announcements/')) {
      body = []
    } else if (url.pathname === '/api/users/profile/') {
      body = user
    } else {
      status = 404
      body = { code: 'SYNTHETIC_ROUTE_NOT_CONFIGURED' }
    }
    network.push({ path: url.pathname, method: request.method(), status,
      ...(request.method() === 'GET' && url.searchParams.has('offset') ? { offset: Number(url.searchParams.get('offset')),
        ...(url.searchParams.has('limit') ? { limit: Number(url.searchParams.get('limit')) } : {}) } : {}) })
    return route.fulfill({ status, json: body, headers: { 'Cache-Control': 'no-store, private', Pragma: 'no-cache' } })
  })
  page = await context.newPage()
  page.on('pageerror', error => errors.push(error.name))
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()) })
  step = 'load-request-page'
  await page.goto(`${base}/admin/data-security`)
  await page.locator('#request-title').waitFor()
  await page.getByText('核对资料 [内容已遮蔽]', { exact: true }).first().waitFor()
  assert.ok((await page.locator('.security-page').innerText()).includes('已启用，尚未验收'))
  checks.enabled_unverified_not_accepted = true

  step = 'lookup-application-source'
  await page.locator('#request-source-id').fill('41')
  await page.locator('#request-course').fill('1')
  assert.equal(await page.getByRole('button', { name: '提交申请', exact: true }).isDisabled(), true)
  await page.getByRole('button', { name: '核对资料', exact: true }).click()
  await page.getByText('资料已核对，请填写查看理由后提交申请。', { exact: true }).waitFor()
  assert.deepEqual(lookups, [{ source_id: '41', field: 'email', field_ref: 'users.ctfuser/email', course_id: '1' }])
  assert.equal(await page.locator('#request-object').inputValue(), '00000000-0000-4000-8000-000000000041')
  assert.equal(await page.locator('#request-version').inputValue(), 'v3')
  assert.equal(await page.locator('#request-object').getAttribute('readonly'), '')
  assert.equal(await page.locator('#request-version').getAttribute('readonly'), '')
  await page.locator('#request-field').selectOption('report')
  await page.waitForFunction(() => document.querySelector('#request-object').value === '')
  assert.equal(await page.locator('#request-version').inputValue(), '')
  assert.equal(await page.getByRole('button', { name: '提交申请', exact: true }).isDisabled(), true)
  await page.locator('#request-field').selectOption('email')
  denySource = true
  await page.getByRole('button', { name: '核对资料', exact: true }).click()
  await page.getByText('当前账号缺少所需资料权限，或这项操作不符合申请条件。', { exact: true }).waitFor()
  assert.equal(await page.locator('#request-object').inputValue(), '')
  assert.ok(!(await page.locator('.security-page').innerText()).includes('do-not-render-source-detail'))
  denySource = false
  await page.getByRole('button', { name: '核对资料', exact: true }).click()
  await page.getByText('资料已核对，请填写查看理由后提交申请。', { exact: true }).waitFor()
  checks.source_lookup_is_read_only_clears_changed_scope_and_hides_denial_detail = true

  step = 'submit-application'
  await page.locator('#request-reason').fill(reason)
  await page.getByRole('button', { name: '提交申请', exact: true }).click()
  await page.getByText(protectedReason, { exact: true }).waitFor()
  assert.deepEqual(submitted, [{ object_ref: '00000000-0000-4000-8000-000000000041', object_version: 'v3',
    fields: [['email', 'users.ctfuser/email']], purpose: 'investigation', reason, course_id: 1 }])
  assert.equal(await page.locator('#request-reason').inputValue(), '')
  assert.ok(!(await page.locator('.security-page').innerText()).includes(reason))
  checks.application_body_is_request_only_and_reason_cleared = true

  step = 'cancel-approval'
  page.once('dialog', dialog => dialog.dismiss())
  await page.getByRole('button', { name: '批准', exact: true }).last().click()
  assert.equal(decisions.length, 0)
  checks.cancel_does_not_submit_decision = true
  step = 'approve-and-revoke'
  page.once('dialog', dialog => dialog.accept())
  await page.getByRole('button', { name: '批准', exact: true }).last().click()
  await page.getByText('申请已批准。', { exact: true }).waitFor()
  await page.getByRole('button', { name: '撤销批准', exact: true }).first().waitFor()
  page.once('dialog', dialog => dialog.accept())
  await page.getByRole('button', { name: '撤销批准', exact: true }).first().click()
  await page.getByText('批准已撤销。', { exact: true }).waitFor()
  await page.getByText('已撤销', { exact: true }).waitFor()
  step = 'reject-application'
  page.once('dialog', dialog => dialog.accept())
  await page.getByRole('button', { name: '不批准', exact: true }).click()
  await page.getByText('申请未获批准。', { exact: true }).waitFor()
  assert.deepEqual(decisions.map(item => item.action), ['approve', 'revoke', 'reject'])
  assert.ok(decisions.every(item => JSON.stringify(item.body) === '{}'))
  checks.decisions_use_empty_bodies_and_server_states = true

  step = 'statistics-measurements'
  const statisticsSection = page.locator('section[aria-labelledby="statistics-title"]')
  await statisticsSection.getByText('记录 901 · 报告已核对', { exact: true }).waitFor()
  assert.equal(await statisticsSection.locator('article').count(), 3)
  const measured = statisticsSection.locator('article').nth(0)
  const zero = statisticsSection.locator('article').nth(1)
  const unknown = statisticsSection.locator('article').nth(2)
  assert.deepEqual(await measured.locator('tbody tr').nth(0).locator('th, td').allTextContents(),
    ['原处理', '单元格', '4', '3／3', '1', '0', '0', '0', '100%', 'coverage-browser.v1'])
  assert.deepEqual(await measured.locator('tbody tr').nth(1).locator('th, td').allTextContents(),
    ['复扫', '字段', '2', '2／2', '0', '0', '0', '0', '100%', 'coverage-browser.v1'])
  await measured.getByText('查看版本信息', { exact: true }).click()
  await zero.getByText('查看版本信息', { exact: true }).click()
  assert.ok((await measured.innerText()).includes('asset/statistics-browser-v1'))
  assert.ok((await zero.innerText()).includes('asset/statistics-browser-v2'))
  assert.equal(await zero.getByText('未计算（无应处理单位）', { exact: true }).count(), 2)
  assert.equal(await zero.getByText('0／0', { exact: true }).count(), 2)
  assert.ok(!(await zero.innerText()).includes('%'))
  assert.equal(await unknown.locator('table').count(), 0)
  assert.ok((await unknown.innerText()).includes('报告未通过完整性核对，不纳入处理统计。'))
  assert.ok((await statisticsSection.innerText()).includes('本页有 1 份报告尚未核对'))
  assert.ok(!(await statisticsSection.innerText()).includes('状态：已验收'))
  checks.statistics_units_versions_zero_and_unknown_separated = true

  step = 'desktop-layout'
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
  await page.screenshot({ path: path.join(evidence, label + '-desktop.png'), fullPage: true })
  screenshots.push(label + '-desktop.png')
  step = 'mobile-layout'
  await page.setViewportSize({ width: 390, height: 844 })
  await page.locator('#request-title').scrollIntoViewIfNeeded()
  await page.screenshot({ path: path.join(evidence, label + '-mobile.png'), fullPage: true })
  screenshots.push(label + '-mobile.png')
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
  checks.desktop_and_mobile_no_document_overflow = true

  step = 'permission-error-display'
  denyDecision = true
  page.once('dialog', dialog => dialog.accept())
  await page.getByRole('button', { name: '撤销批准', exact: true }).click()
  await page.getByText('当前账号缺少所需资料权限，或这项操作不符合申请条件。', { exact: true }).waitFor()
  assert.ok(!(await page.locator('.security-page').innerText()).includes('do-not-render-private-detail'))
  checks.permission_denial_has_fixed_message = true

  step = 'pagination'
  listMode = 'pagination'
  await page.getByRole('button', { name: '刷新申请', exact: true }).click()
  await page.waitForFunction(() => document.querySelectorAll('section[aria-labelledby="request-title"] tbody tr').length === 20)
  await page.getByRole('button', { name: '下一页', exact: true }).click()
  await page.locator('section[aria-labelledby="request-title"]').getByText('第 2 页', { exact: true }).waitFor()
  assert.equal(await page.locator('section[aria-labelledby="request-title"] tbody tr').count(), 1)
  assert.equal(await page.getByRole('button', { name: '下一页', exact: true }).isDisabled(), true)
  assert.ok(network.some(item => item.offset === 20 && item.limit === 20))
  checks.visible_list_pagination = true

  step = 'disabled-and-unavailable'
  listMode = 'disabled'
  await page.getByRole('button', { name: '刷新申请', exact: true }).click()
  await page.getByText('原文查看尚未开放，暂不能提交或审批。', { exact: true }).waitFor()
  assert.equal(await page.locator('#request-reason').count(), 0)
  listMode = 'unavailable'
  await page.getByRole('button', { name: '刷新申请', exact: true }).click()
  await page.getByText('操作未完成，请稍后重试。', { exact: true }).waitFor()
  assert.ok((await page.locator('.security-page').innerText()).includes('状态待确认'))
  assert.equal(await page.locator('#request-reason').count(), 0)
  checks.disabled_and_unknown_states_not_actionable = true

  step = 'statistics-pagination'
  statisticsMode = 'pagination'
  await statisticsSection.getByRole('button', { name: '刷新统计', exact: true }).click()
  await page.waitForFunction(() => document.querySelectorAll('section[aria-labelledby="statistics-title"] article').length === 20)
  await statisticsSection.getByRole('button', { name: '下一页统计', exact: true }).click()
  await statisticsSection.getByText('第 2 页', { exact: true }).waitFor()
  assert.equal(await statisticsSection.locator('article').count(), 1)
  assert.equal(await statisticsSection.getByRole('button', { name: '下一页统计', exact: true }).isDisabled(), true)
  assert.ok(network.some(item => item.path === '/api/data-security/stats/' && item.offset === 20))
  checks.statistics_fixed_page_limit = true

  step = 'statistics-empty'
  statisticsMode = 'empty'
  await statisticsSection.getByRole('button', { name: '上一页统计', exact: true }).click()
  await statisticsSection.getByText('当前没有处理报告可统计，暂不计算处理覆盖率。', { exact: true }).waitFor()
  assert.equal(await statisticsSection.locator('table').count(), 0)
  assert.ok((await statisticsSection.innerText()).includes('暂无可核对的完整处理总量，暂不计算比例。'))
  assert.ok(!(await statisticsSection.innerText()).includes('%'))
  checks.statistics_missing_denominators_not_zero_percent = true

  step = 'statistics-disabled-unavailable-and-forbidden'
  statisticsMode = 'disabled'
  await statisticsSection.getByRole('button', { name: '刷新统计', exact: true }).click()
  await statisticsSection.getByText('处理统计尚未启用。', { exact: true }).waitFor()
  assert.equal(await statisticsSection.locator('article').count(), 0)
  statisticsMode = 'unavailable'
  await statisticsSection.getByRole('button', { name: '刷新统计', exact: true }).click()
  await statisticsSection.getByText('状态：状态待确认', { exact: true }).waitFor()
  await statisticsSection.getByText('处理统计暂不可用，请稍后重试。', { exact: true }).waitFor()
  statisticsMode = 'forbidden'
  await statisticsSection.getByRole('button', { name: '刷新统计', exact: true }).click()
  await statisticsSection.getByText('当前账号无权查看处理统计。', { exact: true }).waitFor()
  assert.equal(await statisticsSection.locator('article').count(), 0)
  assert.ok(!(await statisticsSection.innerText()).includes('do-not-render-statistics-detail'))
  assert.ok(network.filter(item => item.path === '/api/data-security/stats/').every(item => item.method === 'GET' && !('limit' in item)))
  assert.ok(!(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))).includes('asset/statistics-browser-'))
  checks.statistics_errors_clear_stale_data_and_hide_details = true
  checks.statistics_read_only_and_not_persisted_in_browser_storage = true
  assert.ok(!(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))).includes(reason))
  assert.ok(!network.some(item => item.path.endsWith('/read/')))
  assert.equal(errors.length, 0)
  assert.ok(consoleErrors.every(value => /Failed to load resource.*status of (403|503)/.test(value)))
  assert.equal(external.length, 0)
  assert.ok(!network.some(item => item.status === 404))
  checks.no_original_read_or_browser_storage_of_reason = true
  checks.page_javascript_errors = 0
  checks.external_browser_requests = 0
  console.log(JSON.stringify({ checks, network, screenshots, browser_version: browser.version(),
    ui_mode: 'actual built Vue application; synthetic HTTP responses; no Django/PG backend', backend_used: false }))
} catch (error) {
  if (page) {
    await page.screenshot({ path: path.join(evidence, label + '-failure.png'), fullPage: true })
    screenshots.push(label + '-failure.png')
  }
  console.log(JSON.stringify({ failure_step: step, error_type: error.name, checks, network, screenshots,
    page_error_types: errors, external_attempts: external.length, backend_used: false }))
  process.exitCode = 1
} finally {
  if (browser) await browser.close()
  if (server) await new Promise(resolve => server.httpServer.close(resolve))
}
