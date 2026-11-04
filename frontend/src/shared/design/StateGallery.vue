<template>
  <main class="state-gallery">
    <header><p>共享设计 · 本地验收样本</p><h1>基础组件状态对照</h1><p>此页只用于观察组件状态，不展示业务数据。</p></header>
    <section><h2>操作与输入</h2><div class="state-row"><div><p>默认 / 悬停 / 聚焦 / 按下</p><a-button id="state-action" type="primary" @click="saved = true">保存学习目标</a-button></div><div><p>次要操作</p><a-button>返回</a-button></div><div><p>禁用</p><a-button type="primary" disabled>暂不可用</a-button></div><div><p>加载</p><a-button loading>正在保存</a-button></div></div>
      <div class="state-inputs"><label>学习目标<a-input placeholder="输入目标" /></label><label>已禁用<a-input disabled model-value="暂不可编辑" /></label><label>需要修正<a-input error placeholder="请补充目标" /><span class="error-copy"><icon-exclamation-circle /> 请填写学习目标</span></label></div>
    </section>
    <section><h2>页签与菜单</h2><a-tabs default-active-key="plan"><a-tab-pane key="plan" title="学习计划">选中项以文字与下划线共同标记。</a-tab-pane><a-tab-pane key="review" title="复习提醒">查看待复习内容。</a-tab-pane><a-tab-pane key="disabled" title="尚未开放" disabled /></a-tabs><a-menu mode="horizontal" :default-selected-keys="['guide']"><a-menu-item key="guide">智航</a-menu-item><a-menu-item key="practice">靶场</a-menu-item><a-menu-item key="disabled" disabled>暂不可用</a-menu-item></a-menu></section>
    <section><h2>内容与反馈</h2><div class="feedback-grid"><a-card title="默认内容"><p>正文、辅助说明与操作使用共享层级。</p><a-button type="text">查看详情</a-button></a-card><a-card title="空状态"><a-empty description="暂无学习记录" /></a-card></div><div class="feedback-list"><a-alert type="success">{{ saved ? '学习目标已保存。' : '保存成功。可以继续学习。' }}</a-alert><a-alert type="warning">部分记录暂时无法读取，已有内容仍可使用。</a-alert><a-alert type="error">读取失败，请稍后重试。<a-button type="text">重试</a-button></a-alert></div></section>
  </main>
</template>
<script setup>
import { ref } from 'vue'
const saved = ref(false)
</script>
<style scoped>
.state-gallery { width: min(var(--page-width), calc(100% - var(--page-gutter) * 2)); margin: var(--space-4) auto; }
header, section { margin-bottom: var(--space-4); }
header p, .state-row p { color: var(--ink-secondary); }
section { padding: var(--space-3); background: var(--surface); border-radius: var(--radius-panel); }
.state-row { display: flex; flex-wrap: wrap; gap: var(--space-4); }
.state-inputs, .feedback-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, var(--sidebar-width)), 1fr)); gap: var(--space-3); margin-block: var(--space-3); }
.state-inputs label { display: grid; align-content: start; gap: var(--space-1); }
.error-copy { color: var(--negative); }
.feedback-list { display: grid; gap: var(--space-2); }
</style>
