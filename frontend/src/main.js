import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import AppIcon from './shared/design/AppIcon.vue'
import ArcoVue from '@arco-design/web-vue'
import ArcoIcon from '@arco-design/web-vue/es/icon'
import '@arco-design/web-vue/dist/arco.css'
import './assets/styles/main.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(ArcoVue)
app.use(ArcoIcon)
app.component('AppIcon', AppIcon)

app.mount('#app')
