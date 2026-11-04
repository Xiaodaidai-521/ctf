<template>
  <div class="knowledge-map" ref="containerRef">
    <div ref="chartRef" class="chart-container"></div>

    <!-- Hover popover -->
    <a-popover
      v-model:popup-visible="popoverVisible"
      :trigger="'manual'"
      position="rt"
      :content-style="{ maxWidth: '280px' }"
    >
      <template #content>
        <div v-if="hoveredNode" class="node-popover">
          <div class="popover-name">{{ hoveredNode.name }}</div>
          <div class="popover-row">
            <span>掌握度</span>
            <a-progress
              :percent="Math.round(hoveredNode.mastery * 100)"
              :style="{ width: '100px' }"
              size="small"
              :color="masteryColor(hoveredNode.mastery)"
            />
          </div>
          <div class="popover-row">
            <span>重要度</span>
            <span>{{ Math.round(hoveredNode.importance * 100) }}%</span>
          </div>
          <div v-if="hoveredNode.type" class="popover-row">
            <span>类型</span>
            <a-tag size="small">{{ hoveredNode.type }}</a-tag>
          </div>
        </div>
      </template>
      <span class="popover-anchor" :style="popoverAnchorStyle"></span>
    </a-popover>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount, nextTick, computed } from 'vue'
import * as echarts from 'echarts'
import { sequentialColor, tokenValue, tokenNumber } from '@/shared/design/chartTokens'

const props = defineProps({
  nodes: {
    type: Array,
    default: () => []
  },
  edges: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['node-click'])

const containerRef = ref(null)
const chartRef = ref(null)
const popoverVisible = ref(false)
const hoveredNode = ref(null)
const popoverAnchorStyle = ref({})
let chartInstance = null
let resizeObserver = null

const masteryColor = (mastery) => sequentialColor(mastery)

const buildOption = () => {
  const nodes = (props.nodes || []).map(n => ({
    id: n.id,
    name: n.name,
    symbolSize: (n.importance || 0.5) * 50,
    itemStyle: {
      color: masteryColor(n.mastery ?? 0)
    },
    label: {
      show: true,
      fontSize: tokenNumber('text-caption'),
      color: tokenValue('ink')
    },
    // 存储原始数据供 popover 和 click 使用
    _raw: n
  }))

  const links = (props.edges || []).map(e => ({
    source: e.source,
    target: e.target,
    lineStyle: {
      width: (e.strength || 0.5) * 3,
      curveness: 0.2,
      opacity: 0.6
    },
    label: {
      show: !!e.relation,
      formatter: e.relation || '',
      fontSize: tokenNumber('text-caption'),
      color: tokenValue('ink-secondary')
    }
  }))

  return {
    tooltip: {
      show: false
    },
    series: [{
      type: 'graph',
      layout: 'force',
      force: {
        repulsion: 300,
        edgeLength: [100, 250],
        gravity: 0.1,
        friction: 0.6
      },
      roam: true,
      draggable: true,
      data: nodes,
      links: links,
      scaleLimit: {
        min: 0.3,
        max: 3
      },
      emphasis: {
        focus: 'adjacency',
        lineStyle: {
          width: 4
        }
      }
    }]
  }
}

const updateChart = () => {
  if (!chartInstance) return
  chartInstance.setOption(buildOption(), true)
}

const initChart = () => {
  if (!chartRef.value) return
  chartInstance = echarts.init(chartRef.value)
  chartInstance.setOption(buildOption())

  // mouseover → 显示 popover
  chartInstance.on('mouseover', (params) => {
    if (params.dataType === 'node' && params.data._raw) {
      hoveredNode.value = params.data._raw
      // 获取容器位置用于定位 popover anchor
      const rect = containerRef.value?.getBoundingClientRect()
      if (rect) {
        popoverAnchorStyle.value = {
          position: 'fixed',
          left: `${params.event.event.clientX}px`,
          top: `${params.event.event.clientY}px`,
          width: '1px',
          height: '1px',
          pointerEvents: 'none'
        }
      }
      popoverVisible.value = true
    } else {
      popoverVisible.value = false
    }
  })

  // mouseout → 隐藏 popover
  chartInstance.on('mouseout', () => {
    popoverVisible.value = false
    hoveredNode.value = null
  })

  // click → emit
  chartInstance.on('click', (params) => {
    if (params.dataType === 'node' && params.data._raw) {
      emit('node-click', params.data._raw)
    }
  })

  // resize
  resizeObserver = new ResizeObserver(() => {
    chartInstance?.resize()
  })
  resizeObserver.observe(chartRef.value)
}

watch(() => [props.nodes, props.edges], () => {
  updateChart()
}, { deep: true })

onMounted(() => {
  nextTick(initChart)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chartInstance?.dispose()
  chartInstance = null
})
</script>

<style scoped>
.knowledge-map {
  position:relative;
  width:100%;
  min-height:var(--chart-height);
  background:var(--color-bg-1);
  border:var(--stroke) solid var(--color-border);
  border-radius:var(--radius-control);
  overflow:hidden;
}

.chart-container {
  width:100%;
  height:var(--chart-height);
}

.popover-anchor {
  display:block;
}

.node-popover {
  display:flex;
  flex-direction:column;
  gap:var(--space-1);
}

.popover-name {
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
  color:var(--color-text-1);
  margin-bottom:calc(var(--space-1) / 2);
}

.popover-row {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:var(--space-1);
  font-size:var(--text-caption);
  color:var(--color-text-2);
}
</style>
