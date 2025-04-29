# -*- coding: utf-8 -*-
"""
日志设置工具函数。
"""
import os # 添加 os 用于路径检查
import logging
import logging.handlers
import sys
from pathlib import Path
from datetime import datetime # 添加 datetime 用于生成时间戳文件名

# 从 .config_utils 导入常量和函数 (相对于 channel_manager_lib 包)
# 注意：load_script_config 会读取 script_config.yaml
from .config_utils import LOGS_DIR, DEFAULT_LOG_FILE_BASENAME, load_script_config

# 默认日志格式
DEFAULT_LOG_FORMAT = '%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
DEFAULT_DATE_FORMAT = '%Y-%m-%d %H:%M:%S,%f'[:-3] # 保留毫秒

# --- 全局日志配置状态 ---
_logging_configured = False

def setup_logging(log_level_arg=None, log_file_path_arg=None):
    """
    配置项目的基础日志记录。
    可以安全地多次调用，但只有第一次调用会生效 Handler 的配置，后续调用可调整级别。

    Args:
        log_level_arg (str | None): 命令行参数指定的日志级别字符串 (优先级最高)。
        log_file_path_arg (str | Path | None | ""):
            - 命令行参数指定的文件路径或目录。
            - 如果是有效路径，则将日志写入该文件（带轮转）。
            - 如果是目录，则写入该目录下带时间戳的默认文件名。
            - 如果是 None，则使用默认日志目录和文件名。
            - 如果是空字符串 '' 或 "none" (不区分大小写)，则禁用文件日志。
    """
    global _logging_configured

    # --- 1. 确定最终的日志级别 ---
    final_log_level_str = "INFO" # 默认值
    # 优先级: 命令行 > 配置文件 > 默认
    if log_level_arg:
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if log_level_arg.upper() in valid_levels:
            final_log_level_str = log_level_arg.upper()
            # 初始设置时用 print，因为 logging 可能尚未完全配置
            if not _logging_configured: print(f"[Log Setup] 使用命令行指定的日志级别: {final_log_level_str}")
        else:
            if not _logging_configured: print(f"[Log Setup] 警告：命令行指定的日志级别 '{log_level_arg}' 无效，将尝试配置文件或默认值。")
            # 如果命令行无效，继续尝试配置文件
            script_config = load_script_config() # load_script_config 内部有缓存或默认值逻辑
            config_log_level = script_config.get('logging', {}).get('level', 'INFO')
            final_log_level_str = config_log_level
            if not _logging_configured: print(f"[Log Setup] 使用配置文件或默认日志级别: {final_log_level_str}")
    else:
        # 没有命令行参数，尝试从配置文件加载
        script_config = load_script_config()
        config_log_level = script_config.get('logging', {}).get('level', 'INFO')
        final_log_level_str = config_log_level
        if not _logging_configured: print(f"[Log Setup] 使用配置文件或默认日志级别: {final_log_level_str}")

    log_level = getattr(logging, final_log_level_str, logging.INFO)

    # --- 2. 配置根 logger 和 Handlers (仅在首次配置时) ---
    root_logger = logging.getLogger()
    if not _logging_configured:
        root_logger.setLevel(log_level) # 首次设置基础级别

        # 移除可能存在的默认处理器
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # 创建格式化器
        formatter = logging.Formatter(DEFAULT_LOG_FORMAT, datefmt=DEFAULT_DATE_FORMAT)

        # 配置控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level) # 控制台处理器也使用最终级别
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        print(f"[Log Setup] 控制台日志处理器已添加，级别: {final_log_level_str}") # Use print for initial setup phase

        # --- 3. 确定并配置日志文件路径 ---
        disable_file_logging = False
        final_log_file_path = None

        if isinstance(log_file_path_arg, str) and log_file_path_arg.lower() in ('', 'none'):
            disable_file_logging = True
            print("[Log Setup] 根据命令行参数禁用文件日志记录。")
        elif log_file_path_arg:
            # 用户通过命令行指定了路径或目录
            log_path_arg = Path(log_file_path_arg)
            try:
                 if log_path_arg.is_dir():
                     # 提供的是目录，生成带时间戳的文件名
                     timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                     final_log_file_path = log_path_arg / f"channel_updater_{timestamp}.log"
                     print(f"[Log Setup] 日志将记录到指定目录下的文件: {final_log_file_path}")
                 else:
                     # 提供的是具体文件路径, 尝试创建父目录
                     log_path_arg.parent.mkdir(parents=True, exist_ok=True)
                     final_log_file_path = log_path_arg
                     print(f"[Log Setup] 日志将记录到指定的文件: {final_log_file_path}")
            except OSError as e:
                 print(f"[Log Setup] 处理命令行日志路径 '{log_file_path_arg}' 时出错: {e}。将禁用文件日志。")
                 disable_file_logging = True
        else:
            # 没有命令行指定，使用默认路径
            try:
                LOGS_DIR.mkdir(parents=True, exist_ok=True) # 确保默认目录存在
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                final_log_file_path = LOGS_DIR / f"channel_updater_{timestamp}.log"
                print(f"[Log Setup] 使用默认日志路径: {final_log_file_path}")
            except OSError as e:
                 print(f"[Log Setup] 创建默认日志目录 '{LOGS_DIR}' 时出错: {e}。将禁用文件日志。")
                 disable_file_logging = True


        # 配置轮转文件处理器 (如果不禁用且路径有效)
        if not disable_file_logging and final_log_file_path:
            try:
                # 确保日志文件的父目录存在 (上面可能已创建，再次确认)
                final_log_file_path.parent.mkdir(parents=True, exist_ok=True)

                # 使用 RotatingFileHandler
                file_handler = logging.handlers.RotatingFileHandler(
                    final_log_file_path, maxBytes=5*1024*1024, backupCount=20, encoding='utf-8'
                )
                file_handler.setLevel(log_level) # 文件处理器也用最终级别
                file_handler.setFormatter(formatter)
                root_logger.addHandler(file_handler)
                # Use logging now that handlers are potentially set up
                logging.info(f"文件日志处理器已添加，目标文件: {final_log_file_path}")
            except Exception as e:
                # Use logging here as console handler should exist
                logging.error(f"无法配置轮转日志文件处理器 ({final_log_file_path}): {e}", exc_info=True)
                print(f"[ERROR] 无法设置日志文件 '{final_log_file_path}'。请检查权限或路径。", file=sys.stderr)
        elif disable_file_logging:
             logging.info("文件日志记录已禁用。")
        else:
             logging.warning("未能确定有效的日志文件路径，文件日志未启用。")

        _logging_configured = True
        logging.info(f"日志记录系统初始化完成，级别: {final_log_level_str}")

    else:
        # 如果已经配置过，仅调整级别
        print(f"[Log Setup] 调整现有日志记录器级别为: {final_log_level_str}")
        root_logger.setLevel(log_level)
        for handler in root_logger.handlers:
             # 可能需要检查 handler 类型，如果只想调整特定类型的 handler
             try:
                 handler.setLevel(log_level)
             except Exception as e:
                 logging.warning(f"调整处理器 {handler} 级别时出错: {e}")


# 现在 main_tool.py 中应该这样调用:
# setup_logging(log_level_arg=args.log_level, log_file_path_arg=args.log_file)