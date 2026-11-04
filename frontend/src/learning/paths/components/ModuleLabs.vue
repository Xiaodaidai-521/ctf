<template>
  <section class="module-labs" aria-labelledby="module-labs-title">
    <header class="labs-head">
      <h2 id="module-labs-title">实践实验</h2>
      <span class="count">{{ labs.length }} 个</span>
    </header>
    <p class="labs-note">{{ capability.reason }}</p>

    <ol v-if="labs.length" class="lab-list">
      <li v-for="lab in labs" :key="lab.id ?? lab.order" class="lab-card">
        <div class="lab-copy">
          <div class="lab-tags">
            <span class="tag">{{ lab.difficultyLabel }}</span>
            <span class="tag">{{ lab.scoreLabel }}</span>
            <span v-if="lab.optional" class="tag">选修</span>
          </div>
          <h3 class="lab-title">{{ lab.title }}</h3>
          <p class="lab-description">{{ lab.description }}</p>
          <p class="lab-status">状态：{{ capability.statusLabel }}</p>
        </div>
        <button type="button" class="btn" @click="openLab(lab)">查看说明</button>
      </li>
    </ol>
    <p v-else class="labs-empty">本章节暂未关联实验。</p>

    <div v-if="selected" class="modal-overlay" @click.self="closeLab">
      <div class="modal-content" role="dialog" aria-modal="true" aria-labelledby="lab-title">
        <header class="modal-header">
          <h3 id="lab-title">{{ selected.title }}</h3>
          <button type="button" class="close-btn" aria-label="关闭实验说明" @click="closeLab"><icon-close aria-hidden="true" /></button>
        </header>
        <div class="modal-body">
          <div class="lab-facts">
            <span class="tag">{{ selected.difficultyLabel }}</span>
            <span class="tag">{{ selected.scoreLabel }}</span>
            <span v-if="selected.optional" class="tag">选修</span>
          </div>
          <p class="lab-description">{{ selected.description }}</p>
          <div class="env-block">
            <h4>实验环境与提交</h4>
            <p class="hint">{{ capability.reason }}</p>
            <label class="flag-field">
              <span>提交 Flag</span>
              <input type="text" placeholder="当前不可提交" disabled />
            </label>
            <button type="button" class="btn" disabled>提交（待接口接入）</button>
            <p class="hint">附件与题目入口同样未在关联字段中返回；原入口保留，待后端提供映射后再接入。</p>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  labs: { type: Array, default: () => [] },
  capability: { type: Object, required: true },
})

const selected = ref(null)
function openLab(lab) { selected.value = lab }
function closeLab() { selected.value = null }
</script>

<style scoped>
.module-labs { display: grid; gap: var(--space-2); align-content: start; min-width: 0; padding: var(--space-3); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); background: var(--surface); }
.labs-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--space-1); }
h2 { margin: 0; font-size: var(--text-card); }
.count { color: var(--ink-muted); font-size: var(--text-caption); }
.labs-note { margin: 0; padding: var(--space-1) var(--space-2); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); line-height: 1.6; }
.lab-list { display: grid; gap: var(--space-2); margin: 0; padding: 0; list-style: none; }
.lab-card { display: grid; gap: var(--space-1); min-width: 0; padding: var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-control); }
.lab-copy { display: grid; gap: calc(var(--space-1) / 2); min-width: 0; }
.lab-tags { display: flex; flex-wrap: wrap; gap: var(--space-1); }
.tag { padding: 0 var(--space-1); border: var(--stroke) solid var(--line); border-radius: var(--radius-pill); color: var(--ink-secondary); font-size: var(--text-caption); }
.lab-title { margin: 0; font-size: var(--text-caption); font-weight: var(--weight-strong); overflow-wrap: anywhere; }
.lab-description { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); line-height: 1.6; overflow-wrap: anywhere; }
.lab-status { margin: 0; color: var(--ink-muted); font-size: var(--text-caption); }
.labs-empty { margin: 0; color: var(--ink-muted); font-size: var(--text-caption); }
.btn { display: inline-flex; align-items: center; justify-content: center; justify-self: start; min-height: var(--control-height); padding: 0 var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; font-size: var(--text-caption); cursor: pointer; }
.btn:hover:not(:disabled) { border-color: var(--action); color: var(--action); }
.btn:active:not(:disabled) { background: var(--surface-muted); }
.btn:disabled { border-color: var(--line); background: var(--surface-muted); color: var(--ink-muted); cursor: not-allowed; }
.btn:focus-visible, .close-btn:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.modal-overlay { position: fixed; inset: 0; z-index: calc(var(--z-overlay) + 1); display: flex; align-items: center; justify-content: center; padding: var(--page-gutter); background: var(--surface-muted); }
.modal-content { display: flex; flex-direction: column; width: 100%; max-width: var(--reading-width); max-height: calc(100dvh - var(--page-gutter) * 2); overflow: hidden; border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); background: var(--surface); box-shadow: var(--shadow-overlay); }
.modal-header { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); padding: var(--space-2) var(--space-3); border-bottom: var(--stroke) solid var(--line); }
.modal-header h3 { margin: 0; font-size: var(--text-card); }
.modal-body { display: grid; gap: var(--space-2); padding: var(--space-3); overflow-y: auto; }
.lab-facts { display: flex; flex-wrap: wrap; gap: var(--space-1); }
.env-block { display: grid; gap: var(--space-1); padding: var(--space-2); border-radius: var(--radius-control); background: var(--surface-muted); }
.env-block h4 { margin: 0; font-size: var(--text-caption); font-weight: var(--weight-strong); }
.hint { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); line-height: 1.6; }
.flag-field { display: grid; gap: calc(var(--space-1) / 2); color: var(--ink-secondary); font-size: var(--text-caption); }
.flag-field input { min-height: var(--control-height); padding: 0 var(--space-1); border: var(--stroke) solid var(--line); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink-muted); font: inherit; }
.close-btn { display: inline-flex; align-items: center; justify-content: center; width: var(--control-height); min-height: var(--control-height); border: var(--stroke) solid transparent; border-radius: var(--radius-control); background: transparent; color: var(--ink-secondary); font: inherit; cursor: pointer; }
.close-btn:hover { background: var(--surface-hover); border-color: var(--line); }
.is-compact .module-labs .btn { justify-self: stretch; }
</style>
