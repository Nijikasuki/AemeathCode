<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { withBase } from 'vitepress'

const INSTALL = 'uv tool install aemeathcode && aemeath'
const copied = ref(false)
async function copy() {
  await navigator.clipboard.writeText(INSTALL)
  copied.value = true
  setTimeout(() => (copied.value = false), 1600)
}

// ---------- 一轮 run 的回放脚本 ----------
// 每一步揭开 Content 里的一行;Thinking / Tasks / Changes 跟着步数变。
// 符号与 TUI 一致(src/aemeathcode/tui/ledger.py):› 用户 · ◇ 只读工具 · ◆ 改变世界的工具 · ✧ 完成
type Line = { g: string; gc?: string; text: string; kind: string; meta?: string }
const LINES: Line[] = [
  { g: '›', gc: 'pink', text: '先列个计划,再读 agent/loop.py', kind: 'user' },
  { g: '', text: '好的,先看看这片代码的结构,再制定计划。', kind: 'say' },
  { g: '◇', gc: 'cyan', text: '探索 2 个文件', kind: 'tool', meta: '3.5s ⌄' },
  { g: '', text: '主循环依赖 Context、LLMProvider、ToolRegistry 三块,拆成三个任务。', kind: 'say' },
  { g: '◆', gc: 'iris', text: 'task_create 读 loop.py 主循环', kind: 'tool' },
  { g: '◆', gc: 'iris', text: 'task_create 审查 stop_reason', kind: 'tool' },
  { g: '◆', gc: 'iris', text: 'task_create 写进 plan.md', kind: 'tool' },
  { g: '◆', gc: 'pink', text: '需要授权 · write_file plan.md', kind: 'ask' },
  { g: '✧', gc: 'cyan', text: '计划已就位,三处可以改,详见 plan.md。', kind: 'done' },
]
const THINKING = [            // 下标 = 已揭开的行数
  '',
  '用户要先列计划再读主循环。',
  '用户要先列计划再读主循环。',
  '我并行读取:\n- agent/loop.py\n- core/context.py',
  '依赖关系清楚了,拆成三个任务。',
  '依赖关系清楚了,拆成三个任务。',
  '先标记任务 1 进行中。',
  '任务 1 完成,任务 2 进行中。',
  '要写文件,先请求授权。',
  '写完了,收尾汇报。',
]
const TASKS = ['读 loop.py 主循环', '审查 stop_reason', '写进 plan.md']

const step = ref(LINES.length)   // SSR / 关动画时直接显示完整画面
const elapsed = ref(13)
let timer: number | undefined
let clock: number | undefined

onMounted(() => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  animate = true
  const restart = () => { step.value = 0; elapsed.value = 0 }
  const tick = () => {
    if (step.value < LINES.length) {
      step.value++
      const waitLonger = LINES[step.value - 1].kind === 'ask'
      timer = window.setTimeout(tick, waitLonger ? 2200 : 900)
    } else {
      timer = window.setTimeout(() => { restart(); tick() }, 4500)
    }
  }
  restart()
  timer = window.setTimeout(tick, 600)
  clock = window.setInterval(() => { if (step.value < LINES.length) elapsed.value++ }, 1000)
})
onBeforeUnmount(() => { clearTimeout(timer); clearInterval(clock); clearInterval(typer) })

const finished = computed(() => step.value >= LINES.length)
const running = computed(() => step.value > 0 && !finished.value)
const thinking = computed(() => THINKING[step.value])

// Thinking 面板逐字往外冒 —— 对应 TUI 里 thinking 是流式推过来的
const typed = ref(THINKING[THINKING.length - 1])
let typer: number | undefined
let animate = false
watch(thinking, (text, prev) => {
  if (text === prev) return
  clearInterval(typer)
  if (!animate || !text) { typed.value = text; return }
  typed.value = ''
  let i = 0
  typer = window.setInterval(() => {
    typed.value = text.slice(0, ++i)
    if (i >= text.length) clearInterval(typer)
  }, 45)
})
const tasks = computed(() => {
  const made = Math.max(0, Math.min(3, step.value - 4))
  const doneCount = finished.value ? 3 : Math.max(0, step.value - 6)
  return TASKS.slice(0, made).map((n, i) => {
    const done = i < doneCount
    const doing = !done && i === doneCount && step.value >= 6
    return { n, done, sym: done ? '✧' : doing ? '◐' : '○' }
  })
})

// AEMEATH 方块字:和 TUI 同一份(src/aemeathcode/tui/splash.py 的 WORDMARK_SMALL)
const WM = ['▄▀█ █▀▀ █▀▄▀█ █▀▀ ▄▀█ ▀█▀ █ █', '█▀█ ██▄ █ ▀ █ ██▄ █▀█  █  █▀█']
const COLORS = ['#FF9ED8', '#F7A8E0', '#E3B8EA', '#BFD3EE', '#9FDFEA', '#9DB4F6', '#9B8CFF']
const wmRows = WM.map(r => {
  let li = -1
  return [...r].map((ch, x) => {
    const blank = WM.every(row => row[x] === ' ')
    if (!blank && (x === 0 || WM.every(row => row[x - 1] === ' '))) li++
    return { ch, color: blank ? undefined : COLORS[li] }
  })
})
</script>

<template>
  <section class="ah">
    <div class="ah-grid" aria-hidden="true" />

    <div class="ah-main">
      <!-- 右:分栏 TUI(DOM 在前,靠 .ah-text 的 order:-1 排到右边)。三栏三色、标题嵌边框,比例按半宽重配(真 TUI 是 34 / 1fr / 32) -->
      <div class="ah-term">
        <div class="tui" role="img" aria-label="AemeathCode 分栏终端界面示意">
          <div class="bar">
            <i class="d r" /><i class="d y" /><i class="d g" />
            <span>aemeath — ~/code_rep/AemeathCode</span>
          </div>
          <div class="cols">
            <!-- 左栏:鸢尾紫 -->
            <div class="col">
              <section class="p c-iris">
                <span class="pt">Status</span>
                <div>deepseek-v4-flash</div>
                <div :class="running ? 'pink' : 'muted'">{{ running ? `running ${elapsed}s` : '就绪' }}</div>
              </section>
              <section class="p c-iris">
                <span class="pt">Sessions</span>
                <div class="sel">先列个计划,再读 loop.py</div>
                <div class="sess">给 bash 工具加超时</div>
                <div class="sess">resume 后上下文对不上</div>
                <div class="sess">接一个 GitHub MCP</div>
                <span class="pc">4 of 18</span>
              </section>
              <section class="p c-iris grow">
                <span class="pt">Thinking</span>
                <div v-if="thinking" class="think">{{ typed }}<span v-if="typed.length < thinking.length" class="cursor sm" /></div>
                <div v-else class="muted">(没有 thinking)</div>
              </section>
            </div>

            <!-- 中栏:青 -->
            <div class="col">
              <section class="p c-cyan grow">
                <span class="pt">Content</span>
                <pre class="wm"><template v-for="(row, i) in wmRows" :key="i"><span
                  v-for="(c, j) in row" :key="j" :style="c.color ? { color: c.color } : undefined">{{ c.ch }}</span>
</template></pre>
                <div class="ledger">
                  <template v-for="(l, i) in LINES" :key="i">
                    <div v-if="i < step" class="row" :class="l.kind">
                      <span class="g" :class="l.gc">{{ l.g }}</span>
                      <span class="rule" />
                      <span class="txt">
                        <template v-if="l.kind === 'ask'">
                          <span class="pink">{{ l.text }}</span>
                          <span class="diff">+ ## 主循环改进计划</span>
                          <span class="diff">+ 1. max_tokens 撞 tool_call…</span>
                          <span class="keys"><kbd>y</kbd> 这次 <kbd>a</kbd> 永远 <kbd>n</kbd> 拒绝</span>
                        </template>
                        <template v-else>{{ l.text }}</template>
                        <em v-if="l.meta">{{ l.meta }}</em>
                        <span v-if="i === step - 1 && running" class="cursor" />
                      </span>
                    </div>
                  </template>
                </div>
                <span class="pc">v0.2.3</span>
              </section>
              <section class="p c-cyan input">
                <span class="pt">›</span>
                <span class="muted">输入目标回车执行 · / 命令</span>
              </section>
            </div>

            <!-- 右栏:粉 -->
            <div class="col">
              <section class="p c-pink grow">
                <span class="pt">Tasks</span>
                <div v-if="!tasks.length" class="muted">(还没有任务)</div>
                <div v-for="t in tasks" :key="t.n" class="task" :class="{ done: t.done }">
                  <span class="sym">{{ t.sym }}</span>{{ t.n }}
                </div>
                <span class="pc">{{ tasks.filter(t => t.done).length }} of {{ tasks.length }}</span>
              </section>
              <section class="p c-pink">
                <span class="pt">Changes</span>
                <div v-if="finished"><span class="add">+</span> plan.md</div>
                <div v-else class="muted">(本轮没改文件)</div>
              </section>
              <section class="p c-pink">
                <span class="pt">MCP</span>
                <div class="kv"><span><span class="cyan">✧</span> github</span><span>26</span></div>
                <div class="kv"><span><span class="cyan">✧</span> everything</span><span>13</span></div>
                <span class="pc">2 of 2</span>
              </section>
            </div>
          </div>
          <div class="hints">
            <span>^↑/^↓ 选会话 · ^y 复制回答 · ^q 退出</span>
            <span class="pbar"><i :style="{ width: Math.max(2, step * 4) + '%' }" /></span>
          </div>
        </div>
        <p class="cap">↑ 一轮 run 的回放:读代码 → 拆任务 → 写文件前先问你</p>
      </div>

      <!-- 左:文字介绍 -->
      <div class="ah-text">
        <div class="ah-badges">
          <a class="ah-badge" href="https://pypi.org/project/aemeathcode/">PyPI · 0.2.3</a>
          <span class="ah-badge">MIT</span>
          <span class="ah-badge">纯 Python + asyncio</span>
        </div>

        <div class="ah-title">
          <div class="mascot">
            <img :src="withBase('/mascot.gif')" alt="AemeathCode 吉祥物" />
            <span class="bubble">求个 Star ✦</span>
          </div>
          <h1><span class="grad">Aemeath</span><br />Code</h1>
        </div>

        <p class="ah-lead">
          从零手搓的终端 Coding Agent,<br />
          也是一趟<b>看得见的系统工程</b>。
        </p>
        <p class="ah-sub">
          后台 daemon + 分栏 TUI,中间一条自己实现的多路复用连接。ReAct 循环、权限审批、
          上下文压缩、子 agent、MCP 客户端 —— 没有用任何 agent 框架。
        </p>

        <div class="ah-actions">
          <a class="btn brand" :href="withBase('/guide/install')">快速开始 →</a>
          <a class="btn" :href="withBase('/walkthrough/stage-0')">从零手搓</a>
        </div>

        <div class="ah-install">
          <span class="prompt">❯</span>
          <code>{{ INSTALL }}</code>
          <button :class="{ ok: copied }" @click="copy">{{ copied ? '已复制 ✓' : '复制' }}</button>
        </div>
        <p class="ah-meta">Linux · macOS · WSL2 · Python 3.12+(uv 会自己装)</p>

      </div>
    </div>

  </section>
</template>

<style scoped>
.ah { position: relative; overflow: hidden; padding: 64px 24px 56px; }
.ah-grid {
  position: absolute; inset: 0; pointer-events: none;
  background-image:
    linear-gradient(var(--ah-grid) 1px, transparent 1px),
    linear-gradient(90deg, var(--ah-grid) 1px, transparent 1px);
  background-size: 32px 32px;
  mask-image: radial-gradient(ellipse 80% 70% at 50% 45%, #000 40%, transparent 100%);
}
.ah-main {
  position: relative; max-width: 1280px; margin: 0 auto;
  display: grid; grid-template-columns: 1fr 1.5fr; gap: 48px; align-items: stretch;
}
@media (max-width: 1000px) { .ah-main { grid-template-columns: 1fr; } .ah-text { order: -1; padding-bottom: 0; gap: 24px; } }

/* ---------- 左:文字 ----------
   和左边终端等高:顶对齐终端标题栏,底对齐终端下沿(减掉终端下方那行说明的高度),
   中间的空隙由 space-between 均分 —— 不再整体居中留出上下两块空白。 */
.ah-text { order: -1; display: flex; flex-direction: column; justify-content: space-between; padding-bottom: 32px; }
.ah-badges { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 26px; }
.ah-badge {
  font-size: 12px; padding: 3px 10px; border-radius: 6px; text-decoration: none; white-space: nowrap;
  border: 1px solid var(--vp-c-divider); background: var(--vp-c-bg);
  color: var(--vp-c-text-2); font-family: var(--vp-font-family-mono);
}
a.ah-badge { color: var(--ah-pink-strong); }

.ah-title { display: flex; align-items: center; gap: 18px; margin-bottom: 26px; }
.mascot { position: relative; flex: none; }
.mascot img { width: 136px; height: 136px; image-rendering: pixelated; display: block; }
.bubble {
  position: absolute; left: 30px; top: -30px; white-space: nowrap;
  font-size: 12px; font-weight: 700; padding: 3px 9px;
  background: var(--vp-c-bg); color: var(--vp-c-text-1);
  border: 2px solid var(--vp-c-text-1); box-shadow: 3px 3px 0 var(--ah-pink-strong);
}
.ah-title h1 {
  font-family: var(--vp-font-family-mono); font-weight: 800;
  font-size: clamp(44px, 5.4vw, 70px); line-height: .98; letter-spacing: -0.04em; color: var(--vp-c-text-1);
}
.grad {
  background: linear-gradient(110deg, var(--ah-pink-strong), var(--ah-iris));
  -webkit-background-clip: text; background-clip: text; color: transparent;
}
.ah-lead { font-size: 19px; line-height: 1.65; color: var(--vp-c-text-1); margin-bottom: 14px; }
.ah-lead b { color: var(--ah-pink-strong); }
.ah-sub { font-size: 14px; line-height: 1.85; color: var(--vp-c-text-2); margin-bottom: 24px; }

.ah-actions { display: flex; flex-wrap: wrap; gap: 12px; }
.btn {
  font-size: 14px; font-weight: 600; padding: 10px 20px; border-radius: 8px; text-decoration: none;
  border: 1px solid var(--vp-c-divider); color: var(--vp-c-text-1); background: var(--vp-c-bg);
  transition: all .2s;
}
.btn:hover { border-color: var(--ah-pink-strong); color: var(--ah-pink-strong); }
.btn.brand { background: var(--ah-pink-strong); border-color: var(--ah-pink-strong); color: var(--ah-on-brand); }
.btn.brand:hover { filter: brightness(1.08); color: var(--ah-on-brand); }

.ah-install {
  display: flex; align-items: center; gap: 10px; margin-top: 22px;
  padding: 9px 9px 9px 16px; border-radius: 10px;
  border: 1px solid var(--vp-c-divider); background: var(--vp-c-bg);
}
.ah-install .prompt { color: var(--ah-pink-strong); font-family: var(--vp-font-family-mono); }
.ah-install code { flex: 1; background: none; padding: 0; font-size: 13px; color: var(--vp-c-text-1); }
.ah-install button {
  font-size: 12px; padding: 5px 12px; border-radius: 7px; color: var(--vp-c-text-2);
  background: var(--vp-c-bg-soft); transition: color .2s;
}
.ah-install button:hover, .ah-install button.ok { color: var(--ah-pink-strong); }
.ah-meta { margin-top: 10px; font-size: 12px; color: var(--vp-c-text-3); font-family: var(--vp-font-family-mono); }


/* ---------- 右:分栏 TUI ---------- */
.tui {
  --bg: #0E0D14; --surface: #15141D; --text: #E4E1EC; --soft: #CFCBE0; --muted: #6D82A4;
  --pink: #FF9ED8; --cyan: #7DE8E8; --iris: #9B8CFF;
  border-radius: 12px; overflow: hidden; background: var(--bg); color: var(--text);
  font-family: var(--vp-font-family-mono); font-size: 11.5px; line-height: 1.65;
  border: 1px solid rgba(155, 140, 255, .3);
  box-shadow: 0 34px 90px -28px rgba(155, 140, 255, .55);
}
.bar {
  display: flex; align-items: center; gap: 7px; padding: 9px 14px; font-size: 11.5px;
  background: var(--surface); color: var(--muted); border-bottom: 1px solid rgba(255,255,255,.06);
}
.bar span { margin-left: 10px; }
.d { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.d.r { background: #ff5f57; } .d.y { background: #febc2e; } .d.g { background: #28c840; }

/* 半宽里放三栏:侧栏收窄到 22ch,整体加高,避免「扁」 */
.cols { display: grid; grid-template-columns: 22ch 1fr 22ch; gap: 7px; height: 520px; padding: 14px 9px 4px; }
.col { display: flex; flex-direction: column; gap: 13px; min-width: 0; }
.p { position: relative; border: 1px solid; border-radius: 7px; padding: 9px 9px 7px; min-height: 0; }
.c-iris { border-color: var(--iris); }
.c-cyan { border-color: var(--cyan); }
.c-pink { border-color: var(--pink); }
.grow { flex: 1; }   /* 不能 overflow:hidden —— 会把坐在边框线上的标题一起裁掉 */
/* 标题嵌上边框、计数嵌下边框 —— 对应 Textual 的 border_title / border_subtitle */
.pt, .pc { position: absolute; padding: 0 5px; background: var(--bg); line-height: 1; }
.pt { top: -6px; left: 9px; font-weight: 700; }
.pc { bottom: -6px; right: 9px; }
.p > div { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }

.muted { color: var(--muted); }
.pink { color: var(--pink); }
.cyan { color: var(--cyan); }
.iris { color: var(--iris); }
.sel { margin: 0 -9px; padding: 0 9px 0 1.5ch; background: rgba(155, 140, 255, .18); }
.sess { padding-left: 1.5ch; color: var(--soft); }
.think { white-space: pre-wrap !important; color: var(--soft); }

.wm { margin: 4px 0 12px 3ch; padding: 0; background: none; font-size: 11.5px; line-height: 1.05; white-space: pre; }
.ledger { display: flex; flex-direction: column; }
.row { display: grid; grid-template-columns: 2ch 1px 1fr; column-gap: 1ch; animation: in .35s ease both; }
.g { text-align: right; }
.rule { background: rgba(109, 130, 164, .55); }
.txt { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row.user .txt { font-weight: 700; }
.row.say .txt, .row.done .txt { white-space: normal; }   /* 叙述折行,不截断 */
.row.say .txt { color: var(--soft); }
.txt em { font-style: normal; color: var(--cyan); margin-left: 2ch; }
.row.ask .txt {
  display: flex; flex-direction: column; white-space: normal; margin: 3px 0; padding: 4px 8px;
  border: 1px solid rgba(255, 158, 216, .55); border-radius: 5px;
}
.diff { color: #7FB093; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.keys { color: var(--muted); }
.keys kbd { font: inherit; font-size: 10.5px; padding: 0 4px; margin: 0 2px 0 7px; border: 1px solid var(--muted); border-radius: 3px; color: var(--text); }
.keys kbd:first-child { margin-left: 0; border-color: var(--pink); color: var(--pink); }
.cursor.sm { width: 5px; height: 10px; background: var(--iris); }
.cursor { display: inline-block; width: 7px; height: 12px; margin-left: 4px; vertical-align: -2px; background: var(--pink); animation: blink 1s steps(1) infinite; }
@keyframes blink { 50% { opacity: 0; } }
@keyframes in { from { opacity: 0; transform: translateY(4px); } }

.input { flex: none; padding: 7px 9px; }
.task .sym { color: var(--pink); margin-right: 1ch; }
.task.done { color: var(--muted); }
.add { color: #7FB093; }
.kv { display: flex; justify-content: space-between; padding-right: .5ch; }

.hints { padding: 4px 13px 8px; color: var(--muted); font-size: 11px; display: flex; align-items: center; gap: 2ch; }
.pbar { margin-left: auto; width: 56px; height: 5px; background: rgba(109, 130, 164, .25); border-radius: 3px; overflow: hidden; }
.pbar i { display: block; height: 100%; background: linear-gradient(90deg, var(--cyan), var(--iris)); transition: width .6s; }

.cap { margin-top: 14px; text-align: center; font-size: 12px; color: var(--vp-c-text-3); font-family: var(--vp-font-family-mono); }

/* 窄屏:学真 TUI 的思路,先丢左栏,再丢右栏 */
@media (max-width: 700px) { .cols { grid-template-columns: 1fr 22ch; } .cols > .col:first-child { display: none; } }
@media (max-width: 480px) { .cols { grid-template-columns: 1fr; } .cols > .col:last-child { display: none; } }
@media (prefers-reduced-motion: reduce) { .row, .cursor { animation: none; } }
</style>
