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
  return value
}

const badgeClass = (value) => {
  const normalized = String(value || '').toLowerCase()
  if (['completed', 'active', 'final', 'exported', 'published', 'low', 'resolved'].includes(normalized)) return 'ok'
  if (['running', 'draft', 'medium', 'investigating'].includes(normalized)) return 'warn'
  if (['failed', 'critical', 'high', 'open'].includes(normalized)) return 'danger'
  return 'neutral'
}
</script>

<style scoped>
@import '../../assets/admin.css';

.legal-workspace {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.legal-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.legal-toolbar h2 {
  margin: 0 0 6px;
  font-size: 22px;
  color: #1f2937;
}

.legal-toolbar p {
  margin: 0;
  color: #64748b;
  max-width: 68ch;
}

.toolbar-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.metric-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
}

.metric-tile {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.metric-label {
  font-size: 12px;
  color: #64748b;
}

.metric-tile strong {
  font-size: 24px;
  color: #0f172a;
}

.metric-tile small {
  color: #64748b;
}

.content-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 18px;
}

.content-grid.single {
  grid-template-columns: 1fr;
}

.table-wrap {
  overflow-x: auto;
}

.legal-table th,
.legal-table td {
  white-space: nowrap;
}

.search-input {
  width: 240px;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}

.status-badge.ok {
  background: #ecfdf5;
  color: #047857;
}

.status-badge.warn {
  background: #fffbeb;
  color: #b45309;
}

.status-badge.danger {
  background: #fef2f2;
  color: #b91c1c;
}

.status-badge.neutral {
  background: #f1f5f9;
  color: #475569;
}

.inline-action {
  border: 0;
  background: transparent;
  color: #2563eb;
  cursor: pointer;
  font-weight: 600;
  margin-right: 10px;
}

.inline-action:disabled {
  color: #94a3b8;
  cursor: not-allowed;
}

.aside-panel {
  min-height: 240px;
}

.loading-state {
  padding: 28px;
  text-align: center;
  color: #64748b;
}

@media (max-width: 1100px) {
  .content-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .legal-toolbar {
    flex-direction: column;
  }

  .toolbar-actions,
  .search-input {
    width: 100%;
  }
}
</style>
