.PHONY: help install test run stop build clean diagrams

help:  ## 显示可用命令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install:  ## 安装依赖(uv sync)
	uv sync

test:  ## 跑测试
	uv run pytest -q

run:  ## 启动(自动拉起 daemon + 进 TUI)
	uv run aemeath

stop:  ## 关闭后台 daemon
	uv run aemeath stop

diagrams:  ## 把 assets/diagrams/*.mmd 重新渲染成 SVG(README 里引用的是 SVG)
	uv run python assets/diagrams/render.py

build:  ## 构建 wheel + sdist
	uv build

clean:  ## 清理构建产物与缓存
	rm -rf dist build *.egg-info .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
