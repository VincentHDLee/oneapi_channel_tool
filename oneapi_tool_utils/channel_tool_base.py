# -*- coding: utf-8 -*-
"""
共享的基础模块，包含通道更新工具的抽象基类和通用功能。
"""
import abc
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json # 仍然需要用于 API payload 的 dumps
import yaml # 导入 YAML 库
import logging
import aiohttp
import asyncio
import copy
from pathlib import Path
import os # 用于检查文件修改时间
import re # 导入正则表达式模块

from channel_manager_lib.config_utils import load_yaml_config # 导入 YAML 加载函数
# --- 常量 ---
# 定义缓存目录相对于此文件的位置 (或者从 main 导入)
# 假设 main_tool.py 和 oneapi_tool_utils 在同一级
# 注意：如果脚本从不同位置运行，这个相对路径可能需要调整
_TOOL_UTILS_DIR = Path(__file__).parent
_RUNTIME_DATA_DIR = _TOOL_UTILS_DIR / "runtime_data"
LOADED_CONNECTION_CONFIG_DIR = _RUNTIME_DATA_DIR / "loaded_connection_configs"
MAX_PAGES_TO_FETCH = 500 # 最大获取页数限制
RETRY_TIMES = 3
RETRY_BACKOFF_FACTOR = 0.5
RETRY_STATUS_FORCELIST = [500, 502, 503, 504] # 移除 404，因为找不到可能是正常情况

# --- 通用工具函数 ---
# load_yaml_config 已移至 config_utils.py

def create_retry_session():
    """创建带有重试机制的 requests session"""
    session = requests.Session()
    retry_strategy = Retry(
        total=RETRY_TIMES,
        backoff_factor=RETRY_BACKOFF_FACTOR,
        status_forcelist=RETRY_STATUS_FORCELIST,
        allowed_methods=["HEAD", "GET", "OPTIONS", "PUT", "POST"] # 允许重试 PUT/POST
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    logging.debug("创建带有重试机制的 session 成功")
    return session

# --- 抽象基类 ---
class ChannelToolBase(abc.ABC):
    """渠道更新工具的抽象基类"""

    def __init__(self, api_config_path, update_config_path=None, script_config=None):
        """
        初始化工具实例。

        Args:
            api_config_path (str): API 连接配置文件的路径。
            update_config_path (str, optional): 更新规则配置文件的路径。
                                                如果为 None (例如在撤销操作中)，则不加载。
            script_config (dict, optional): 加载后的脚本通用配置字典。
        """
        self.api_config = self._load_api_config(api_config_path)
        self.update_config = self._load_update_config(update_config_path) if update_config_path else None
        # 存储传入的脚本配置，如果未提供则加载默认值（尽管调用者应确保提供）
        # 注意: load_script_config() 函数需要在 channel_manager_lib.config_utils 中定义
        # 如果 script_config 为 None，尝试加载默认配置
        if script_config is None:
            try:
                from channel_manager_lib.config_utils import load_script_config
                self.script_config = load_script_config()
            except ImportError:
                logging.warning("无法导入 load_script_config，将使用空字典作为 script_config。")
                self.script_config = {}
        else:
             self.script_config = script_config

        self.session = create_retry_session() # 同步 session 用于 get_all_channels
        # aiohttp session 在需要时创建

    def _load_api_config(self, yaml_path_str):
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
            config_data = load_yaml_config(yaml_path) # 使用已有的 YAML 加载函数

            # --- 验证加载的数据 ---
            if not isinstance(config_data, dict):
                msg = f"API 配置文件内容无效，期望为字典格式: {yaml_path}"
                logging.error(msg)
                raise ValueError(msg)
            required_keys = ['site_url', 'api_token', 'api_type'] # 添加 api_type 到必需键
            missing_keys = [k for k in required_keys if k not in config_data]
            if missing_keys:
                msg = f"API 配置缺失: 请检查 {yaml_path} 中的 {', '.join(missing_keys)}"
                logging.error(msg)
                raise ValueError(msg)

            # 验证 api_type 的值
            api_type_value = config_data.get('api_type')
            valid_api_types = {"newapi", "voapi"}
            if api_type_value not in valid_api_types:
                msg = f"API 配置错误: {yaml_path} 中的 'api_type' 值 '{api_type_value}' 无效。有效值为: {valid_api_types}"
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
            required_keys = ['site_url', 'api_token', 'api_type']
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
                 # 重新验证 api_type
                 api_type_value = config_data.get('api_type')
                 valid_api_types = {"newapi", "voapi"}
                 if api_type_value not in valid_api_types:
                     raise ValueError(f"API 配置错误 (YAML): {yaml_path} 中的 'api_type' 值 '{api_type_value}' 无效。有效值为: {valid_api_types}")
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

            else:
                 # 验证缓存中的 api_type 值
                 api_type_value = config_data.get('api_type')
                 valid_api_types = {"newapi", "voapi"}
                 if api_type_value not in valid_api_types:
                     # 缓存无效
                     logging.warning(f"缓存的 API 配置 {json_cache_path} 中的 'api_type' 值 '{api_type_value}' 无效。将强制重新加载 YAML。")
                     # 同上，重新加载 YAML 并验证
                     logging.debug(f"从 YAML 文件加载 API 配置: {yaml_path}")
                     config_data = load_yaml_config(yaml_path)
                     if not isinstance(config_data, dict): raise ValueError(f"API 配置文件内容无效: {yaml_path}")
                     required_keys_yaml = ['site_url', 'api_token', 'api_type']
                     missing_keys_yaml = [k for k in required_keys_yaml if k not in config_data]
                     if missing_keys_yaml: raise ValueError(f"API 配置缺失 (YAML): {yaml_path} 中的 {', '.join(missing_keys_yaml)}")
                     use_cache = False
                     api_type_value_yaml = config_data.get('api_type')
                     if api_type_value_yaml not in valid_api_types:
                         raise ValueError(f"API 配置错误 (YAML): {yaml_path} 中的 'api_type' 值 '{api_type_value_yaml}' 无效。有效值为: {valid_api_types}")
                     if config_data.get('site_url') and not config_data['site_url'].endswith('/'):
                         config_data['site_url'] += '/'
                     try:
                         cache_dir.mkdir(parents=True, exist_ok=True)
                         with open(json_cache_path, 'w', encoding='utf-8') as f_json:
                             json.dump(config_data, f_json, indent=2, ensure_ascii=False)
                         logging.debug(f"已更新/创建 JSON 缓存文件 (因缓存 api_type 失效): {json_cache_path}")
                     except Exception as e:
                         logging.warning(f"写入 JSON 缓存文件 {json_cache_path} 时出错 (因缓存 api_type 失效): {e}")

        # 记录最终加载成功的日志（确保在所有逻辑之后，并在返回前）
        logging.info(f"API 配置加载成功 (来源: {'缓存' if use_cache else 'YAML'}): URL={config_data.get('site_url', '未配置')}, 类型={config_data.get('api_type', '未知')}")
        return config_data

    def _load_update_config(self, path):
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
                self._validate_match_mode(match_mode) # Use existing validation function
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
                     # msg = f"{path} 中 'updates.{field}' 必须包含 'value' 键。"
                     # logging.error(msg)
                     # raise ValueError(msg)
        return config # 返回加载并验证后的配置

    @property
    def site_url(self):
        return self.api_config.get('site_url', '')

    @property
    def api_token(self):
        return self.api_config.get('api_token', '')

    @property
    def user_id(self):
        # user_id 是可选的
        return self.api_config.get('user_id', '1') # 提供默认值 '1'

    @abc.abstractmethod
    def get_all_channels(self):
        """
        获取所有渠道的列表。
        子类必须实现此方法以适应特定的 API。
        应返回包含两个元素的元组: (渠道字典列表 | None, 消息字符串)。
        如果成功，列表包含数据，消息为成功信息。
        如果失败，列表为 None，消息为错误描述。
        """
        pass

    @abc.abstractmethod
    async def update_channel_api(self, channel_data_payload):
        """
        调用 API 更新单个渠道。
        子类必须实现此方法以适应特定的 API 端点和认证。
        Args:
            channel_data_payload (dict): 包含渠道 ID 和待更新字段的字典。
        Returns:
            tuple[bool, str]: (更新是否成功, 包含成功或失败信息的消息字符串)
        """
        pass

    @abc.abstractmethod
    async def get_channel_details(self, channel_id):
        """
        获取单个渠道的详细信息。
        子类必须实现此方法以适应特定的 API 端点。
        Args:
            channel_id (int): 渠道 ID。
        Returns:
            tuple[dict | None, str]: (渠道的详细数据字典 | None, 包含成功或失败信息的消息字符串)
        """
        pass # Needed for save_undo_data

    @abc.abstractmethod
    def format_list_field_for_api(self, field_name: str, data_set: set) -> str | list:
        """
        将处理后的集合数据格式化为目标 API 更新时所需的格式。
        例如，转换为逗号分隔的字符串或列表本身。
        子类必须实现此方法。

        Args:
            field_name (str): 字段名称 (例如 "models", "group")。
            data_set (set): 包含最终值的集合。

        Returns:
            str | list: 格式化后的值，用于 API payload。
        """
        pass

    @abc.abstractmethod
    def format_dict_field_for_api(self, field_name: str, data_dict: dict) -> str | dict:
        """
        将处理后的字典数据格式化为目标 API 更新时所需的格式。
        例如，返回字典本身或 JSON 字符串。
        子类必须实现此方法。

        Args:
            field_name (str): 字段名称 (例如 "model_mapping", "setting")。
            data_dict (dict): 包含最终键值的字典。

        Returns:
            str | dict: 格式化后的值，用于 API payload。
        """
        pass

    @abc.abstractmethod
    def format_field_value_for_api(self, field_name: str, value: any) -> any:
        """
        对计算出的最终字段值进行特定于 API 的最后格式化。
        这主要用于确保简单字段类型正确（例如，整数、布尔值、字符串）。
        对于列表和字典字段，此方法可以在 format_list/dict_field_for_api 之后调用，
        或者那两个方法可以直接返回最终格式。子类应决定最佳实现。

        Args:
            field_name (str): 字段名称。
            value (any): 由 copy_fields 逻辑计算出的值。

        Returns:
            any: 最终格式化后，用于放入 API payload 的值。
        """
        pass
    def filter_channels(self, channel_list: list, filters_config: dict | None = None) -> list:
        """
        根据提供的筛选器配置过滤渠道列表。

        Args:
            channel_list (list): 要过滤的原始渠道字典列表。
            filters_config (dict | None, optional):
                包含筛选条件的字典，结构应与 update_config.yaml 或
                cross_site_config.yaml 中的 'filters'/'channel_filter' 部分一致。
                如果为 None 或空字典，则不进行过滤，返回原始列表。
                默认为 None。

        Returns:
            list: 过滤后的渠道字典列表。
        """
        if not filters_config:
            logging.info("未提供筛选配置或配置为空，不过滤渠道。")
            return channel_list # 没有筛选器，返回原列表
        if not channel_list:
            logging.warning("输入的渠道列表为空，无需过滤。")
            return []

        # 确保 filters_config 是字典
        if not isinstance(filters_config, dict):
             logging.error(f"传入的筛选配置 filters_config 不是有效的字典: {type(filters_config)}")
             # 返回空列表表示过滤出错或无效配置
             return []

        match_mode = filters_config.get("match_mode", "any") # 默认 any

        try:
            self._validate_match_mode(match_mode)
        except ValueError as e:
            logging.error(f"筛选配置中的 match_mode 无效: {e}")
            return [] # 返回空列表表示过滤失败

        logging.info(f"开始使用提供的配置过滤 {len(channel_list)} 个渠道...")

        # 构建日志信息
        log_parts = [f"模式='{match_mode}'"]
        known_filters = [
            "id", "name_filters", "exclude_name_filters",
            "group_filters", "exclude_group_filters",
            "model_filters", "exclude_model_filters",
            "tag_filters", # 假设 tag 只有包含，没有排除
            "type_filters", # 假设 type 只有包含
            "exclude_model_mapping_keys",
            "exclude_override_params_keys"
        ]
        for key in known_filters:
             # 仅当过滤器存在且非 None 时才记录 (允许 null 值表示禁用)
             filter_value = filters_config.get(key)
             if filter_value is not None:
                  log_parts.append(f"{key}={filter_value}")
        logging.info(f"筛选条件: {', '.join(log_parts)}")

        # 执行过滤
        # 使用 _channel_matches_filters (它现在应该能够处理传入的 filters_config)
        filtered_channels = [
            channel for channel in channel_list
            if self._channel_matches_filters(channel, filters_config)
        ]

        if not filtered_channels:
            logging.warning("根据提供的筛选条件，未匹配到任何渠道。")
        else:
            logging.info(f"根据提供的筛选条件，总共匹配到 {len(filtered_channels)} 个渠道。")
        return filtered_channels

    def _validate_match_mode(self, match_mode):
        """验证匹配模式是否有效"""
        valid_modes = {"any", "exact", "none", "all"} # 添加 all 模式
        if match_mode not in valid_modes:
            raise ValueError(f"无效的匹配模式: {match_mode}. 有效值为: {valid_modes}")
        logging.debug(f"验证匹配模式成功: {match_mode}")

    def _match_filter(self, value, filter_list, match_mode):
        """根据匹配模式和筛选列表判断值是否匹配 (用于字符串类型字段)"""
        # 仅当过滤器列表非空时才进行匹配
        if not filter_list:
            # 根据模式决定：any/all 模式下，空过滤器不应阻止匹配；exact/none 则需要考虑
            if match_mode in ["any", "all"]:
                return True # 没有指定条件，默认满足
            else:
                # 对于 exact/none，如果过滤器为空，则无法匹配/排除
                # 但通常 _channel_matches_filters 会先检查 filter_list 是否为空
                return True # 保持原逻辑，认为没有过滤器就是匹配
        if value is None: return False # None 值不匹配任何非空过滤器

        value_str = str(value)
        filter_strs = [str(f) for f in filter_list if f is not None] # 忽略过滤器中的 None 值

        if not filter_strs: # 如果过滤掉 None 后列表为空
             return True # 同上，没有有效条件

        if match_mode == "any":
            # 部分匹配
            return any(f in value_str for f in filter_strs)
        elif match_mode == "exact":
            # 完全匹配
            return value_str in filter_strs
        elif match_mode == "none":
            # 不包含任何一个
            return all(f not in value_str for f in filter_strs)
        # "all" 模式对于单一字符串字段意义不大，除非解释为包含所有子串？
        # 暂时不为字符串实现 "all" 的特殊逻辑，认为不匹配
        return False

    def _channel_matches_filters(self, channel, filters_config):
        """判断单个渠道是否符合所有筛选条件"""
        if not isinstance(channel, dict):
            logging.warning(f"跳过无效的渠道数据项 (非字典): {channel}")
            return False

        channel_id = channel.get('id') # 获取当前渠道的 ID

        # --- 精确 ID 匹配 (最高优先级) ---
        filter_id_value = filters_config.get('id')
        if filter_id_value is not None: # 允许用 id: null 来禁用 ID 匹配
            # 尝试将两者都转为整数进行比较，以处理类型差异
            try:
                match = int(channel_id) == int(filter_id_value)
                logging.debug(f"  - ID 精确匹配检查: channel_id={channel_id}, filter_id={filter_id_value}, 结果={match}")
                return match
            except (ValueError, TypeError, AttributeError): # 添加 AttributeError 处理 channel_id 为 None 的情况
                # 如果转换失败或 channel_id 为 None，进行原始类型比较
                match = channel_id == filter_id_value
                logging.debug(f"  - ID 精确匹配检查 (原始类型): channel_id={channel_id}, filter_id={filter_id_value}, 结果={match}")
                return match

        # --- 常规筛选器 (仅在没有精确 ID 筛选时应用) ---
        # 使用 .get(key, []) 或 .get(key) is not None 来安全地处理可能不存在或为 null 的过滤器
        name_filters = filters_config.get("name_filters", [])
        exclude_name_filters = filters_config.get("exclude_name_filters", [])
        group_filters = filters_config.get("group_filters", [])
        exclude_group_filters = filters_config.get("exclude_group_filters", [])
        model_filters = filters_config.get("model_filters", [])
        exclude_model_filters = filters_config.get("exclude_model_filters", [])
        tag_filters = filters_config.get("tag_filters", [])
        type_filters = filters_config.get("type_filters", [])
        exclude_model_mapping_keys = filters_config.get("exclude_model_mapping_keys", [])
        exclude_override_params_keys = filters_config.get("exclude_override_params_keys", [])
        match_mode = filters_config.get("match_mode", "any")

        # --- 排除逻辑 ---
        # 只要满足任何一个排除条件，就直接返回 False
        channel_name = channel.get('name', '')
        if exclude_name_filters and self._match_filter(channel_name, exclude_name_filters, "any"):
            logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 因 exclude_name_filters 被排除")
            return False

        # 处理分组（可能是逗号分隔的字符串或列表，需要规范化）
        channel_groups = self._normalize_to_set(channel.get('group', ''))
        if exclude_group_filters and any(g in channel_groups for g in exclude_group_filters):
            logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 因 exclude_group_filters 被排除")
            return False

        # 处理模型
        channel_models = self._normalize_to_set(channel.get('models', ''))
        if exclude_model_filters and any(m in channel_models for m in exclude_model_filters):
            logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 因 exclude_model_filters 被排除")
            return False

        # 处理模型映射键 (假设 model_mapping 是字典)
        model_mapping = self._normalize_to_dict(channel.get('model_mapping'), 'model_mapping', channel_name)
        if exclude_model_mapping_keys and any(key in model_mapping for key in exclude_model_mapping_keys):
            logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 因 exclude_model_mapping_keys 被排除")
            return False

        # 处理覆盖参数键 (假设 override_params 是字典)
        # 注意: API 返回的可能是 param_override，需要确认哪个是实际字段名
        override_params_key = 'override_params' if 'override_params' in channel else 'param_override'
        override_params = self._normalize_to_dict(channel.get(override_params_key), override_params_key, channel_name)
        if exclude_override_params_keys and any(key in override_params for key in exclude_override_params_keys):
            logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 因 exclude_override_params_keys 被排除")
            return False

        # --- 包含逻辑 ---
        # 检查是否至少有一个包含性过滤器被设置了非空值
        has_include_filter = any([name_filters, group_filters, model_filters, tag_filters, type_filters])

        # 如果没有任何包含性过滤器被设置，则默认匹配 (因为排除了不匹配的)
        if not has_include_filter:
            logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 因无包含过滤器而匹配 (已通过排除)")
            return True

        # 检查是否需要匹配所有条件 ("all" 模式)
        if match_mode == "all":
            # 对于 "all" 模式，每个设置了的包含过滤器都必须匹配
            all_matched = True
            if name_filters and not self._match_filter(channel_name, name_filters, "any"):
                all_matched = False
            if group_filters and not any(g in channel_groups for g in group_filters):
                all_matched = False
            if model_filters and not any(m in channel_models for m in model_filters):
                all_matched = False
            if tag_filters:
                channel_tags = self._normalize_to_set(channel.get('tag', ''))
                if not any(t in channel_tags for t in tag_filters):
                    all_matched = False
            if type_filters and channel.get('type') not in type_filters:
                all_matched = False
            logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 的 'all' 模式匹配结果: {all_matched}")
            return all_matched

        # 检查是否满足任何一个条件 ("any" 模式)
        elif match_mode == "any":
            any_matched = False
            if name_filters and self._match_filter(channel_name, name_filters, "any"):
                logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 匹配 name_filters")
                any_matched = True
            # 注意：这里使用 elif 而不是 if，确保只要有一个匹配就停止检查并返回 True
            elif group_filters and any(g in channel_groups for g in group_filters):
                 logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 匹配 group_filters")
                 any_matched = True
            elif model_filters and any(m in channel_models for m in model_filters):
                 logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 匹配 model_filters")
                 any_matched = True
            elif tag_filters:
                channel_tags = self._normalize_to_set(channel.get('tag', ''))
                if any(t in channel_tags for t in tag_filters):
                    logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 匹配 tag_filters")
                    any_matched = True
            elif type_filters and channel.get('type') in type_filters:
                 logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 匹配 type_filters")
                 any_matched = True
            # 如果启用了包含过滤器，但没有任何一个匹配上，则返回 False
            return any_matched

        # 其他模式（exact, none）通常不用于组合多个过滤器类型
        else:
            logging.warning(f"在 'any'/'all' 之外的模式下使用多个过滤器类型，行为未定义，渠道 {channel_name} (ID: {channel_id}) 不匹配")
            return False

        # 如果没有任何启用的包含性过滤器，则默认匹配（因为排除了不匹配的）
        if not enabled_include_filters:
            logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 因无包含过滤器而匹配 (已通过排除)")
            return True

        # 检查是否需要匹配所有条件 ("all" 模式)
        if match_mode == "all":
            all_matched = True # 假设匹配，直到找到不匹配的
            if name_filters and not self._match_filter(channel_name, name_filters, "any"):
                 all_matched = False
            elif group_filters and not any(g in channel_groups for g in group_filters):
                 all_matched = False
            elif model_filters and not any(m in channel_models for m in model_filters):
                 all_matched = False
            elif tag_filters:
                channel_tags = self._normalize_to_set(channel.get('tag', ''))
                if not any(t in channel_tags for t in tag_filters):
                     all_matched = False
            elif type_filters and channel.get('type') not in type_filters:
                 all_matched = False
            # 如果某个过滤器列表为空，它不应该影响 all 模式的结果，所以上面用 if filter_list and not ...
            logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 的 'all' 模式匹配结果: {all_matched}")
            return all_matched

        # 检查是否满足任何一个条件 ("any" 模式)
        elif match_mode == "any":
            any_matched = False
            if name_filters and self._match_filter(channel_name, name_filters, "any"):
                logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 匹配 name_filters")
                any_matched = True
            elif group_filters and any(g in channel_groups for g in group_filters):
                 logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 匹配 group_filters")
                 any_matched = True
            elif model_filters and any(m in channel_models for m in model_filters):
                 logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 匹配 model_filters")
                 any_matched = True
            elif tag_filters:
                channel_tags = self._normalize_to_set(channel.get('tag', ''))
                if any(t in channel_tags for t in tag_filters):
                    logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 匹配 tag_filters")
                    any_matched = True
            elif type_filters and channel.get('type') in type_filters:
                 logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 匹配 type_filters")
                 any_matched = True

            # 在 any 模式下，如果没有任何过滤器，则不匹配任何特定条件，应返回 False
            # （之前的逻辑是返回 True，这里修正为 False，因为没有条件被满足）
            # 但如果所有包含过滤器都为空，我们已经在前面返回 True 了，所以这里只处理有过滤器的情况
            if not enabled_include_filters: # 再次检查以防万一
                 return True # 没有启用包含过滤器，则通过
            else:
                 return any_matched # 返回是否匹配了 *任何一个* 启用的过滤器

        # 其他模式（exact, none）通常不用于组合多个过滤器类型，但为了完整性保留
        else:
            # 对于 exact/none 模式，如果存在多个过滤器类型，行为未定义，返回 False
            logging.warning(f"在 'any'/'all' 之外的模式下使用多个过滤器类型，行为未定义，渠道 {channel_name} (ID: {channel_id}) 不匹配")
            return False

    def _normalize_to_set(self, value):
        """将可能是 None、空字符串、逗号分隔字符串或列表的值规范化为集合"""
        if value is None:
            return set()
        if isinstance(value, list):
            # 过滤掉 None 或空字符串元素
            return {str(item).strip() for item in value if item is not None and str(item).strip()}
        if isinstance(value, str):
            if not value.strip():
                return set()
            # 过滤掉分割后可能产生的空字符串
            return {item.strip() for item in value.split(',') if item.strip()}
        # 尝试转换为字符串处理其他类型
        try:
            s_value = str(value)
            if not s_value.strip():
                return set()
            return {item.strip() for item in s_value.split(',') if item.strip()}
        except Exception as e: # 更具体的异常可能更好，但 Exception 可以捕获所有转换错误
            logging.warning(f"无法将值 '{value}' (类型: {type(value)}) 规范化为集合，返回空集合: {e}")
            return set()

    def _normalize_to_dict(self, value, field_name="未知字段", channel_name="未知渠道"):
        """将可能是 None、JSON 字符串或已经是字典的值规范化为字典"""
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            if not value.strip():
                return {}
            try:
                # 尝试解析 JSON 字符串
                parsed_dict = json.loads(value)
                if isinstance(parsed_dict, dict):
                    return parsed_dict
                else:
                    logging.warning(f"字段 '{field_name}' (渠道: {channel_name}) 的值 '{value}' 解析为非字典类型 ({type(parsed_dict)})，返回空字典。")
                    return {}
            except json.JSONDecodeError:
                logging.warning(f"字段 '{field_name}' (渠道: {channel_name}) 的值 '{value}' 不是有效的 JSON 字符串，也非字典，返回空字典。")
                return {}
        # 对于其他无法处理的类型
        logging.warning(f"字段 '{field_name}' (渠道: {channel_name}) 的值类型 ({type(value)}) 无法规范化为字典，返回空字典。")
        return {}


    def _prepare_update_payload(self, original_channel_data):
        """
        根据更新配置为单个渠道准备 API 更新所需的 payload。

        Args:
            original_channel_data (dict): 原始渠道数据。

        Returns:
            tuple: (dict | None, set)
                - dict | None: 准备好的更新 payload (包含 id 和需要更新的字段)。
                               如果无需更新或出错，则为 None。
                - set: 实际发生变更的字段名称集合。
        """
        # 检查 update_config 是否已加载
        if self.update_config is None or 'updates' not in self.update_config:
            logging.error("准备更新 payload 失败：更新配置文件未加载或缺少 'updates' 部分。")
            return None, set()

        updates_config = self.update_config.get('updates', {})
        channel_id = original_channel_data.get('id')
        if not channel_id:
            logging.error("准备更新 payload 失败：原始渠道数据缺少 ID。")
            return None, set()

        payload = {'id': channel_id} # 始终包含 ID
        changed_fields = set()
        channel_name = original_channel_data.get('name', f'ID:{channel_id}') # 用于日志

        for field, config in updates_config.items():
            if not isinstance(config, dict) or config.get("enabled") is not True:
                continue # 跳过未启用或格式错误的更新

            # --- 获取原始值和配置值 ---
            original_value = original_channel_data.get(field)
            update_value = config.get("value") # Value 可能为 None 或缺失，看模式处理
            mode = config.get("mode", "overwrite") # 默认为覆盖模式

            new_value = None # 初始化新值

            # --- 根据模式计算新值 ---
            try:
                # 模式 1: overwrite (默认)
                if mode == "overwrite":
                    new_value = update_value

                # 模式 2: regex_replace (仅适用于字符串字段)
                elif mode == "regex_replace":
                    if isinstance(original_value, str) and isinstance(update_value, dict) and \
                       'pattern' in update_value and 'replacement' in update_value:
                        try:
                            new_value = re.sub(update_value['pattern'], update_value['replacement'], original_value)
                        except re.error as re_err:
                            logging.warning(f"渠道 {channel_name} 的字段 '{field}' 正则替换失败: 无效模式 '{update_value['pattern']}' 或替换 '{update_value['replacement']}' ({re_err})。跳过此字段。")
                            continue # 跳过这个字段的更新
                    else:
                        logging.warning(f"渠道 {channel_name} 的字段 '{field}' 使用 regex_replace 模式，但原始值非字符串或配置值格式错误。跳过此字段。")
                        continue

                # 模式 3: append (适用于列表/集合字段)
                elif mode == "append":
                    original_set = self._normalize_to_set(original_value)
                    update_set = self._normalize_to_set(update_value)
                    final_set = original_set.union(update_set)
                    new_value = self.format_list_field_for_api(field, final_set) # 使用子类方法格式化

                # 模式 4: remove (适用于列表/集合字段)
                elif mode == "remove":
                    original_set = self._normalize_to_set(original_value)
                    remove_set = self._normalize_to_set(update_value)
                    final_set = original_set - remove_set
                    new_value = self.format_list_field_for_api(field, final_set) # 使用子类方法格式化

                # 模式 5: merge (适用于字典字段)
                elif mode == "merge":
                    original_dict = self._normalize_to_dict(original_value, field, channel_name)
                    update_dict = self._normalize_to_dict(update_value, field, channel_name)
                    # 创建副本以避免修改原始字典
                    final_dict = copy.deepcopy(original_dict)
                    final_dict.update(update_dict) # update_dict 中的键会覆盖 final_dict 中的
                    new_value = self.format_dict_field_for_api(field, final_dict) # 使用子类方法格式化

                # 模式 6: delete_keys (适用于字典字段)
                elif mode == "delete_keys":
                    original_dict = self._normalize_to_dict(original_value, field, channel_name)
                    # delete_keys 的 value 应该是一个 key 的列表
                    # update_value 在这里应该是要删除的键的列表
                    if update_value is None: # 如果 value 未提供，认为不删除任何键
                        keys_to_delete = set()
                        logging.debug(f"渠道 {channel_name} 字段 '{field}' 的 delete_keys 模式缺少 value，不删除任何键。")
                    else:
                        keys_to_delete = self._normalize_to_set(update_value)

                    # 创建副本
                    final_dict = copy.deepcopy(original_dict)
                    deleted_count = 0
                    for key in keys_to_delete:
                        if key in final_dict:
                            del final_dict[key]
                            deleted_count += 1
                    logging.debug(f"渠道 {channel_name} 字段 '{field}' 的 delete_keys 模式删除了 {deleted_count} 个键。")
                    new_value = self.format_dict_field_for_api(field, final_dict) # 使用子类方法格式化

                else:
                     logging.warning(f"渠道 {channel_name} 的字段 '{field}' 配置了未知模式 '{mode}'。跳过此字段。")
                     continue

                # --- 检查值是否实际改变 ---
                # 对比 new_value 和 original_value 是否真的不同
                is_changed = False
                # 优化比较逻辑：先进行最终格式化，再比较
                formatted_new_value = self.format_field_value_for_api(field, new_value)
                formatted_original_value = self.format_field_value_for_api(field, original_value) # 也对原始值格式化

                # 特殊处理 None 和空字符串/列表/字典的比较
                if formatted_new_value is None and isinstance(formatted_original_value, (str, list, dict)) and not formatted_original_value:
                    is_changed = False # None 等同于空结构
                elif formatted_original_value is None and isinstance(formatted_new_value, (str, list, dict)) and not formatted_new_value:
                     is_changed = False # 空结构等同于 None
                elif isinstance(formatted_original_value, list) and isinstance(formatted_new_value, list):
                     # 对于列表，考虑顺序不敏感的比较？目前使用严格比较
                     if sorted(formatted_original_value) != sorted(formatted_new_value): # 排序后比较
                          is_changed = True
                elif isinstance(formatted_original_value, dict) and isinstance(formatted_new_value, dict):
                     # 对于字典，直接比较
                     if formatted_original_value != formatted_new_value:
                          is_changed = True
                elif formatted_original_value != formatted_new_value:
                     # 其他类型直接比较
                     is_changed = True


                if is_changed:
                    payload[field] = formatted_new_value # 使用格式化后的值
                    changed_fields.add(field)
                    logging.debug(f"渠道 {channel_name} 的字段 '{field}' 准备更新: {repr(formatted_original_value)} -> {repr(payload[field])} (模式: {mode})")
                else:
                    logging.debug(f"渠道 {channel_name} 的字段 '{field}' 值未改变 ({repr(formatted_original_value)} -> {repr(formatted_new_value)})，跳过。")

            except Exception as e:
                logging.error(f"为渠道 {channel_name} 处理字段 '{field}' (模式: {mode}) 时发生错误: {e}", exc_info=True)
                continue # 跳过这个字段的更新

        if not changed_fields:
            logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 没有需要更新的字段。")
            return None, set()

        return payload, changed_fields

    async def run_updates(self, dry_run=False):
        """
        (已废弃/或待重构) 统一执行更新流程 (获取、过滤、准备、执行)。
        注意：此方法目前未使用，推荐使用 single_site_handler 中的流程。
              如果需要保留，需要重构以适应新的并发和错误处理逻辑。

        Args:
            dry_run (bool): 如果为 True，则只打印计划的更新而不执行。

        Returns:
            int: 0 表示成功或无操作, 1 表示失败, 3 表示严重错误。
        """
        logging.warning("run_updates 方法已不推荐使用，请使用 single_site_handler 中的流程。")
        # --- 1. 获取和过滤渠道 ---
        # get_all_channels 现在是同步方法，需要调整为异步或在同步上下文中处理
        # 假设在异步上下文中调用
        try:
            # 需要调用异步版本的 get_all_channels
            # 或者假设 get_all_channels 已经在外部调用并传入
            # 这里无法直接调用，因为 run_updates 设计为同步方法
            # all_channels, get_list_message = await self.get_all_channels_async() # 假设有异步版本
            logging.error("run_updates 无法直接调用异步的 get_all_channels，需要重构。")
            return 3 # 结构性问题

            # if all_channels is None:
            #     logging.error(f"获取渠道列表失败: {get_list_message}")
            #     return 1
            # if not all_channels:
            #     logging.info(f"渠道列表为空 ({get_list_message})，无需更新。")
            #     return 0
        except AttributeError:
             logging.error("假设的 get_all_channels_async 方法不存在。run_updates 需要重构。")
             return 3

        # 使用 self.update_config['filters'] 进行过滤
        filters = self.update_config.get('filters') if self.update_config else None
        # filtered_channels = self.filter_channels(all_channels, filters) # all_channels 未定义

        # if not filtered_channels:
        #     logging.info("没有匹配筛选条件的渠道。")
        #     return 0

        # logging.info(f"找到 {len(filtered_channels)} 个匹配的渠道，准备处理...")

        # --- 2. 准备更新任务 ---
        payloads_to_update = []
        channels_info = [] # 用于记录失败信息
        # for channel in filtered_channels: # filtered_channels 未定义
            # channel_id = channel.get('id')
            # channel_name = channel.get('name', f'ID:{channel_id}')
            # payload, changed = self._prepare_update_payload(channel)
            # if payload and changed:
            #     payloads_to_update.append(payload)
            #     channels_info.append({'id': channel_id, 'name': channel_name})
            #     # 打印计划变更 (如果 dry_run 或需要模拟输出)
            #     if dry_run:
            #         print(f"\n计划更新渠道 {channel_name} (ID: {channel_id}):")
            #         for field in changed:
            #              original_value = channel.get(field)
            #              new_value = payload.get(field)
            #              print(f"  - {field}: {repr(original_value)} -> {repr(new_value)}")

        if not payloads_to_update:
            logging.info("所有匹配的渠道都无需更新。")
            if dry_run: print("\n模拟运行：没有检测到需要执行的更新。")
            return 0

        if dry_run:
            print("\n模拟运行结束。")
            return 0

        # --- 3. 执行更新 (需要改成异步并发) ---
        logging.info(f"开始执行 {len(payloads_to_update)} 个渠道的更新...")

        # 获取并发设置
        api_settings = self.script_config.get('api_settings', {})
        max_concurrent = api_settings.get('max_concurrent_requests', 5)
        semaphore = asyncio.Semaphore(max_concurrent)

        async def update_task_wrapper(payload):
            async with semaphore:
                # update_channel_api 是异步方法
                # 返回 tuple[bool, str]
                success, msg = await self.update_channel_api(payload)
                return success, msg # 返回元组

        tasks = [update_task_wrapper(p) for p in payloads_to_update]
        results = []
        try:
            # 需要在异步上下文中运行 asyncio.gather
            # 这个方法本身是同步的，不能直接 await gather
            # 再次强调：此方法需要重构为异步或由异步函数调用
            logging.error("run_updates 方法需要重构以支持异步更新执行。")
            return 1 # 表示失败，因为无法执行

            # 假设能拿到 results
            # results = await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
             logging.critical(f"执行更新流程时发生严重错误: {e}", exc_info=True)
             return 3 # 未知严重错误

        # --- 4. 处理结果 ---
        success_count = 0
        failure_count = 0
        # for i, r in enumerate(results): # results 未定义
        #     if isinstance(r, tuple) and len(r) == 2:
        #         success, msg = r
        #         if success:
        #             success_count += 1
        #         else:
        #             failure_count += 1
        #             # 记录失败信息
        #             if i < len(channels_info):
        #                 ch_info = channels_info[i]
        #                 logging.error(f"渠道 {ch_info['name']} (ID: {ch_info['id']}) 更新失败: {msg}")
        #             else:
        #                  logging.error(f"未知渠道更新失败: {msg}")
        #     elif isinstance(r, Exception):
        #          failure_count += 1
        #          # 记录异常信息
        #          if i < len(channels_info):
        #              ch_info = channels_info[i]
        #              logging.error(f"渠道 {ch_info['name']} (ID: {ch_info['id']}) 更新时发生异常: {r}", exc_info=r)
        #          else:
        #              logging.error(f"未知渠道更新时发生异常: {r}", exc_info=r)
        #     else:
        #          failure_count += 1
        #          logging.error(f"更新任务返回未知结果类型: {r}")


        logging.info(f"更新任务完成: {success_count} 个成功, {failure_count} 个失败。")

        if failure_count > 0:
            return 1 # 返回 1 表示部分或全部失败
        else:
            return 0 # 返回 0 表示全部成功