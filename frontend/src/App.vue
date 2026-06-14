<template>
  <div id="app">
    <Navbar v-if="!isAdminRoute" />
    <div class="app-container" :class="{ 'no-navbar': isAdminRoute }">
      <RouterView />
    </div>
    <AnnouncementButton />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { RouterView } from 'vue-router'
import Navbar from './components/Navbar.vue'
import AnnouncementButton from './components/AnnouncementButton.vue'

const route = useRoute()

const isAdminRoute = computed(() => {
  return route.path.startsWith('/admin')
})
</script>

<style>
#app {
  min-height: 100vh;
  background-color: #f5f5f5;
}

.app-container {
  padding-top: 64px;
}

.app-container.no-navbar {
  padding-top: 0;
}
</style>
