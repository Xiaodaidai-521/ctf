import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'

const nginx = readFileSync(new URL('../../nginx.conf', import.meta.url), 'utf8')
const viteSource = readFileSync(new URL('../../vite.config.js', import.meta.url), 'utf8')
const vite = runInNewContext(viteSource.replace(/^import .*$/gm, '').replace('export default', 'configuration ='), {
  defineConfig: value => value, vue: () => ({}), path: { resolve: () => '/src' }, __dirname: '/frontend',
})

test('numeric challenge pages use the SPA while container documents and assets use the backend', () => {
  const productionRule = nginx.match(/location ~ (\^\/challenge\/\S+) \{/)
  assert.ok(productionRule, 'production must limit the proxy to container URLs')
  const developmentRule = Object.keys(vite.server.proxy).find(key => key.startsWith('^/challenge/'))
  assert.ok(developmentRule, 'development must support the same container URLs')
  for (const pattern of [productionRule[1], developmentRule]) {
    const matches = new RegExp(pattern)
    for (const path of ['/challenge/7', '/challenge/7/', '/challenges', '/challenge/7?tab=hints']) assert.equal(matches.test(path), false, path)
    for (const path of ['/challenge/1-abc12345/', '/challenge/1-abc12345/index.html', '/challenge/1-abc12345/static/app.css', '/challenge/1-abc12345/app.js', '/challenge/1-abc12345/socket']) assert.equal(matches.test(path), true, path)
  }
  assert.ok(nginx.indexOf(productionRule[0]) < nginx.indexOf('location ~*'), 'container assets must win before the static asset rule')
  assert.doesNotMatch(nginx, /location \^~ \/challenge\//)
  assert.match(nginx, /try_files \$uri \$uri\/ \/index\.html;/)
  assert.match(nginx, /location = \/index\.html \{[^}]*Cache-Control "no-cache"/)
  assert.match(nginx, /location ~ \^\/challenge\/[^}]*proxy_pass http:\/\/127\.0\.0\.1:8000;/, 'a regex proxy must preserve the full original URI')
  assert.equal(vite.server.proxy[developmentRule].ws, true)
})
