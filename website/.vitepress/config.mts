import { defineConfig } from 'vitepress'

// 整个站唯一的配置文件:站名、顶部导航、左侧边栏、搜索都在这里
export default defineConfig({
  lang: 'zh-CN',
  title: 'AemeathCode',
  description: '从零手搓的终端 Coding Agent',

  // 部署在 GitHub Pages 的项目页 nijikasuki.github.io/AemeathCode/,所有资源都在这个子路径下
  base: '/AemeathCode/',

  head: [['link', { rel: 'icon', type: 'image/svg+xml', href: '/AemeathCode/favicon.svg' }]],

  themeConfig: {
    logo: '/logo.svg',
    nav: [
      { text: '指南', link: '/guide/install' },
      { text: '从零手搓', link: '/walkthrough/stage-0' },
      { text: 'GitHub', link: 'https://github.com/Nijikasuki/AemeathCode' },
    ],

    // 左侧边栏:按 tag 一章一篇
    sidebar: {
      '/walkthrough/': [
        {
          text: '从零手搓',
          items: [
            { text: '协议骨架', link: '/walkthrough/stage-0' },
            { text: 'Agent 最小闭环', link: '/walkthrough/stage-1' },
            { text: '双进程 + 多路复用', link: '/walkthrough/stage-2' },
            { text: '八工具 + 任务 + trace', link: '/walkthrough/stage-3' },
            { text: '会话记忆', link: '/walkthrough/stage-4' },
            { text: '权限审批', link: '/walkthrough/stage-5' },
            { text: '上下文压缩', link: '/walkthrough/stage-6' },
            { text: 'Subagent / Skills / MCP', link: '/walkthrough/stage-7' },
          ],
        },
      ],
      '/guide/': [
        { text: '指南', items: [{ text: '安装与快速开始', link: '/guide/install' }] },
      ],
    },

    search: {
      provider: 'local',
      options: {
        translations: {
          button: { buttonText: '搜索', buttonAriaLabel: '搜索' },
          modal: {
            noResultsText: '没有找到',
            resetButtonTitle: '清除',
            footer: { selectText: '选择', navigateText: '切换', closeText: '关闭' },
          },
        },
      },
    },
    darkModeSwitchLabel: '外观',
    returnToTopLabel: '回到顶部',
    sidebarMenuLabel: '目录',
    outline: { label: '本页目录', level: [2, 3] },
    docFooter: { prev: '上一篇', next: '下一篇' },
    socialLinks: [{ icon: 'github', link: 'https://github.com/Nijikasuki/AemeathCode' }],
  },
})
