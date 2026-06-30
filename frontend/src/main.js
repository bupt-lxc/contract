import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'
import i18n from './i18n'
import './assets/main.css'
import { callApi } from '@/api/bridge.js'

const app = createApp(App)
app.use(ElementPlus, { size: 'default' })
app.use(router)
app.use(i18n)

window.__protocolNavigate = async function(params) {
  window.__pendingConfirmAction = params.action === 'confirm'
    ? { type: params.type, id: params.id }
    : null

  if (params.type === 'sc') {
    router.push(`/sc/${params.id}`)
  } else if (params.type === 'po') {
    const po = await callApi('get_po', { po_id: params.id })
    router.push(`/sc/${po.sc_id}/po/${params.id}`)
  } else if (params.type === 'gr') {
    const gr = await callApi('get_gr', { gr_id: params.id })
    const po = await callApi('get_po', { po_id: gr.po_id })
    router.push(`/sc/${po.sc_id}/po/${gr.po_id}/gr/${params.id}`)
  }
}

app.mount('#app')
