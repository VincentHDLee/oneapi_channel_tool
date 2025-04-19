# -*- coding: utf-8 -*-
"""
共享的基础模块，包含通道更新工具的抽象基类和通用功能。
"""
import abc
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json
import logging
import aiohttp
import asyncio
import copy
from pathlib import Path

# --- 常量 ---
MAX_PAGES_TO_FETCH = 500 # 最大获取页数限制
RETRY_TIMES = 3
RETRY_BACKOFF_FACTOR = 0.5
RETRY_STATUS_FORCELIST = [500, 502, 503, 504] # 移除 404，因为找不到可能是正常情况

# --- 通用工具函数 ---
def load_json_config(path):
    """从指定路径加载 JSON 配置文件"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error(f"配置文件未找到: {path}")
        raise
    except json.JSONDecodeError as e:
        logging.error(f"配置文件格式错误: {path} - {e}")
        raise
    except Exception as e:
        logging.error(f"加载配置文件失败: {path} - {e}")
        raise

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

    def __init__(self, api_config_path, update_config_path=None):
        """
        初始化工具实例。

        Args:
            api_config_path (str): API 连接配置文件的路径。
            update_config_path (str, optional): 更新规则配置文件的路径。
                                                如果为 None (例如在撤销操作中)，则不加载。
        """
        self.api_config = self._load_api_config(api_config_path)
        self.update_config = self._load_update_config(update_config_path) if update_config_path else None
        self.session = create_retry_session() # 同步 session 用于 get_all_channels
        # aiohttp session 在需要时创建

    def _load_api_config(self, path):
        """加载并验证 API 配置"""
        logging.debug(f"加载 API 配置: {path}")
        config = load_json_config(path)
        if not all(k in config for k in ['site_url', 'api_token']):
            msg = f"API 配置缺失: 请检查 {path} 中的 site_url, api_token"
            logging.error(msg)
            raise ValueError(msg)
        # 确保 site_url 以 / 结尾，方便拼接
        config['site_url'] = config['site_url'].rstrip('/') + '/'
        logging.info(f"API 配置加载成功: URL={config['site_url']}")
        return config

    def _load_update_config(self, path):
        """加载并验证更新配置"""
        logging.debug(f"加载更新配置: {path}")
        config = load_json_config(path)
        if not all(k in config for k in ['filters', 'updates']):
            msg = f"{path} 中缺少 'filters' 或 'updates' 部分"
            logging.warning(msg) # 允许部分缺失，但记录警告
            # raise ValueError(msg) # 不再强制报错
        if 'filters' in config and not isinstance(config['filters'], dict):
             msg = f"{path} 中的 'filters' 必须是字典类型。"
             logging.error(msg)
             raise ValueError(msg)
        if 'updates' in config and not isinstance(config['updates'], dict):
             msg = f"{path} 中的 'updates' 必须是字典类型。"
             logging.error(msg)
             raise ValueError(msg)
        logging.info(f"更新配置加载成功: 筛选条件={list(config.get('filters', {}).keys())}, 更新项={list(config.get('updates', {}).keys())}")
        return config

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
        应返回渠道字典列表，如果失败则返回 None。
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
            bool: 更新是否成功。
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
            dict or None: 渠道的详细数据字典，如果获取失败则返回 None。
        """
        pass # Needed for save_undo_data

    def filter_channels(self, channel_list):
        """根据加载的更新配置过滤渠道列表"""
        if not self.update_config:
            logging.error("过滤渠道失败：未加载更新配置文件。")
            return []
        if not channel_list:
            logging.warning("输入的渠道列表为空，无法进行过滤。")
            return []

        filters_config = self.update_config.get('filters', {})
        match_mode = filters_config.get("match_mode", "any")

        try:
            self._validate_match_mode(match_mode)
        except ValueError as e:
            logging.error(f"配置错误: {e}")
            return []

        logging.info(f"开始过滤 {len(channel_list)} 个渠道...")
        logging.info(f"筛选条件: 名称={filters_config.get('name_filters', [])}, 分组={filters_config.get('group_filters', [])}, 模型={filters_config.get('model_filters', [])}, 标签={filters_config.get('tag_filters', [])}, 类型={filters_config.get('type_filters', [])}, 模式='{match_mode}'")

        filtered_channels = [
            channel for channel in channel_list
            if self._channel_matches_filters(channel, filters_config)
        ]

        if not filtered_channels:
            logging.warning("根据当前筛选条件，未匹配到任何渠道")
        else:
            logging.info(f"总共匹配到 {len(filtered_channels)} 个渠道")
        return filtered_channels

    def _validate_match_mode(self, match_mode):
        """验证匹配模式是否有效"""
        valid_modes = {"any", "exact", "none", "all"} # 添加 all 模式
        if match_mode not in valid_modes:
            raise ValueError(f"无效的匹配模式: {match_mode}. 有效值为: {valid_modes}")
        logging.debug(f"验证匹配模式成功: {match_mode}")

    def _match_filter(self, value, filter_list, match_mode):
        """根据匹配模式和筛选列表判断值是否匹配 (用于字符串类型字段)"""
        if not filter_list: return True # 没有过滤器则始终匹配
        if value is None: return False # None 值不匹配任何非空过滤器

        value_str = str(value)
        filter_strs = [str(f) for f in filter_list]

        if match_mode == "any":
            return any(f in value_str for f in filter_strs)
        elif match_mode == "exact":
            return value_str in filter_strs # 完全匹配其中一个
        elif match_mode == "none":
            return all(f not in value_str for f in filter_strs)
        # "all" 模式对于单一字符串字段意义不大，除非解释为包含所有子串？
        # 暂时不为字符串实现 "all" 的特殊逻辑
        return False

    def _channel_matches_filters(self, channel, filters_config):
        """判断单个渠道是否符合所有筛选条件"""
        if not isinstance(channel, dict):
            logging.warning(f"跳过无效的渠道数据项 (非字典): {channel}")
            return False

        name_filters = filters_config.get("name_filters", [])
        group_filters = filters_config.get("group_filters", [])
        model_filters = filters_config.get("model_filters", [])
        tag_filters = filters_config.get("tag_filters", [])
        type_filters = filters_config.get("type_filters", []) # 新增类型过滤器
        match_mode = filters_config.get("match_mode", "any") # any 是针对单个过滤器类型内部的匹配

        # all_match_required = match_mode == "all" # 是否要求所有过滤器类型都匹配
        # 暂时简化：只要有一个过滤器类型不匹配，则渠道不匹配
        # TODO: 后续可以实现更复杂的 "all" 逻辑，例如要求至少匹配一个 name AND 一个 group

        channel_name = channel.get('name', '未知名称')
        channel_id = channel.get('id', '未知ID')
        channel_type = channel.get('type')
        logging.debug(f"正在检查渠道: ID={channel_id}, 名称='{channel_name}', 类型={channel_type}")

        # 名称匹配
        if name_filters and not self._match_filter(channel.get("name", ""), name_filters, "any"): # 名称通常用 any 包含匹配
            logging.debug(f"  - 名称不匹配: '{channel.get('name', '')}' vs {name_filters}")
            return False

        # 分组匹配 (假设分组是逗号分隔或列表)
        group_value = channel.get("group", "")
        if group_filters:
            group_list = [g.strip() for g in str(group_value).split(',') if g.strip()]
            if not any(gf in group_list for gf in group_filters): # 分组通常用 any 包含匹配
                 logging.debug(f"  - 分组不匹配: {group_list} vs {group_filters}")
                 return False

        # 模型匹配 (假设模型是逗号分隔或列表)
        models_value = channel.get("models", "")
        if model_filters:
            model_list = [m.strip() for m in str(models_value).split(',') if m.strip()]
            if not any(mf in model_list for mf in model_filters): # 模型通常用 any 包含匹配
                 logging.debug(f"  - 模型不匹配: {model_list} vs {model_filters}")
                 return False

        # 标签匹配 (假设标签是逗号分隔或列表)
        tag_value = channel.get("tag", "")
        if tag_filters:
             tag_list = [t.strip() for t in str(tag_value).split(',') if t.strip()]
             if not any(tf in tag_list for tf in tag_filters): # 标签通常用 any 包含匹配
                  logging.debug(f"  - 标签不匹配: {tag_list} vs {tag_filters}")
                  return False

        # 类型匹配 (精确匹配)
        if type_filters and channel_type not in type_filters:
             logging.debug(f"  - 类型不匹配: {channel_type} vs {type_filters}")
             return False

        logging.debug(f"  >>> 所有条件匹配: ID={channel_id}, 名称='{channel_name}'")
        return True # 所有检查通过

    def _prepare_update_payload(self, original_channel_data):
        """
        比较原始渠道数据和更新配置，准备用于 API 请求的 payload。
        返回 (更新后的数据字典, 更新的字段列表) 或 (None, [])。
        """
        if not self.update_config:
            logging.error("准备更新 payload 失败：未加载更新配置文件。")
            return None, []
        updates_config = self.update_config.get('updates', {})
        if not updates_config:
            logging.warning("更新配置中 'updates' 部分为空，无需准备 payload。")
            return None, []

        # 使用原始数据作为基础，避免丢失未更新的字段
        channel_data_to_update = copy.deepcopy(original_channel_data)
        updated_fields = []
        channel_name = original_channel_data.get('name', f'ID:{original_channel_data.get("id")}')

        for field, config in updates_config.items():
            if config.get("enabled"):
                new_value = config.get("value")
                current_value = original_channel_data.get(field) # 从原始数据获取当前值
                value_changed = False
                processed_value = new_value # 默认使用配置中的值

                # --- 值处理和比较逻辑 (基本同前，但基于 original_channel_data) ---
                if field in ["model_mapping", "status_code_mapping", "setting"]:
                    # 处理 JSON 字符串或字典
                    current_dict = None
                    if isinstance(current_value, str) and current_value.strip():
                        try: current_dict = json.loads(current_value)
                        except json.JSONDecodeError: pass
                    elif isinstance(current_value, dict):
                        current_dict = current_value

                    new_dict = None
                    if isinstance(new_value, str) and new_value.strip():
                         try: new_dict = json.loads(new_value)
                         except json.JSONDecodeError:
                              logging.warning(f"渠道 {channel_name}: 字段 '{field}' 的新值不是有效的 JSON 字符串: {new_value}，将作为普通字符串处理")
                              new_dict = None # 回退到字符串比较
                    elif isinstance(new_value, dict):
                         new_dict = new_value

                    if new_dict is not None: # 如果新值是有效的字典
                        if current_dict != new_dict:
                            value_changed = True
                            processed_value = json.dumps(new_dict) # API 通常需要字符串
                    elif str(current_value) != str(new_value): # 如果新值不是字典，按字符串比较
                         value_changed = True
                         processed_value = str(new_value) # 确保是字符串

                elif field == "models" or field == "group" or field == "tag":
                    # 处理列表或逗号分隔字符串
                    current_list = sorted([item.strip() for item in str(current_value).split(',') if item.strip()])
                    new_list = []
                    if isinstance(new_value, list):
                        new_list = sorted([str(item).strip() for item in new_value if str(item).strip()])
                    elif isinstance(new_value, str):
                        new_list = sorted([item.strip() for item in new_value.split(',') if item.strip()])
                    else:
                        logging.warning(f"渠道 {channel_name}: 字段 '{field}' 的值格式无效 (应为列表或逗号分隔字符串)，跳过更新")
                        continue

                    if current_list != new_list:
                        value_changed = True
                        processed_value = ",".join(new_list) # API 通常需要逗号分隔字符串

                else: # 其他字段（数字、布尔、普通字符串）
                    # 尝试类型转换比较
                    try:
                        current_typed = type(new_value)(current_value) if current_value is not None else None
                        if current_typed != new_value:
                            value_changed = True
                            processed_value = new_value # 使用配置中的原始类型
                    except (ValueError, TypeError, Exception):
                        # 类型转换失败，按字符串比较
                        if str(current_value) != str(new_value):
                            value_changed = True
                            processed_value = new_value

                if value_changed:
                    logging.debug(f"  - {field}: 从 '{current_value}' 更新为 '{processed_value}'")
                    channel_data_to_update[field] = processed_value # 更新副本
                    updated_fields.append(field)

        if not updated_fields:
            return None, []

        # 返回包含原始 ID 和所有更新后字段的字典
        # 注意：API 可能只需要发送 ID 和已更改的字段，这需要在 update_channel_api 中处理
        return channel_data_to_update, updated_fields

    async def run_updates(self, dry_run=False):
        """主执行逻辑，用于批量更新渠道"""
        if not self.update_config:
            logging.error("执行更新失败：未加载更新配置文件。")
            return 2 # 配置错误

        try:
            logging.info(f"开始执行 {self.__class__.__name__} 更新流程...")
            channel_list = self.get_all_channels()
            if channel_list is None:
                logging.error("获取渠道列表失败。")
                return 1
            if not channel_list:
                logging.warning("获取到的渠道列表为空。")
                return 0

            filtered_list = self.filter_channels(channel_list)
            if not filtered_list:
                logging.info("没有需要更新的渠道。")
                return 0

            logging.info(f"准备处理 {len(filtered_list)} 个匹配的渠道...")
            tasks = []
            update_count = 0
            for channel in filtered_list:
                channel_id = channel.get('id')
                channel_name = channel.get('name', f'ID:{channel_id}')
                payload_data, updated_fields = self._prepare_update_payload(channel)

                if payload_data and updated_fields:
                    logging.info(f"渠道 {channel_name} (ID: {channel_id}) 将更新以下字段: {', '.join(updated_fields)}")
                    if dry_run:
                        logging.info(f"[Dry Run] 跳过对渠道 {channel_name} (ID: {channel_id}) 的实际 API 更新调用。")
                        logging.debug(f"[Dry Run] 计划发送的数据片段: { {k: payload_data[k] for k in updated_fields} }")
                    else:
                        # 传递给 API 实现的是包含 ID 和所有更新后值的完整字典
                        tasks.append(self.update_channel_api(payload_data))
                        update_count += 1
                elif payload_data:
                     logging.info(f"渠道 {channel_name} (ID: {channel_id}) 无需更新。")
                # else: payload_data is None, error logged in _prepare_update_payload

            if not tasks and not dry_run:
                logging.info("没有需要实际执行的更新任务。")
                return 0
            elif dry_run:
                 logging.info("Dry Run 完成，未执行实际更新。")
                 return 0

            logging.info(f"开始并发执行 {len(tasks)} 个更新任务...")
            results = await asyncio.gather(*tasks, return_exceptions=True)

            success_count = sum(1 for r in results if isinstance(r, bool) and r)
            fail_count = len(results) - success_count

            logging.info(f"更新任务完成: {success_count} 个成功, {fail_count} 个失败。")

            if fail_count > 0:
                logging.error(f"{fail_count} 个渠道更新失败，请检查之前的错误日志。")
                # 打印具体错误
                for i, result in enumerate(results):
                    if not isinstance(result, bool) or not result:
                         failed_channel_id = filtered_list[i].get('id', '未知ID') # 需要确保 filtered_list 和 tasks 对应
                         logging.error(f"  - 渠道 ID {failed_channel_id} 更新失败: {result}")
                return 1 # 部分失败
            else:
                return 0 # 全部成功

        except Exception as e:
            logging.error(f"{self.__class__.__name__} 执行过程中发生错误: {e}", exc_info=True)
            return 2 # 严重错误