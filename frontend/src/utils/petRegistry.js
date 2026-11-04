import { loadPetManifest, normalizePetPack } from './pet.js'

export async function loadPetRegistry(signal) {
  const response = await fetch('/pets/index.json', { signal })
  if (!response.ok) throw new Error('宠物列表加载失败')
  const packs = await response.json()
  if (!Array.isArray(packs) || !packs.length || packs.some(pack => !normalizePetPack(pack))) {
    throw new Error('宠物列表格式不正确')
  }
  const directories = [...new Set(packs.map(normalizePetPack))]
  return Promise.all(directories.map(async pack => {
    try {
      const manifest = await loadPetManifest(pack, signal)
      if (typeof manifest.displayName !== 'string' || !manifest.displayName.trim()) {
        throw new Error('宠物缺少显示名')
      }
      return { pack, manifest }
    } catch (error) {
      if (signal?.aborted) throw error
      // One unavailable pack must not prevent choosing the other pets.
      return { pack, manifest: null }
    }
  }))
}

export function petThumbnailStyle(manifest) {
  const scale = Math.min(48 / manifest.cellWidth, 52 / manifest.cellHeight)
  const width = manifest.cellWidth * scale
  const height = manifest.cellHeight * scale
  return {
    width: `${width}px`,
    height: `${height}px`,
    '--sheet-width': `${manifest.columns * width}px`,
    '--sheet-top': `${-manifest.animations.idle.row * height}px`
  }
}
