// Read-only baseline comparison: source reads use HEAD, workspace files stay intact.
const fs = require('node:fs')
const path = require('node:path')
const { fileURLToPath } = require('node:url')
const { spawnSync } = require('node:child_process')
const { syncBuiltinESMExports } = require('node:module')
const root = path.resolve(__dirname, '..')
const original = fs.readFileSync
const cache = new Map()
fs.readFileSync = function (file, options) {
  let local
  try { local = file instanceof URL ? fileURLToPath(file) : path.resolve(String(file)) } catch { return original.apply(this, arguments) }
  const relative = path.relative(root, local).replaceAll('\\', '/')
  if (relative.startsWith('frontend/src/') && relative !== 'frontend/src/views/Resources.vue' && !relative.endsWith('.test.js') && !relative.endsWith('.test.mjs')) {
    if (!cache.has(relative)) {
      const result = spawnSync('git', ['show', 'HEAD:' + relative], { cwd: root, maxBuffer: 5 * 1024 * 1024, windowsHide: true })
      cache.set(relative, result.status === 0 ? result.stdout : null)
    }
    const data = cache.get(relative)
    if (data) { const encoding = typeof options === 'string' ? options : options?.encoding; return encoding ? data.toString(encoding) : Buffer.from(data) }
  }
  return original.apply(this, arguments)
}
syncBuiltinESMExports()
