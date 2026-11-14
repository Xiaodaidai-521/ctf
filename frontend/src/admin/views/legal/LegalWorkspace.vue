<template>
  <div class="legal-workspace">
    <div class="legal-toolbar">
      <div>
        <h2>{{ title }}</h2>
        <p>{{ subtitle }}</p>
      </div>
      <div class="toolbar-actions">
        <button
          v-for="action in actions"
          :key="action.key"
          class="action-btn"
          :class="action.primary ? 'btn-primary' : 'btn-default'"
          :disabled="loading || action.disabled"
          @click="$emit('action', action.key)"
        >
          {{ action.label }}
        </button>
        <button class="action-btn btn-default" :disabled="loading" @click="$emit('refresh')">刷新</button>
      </div>
    </div>

    <div class="metric-row">
      <div v-for="metric in metrics" :key="metric.label" class="metric-tile">
        <span class="metric-label">{{ metric.label }}</span>
        <strong>{{ metric.value }}</strong>
        <small>{{ metric.hint }}</small>
      </div>
    </div>

    <div class="content-grid" :class="{ single: !showAside }">
      <section class="page-card">
        <div class="page-header">
          <h3 class="page-title">{{ tableTitle }}</h3>
          <div class="page-actions">
            <input
              v-model="keyword"
              class="form-input search-input"
              type="text"
              placeholder="搜索标题、状态或摘要"
            />
          </div>
        </div>

        <div class="table-wrap">
          <table class="admin-table legal-table">
            <thead>
              <tr>
                <th v-for="column in columns" :key="column.key">{{ column.label }}</th>
                <th v-if="rowActions.length">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in filteredRows" :key="row.id || row.key">
                <td v-for="column in columns" :key="column.key">
                  <span v-if="column.badge" class="status-badge" :class="badgeClass(row[column.key])">
                    {{ formatCell(row, column) }}
                  </span>
                  <span v-else>{{ formatCell(row, column) }}</span>
                  <template v-if="column.key === 'title'"><ProtectionBadge v-for="(label, field) in protectionLabels" :key="field" :status="row.protection?.[field]" :label="label" /></template>
                </td>
                <td v-if="rowActions.length">
                  <button
                    v-for="action in rowActions"
                    :key="action.key"
                    class="inline-action"
                    :disabled="action.disabled && action.disabled(row)"
                    @click="$emit('row-action', action.key, row)"
                  >
                    {{ action.label }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-if="!loading && filteredRows.length === 0" class="empty-state">
            <div class="empty-icon">∅</div>
            <p>暂无数据</p>
          </div>
          <div v-if="loading" class="loading-state">加载中...</div>
        </div>
      </section>

      <aside v-if="showAside" class="page-card aside-panel">
        <div class="page-header">
          <h3 class="page-title">{{ asideTitle }}</h3>
        </div>
        <slot name="aside" />
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import ProtectionBadge from '@/shared/privacy/ProtectionBadge.vue'
const protectionLabels = { input_text: '分析原文加密保存', content: '报告正文加密保存', manual_notes: '人工备注加密保存' }
import { legalLabel, legalBadgeTone } from './displayLabels.js'

const props = defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  metrics: { type: Array, default: () => [] },
  columns: { type: Array, default: () => [] },
  rows: { type: Array, default: () => [] },
  actions: { type: Array, default: () => [] },
  rowActions: { type: Array, default: () => [] },
  tableTitle: { type: String, default: '数据列表' },
  asideTitle: { type: String, default: '详情' },
  showAside: { type: Boolean, default: true },
  loading: { type: Boolean, default: false },
})

defineEmits(['refresh', 'action', 'row-action'])

const keyword = ref('')

const filteredRows = computed(() => {
  const value = keyword.value.trim().toLowerCase()
  if (!value) return props.rows
  return props.rows.filter((row) => JSON.stringify(row).toLowerCase().includes(value))
})

const formatCell = (row, column) => {
  if (column.formatter) return column.formatter(row[column.key], row)
  const value = row[column.key]
  if (value === null || value === undefined || value === '') return '-'
  if (column.labelKey) return legalLabel(column.labelKey, value)
  return value
}

const badgeClass = legalBadgeTone
</script>

<style scoped src="../../assets/admin.css"></style>

<style scoped>

.legal-workspace {
  display:flex;
  flex-direction:column;
  gap:var(--space-2);
}

.legal-toolbar {
  display:flex;
  justify-content:space-between;
  gap:var(--space-2);
  align-items:flex-start;
}

.legal-toolbar h2 {
  margin:0 0 calc(var(--space-1) / 2);
  font-size:var(--text-card);
  color:var(--action);
}

.legal-toolbar p {
  margin:0;
  color:var(--ink-secondary);
  max-width:68ch;
}

.toolbar-actions {
  display:flex;
  flex-wrap:wrap;
  gap:var(--space-1);
  justify-content:flex-end;
}

.metric-row {
  display:grid;
  grid-template-columns:repeat(auto-fit, minmax(var(--row-label-width), 1fr));
  gap:var(--space-1);
}

.metric-tile {
  background:var(--surface);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
  padding:var(--space-2);
  display:flex;
  flex-direction:column;
  gap:calc(var(--space-1) / 2);
}

.metric-label {
  font-size:var(--text-caption);
  color:var(--ink-secondary);
}

.metric-tile strong {
  font-size:var(--text-section);
  color:var(--action);
}

.metric-tile small {
  color:var(--ink-secondary);
}

.content-grid {
  display:grid;
  grid-template-columns:minmax(0, 1fr) var(--panel-width);
  gap:var(--space-2);
}

.content-grid.single {
  grid-template-columns:1fr;
}

.table-wrap {
  overflow-x:auto;
}

.legal-table th,
.legal-table td {
  white-space:nowrap;
}

.search-input {
  width:var(--sidebar-width);
}

.status-badge {
  display:inline-flex;
  align-items:center;
  min-height:var(--space-3);
  padding:var(--focus-width) var(--space-1);
  border-radius:var(--radius-pill);
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
}

.status-badge.ok {
  background:var(--positive-soft);
  color:var(--positive);
}

.status-badge.warn {
  background:var(--warning-soft);
  color:var(--warning);
}

.status-badge.danger {
  background:var(--negative-soft);
  color:var(--negative);
}

.status-badge.neutral {
  background:var(--surface);
  color:var(--ink-secondary);
}

.inline-action {
  border:0;
  background:transparent;
  color:var(--action);
  cursor:pointer;
  font-weight: var(--weight-strong);
  margin-right:var(--space-1);
}

.inline-action:disabled {
  color:var(--ink-muted);
  cursor:not-allowed;
}

.aside-panel {
  min-height:var(--content-short-height);
}

.loading-state {
  padding:var(--space-3);
  text-align:center;
  color:var(--ink-secondary);
}

@media (max-width: 1120px) {
  .content-grid {
    grid-template-columns:1fr;
  }
}

@media (max-width: 768px) {
  .legal-toolbar {
    flex-direction:column;
  }

  .toolbar-actions,
  .search-input {
    width:100%;
  }

  .content-grid,
  .content-grid.single {
    grid-template-columns:minmax(0, 1fr);
  }

  .content-grid > .page-card {
    min-width:0;
  }

  .page-header {
    flex-direction:column;
    align-items:stretch;
  }
}
</style>
