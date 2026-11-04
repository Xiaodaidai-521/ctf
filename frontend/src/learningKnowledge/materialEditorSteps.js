import { nextTick, ref, watch } from 'vue'
import { materialPayload, metadataFields, taskSelectionBlocker } from './materialEditor.js'

export const materialEditorSteps = [
  { number: 1, label: '基本信息' },
  { number: 2, label: '来源与许可' },
  { number: 3, label: '原文内容' },
]
const basicFields = new Set(['title', 'applicability', 'conflict_group'])
const contentFields = new Set(['source_snapshot', 'change_note'])
export const materialStepForField = key => contentFields.has(key) ? 3 : basicFields.has(key) ? 1 : 2

// Presentation state stays outside the payload. Hidden fields remain mounted and
// retain their original required/type/length rules; only submit focus is deferred.
export function useMaterialEditorSteps(props, emit) {
  const form = ref(null)
  const step = ref(props.initialStep || 1)
  const validationIssue = ref(null)
  watch(() => [props.draft, props.initialStep], () => {
    step.value = props.initialStep || 1
    validationIssue.value = null
  })
  const fieldsForStep = number => metadataFields.filter(field => materialStepForField(field.key) === number)
  function basicIssue() {
    if (props.mode === 'revise' && !props.targetId) return { step: 1, key: 'revision_target', message: '请选择已授权的修订目标。' }
    if (!props.draft.task_ids?.length) return { step: 1, key: 'task_ids', message: taskSelectionBlocker }
    if (props.mode === 'register' && !props.draft.catalog_version) return { step: 1, key: 'catalog_version', message: '请选择课程。' }
    return null
  }
  function metadataIssue(number) {
    for (const field of fieldsForStep(number)) {
      const value = props.draft.metadata[field.key]
      if (field.required && (typeof value !== 'string' || !value.trim())) return { step: number, key: field.key, message: `请填写${field.label}。` }
      if (value === undefined && !field.required) continue
      if (typeof value !== 'string' || (field.max && [...value].length > field.max)) return { step: number, key: field.key, message: `请检查${field.label}的内容和长度。` }
      if (field.type === 'date' && (!/^\d{4}-\d{2}-\d{2}$/.test(value)
        || !Number.isFinite(Date.parse(value)) || new Date(value).toISOString().slice(0, 10) !== value)) return { step: number, key: field.key, message: `请选择有效的${field.label}。` }
    }
    return null
  }
  function nativeIssue(number) {
    for (const control of form.value?.querySelectorAll('[data-material-field]') || []) {
      if (number && Number(control.closest('[data-material-step]')?.dataset.materialStep) !== number) continue
      if (!control.willValidate || control.checkValidity()) continue
      return {
        step: Number(control.closest('[data-material-step]')?.dataset.materialStep) || 1,
        key: control.dataset.materialField,
        message: control.validationMessage || '请检查此项内容。',
      }
    }
    return null
  }
  async function showIssue(issue) {
    validationIssue.value = issue
    step.value = issue.step
    // Never reportValidity on a display:none control. Vue must reveal its group
    // before the browser is allowed to focus or show the native validation bubble.
    await nextTick()
    const control = form.value?.querySelector(`[data-material-field="${issue.key}"]`)
    control?.focus()
    if (control?.willValidate && !control.checkValidity()) control.reportValidity()
    if (!control) form.value?.querySelector('[data-material-validation]')?.focus()
  }
  function selectStep(number) {
    if (props.busy || !materialEditorSteps.some(item => item.number === number)) return
    step.value = number
    validationIssue.value = null
  }
  async function nextStep() {
    if (props.busy) return
    const issue = (step.value === 1 && basicIssue()) || metadataIssue(step.value) || nativeIssue(step.value)
    if (issue) return showIssue(issue)
    selectStep(Math.min(3, step.value + 1))
  }
  async function submit() {
    if (props.busy) return
    let issue = basicIssue()
    for (const number of [1, 2, 3]) issue ||= metadataIssue(number) || nativeIssue(number)
    if (!issue) {
      try { materialPayload(props.draft, props.mode) } catch (error) {
        const field = metadataFields.find(item => error.message.includes(item.label))
        issue = { step: field ? materialStepForField(field.key) : 1, key: field?.key || 'task_ids', message: error.message }
      }
    }
    if (issue) return showIssue(issue)
    validationIssue.value = null
    emit('save')
  }
  return { form, step, validationIssue, fieldsForStep, selectStep, nextStep, submit }
}
