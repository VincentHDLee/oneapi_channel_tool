import copy
# -*- coding: utf-8 -*-
"""
配置文件加载、路径常量和运行时数据目录管理工具。
"""
import os
import yaml
import json
import logging
from pathlib import Path

# --- 配置常量 ---
CONNECTION_CONFIG_DIR = Path("connection_configs")
UPDATE_CONFIG_PATH = Path("update_config.yaml") # 默认更新配置文件 (YAML)
QUERY_CONFIG_PATH = Path("query_config.yaml") # 自定义查询配置文件 (YAML) # 新增
CROSS_SITE_ACTION_CONFIG_PATH = Path("cross_site_action.yaml") # 跨站点操作配置文件

# --- 内部运行时数据目录 ---
RUNTIME_DATA_BASE_DIR = Path("oneapi_tool_utils") / "runtime_data"
UPDATE_CONFIG_BACKUP_DIR = RUNTIME_DATA_BASE_DIR / "used_update_configs" # 备份目录
LOGS_DIR = RUNTIME_DATA_BASE_DIR / "logs" # 日志文件存放目录
UNDO_DIR = RUNTIME_DATA_BASE_DIR / "undo_data" # 撤销数据存放目录
LOADED_CONNECTION_CONFIG_DIR = RUNTIME_DATA_BASE_DIR / "loaded_connection_configs" # 缓存的 JSON 连接配置

# 干净的配置文件模板 (YAML 示例)
CLEAN_UPDATE_CONFIG_TEMPLATE_PATH = Path("update_config.example") # 用于恢复的模板

# 默认日志文件名基础部分
DEFAULT_LOG_FILE_BASENAME = "channel_updater.log"

# --- 辅助函数 ---

def list_connection_configs() -> list[Path]:
    """
    列出 connection_configs 目录下的可用 YAML 配置文件，
    并清理无效的 JSON 缓存文件。
    返回有效的 YAML 配置文件路径列表 (List[Path])。
    """
    config_dir = CONNECTION_CONFIG_DIR # 使用此模块中的常量
    cache_dir = LOADED_CONNECTION_CONFIG_DIR # 使用此模块中的常量
    valid_yaml_configs = []
    expected_cache_files = set()

    if not config_dir.is_dir():
        logging.error(f"错误：连接配置目录 '{config_dir}' 不存在。")
        return []

    # 1. 查找有效的 YAML 配置文件并记录预期的缓存文件名
    for item in config_dir.glob("*.yaml"):
        if item.is_file():
            valid_yaml_configs.append(item)
            expected_cache_files.add(item.stem + ".json")

    # 2. 清理无效的 JSON 缓存
    if cache_dir.is_dir():
        for cache_item in cache_dir.glob("*.json"):
            if cache_item.is_file() and cache_item.name not in expected_cache_files:
                try:
                    cache_item.unlink()
                    logging.info(f"已清理无效的连接配置缓存文件: {cache_item}")
                except OSError as e:
                    logging.warning(f"清理缓存文件 {cache_item} 时出错: {e}")
    else:
        # 如果缓存目录不存在，尝试创建（虽然加载时也会创建，这里预先创建一下）
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
             logging.warning(f"创建连接配置缓存目录 {cache_dir} 时出错: {e}")

    return valid_yaml_configs

# TODO: 添加加载/验证配置文件的函数
# def load_connection_config(path: Path) -> dict | None: ...
# def load_update_config(path: Path) -> dict | None: ...
# def load_cross_site_config(path: Path) -> dict | None: ...
# def get_cached_connection_config(yaml_path: Path) -> dict | None: ...
# def cache_connection_config(yaml_path: Path, data: dict): ...
def load_yaml_config(path: str | Path) -> dict | None:
    """
    从指定路径加载 YAML 配置文件。

    Args:
        path (str | Path): YAML 文件的路径。

    Returns:
        dict | None: 加载后的配置字典，或在失败时返回 None。
                     (注意：与原始版本不同，这里不重新抛出异常，而是返回 None)
    """
    path = Path(path) # 确保是 Path 对象
    try:
        with open(path, 'r', encoding='utf-8') as f:
            # 使用 safe_load 防止执行任意代码
            config_data = yaml.safe_load(f)
            if not isinstance(config_data, dict):
                 logging.error(f"配置文件内容无效，期望为字典格式: {path}")
                 return None
            return config_data
    except FileNotFoundError:
        logging.error(f"配置文件未找到: {path}")
        raise # 重新抛出 FileNotFoundError
    except yaml.YAMLError as e:
        logging.error(f"YAML 配置文件格式错误: {path} - {e}")
        raise # 重新抛出 YAMLError
    except Exception as e:
        logging.error(f"加载 YAML 配置文件失败: {path} - {e}", exc_info=True)
        return None
# --- 脚本通用配置 ---
SCRIPT_CONFIG_PATH = Path("script_config.yaml")

DEFAULT_SCRIPT_CONFIG = {
    'api_settings': {
        'max_concurrent_requests': 5,
        'request_timeout': 60,
        'request_interval_ms': 100, # 新增：默认请求间隔 (毫秒)
    },
    'api_page_sizes': {
        'newapi': 100 # 默认 newapi 分页大小
    },
    'logging': { # 新增日志配置部分
        'level': "INFO" # 默认日志级别
    }
}

def load_script_config() -> dict:
    """
    加载脚本通用配置文件 (script_config.yaml)。
    如果文件不存在或加载失败，或缺少键，则使用默认值。

    Returns:
        dict: 加载或默认的脚本配置字典。
    """
    config = copy.deepcopy(DEFAULT_SCRIPT_CONFIG) # Start with defaults

    if SCRIPT_CONFIG_PATH.is_file():
        try:
            loaded_data = load_yaml_config(SCRIPT_CONFIG_PATH) # Use existing loader
            if loaded_data:
                # Merge loaded data into defaults, overwriting default values
                for section, settings in loaded_data.items():
                    if section in config and isinstance(settings, dict):
                        for key, value in settings.items():
                            if key in config[section]:
                                # 验证日志级别是否有效
                                if section == 'logging' and key == 'level':
                                    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
                                    if isinstance(value, str) and value.upper() in valid_levels:
                                        config[section][key] = value.upper() # 存储大写形式
                                    else:
                                        logging.warning(f"脚本配置 {SCRIPT_CONFIG_PATH} 中 'logging.level' 的值 '{value}' 无效，"
                                                        f"将使用默认值 '{config[section][key]}'. 有效值: {', '.join(valid_levels)}")
                                # 验证 request_interval_ms 是否为非负整数
                                elif section == 'api_settings' and key == 'request_interval_ms':
                                    if isinstance(value, int) and value >= 0:
                                        config[section][key] = value
                                    else:
                                        logging.warning(f"脚本配置 {SCRIPT_CONFIG_PATH} 中 'api_settings.request_interval_ms' 的值 '{value}' 无效 (必须是非负整数)，"
                                                        f"将使用默认值 '{config[section][key]}'.")
                                # Basic type check for other keys
                                elif isinstance(value, type(config[section][key])):
                                    config[section][key] = value
                                else:
                                     logging.warning(f"脚本配置 {SCRIPT_CONFIG_PATH} 中 '{section}.{key}' 的类型 "
                                                     f"({type(value).__name__}) 与默认值类型 "
                                                     f"({type(config[section][key]).__name__}) 不匹配，将使用默认值。")
                            else:
                                logging.warning(f"脚本配置 {SCRIPT_CONFIG_PATH} 中发现未知键 '{section}.{key}'，将被忽略。")
                    else:
                         logging.warning(f"脚本配置 {SCRIPT_CONFIG_PATH} 中发现未知顶层键 '{section}'，将被忽略。")
                logging.info(f"成功加载脚本配置文件: {SCRIPT_CONFIG_PATH}")
            else:
                logging.warning(f"脚本配置文件 {SCRIPT_CONFIG_PATH} 加载失败或内容无效，将使用默认配置。")
        except Exception as e:
            logging.error(f"加载脚本配置文件 {SCRIPT_CONFIG_PATH} 时发生错误: {e}，将使用默认配置。", exc_info=True)
    else:
        logging.info(f"脚本配置文件 {SCRIPT_CONFIG_PATH} 未找到，将使用默认配置。")

    # Log the final effective config
    logging.debug(f"最终生效的脚本配置: {config}")
    return config