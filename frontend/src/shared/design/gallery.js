import { createApp } from 'vue'
import Arco from '@arco-design/web-vue'
import ArcoIcon from '@arco-design/web-vue/es/icon'
import '@arco-design/web-vue/dist/arco.css'
import '../../assets/styles/main.css'
import StateGallery from './StateGallery.vue'
createApp(StateGallery).use(Arco).use(ArcoIcon).mount('#app')
