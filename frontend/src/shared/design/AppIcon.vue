<template>
  <component :is="component" v-if="component" class="app-icon" aria-hidden="true" focusable="false" />
</template>

<script setup>
import { computed } from 'vue'
import {
  IconArchive, IconArrowDown, IconArrowLeft, IconArrowUp, IconBarChart,
  IconBook, IconBookmark, IconBulb, IconCheck, IconCheckCircle, IconCheckSquare,
  IconClockCircle, IconClose, IconCodeBlock, IconCompass, IconDashboard,
  IconDelete, IconDesktop, IconDown, IconEdit, IconExclamationCircle, IconExperiment, IconEye,
  IconFile, IconFire, IconFolder, IconHeart, IconInfoCircle, IconLayers,
  IconLeft, IconLink, IconList, IconLock, IconMessage, IconMindMapping,
  IconMobile, IconMoon, IconPlayArrow, IconPlus, IconPublic, IconPushpin,
  IconRefresh, IconRight, IconRobot, IconSafe, IconSave, IconSearch,
  IconSettings, IconStorage, IconSync, IconThunderbolt, IconTrophy,
  IconUndo, IconUp, IconUser, IconUserGroup, IconHeartFill, IconStar, IconStarFill,
  IconNotification, IconImage, IconDownload, IconVideoCamera, IconLocation,
  IconThumbUp, IconCloud,
} from '@arco-design/web-vue/es/icon'
import { iconCatalog, iconName } from './iconCatalog'

const props = defineProps({ name: { type: [String, Array], required: true } })
const components = {
  IconArchive, IconArrowDown, IconArrowLeft, IconArrowUp, IconBarChart,
  IconBook, IconBookmark, IconBulb, IconCheck, IconCheckCircle, IconCheckSquare,
  IconClockCircle, IconClose, IconCodeBlock, IconCompass, IconDashboard,
  IconDelete, IconDesktop, IconDown, IconEdit, IconExclamationCircle, IconExperiment, IconEye,
  IconFile, IconFire, IconFolder, IconHeart, IconInfoCircle, IconLayers,
  IconLeft, IconLink, IconList, IconLock, IconMessage, IconMindMapping,
  IconMobile, IconMoon, IconPlayArrow, IconPlus, IconPublic, IconPushpin,
  IconRefresh, IconRight, IconRobot, IconSafe, IconSave, IconSearch,
  IconSettings, IconStorage, IconSync, IconThunderbolt, IconTrophy,
  IconUndo, IconUp, IconUser, IconUserGroup, IconHeartFill, IconStar, IconStarFill,
  IconNotification, IconImage, IconDownload, IconVideoCamera, IconLocation,
  IconThumbUp, IconCloud,
}
const component = computed(() => components[iconCatalog[iconName(props.name)]])
</script>

<style scoped>
.app-icon { display: inline-block; width: 1em; height: 1em; flex-shrink: 0; vertical-align: -.125em; }
</style>
