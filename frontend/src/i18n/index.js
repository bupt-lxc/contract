import { createI18n } from 'vue-i18n'
import enUS from './locales/en-US.js'
import zhCN from './locales/zh-CN.js'

const saved = localStorage.getItem('app-locale')
const locale = saved || 'en-US'

const i18n = createI18n({
  legacy: false,
  locale,
  fallbackLocale: 'en-US',
  messages: {
    'en-US': enUS,
    'zh-CN': zhCN
  }
})

export default i18n
