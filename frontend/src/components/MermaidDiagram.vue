<template>
  <div class="mermaid-diagram" ref="containerRef">
    <div v-if="loading" class="mermaid-loading">
      <span class="loading-spinner"></span>
      渲染中...
    </div>

    <div v-if="error" class="mermaid-error">
      <div class="error-header">
        <span class="error-icon"><AppIcon name="bi-exclamation-octagon" /></span>
        <span>Mermaid 渲染失败</span>
      </div>
      <pre class="error-code">{{ mermaidCode }}</pre>
    </div>

    <div
      v-show="!error && !loading"
      class="mermaid-svg-wrapper"
      ref="svgWrapper"
      v-html="svgContent"
    ></div>

    <div v-if="!error && !loading && svgContent" class="mermaid-toolbar">
      <a-tooltip content="放大查看">
        <a-button size="mini" type="text" @click="showZoomModal = true">
          <template #icon><icon-fullscreen /></template>
        </a-button>
      </a-tooltip>
      <a-tooltip content="复制源码">
        <a-button size="mini" type="text" @click="copySource">
          <template #icon><icon-copy /></template>
        </a-button>
      </a-tooltip>
      <a-tooltip content="下载SVG">
        <a-button size="mini" type="text" @click="downloadSVG">
          <template #icon><icon-download /></template>
        </a-button>
      </a-tooltip>
    </div>

    <a-modal
      v-model:visible="showZoomModal"
      title="Mermaid 图表"
      :footer="false"
      :width="'90vw'"
      :body-style="{ padding:'var(--space-2)', overflow: 'auto', maxHeight: '80vh' }"
    >
      <div v-html="svgContent" class="zoom-svg"></div>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { Message } from '@arco-design/web-vue'
import DOMPurify from 'dompurify'
import mermaid from 'mermaid'

const props = defineProps({
  mermaidCode: {
    type: String,
    required: true
  }
})

const containerRef = ref(null)
const svgWrapper = ref(null)
const svgContent = ref('')
const loading = ref(false)
const error = ref(false)
const showZoomModal = ref(false)

let renderIdCounter = 0

mermaid.initialize({
  startOnLoad: false,
  theme: 'default',
  securityLevel: 'strict',
  fontFamily: 'inherit'
})

const sanitizeSvg = (svg) => DOMPurify.sanitize(svg, {
  USE_PROFILES: { svg: true, svgFilters: true },
  FORBID_TAGS: ['foreignObject', 'iframe', 'object', 'embed', 'script']
})

const renderDiagram = async () => {
  if (!props.mermaidCode?.trim()) {
    svgContent.value = ''
    error.value = false
    return
  }

  loading.value = true
  error.value = false

  try {
    const id = `mermaid-${Date.now()}-${++renderIdCounter}`
    const { svg } = await mermaid.render(id, props.mermaidCode)
    svgContent.value = sanitizeSvg(svg)
    error.value = false
  } catch (e) {
    error.value = true
    svgContent.value = ''
    console.error('Mermaid render error:', e)
  } finally {
    loading.value = false
  }
}

const copySource = () => {
  if (!props.mermaidCode) return
  navigator.clipboard.writeText(props.mermaidCode).then(() => {
    Message.success('源码已复制到剪贴板')
  }).catch(() => {
    Message.error('复制失败')
  })
}

const downloadSVG = () => {
  if (!svgContent.value) return
  const blob = new Blob([svgContent.value], { type: 'image/svg+xml' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'mermaid-diagram.svg'
  a.click()
  URL.revokeObjectURL(url)
}

watch(() => props.mermaidCode, () => {
  renderDiagram()
})

onMounted(() => {
  renderDiagram()
})
</script>

<style scoped>
.mermaid-diagram {
  position:relative;
  overflow-x:auto;
  background:var(--color-bg-1);
  border:var(--stroke) solid var(--color-border);
  border-radius:var(--radius-control);
  min-height:var(--tile-height);
}

.mermaid-svg-wrapper {
  padding:var(--space-2);
  display:flex;
  justify-content:center;
}

.mermaid-svg-wrapper :deep(svg) {
  max-width:100%;
  height:auto;
}

.mermaid-loading {
  display:flex;
  align-items:center;
  justify-content:center;
  gap:var(--space-1);
  padding:var(--space-5) var(--space-2);
  color:var(--color-text-3);
  font-size:var(--text-caption);
}

.loading-spinner {
  width:var(--space-2);
  height:var(--space-2);
  border:calc(var(--stroke) * 2) solid var(--color-fill-3);
  border-top-color:var(--action);
  border-radius:50%;
  animation:spin var(--motion-loop) linear infinite;
}

@keyframes spin {
  to { transform:rotate(360deg); }
}

.mermaid-error {
  padding:var(--space-2);
}

.error-header {
  display:flex;
  align-items:center;
  gap:var(--space-1);
  color:var(--warning);
  font-weight: var(--weight-medium);
  margin-bottom:var(--space-1);
}

.error-icon {
  font-size:var(--text-card);
}

.error-code {
  background:var(--color-fill-2);
  border:var(--stroke) solid var(--color-border);
  border-radius:var(--radius-control);
  padding:var(--space-1) var(--space-2);
  font-size:var(--text-caption);
  line-height:1.6;
  overflow-x:auto;
  white-space:pre-wrap;
  word-break:break-word;
  color:var(--color-text-2);
  margin:0;
}

.mermaid-toolbar {
  position:absolute;
  top:var(--space-1);
  right:var(--space-1);
  display:flex;
  gap:calc(var(--stroke) * 2);
  background:var(--color-bg-1);
  border:var(--stroke) solid var(--color-border);
  border-radius:var(--radius-control);
  padding:calc(var(--stroke) * 2);
  opacity:0;
  transition:opacity var(--motion-normal);
}

.mermaid-diagram:hover .mermaid-toolbar {
  opacity:1;
}

.zoom-svg {
  display:flex;
  justify-content:center;
}

.zoom-svg :deep(svg) {
  max-width:100%;
  height:auto;
}
</style>
