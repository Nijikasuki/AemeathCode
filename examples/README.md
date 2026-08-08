# examples —— 可参考的示例

AemeathCode 运行时会在你的项目目录下生成一个 `.aemeath/` 文件夹存放数据(会话、日志、
权限等,已被 `.gitignore` 忽略)。其中有几类东西是**给你手写、用来定制 agent 的**——
本目录就放这类内容的**示例**,格式和 `.aemeath/` 下的一致,拿来照着改即可。

| 示例文件 | 对应放到 | 是什么 |
|---|---|---|
| `skills/code-review.md` | `.aemeath/skills/` | 自定义 skill(按需加载的操作手册) |
| `AEMEATH.md` | `.aemeath/AEMEATH.md` | 项目记忆(常驻的项目背景,你写) |
| `mcp.json` | `.aemeath/mcp.json` | 外部 MCP server 配置 |

---

## 1. 自定义 Skill —— `skills/code-review.md`

**skill = 一段可复用的操作手册(SOP)**:平时只有它的**简介**常驻(让模型知道「有这么个
技能」),真正的**正文**只在模型调用 `use_skill` 时才加载 —— 所以你可以放很多 skill 也不
撑爆上下文。

格式:文件名 = skill 名;顶部 `---` 里一行 `description:`(给模型看的目录);下面正文 = 流程。

```bash
mkdir -p .aemeath/skills
cp examples/skills/code-review.md .aemeath/skills/    # 同名会覆盖内置 skill
```

## 2. 项目记忆 —— `AEMEATH.md`

人写的项目背景,类似 Claude Code 的 `CLAUDE.md`,会**常驻**拼进 system prompt,让 agent
一上来就懂你的项目约定。

```bash
cp examples/AEMEATH.md .aemeath/AEMEATH.md            # 再按你的项目改写
```

## 3. 外部工具 MCP —— `mcp.json`

AemeathCode 能作为 **MCP 客户端**连接外部工具 server(GitHub、文件系统等),把它们的工具
当自己的用。两种配置方式:

- **命令行**(推荐):`aemeath mcp add github npx -y @modelcontextprotocol/server-github`
- **手写** `.aemeath/mcp.json`(格式见 `examples/mcp.json`):一条记录 = `{"name": ..., "command": [...]}`

```bash
cp examples/mcp.json .aemeath/mcp.json               # 按需增删,改完重启 aemeath core 生效
```

> GitHub 那个 server 需要在 `.env` 里配 `GITHUB_PERSONAL_ACCESS_TOKEN`(子进程会继承)。
> 连真实 MCP server 需要本机装了 `node` / `npx`。

---

> 几者区别:**skill** 是按需加载的操作流程;**项目记忆** 是常驻的项目背景(你写);
> **mcp.json** 是接外部工具;而 agent 还能用 `note_save` 自己往 `.aemeath/note.md` 写全局笔记(agent 写)。
