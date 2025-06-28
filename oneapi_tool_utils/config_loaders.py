# -*- coding: utf-8 -*-
"""
负责加载和验证 API 连接配置及更新规则配置。
包含 YAML 加载、JSON 缓存处理和结构校验逻辑。
"""
import json
import logging
import os
from pathlib import Path
import yaml

# 假设 main_tool.py 和 oneapi_tool_utils 在同一级
# 注意：如果脚本从不同位置运行，这个相对路径可能需要调整
_TOOL_UTILS_DIR = Path(__file__).parent
_RUNTIME_DATA_DIR = _TOOL_UTILS_DIR / "runtime_data"
LOADED_CONNECTION_CONFIG_DIR = _RUNTIME_DATA_DIR / "loaded_connection_configs"

# 需要从 channel_manager_lib 导入基础的 YAML 加载函数
# 使用绝对导入路径，假设 channel_manager_lib 和 oneapi_tool_utils 在同一 PYTHONPATH 下
# 如果目录结构不同，可能需要调整
try:
    from channel_manager_lib.config_utils import load_yaml_config
except ImportError:
    logging.error("无法从 channel_manager_lib.config_utils 导入 load_yaml_config。配置加载功能将受限。")
    # 定义一个假的 load_yaml_config 以避免 NameError，但它会报错
    def load_yaml_config(path):
        raise NotImplementedError("基础 YAML 加载函数未能导入。")


def load_api_config(yaml_path_str: str) -> dict:
    """
    加载并验证 API 连接配置 (从 YAML 文件加载，使用 JSON 缓存)。

    Args:
        yaml_path_str (str): YAML 配置文件的路径字符串。

    Returns:
        dict: 加载并验证后的配置字典。

    Raises:
        FileNotFoundError: 如果 YAML 文件不存在。
        ValueError: 如果配置内容无效或缺少关键字段。
        Exception: 其他文件读写或解析错误。
    """
    yaml_path = Path(yaml_path_str)
    if not yaml_path.is_file():
        logging.error(f"API 配置文件 (YAML) 未找到: {yaml_path}")
        raise FileNotFoundError(f"API 配置文件 (YAML) 未找到: {yaml_path}")

    # 构造 JSON 缓存文件路径
    cache_dir = LOADED_CONNECTION_CONFIG_DIR
    json_cache_filename = yaml_path.stem + ".json" # e.g., my_server.json
    json_cache_path = cache_dir / json_cache_filename

    config_data = None
    use_cache = False

    # 检查缓存有效性
    if json_cache_path.is_file():
        try:
            yaml_mtime = os.path.getmtime(yaml_path)
            json_mtime = os.path.getmtime(json_cache_path)
            if json_mtime >= yaml_mtime:
                logging.debug(f"使用有效的 JSON 缓存文件: {json_cache_path}")
                with open(json_cache_path, 'r', encoding='utf-8') as f_json:
                    config_data = json.load(f_json)
                use_cache = True
            else:
                logging.debug(f"JSON 缓存文件已过期: {json_cache_path} (源文件已更新)")
        except Exception as e:
            logging.warning(f"检查或读取 JSON 缓存文件 {json_cache_path} 时出错: {e}，将重新加载 YAML。")

    # 如果未使用缓存，则加载 YAML 并更新/创建缓存
    if not use_cache:
        logging.debug(f"从 YAML 文件加载 API 配置: {yaml_path}")
        config_data = load_yaml_config(yaml_path) # 使用导入的 YAML 加载函数

        # --- 验证加载的数据 ---
        if not isinstance(config_data, dict):
            msg = f"API 配置文件内容无效，期望为字典格式: {yaml_path}"
            logging.error(msg)
            raise ValueError(msg)
        required_keys = ['site_url', 'api_token'] # 移除 api_type
        missing_keys = [k for k in required_keys if k not in config_data]
        if missing_keys:
            msg = f"API 配置缺失: 请检查 {yaml_path} 中的 {', '.join(missing_keys)}"
            logging.error(msg)
            raise ValueError(msg)

        # 确保 site_url 以 / 结尾
        if config_data.get('site_url') and not config_data['site_url'].endswith('/'):
            config_data['site_url'] += '/'

        # --- 更新/创建 JSON 缓存 ---
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            with open(json_cache_path, 'w', encoding='utf-8') as f_json:
                json.dump(config_data, f_json, indent=2, ensure_ascii=False)
            logging.debug(f"已更新/创建 JSON 缓存文件: {json_cache_path}")
        except Exception as e:
            logging.warning(f"写入 JSON 缓存文件 {json_cache_path} 时出错: {e}") # 缓存失败不应阻止主流程

    # 验证从缓存加载的数据 (如果使用了缓存)
    if use_cache:
        required_keys = ['site_url', 'api_token']
        missing_keys = [k for k in required_keys if k not in config_data]
        if missing_keys:
             # 缓存无效，需要重新加载 YAML
             logging.warning(f"缓存的 API 配置 {json_cache_path} 缺少必需键: {', '.join(missing_keys)}。将强制重新加载 YAML。")
             # 重新执行 YAML 加载逻辑
             logging.debug(f"从 YAML 文件加载 API 配置: {yaml_path}")
             config_data = load_yaml_config(yaml_path)
             if not isinstance(config_data, dict): raise ValueError(f"API 配置文件内容无效: {yaml_path}")
             missing_keys_yaml = [k for k in required_keys if k not in config_data]
             if missing_keys_yaml: raise ValueError(f"API 配置缺失 (YAML): {yaml_path} 中的 {', '.join(missing_keys_yaml)}")
             use_cache = False # 标记未使用缓存
             # 重新确保 site_url 结尾
             if config_data.get('site_url') and not config_data['site_url'].endswith('/'):
                 config_data['site_url'] += '/'
             # 尝试重新写入缓存
             try:
                 cache_dir.mkdir(parents=True, exist_ok=True)
                 with open(json_cache_path, 'w', encoding='utf-8') as f_json:
                     json.dump(config_data, f_json, indent=2, ensure_ascii=False)
                 logging.debug(f"已更新/创建 JSON 缓存文件 (因缓存失效): {json_cache_path}")
             except Exception as e:
                 logging.warning(f"写入 JSON 缓存文件 {json_cache_path} 时出错 (因缓存失效): {e}")

    # 记录最终加载成功的日志（确保在所有逻辑之后，并在返回前）
    logging.info(f"API 配置加载成功 (来源: {'缓存' if use_cache else 'YAML'}): URL={config_data.get('site_url', '未配置')}")
    return config_data

def _validate_match_mode(match_mode):
    """验证匹配模式是否有效 (辅助函数)"""
    valid_modes = {"any", "exact", "none", "all"}
    if match_mode not in valid_modes:
        raise ValueError(f"无效的匹配模式: {match_mode}. 有效值为: {valid_modes}")
    # logging.debug(f"验证匹配模式成功: {match_mode}") # 在 load_update_config 中记录更合适

def load_update_config(path: str | Path) -> dict:
    """加载并验证更新配置 (YAML)，增加更严格的结构和类型校验"""
    logging.debug(f"加载更新配置: {path}")
    config = load_yaml_config(path) # load_yaml_config 会处理 FileNotFoundError 和 YAMLError

    # 1. 顶层结构验证
    if not isinstance(config, dict):
        msg = f"更新配置文件内容无效，期望为字典格式: {path}"
        logging.error(msg)
        raise ValueError(msg)
    if not all(k in config for k in ['filters', 'updates']):
        # 允许部分缺失，但记录警告，因为可能只想筛选或只想更新（虽然不常见）
        logging.warning(f"{path} 中缺少 'filters' 或 'updates' 部分。如果这是预期行为，请忽略此警告。")

    # 2. 'filters' 部分验证
    if 'filters' in config:
        filters_config = config['filters']
        if not isinstance(filters_config, dict):
            msg = f"{path} 中的 'filters' 必须是字典类型。"
            logging.error(msg)
            raise ValueError(msg)

        # 验证 match_mode
        match_mode = filters_config.get("match_mode", "any") # Default to 'any' if not present
        try:
            _validate_match_mode(match_mode) # Use internal validation function
            logging.debug(f"{path} 'filters.match_mode' 验证成功: {match_mode}")
        except ValueError as e:
             msg = f"{path} 中 'filters.match_mode' 配置错误: {e}"
             logging.error(msg)
             raise ValueError(msg) from e

        # 验证 filter 列表类型
        filter_keys = ["name_filters", "group_filters", "model_filters", "tag_filters", "type_filters",
                       "exclude_name_filters", "exclude_group_filters", "exclude_model_filters",
                       "exclude_model_mapping_keys", "exclude_override_params_keys"] # 包含所有可能的过滤器键
        for key in filter_keys:
            if key in filters_config and filters_config[key] is not None and not isinstance(filters_config[key], list): # 检查非 None 且非列表
                msg = f"{path} 中的 'filters.{key}' 必须是列表类型或 null。"
                logging.error(msg)
                raise ValueError(msg)
            # 可以进一步验证列表内元素类型，但暂时保持简单

    # 3. 'updates' 部分验证
    if 'updates' in config:
        updates_config = config['updates']
        if not isinstance(updates_config, dict):
            msg = f"{path} 中的 'updates' 必须是字典类型。"
            logging.error(msg)
            raise ValueError(msg)

        for field, field_config in updates_config.items():
            if not isinstance(field_config, dict):
                msg = f"{path} 中 'updates.{field}' 的配置必须是字典类型。"
                logging.error(msg)
                raise ValueError(msg)
            if "enabled" not in field_config or not isinstance(field_config["enabled"], bool):
                msg = f"{path} 中 'updates.{field}' 必须包含布尔类型的 'enabled' 键。"
                logging.error(msg)
                raise ValueError(msg)
            # 对于 enabled=true 的情况，检查 value 是否存在 (某些模式可能不需要 value，后续逻辑处理)
            if field_config["enabled"] and "value" not in field_config:
                 # 允许 delete_keys 模式没有 value？目前 _prepare_update_payload 会处理
                 # 仅记录警告，让后续逻辑决定是否报错
                 logging.debug(f"{path} 中启用的 'updates.{field}' 缺少 'value' 键。这对于某些模式可能是正常的。")

    logging.info(f"更新配置加载并初步验证成功: {path}")
    return config # 返回加载并验证后的配置