#!/usr/bin/env bash
# 市场调研报告助手 —— 零依赖 CLI 启动器
# 用法： ./run.sh "调研胶囊咖啡在中国市场的竞争格局" --market 中国大陆 --depth 3
set -euo pipefail

export PYTHONUTF8=1
: "${MRA_BASE_URL:=https://api.deepseek.com/v1}"
: "${MRA_MODEL:=deepseek-chat}"
# export MRA_API_KEY="sk-..."
# export TAVILY_API_KEY="tvly-..."

cd "$(dirname "$0")"
exec python3 -m mra "$@"
