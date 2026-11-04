<template>
  <div class="material-inspection">
    <h3>{{ inspection.title }}</h3>
    <section aria-label="材料出处">
      <h4>出处</h4>
      <dl>
        <dt>来源</dt><dd>{{ inspection.publisher || '未提供' }} <a v-if="safeSourceLink(inspection.source_url)" :href="safeSourceLink(inspection.source_url)" target="_blank" rel="noopener noreferrer">查看来源</a></dd>
        <dt>来源版本</dt><dd>{{ inspection.source_version || '未提供' }}</dd>
        <dt>许可</dt><dd>{{ inspection.license_id || '未提供' }} <a v-if="safeSourceLink(inspection.license_url)" :href="safeSourceLink(inspection.license_url)" target="_blank" rel="noopener noreferrer">查看许可</a></dd>
      </dl>
    </section>
    <section aria-label="审阅信息">
      <h4>审阅信息</h4>
      <dl>
        <dt>材料版本</dt><dd>第 {{ inspection.revision }} 版</dd>
        <dt>课程</dt><dd>{{ catalogLabel || '课程名称暂不可用' }}</dd>
        <dt>来源日期</dt><dd>{{ dateLabel(inspection.source_date) }}</dd>
        <dt>来源核验日期</dt><dd>{{ dateLabel(inspection.verified_at) }}</dd>
        <dt>下次复查</dt><dd>{{ dateLabel(inspection.recheck_due_at) }}</dd>
        <dt>编写教师</dt><dd>{{ inspection.author_id ? '已记录编写教师，姓名暂不可用' : '编写教师信息不完整，请核实' }}</dd>
        <dt>独立审阅教师</dt><dd>{{ inspection.reviewer_id ? '已记录审阅教师，姓名暂不可用' : '待独立审阅' }}</dd>
        <dt>审阅时间</dt><dd>{{ dateLabel(inspection.reviewed_at) }}</dd>
        <dt>发布时间</dt><dd>{{ dateLabel(inspection.published_at) }}</dd>
        <dt>适用范围</dt><dd>{{ inspection.applicability || '未提供' }}</dd>
        <dt>变更说明</dt><dd>{{ inspection.change_note || '未提供' }}</dd>
        <dt>内容冲突</dt><dd>{{ inspection.conflict_group ? '已归入内容冲突分组，请核对相关材料' : '未设置内容冲突分组' }}</dd>
        <dt>署名要求</dt><dd>{{ inspection.attribution_text || '未提供' }}</dd>
        <dt>复用范围</dt><dd>{{ inspection.reuse_scope || '未提供' }}</dd>
        <dt>材料分类</dt><dd>{{ classLabel(inspection.material_class) }}</dd>
        <dt>提示等级</dt><dd>{{ [1, 2, 3, 4].includes(inspection.hint_level) ? `第 ${inspection.hint_level} 级` : '不适用' }}</dd>
        <dt>审阅状态</dt><dd>{{ statusLabel(inspection.review_status) }}</dd>
        <dt>段落检查</dt><dd>{{ parseLabel(inspection.parse_status) }}</dd>
        <dt>发布范围</dt><dd>{{ inspection.review_status === 'withdrawn' ? '已撤回，不可继续使用' : scopeLabel(inspection.published_scope) }}</dd>
        <dt>受影响任务</dt><dd>{{ inspection.affected_task_count }} 项（包含各次修订，同一任务只计一次）</dd>
      </dl>
      <p class="inspection-note">来源核验日期不代表教师签收或内容仍然有效。此处仅供材料管理，不代表学生能够访问。</p>
    </section>
    <section aria-label="适用任务">
      <h4>适用任务</h4>
      <p v-if="inspection.tasks?.length">关联 {{ inspection.tasks.length }} 项任务。名称缺失时请先核实适用范围；不能据此判断审阅已通过。</p>
      <p v-else class="inspection-warning">尚未提供适用任务，请核实后再提交审阅。</p>
      <ul><li v-for="(task, index) in inspection.tasks" :key="index">{{ taskName(task) }} · 关联 {{ task.knowledge_point_ids?.length || 0 }} 个知识点（名称待核实）</li></ul>
    </section>
    <section aria-label="完整原文">
      <h4>完整原文</h4><pre>{{ inspection.source_snapshot }}</pre>
    </section>
    <section aria-label="材料段落">
      <h4>材料段落（{{ inspection.chunks?.length || 0 }}）</h4>
      <p v-if="!inspection.chunks?.length" class="inspection-warning">没有可检查段落，请补齐后再提交审阅。</p>
      <article v-for="chunk in inspection.chunks" :key="chunk.chunk_ref">
        <h5>{{ formatLocator({ heading_path: chunk.heading_path }) || '章节待补充' }}</h5>
        <p v-if="formatLocator(chunk.locator)">{{ formatLocator(chunk.locator) }}</p>
        <p v-else class="inspection-warning">章节或段落位置待补充，请核对原文。</p>
        <pre>{{ chunk.text }}</pre>
      </article>
    </section>
  </div>
</template>

<script setup>
import { classLabel, statusLabel, parseLabel, scopeLabel, dateLabel, safeSourceLink } from './materialEditor.js'
import { formatLocator } from './libraryController.js'
const props = defineProps({ inspection: { type: Object, required: true }, catalogLabel: String, taskNames: { type: Array, default: () => [] } })
const taskName = task => props.taskNames.find(item => item.key === task.task__task_key && item.version === task.task__version)?.label || '任务名称暂不可用'
</script>

<style scoped>
.material-inspection { display: grid; gap: var(--space-3); }
h3, h4, h5, p { margin: 0; }
h3, h4 { font-size: var(--text-card); }
h5 { font-size: var(--text-body); }
dl { display: grid; grid-template-columns: minmax(0, var(--sidebar-width)) minmax(0, 1fr); gap: var(--space-1) var(--space-2); margin: var(--space-2) 0; }
.is-compact dl { grid-template-columns: 1fr; }
.is-compact dd { margin-bottom: var(--space-1); }
dt { color: var(--ink-secondary); }
dd { margin: 0; white-space: pre-wrap; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; margin: var(--space-2) 0; padding: var(--space-2); background: var(--surface-muted); max-height: var(--message-width); overflow: auto; }
article { border-top: var(--stroke) solid var(--line); padding-top: var(--space-2); margin-top: var(--space-2); }
.inspection-note { color: var(--ink-secondary); font-size: var(--text-caption); }
.inspection-warning { background: var(--warning-soft); color: var(--warning); padding: var(--space-2); }
a { color: var(--action); }
a:hover { color: var(--action-hover); }
a:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
</style>
