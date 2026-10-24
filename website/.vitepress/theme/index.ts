import DefaultTheme from 'vitepress/theme'
import { h } from 'vue'
import AemeathHero from './AemeathHero.vue'
import './custom.css'

// 沿用默认主题,只在首页 hero 的位置插入自己的组件
export default {
  extends: DefaultTheme,
  Layout: () => h(DefaultTheme.Layout, null, {
    'home-hero-before': () => h(AemeathHero),
  }),
}
