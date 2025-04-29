#!/bin/bash

# 获取脚本所在的目录
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)

# 切换到脚本所在目录 (确保相对路径正确)
cd "$SCRIPT_DIR" || exit 1

# 执行 Python 主脚本，传递所有命令行参数
python main_tool.py "$@"