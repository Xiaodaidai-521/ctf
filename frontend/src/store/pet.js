import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { loadPetPreferences, normalizePetPack, savePetPreferences, validPosition } from '../utils/pet.js'

const priority = { working: 4, 'needs-input': 3, failed: 2, ready: 1 }

export const usePetStore = defineStore('pet', () => {
  const preferences = ref(loadPetPreferences())
  const activities = ref({})
  // The fixed launcher starts collapsed; expansion is never persisted.
  const opened = ref(false)
  let sequence = 0

  const current = computed(() => Object.values(activities.value).sort((a, b) =>
    priority[b.state] - priority[a.state] || b.token - a.token
  )[0] || null)
  const state = computed(() => current.value?.state || 'idle')

  function startActivity(source, { target = '/multi-agent', label = '智能体' } = {}, state) {
    const token = ++sequence
    activities.value[source] = { source, token, target, label, state }
    return token
  }

  function begin(source, details) {
    return startActivity(source, details, 'working')
  }

  function requestInput(source, details) {
    return startActivity(source, details, 'needs-input')
  }

  function settle(source, token, state) {
    const activity = activities.value[source]
    // A late response may belong to a cleared conversation or a previous login.
    if (!activity || activity.token !== token || activity.state !== 'working') return false
    activity.state = state
    return true
  }

  function complete(source, token, { needsInput = false } = {}) {
    return settle(source, token, needsInput ? 'needs-input' : 'ready')
  }

  function fail(source, token) {
    return settle(source, token, 'failed')
  }

  function acknowledge(source, token = activities.value[source]?.token) {
    const activity = activities.value[source]
    if (activity && activity.token === token && activity.state === 'ready') delete activities.value[source]
  }

  function clear(source, token = activities.value[source]?.token) {
    if (activities.value[source]?.token === token) delete activities.value[source]
  }

  function reset() {
    activities.value = {}
    opened.value = false
  }

  function setOpened(value) {
    opened.value = !!value && !preferences.value.hidden
  }

  function setHidden(hidden) {
    preferences.value.hidden = !!hidden
    if (preferences.value.hidden) opened.value = false
    savePetPreferences(preferences.value)
  }

  function reveal() {
    setHidden(false)
    setOpened(true)
  }

  function setPosition(position) {
    if (!validPosition(position)) return
    preferences.value.position = { x: position.x, y: position.y }
    savePetPreferences(preferences.value)
  }

  function setPack(pack) {
    const directory = normalizePetPack(pack)
    if (!directory) return false
    preferences.value.pack = directory
    savePetPreferences(preferences.value)
    return true
  }

  return {
    preferences, activities, current, state, opened,
    begin, requestInput, complete, fail, acknowledge, clear, reset,
    setOpened, reveal, setHidden, setPosition, setPack
  }
})
