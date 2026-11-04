export const PET_ANIMATIONS = {
  idle: 'idle',
  working: 'working',
  'needs-input': 'waiting',
  ready: 'wave',
  failed: 'failed'
}

export const PET_LABELS = {
  idle: '待机陪伴',
  working: '智能体工作中',
  'needs-input': '等你回答 / 确认',
  ready: '回复完成 · 未读',
  failed: '请求出错'
}

export const PET_STORAGE_KEY = 'platform-pet:preferences:v1'
export const DEFAULT_PET_PACK = '/pets/dundun'

export function normalizePetPack(value) {
  // Only local public pet directories, never remote URLs or executable image schemes.
  if (typeof value !== 'string') return null
  const path = value.trim().replace(/\/+$/, '')
  return /^\/pets\/[a-zA-Z0-9_-]+(?:\/[a-zA-Z0-9_-]+)*$/.test(path) ? path : null
}

export function loadPetPreferences() {
  try {
    const stored = JSON.parse(localStorage.getItem(PET_STORAGE_KEY))
    return {
      hidden: stored?.hidden === true,
      pack: normalizePetPack(stored?.pack) || DEFAULT_PET_PACK,
      position: validPosition(stored?.position) ? stored.position : null
    }
  } catch {
    return { hidden: false, pack: DEFAULT_PET_PACK, position: null }
  }
}

export function savePetPreferences(preferences) {
  try {
    localStorage.setItem(PET_STORAGE_KEY, JSON.stringify(preferences))
  } catch {
    // Private mode / full storage must not prevent using the pet.
  }
}

export function validPosition(position) {
  return Number.isFinite(position?.x) && Number.isFinite(position?.y)
}

export function clampPetPosition(position, viewport, size) {
  const maxX = Math.max(0, viewport.width - size.width)
  const maxY = Math.max(0, viewport.height - size.height)
  return {
    x: Math.min(Math.max(0, position.x), maxX),
    y: Math.min(Math.max(0, position.y), maxY)
  }
}

export function validatePetManifest(manifest) {
  const positiveInteger = value => Number.isSafeInteger(value) && value > 0
  if (!manifest || !positiveInteger(manifest.cellWidth) || !positiveInteger(manifest.cellHeight)
    || !positiveInteger(manifest.columns) || !manifest.animations
    || typeof manifest.spritesheetPath !== 'string'
    || !/^[a-zA-Z0-9_-]+(?:\/[a-zA-Z0-9_-]+)*\.(webp|png)$/i.test(manifest.spritesheetPath)) {
    throw new Error('宠物清单格式不正确')
  }
  for (const name of Object.values(PET_ANIMATIONS)) {
    if (!manifest.animations[name]) throw new Error(`宠物缺少 ${name} 动画`)
  }
  for (const animation of Object.values(manifest.animations)) {
    if (!animation || !Number.isSafeInteger(animation.row) || animation.row < 0
      || !positiveInteger(animation.frames) || animation.frames > manifest.columns
      || !Number.isFinite(animation.fps) || animation.fps <= 0 || animation.fps > 120) {
      throw new Error('宠物动画映射不正确')
    }
  }
  return manifest
}

export async function loadPetManifest(pack, signal) {
  const directory = normalizePetPack(pack)
  if (!directory) throw new Error('请使用 /pets/ 下的宠物目录')
  const response = await fetch(`${directory}/pet.json`, { signal })
  if (!response.ok) throw new Error('宠物清单加载失败')
  return validatePetManifest(await response.json())
}

export function validatePetImage(manifest, image) {
  const rows = Math.max(...Object.values(manifest.animations).map(animation => animation.row)) + 1
  if (image.naturalWidth !== manifest.columns * manifest.cellWidth
    || image.naturalHeight < rows * manifest.cellHeight) {
    throw new Error('宠物图集尺寸与清单不匹配')
  }
}

export function petFrameAt(animation, elapsed) {
  return Math.floor(Math.max(0, elapsed) * animation.fps / 1000) % animation.frames
}
