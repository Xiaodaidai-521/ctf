<template>
  <div id="app">
    <Navbar v-if="!isAdminRoute" />
    <div class="app-container" :class="{ 'no-navbar': isAdminRoute }">
      <RouterView v-slot="{ Component, route: viewRoute }">
        <KeepAlive :key="userStore.userInfo?.id" include="MultiAgentView" :max="3">
          <component
            :is="Component"
            :key="['MultiAgent', 'MultiAgentChallenge'].includes(viewRoute.name) ? viewRoute.path : undefined"
          />
        </KeepAlive>
      </RouterView>
    </div>
    <AnnouncementButton />
    <PlatformPet v-if="userStore.isAuthenticated" />
  </div>
</template>

<script setup>
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { RouterView } from 'vue-router'
import Navbar from './components/Navbar.vue'
import AnnouncementButton from './components/AnnouncementButton.vue'
import PlatformPet from './components/PlatformPet.vue'
import { useUserStore } from './store/user'
import { usePetStore } from './store/pet'

const route = useRoute()
const userStore = useUserStore()
const petStore = usePetStore()

watch(() => userStore.userInfo?.id, () => petStore.reset(), { flush: 'sync' })

const isAdminRoute = computed(() => {
  return route.path.startsWith('/admin')
})
</script>

<style>
#app {
  min-height: 100vh;
  background:
    linear-gradient(90deg, rgba(24, 23, 19, 0.045) 1px, transparent 1px) 0 0 / 44px 44px,
    linear-gradient(180deg, #faf7f0 0%, var(--bg-paper) 44%, #f8f4ed 100%);
}

.app-container {
  padding-top: 64px;
  min-height: 100vh;
}

.app-container.no-navbar {
  padding-top: 0;
}
</style>
