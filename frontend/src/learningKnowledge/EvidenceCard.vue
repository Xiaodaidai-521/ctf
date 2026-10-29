<template>
  <article class="lk-card">
    <h3>{{ evidence.title }}</h3>
    <p class="lk-excerpt">{{ evidence.excerpt }}</p>
    <dl class="lk-meta">
      <dt>来源</dt><dd>{{ evidence.publisher }} · {{ evidence.source_kind }} · {{ evidence.source_ref }}</dd>
      <dt>来源地址（仅文本）</dt><dd>{{ evidence.source_url || '服务器未提供可展示地址' }}</dd>
      <dt>来源版本 / 材料修订</dt><dd>{{ evidence.source_version }} / {{ evidence.material_revision }}</dd>
      <dt>定位 / 段落引用</dt><dd>{{ locator }} / {{ evidence.chunk_ref }}</dd>
      <dt>适用范围</dt><dd>{{ evidence.applicability || '未提供，不应推定适用' }}</dd>
      <dt>许可 / 署名</dt><dd>{{ evidence.license_id }} / {{ evidence.attribution_text }}</dd>
      <dt>课程目录 / 知识点</dt><dd>{{ evidence.catalog_version }} / {{ evidence.knowledge_point_ids?.join('、') || '未提供' }}</dd>
      <dt>证据 ID</dt><dd>{{ evidence.evidence_id }}</dd>
      <dt>签发时间</dt><dd>{{ evidence.issued_at }}</dd>
    </dl>
    <p v-if="unlocated || evidence.location_notice" class="lk-warning">{{ evidence.location_notice || '定位待人工补齐；不可视为已定位证据。' }}</p>
    <slot />
  </article>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({ evidence: { type: Object, required: true } })
const unlocated = computed(() => props.evidence.location_status !== 'located' || !Object.keys(props.evidence.locator || {}).length)
const locator = computed(() => unlocated.value ? '定位待人工补齐' : JSON.stringify(props.evidence.locator))
</script>
