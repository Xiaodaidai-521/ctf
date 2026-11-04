<template>
  <dialog ref="dialog" class="content-dialog" :aria-label="title" @cancel.prevent="requestClose" @click="onBackdrop">
    <header class="dialog-header"><h2>{{ title }}</h2><button class="content-button" :disabled="busy" aria-label="关闭" @click="requestClose"><AppIcon name="bi-x-lg" /></button></header>
    <div class="dialog-body"><slot /></div>
    <footer class="dialog-footer"><slot name="footer" /></footer>
  </dialog>
</template>
<script setup>
import { onMounted, onBeforeUnmount, ref } from 'vue'
import AppIcon from '../design/AppIcon.vue'
const props = defineProps({ title: { type: String, required: true }, busy: Boolean })
const emit = defineEmits(['close'])
const dialog = ref(null)
let previousFocus
const requestClose = () => { if (!props.busy) emit('close') }
function onBackdrop(event) {
  if (event.target !== dialog.value) return
  const bounds = dialog.value.getBoundingClientRect()
  if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) requestClose()
}
onMounted(() => { previousFocus = document.activeElement; dialog.value.showModal() })
onBeforeUnmount(() => { dialog.value?.close(); if (previousFocus?.isConnected) previousFocus.focus() })
</script>
<style scoped src="./content.css"></style>
