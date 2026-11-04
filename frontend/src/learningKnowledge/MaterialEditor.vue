<template>
  <form ref="form" class="material-editor" autocomplete="off" novalidate @submit.prevent="submit">
    <nav class="editor-steps" aria-label="材料登记步骤">
      <button v-for="item in materialEditorSteps" :key="item.number" type="button" :disabled="busy"
        :aria-current="step === item.number ? 'step' : undefined" :aria-controls="`material-step-${item.number}`" @click="selectStep(item.number)">
        <span>{{ item.number }}</span>{{ item.label }}
      </button>
    </nav>
    <p v-if="validationIssue" class="editor-warning" role="alert" tabindex="-1" data-material-validation>{{ validationIssue.message }}</p>
    <section v-show="step === 1" id="material-step-1" data-material-step="1" class="editor-group" aria-label="基本信息">
    <label>表单类型
      <select :value="mode" :disabled="busy" @change="$emit('mode-change', $event.target.value)">
        <option value="register">登记新材料</option><option value="revise">所选材料的新修订</option>
      </select>
    </label>
    <template v-if="mode === 'revise'">
      <label>修订目标<select data-material-field="revision_target" :value="targetId" :disabled="busy" @change="$emit('revision-target', $event.target.value)"><option value="">请选择已授权的材料</option><option v-for="material in materials" :key="material.material_id" :value="material.material_id">{{ material.title }}</option></select></label>
      <p>目标材料：{{ targetTitle || '尚未选择，请先选择材料' }}。新修订不更改课程、材料分类和来源关联；请重新填写完整内容。</p>
    </template>
    <div class="editor-search">
      <button type="button" :disabled="busy" @click="$emit('download-template')">下载{{ mode === 'register' ? '登记' : '修订' }}模板</button>
      <button type="button" :disabled="busy" @click="$emit('choose-file', mode)">导入材料文件</button>
    </div>
    <p class="editor-help">请由课程负责人按模板补齐课程和任务后导入。导入成功会替换当前表单；所有内容仍需检查，不会自动提交。</p>
    <fieldset :disabled="busy">
      <legend>课程与用途</legend>
      <div class="editor-fields">
        <label>课程
          <select v-if="mode === 'register'" data-material-field="catalog_version" :value="draft.catalog_version" :disabled="busy || (!catalogs.length && !draft.catalog_version)" @change="$emit('catalog-change', $event.target.value)">
            <option value="">{{ catalogs.length ? '请选择课程' : '课程名称暂不可用' }}</option>
            <option v-if="draft.catalog_version && !catalogs.some(item => item.value === draft.catalog_version)" :value="draft.catalog_version">已导入课程，名称暂不可读取</option>
            <option v-for="item in catalogs" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
          <span v-else>{{ targetCatalog || '课程名称暂不可用' }}</span>
        </label>
        <div>
          <p>适用任务（最多二十项）</p>
          <p v-if="draft.task_ids.length">已导入 {{ draft.task_ids.length }} 项适用任务，名称暂不可读取，提交时核验权限。</p>
          <p v-else>尚未填写适用任务，请先导入材料文件。</p>
        </div>
        <p id="material-task-blocker" class="editor-warning editor-full" role="status">{{ taskSelectionBlocker }}</p>
        <p class="editor-help editor-full">这里只能列出当前可读取的课程；其他课程暂不可选。能查看课程不代表拥有材料管理授权。</p>
        <template v-if="mode === 'register'">
          <label>材料分类<select v-model="draft.material_class"><option v-for="[value, label] in materialClasses" :key="value" :value="value">{{ label }}</option></select></label>
          <label v-if="draft.material_class === 'hint'">提示等级<select v-model="draft.hint_level"><option v-for="level in 4" :key="level" :value="level">第 {{ level }} 级</option></select></label>
        </template>
      </div>
    </fieldset>
    <fieldset :disabled="busy">
      <legend>基本信息</legend>
      <div class="editor-fields">
        <label v-for="field in fieldsForStep(1)" :key="field.key" :class="{ 'editor-full': field.multiline }">
          {{ field.label }}{{ field.required ? '（必填）' : '（选填）' }}
          <textarea v-if="field.multiline" v-model="draft.metadata[field.key]" :data-material-field="field.key" :required="field.required" :maxlength="field.max" rows="3" />
          <input v-else v-model="draft.metadata[field.key]" :data-material-field="field.key" :type="field.type || 'text'" :required="field.required" :maxlength="field.max" />
          <span v-if="field.help" class="editor-help">{{ field.help }}</span>
        </label>
      </div>
    </fieldset>
    </section>
    <section v-show="step === 2" id="material-step-2" data-material-step="2" class="editor-group" aria-label="来源与许可">
    <fieldset v-if="mode === 'register'" :disabled="busy">
      <legend>来源关联</legend>
      <label>来源类型<select :value="draft.source_type" @change="$emit('source-type', $event.target.value)"><option v-for="[value, label] in sourceTypes" :key="value" :value="value">{{ label }}</option></select></label>
      <p v-if="draft.source_object_id" class="editor-help">已保留所选或导入的关联来源；名称无法读取时不会显示。提交时核验来源与权限。</p>
      <template v-if="draft.source_type !== 'teacher_authored'">
        <div class="editor-search">
          <label>查找来源<input :value="sourceQuery" maxlength="500" @input="$emit('update:sourceQuery', $event.target.value)" @keydown.enter.prevent="$emit('source-search', 1)" /></label>
          <button type="button" @click="$emit('source-search', 1)">查找</button>
        </div>
        <label>{{ draft.source_type === 'legal_clause' ? '法律文件' : '来源名称' }}
          <select :value="draft.source_type === 'legal_clause' ? sourceDocument : draft.source_object_id" @change="$emit('source-select', $event.target.value ? Number($event.target.value) : null)">
            <option value="">{{ draft.source_type === 'legal_clause' && draft.source_object_id ? '已导入条文，请选择文件以更换' : '不关联现有条目' }}</option>
            <option v-if="draft.source_type !== 'legal_clause' && draft.source_object_id && !sourceOptions.some(item => item.value === draft.source_object_id)" :value="draft.source_object_id">已导入来源，名称暂不可读取</option>
            <option v-for="item in sourceOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </label>
        <div class="editor-search">
          <button type="button" :disabled="!sourcePrevious" @click="$emit('source-search', sourcePage - 1)">上一页来源</button>
          <button type="button" :disabled="!sourceNext" @click="$emit('source-search', sourcePage + 1)">下一页来源</button>
        </div>
        <label v-if="draft.source_type === 'legal_clause'">条文
          <select v-model="draft.source_object_id" :disabled="!clauseOptions.length">
            <option :value="null">请选择条文</option><option v-if="draft.source_object_id && !clauseOptions.some(item => item.value === draft.source_object_id)" :value="draft.source_object_id">已导入条文，名称暂不可读取</option><option v-for="item in clauseOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </label>
        <p v-if="!sourceOptions.length" class="editor-help">暂无可选择来源。这里只显示你有权读取的资料，部分已关联材料的来源不在此列。</p>
        <p class="editor-help">未关联现有来源时，发布可能受限。选择来源不会自动替你填写或核验原文、版本与许可。</p>
      </template>
    </fieldset>
    <fieldset :disabled="busy">
      <legend>来源与许可</legend>
      <div class="editor-fields">
        <label v-for="field in fieldsForStep(2)" :key="field.key" :class="{ 'editor-full': field.multiline }">
          {{ field.label }}{{ field.required ? '（必填）' : '（选填）' }}
          <textarea v-if="field.multiline" v-model="draft.metadata[field.key]" :data-material-field="field.key" :required="field.required" :maxlength="field.max" :rows="field.key === 'source_snapshot' ? 12 : 3" />
          <input v-else v-model="draft.metadata[field.key]" :data-material-field="field.key" :type="field.type || 'text'" :required="field.required" :maxlength="field.max" />
          <span v-if="field.help" class="editor-help">{{ field.help }}</span>
        </label>
        <label>复查时间（选填，按本地时间）<input data-material-field="recheck_due_at" type="datetime-local" step="1" :value="recheckLocal" @input="setRecheck($event.target.value)" /></label>
      </div>
    </fieldset>
    </section>
    <section v-show="step === 3" id="material-step-3" data-material-step="3" class="editor-group" aria-label="原文内容">
    <fieldset :disabled="busy">
      <legend>原文内容</legend>
      <div class="editor-fields">
        <label v-for="field in fieldsForStep(3)" :key="field.key" :class="{ 'editor-full': field.multiline }">
          {{ field.label }}{{ field.required ? '（必填）' : '（选填）' }}
          <textarea v-model="draft.metadata[field.key]" :data-material-field="field.key" :required="field.required" :maxlength="field.max" :rows="field.key === 'source_snapshot' ? 12 : 3" />
          <span v-if="field.help" class="editor-help">{{ field.help }}</span>
        </label>
      </div>
    </fieldset>
    </section>
    <p class="editor-help">来源核验日期不代表教师签收或内容仍然有效。收起或切换步骤会保留草稿；离开页面后，未提交内容将清空。操作中断时请先核对列表，避免重复创建。</p>
    <div class="editor-search">
      <button v-if="step > 1" type="button" :disabled="busy" @click="selectStep(step - 1)">上一步</button>
      <button v-if="step < 3" type="button" :disabled="busy" @click="nextStep">下一步</button>
      <button v-show="step === 3" type="submit" :disabled="busy" aria-describedby="material-task-blocker">{{ mode === 'register' ? '登记材料' : '创建新修订' }}</button>
    </div>
  </form>
</template>

<script setup>
import { computed } from 'vue'
import { materialClasses, sourceTypes, materialEditorSteps, useMaterialEditorSteps, taskSelectionBlocker } from './materialEditor.js'
const props = defineProps({
  draft: { type: Object, required: true }, mode: String, busy: Boolean, initialStep: { type: Number, default: 1 },
  targetTitle: String, targetId: String, materials: { type: Array, default: () => [] }, targetCatalog: String, catalogs: { type: Array, default: () => [] },
  sourceQuery: String, sourceOptions: { type: Array, default: () => [] }, sourcePage: Number,
  sourcePrevious: Boolean, sourceNext: Boolean, sourceDocument: Number,
  clauseOptions: { type: Array, default: () => [] },
})
const emit = defineEmits(['save', 'mode-change', 'source-type', 'source-search', 'source-select', 'update:sourceQuery', 'choose-file', 'download-template', 'catalog-change', 'revision-target'])
const { form, step, validationIssue, fieldsForStep, selectStep, nextStep, submit } = useMaterialEditorSteps(props, emit)
const recheckLocal = computed(() => {
  const value = props.draft.metadata.recheck_due_at
  if (!value) return ''
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return ''
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 19)
})
function setRecheck(value) {
  props.draft.metadata.recheck_due_at = value ? new Date(value).toISOString() : null
}
</script>

<style scoped>
.material-editor, .editor-group, fieldset, .editor-fields { display: grid; gap: var(--space-2); }
.editor-steps { display: flex; flex-wrap: wrap; gap: var(--space-1); border-bottom: var(--stroke) solid var(--line); }
.editor-steps button { display: flex; align-items: center; gap: var(--space-1); border: 0; border-bottom: var(--stroke) solid transparent; border-radius: 0; font-size: var(--text-caption); color: var(--ink-secondary); background: transparent; }
.editor-steps button[aria-current="step"] { border-bottom-color: var(--action); color: var(--action); font-weight: var(--weight-strong); }
.editor-steps span { font-variant-numeric: tabular-nums; }
fieldset { border: 0; border-top: var(--stroke) solid var(--line); padding: var(--space-2) 0; margin: 0; min-width: 0; }
legend { font-size: var(--text-card); font-weight: var(--weight-strong); padding: 0 var(--space-1) 0 0; }
.editor-fields { grid-template-columns: repeat(auto-fit, minmax(min(100%, var(--menu-width)), 1fr)); }
.editor-full { grid-column: 1 / -1; }
label { display: grid; gap: var(--space-1); min-width: 0; }
input, textarea, select, button { font: inherit; color: var(--ink); background: var(--surface); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); padding: var(--space-1) var(--space-2); min-height: var(--control-height); min-width: 0; max-width: 100%; box-sizing: border-box; }
textarea { resize: vertical; }
button { width: fit-content; cursor: pointer; color: var(--action); transition: background var(--motion-fast) var(--motion-ease); }
button:hover:not(:disabled) { background: var(--surface-hover); }
button:active:not(:disabled) { background: var(--action-soft); color: var(--action-pressed); }
:disabled { background: var(--disabled); color: var(--disabled-ink); cursor: not-allowed; }
:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.editor-search { display: flex; flex-wrap: wrap; align-items: end; gap: var(--space-1); }
.editor-search label { flex: 1; }
.editor-help { font-size: var(--text-caption); font-weight: var(--weight-normal); color: var(--ink-secondary); }
.editor-warning { background: var(--warning-soft); color: var(--warning); padding: var(--space-2); border-radius: var(--radius-control); }
p { margin: 0; }
</style>
