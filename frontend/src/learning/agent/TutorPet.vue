<template>
  <PlatformPet :session="snapshot" :exam-page="examPage" @send="send" @full="openFull" @restart="restart" />
</template>
<script setup>
import { onBeforeUnmount, shallowRef } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import { usePetStore } from '@/store/pet'
import PlatformPet from '@/components/PlatformPet.vue'
import { agentSession } from './runtime.js'
import { openTutor } from './public.js'
import { connectPetSession } from './petBridge.js'

defineProps({ examPage: Boolean })
const router = useRouter()
const user = useUserStore()
const pet = usePetStore()
const snapshot = shallowRef(agentSession.state)
const disconnect = connectPetSession(agentSession, pet, value => { snapshot.value = value })
function send(message) { return agentSession.send({ message, agentIds: ['tutor'] }) }
function restart() { agentSession.reset() }
async function openFull() {
  await openTutor(router, { userId: user.userInfo?.id })
  if (router.currentRoute.value.path === '/multi-agent') pet.setOpened(false)
}
onBeforeUnmount(disconnect)
</script>
