# -*- coding: utf-8 -*-
"""
主入口脚本 - One API 渠道批量更新工具。
"""

import sys
import asyncio
import logging # 用于记录入口处的错误和信息
from pathlib import Path
from datetime import datetime # 移到顶部以供日志文件名生成使用
# argparse 和 os 不再直接需要

# 从新模块导入必要的函数和常量
from channel_manager_lib.config_utils import LOGS_DIR, DEFAULT_LOG_FILE_BASENAME # load_yaml_config 不再需要在此处导入
from channel_manager_lib.log_utils import setup_logging
from channel_manager_lib.cli_handler import setup_arg_parser, main_cli_entry # 导入解析器设置和主入口

# --- 程序入口 ---
if __name__ == "__main__":
    # 1. 设置参数解析器
    parser = setup_arg_parser()
    args = parser.parse_args()

    # 2. 配置日志记录 (调用 log_utils 中的函数)
    # setup_logging 现在会处理日志文件路径的逻辑
    try:
        # 直接将命令行参数传递给 setup_logging
        setup_logging(log_level_arg=args.log_level, log_file_path_arg=args.log_file)
    except Exception as e:
        # 捕获 setup_logging 可能出现的意外错误
        print(f"[CRITICAL] 日志系统初始化失败: {e}", file=sys.stderr)
        sys.exit(99) # 特殊退出码表示日志失败

    # 3. 运行主异步逻辑
    exit_code = 1 # 默认为失败
    try:
        logging.info("=" * 20 + " 工具启动 " + "=" * 20)
        logging.info(f"命令行参数: {' '.join(sys.argv)}")
        # 运行 cli_handler 中的主入口函数
        try:
            exit_code = asyncio.run(main_cli_entry(args))
        except Exception as e:
            logging.critical(f"异步操作失败: {e}", exc_info=True)
            exit_code = 1  # 设置为错误退出码
        logging.info(f"工具执行完毕，退出码: {exit_code}")
        logging.info("=" * 20 + " 工具结束 " + "=" * 20)

    except KeyboardInterrupt:
        logging.warning("用户通过 Ctrl+C 中断操作。")
        print("\n操作已由用户中断。")
        exit_code = 130 # 标准退出码 for Ctrl+C
    except Exception as e:
        logging.critical(f"发生未处理的顶层异常: {e}", exc_info=True)
        print(f"\n发生严重错误，请检查日志文件获取详细信息。错误: {e}")
        exit_code = 1 # 通用错误码

    sys.exit(exit_code)