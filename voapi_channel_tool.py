import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json
import logging
import aiohttp
import asyncio
import copy

# 配置日志记录
logging.basicConfig(
    level=logging.INFO, # 设置 INFO 级别可以看到我们新增的日志
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)

# --- 新增：最大获取页数限制 ---
MAX_PAGES_TO_FETCH = 500 # 设置一个合理的上限，例如 500 页

class AppConfig:
    """集中管理所有配置"""
    ONE_API_BASE_URL = None
    ONE_API_TOKEN = None
    ONE_API_USER_ID = None
    FILTERS = {}
    UPDATES = {}

    @classmethod
    def load_configs(cls, api_config_path='connection_config.json', update_config_path='update_config.json'): # 修改默认 API 配置文件名
        """加载 API 配置和更新配置"""
        cls._load_api_config(api_config_path)
        cls._load_update_config(update_config_path)
        logging.info("所有配置加载完成。")

    @classmethod
    def _load_api_config(cls, path):
        """从指定路径加载 API 配置"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                cls.ONE_API_BASE_URL = config.get('site_url', '')
                cls.ONE_API_TOKEN = config.get('api_token', '')
                cls.ONE_API_USER_ID = config.get('user_id', '')
                if not all([cls.ONE_API_BASE_URL, cls.ONE_API_TOKEN, cls.ONE_API_USER_ID]):
                    logging.error(f"API 配置缺失: 请检查 {path} 中的 site_url, api_token, user_id")
                    raise ValueError("API 配置缺失")
                logging.info(f"加载 API 配置成功: BASE_URL={cls.ONE_API_BASE_URL}, USER_ID={cls.ONE_API_USER_ID}")
        except FileNotFoundError:
            logging.error(f"未找到 API 配置文件: {path}")
            raise
        except json.JSONDecodeError as e:
            logging.error(f"{path} 格式错误: {e}")
            raise
        except Exception as e:
            logging.error(f"加载 API 配置文件失败: {e}")
            raise

    @classmethod
    def _load_update_config(cls, path):
        """从指定路径加载更新配置"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                cls.FILTERS = config.get('filters', {})
                cls.UPDATES = config.get('updates', {})
                if not cls.FILTERS or not cls.UPDATES:
                     logging.warning(f"{path} 中缺少 'filters' 或 'updates' 部分，请检查文件结构。")
                # 验证 filters 结构 (示例)
                expected_filter_keys = {'name_filters', 'group_filters', 'model_filters', 'tag_filters', 'type_filters', 'match_mode'}
                provided_filter_keys = set(cls.FILTERS.keys())
                missing_keys = expected_filter_keys - provided_filter_keys
                if missing_keys:
                    logging.warning(f"更新配置文件 {path} 的 'filters' 部分缺少键: {missing_keys}")
                logging.info(f"加载更新配置成功，筛选条件: {cls.FILTERS.keys()}, 更新项: {cls.UPDATES.keys()}")
        except FileNotFoundError:
            logging.error(f"未找到更新配置文件: {path}")
            raise
        except json.JSONDecodeError as e:
            logging.error(f"{path} 格式错误: {e}")
            raise
        except Exception as e:
            logging.error(f"加载更新配置文件失败: {e}")
            raise

# 重试配置 (保持不变)
RETRY_TIMES = 3
RETRY_BACKOFF_FACTOR = 0.5
RETRY_STATUS_FORCELIST = [500, 502, 503, 504, 404]

def create_retry_session():
    session = requests.Session()
    retry_strategy = Retry(
        total=RETRY_TIMES,
        backoff_factor=RETRY_BACKOFF_FACTOR,
        status_forcelist=RETRY_STATUS_FORCELIST,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    logging.debug("创建带有重试机制的 session 成功")
    return session

def validate_match_mode(match_mode):
    """验证匹配模式是否有效"""
    valid_modes = {"any", "exact", "none"}
    if match_mode not in valid_modes:
        raise ValueError(f"无效的匹配模式: {match_mode}. 有效值为: {valid_modes}")
    logging.debug(f"验证匹配模式成功: {match_mode}")

def match_filter(value, filter_list, match_mode):
    """根据匹配模式和筛选列表判断值是否匹配 (用于字符串类型字段)"""
    # 如果值是 None 或空字符串，且过滤器列表非空，则认为不匹配
    if not value and filter_list:
        return False
    # 如果过滤器列表为空，则认为匹配
    if not filter_list:
        return True

    result = (
        any(str(filter_value) in str(value) for filter_value in filter_list) if match_mode == "any" else
        any(str(filter_value) == str(value) for filter_value in filter_list) if match_mode == "exact" else
        all(str(filter_value) not in str(value) for filter_value in filter_list) if match_mode == "none" else False
    )
    # 移除冗余的 debug 日志，避免过多输出
    # logging.debug(f"匹配过滤器: value='{value}', filter_list={filter_list}, match_mode='{match_mode}', result={result}")
    return result

def get_channel_list():
    """获取 One API 中所有渠道的列表"""
    headers = {
        "Authorization": f"Bearer {AppConfig.ONE_API_TOKEN}",
        "New-Api-User": AppConfig.ONE_API_USER_ID,
    }
    session = create_retry_session()
    all_channels = []
    page = 0
    logging.info(f"开始获取渠道列表, 初始页码: {page}, 最大页数限制: {MAX_PAGES_TO_FETCH}") # 添加最大页数日志
    while True:
        # --- 新增：检查是否超过最大页数 ---
        if page >= MAX_PAGES_TO_FETCH:
            logging.warning(f"已达到最大获取页数限制 ({MAX_PAGES_TO_FETCH}), 停止获取更多渠道。可能列表不完整。")
            break
        # --- 结束新增检查 ---

        try:
            base_url = AppConfig.ONE_API_BASE_URL.rstrip('/')
            api_path = "/api/channel/"
            # --- 修改：API 可能需要 p=1 作为起始页 ---
            request_url = f"{base_url}{api_path}?p={page + 1}&page_size=100" # 请求 p=1, p=2 ...
            logging.debug(f"请求 URL: {request_url}")

            response = session.get(
                request_url,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            json_data = response.json()
            if not json_data.get("success", False):
                logging.error(f"获取渠道列表失败: {json_data.get('message', '未知错误')}, 页码参数: {page + 1}")
                # 即使失败也可能需要停止，避免死循环
                break # 或者 return None
            data = json_data.get("data")
            if data is None:
                 logging.error(f"获取渠道列表时 API 返回的 data 为 null, 页码参数: {page + 1}")
                 # data 为 null 通常意味着结束或错误
                 break # 或者 return None

            # --- 修改：从 data 中提取实际的渠道列表 ---
            # 尝试 'records', 'list', 或直接使用 data (如果它本身就是列表)
            channel_records = data.get('records', data if isinstance(data, list) else data.get('list'))

            if channel_records is None:
                 logging.error(f"在 API 响应的 data 字段中未找到 'records' 或 'list'，且 data 本身不是列表, 页码参数: {page + 1}, data 内容: {data}")
                 # 无法解析数据，停止
                 break # 或者 return None

            if not channel_records: # 如果记录列表为空，说明是最后一页
                logging.info(f"获取所有渠道完成, 最后一页参数: {page + 1}, 总记录数: {len(all_channels)}")
                break

            logging.info(f"获取第 {page + 1} 页渠道成功, 记录数: {len(channel_records)}")
            all_channels.extend(channel_records) # 添加实际的记录
            page += 1
        except requests.exceptions.RequestException as e:
            logging.error(f"获取渠道列表失败: {e}, 页码参数: {page + 1}")
            return None # 网络错误，直接返回 None
        except json.JSONDecodeError as e:
            logging.error(f"解析渠道列表响应失败: {e}, 页码参数: {page + 1}, 响应内容: {response.text}")
            return None # JSON 解析错误，返回 None
    logging.info(f"最终获取到 {len(all_channels)} 个渠道记录。") # 添加最终数量日志
    return all_channels

async def update_channel(original_channel_data):
    """异步更新指定渠道的配置 (使用 AppConfig.UPDATES)"""
    if not isinstance(original_channel_data, dict) or "id" not in original_channel_data:
        logging.error(f"无效的 channel_data (缺少 id 或非字典): {original_channel_data}")
        return

    channel_id = original_channel_data.get('id')
    channel_name = original_channel_data.get('name', f'ID:{channel_id}')
    logging.info(f"准备更新渠道: {channel_name} (ID: {channel_id})")

    channel_data_to_update = copy.deepcopy(original_channel_data)
    updated_fields = []
    updates_config = AppConfig.UPDATES # 获取更新配置

    # --- 动态应用更新配置 ---
    for field, config in updates_config.items():
        if config.get("enabled"):
            new_value = config.get("value")
            current_value = channel_data_to_update.get(field)
            value_changed = False
            processed_value = new_value # 默认使用原始值

            # 特殊处理需要序列化为 JSON 的字段
            if field in ["model_mapping", "status_code_mapping", "setting"]:
                try:
                    # 如果当前值是字符串，尝试解析为字典比较；如果目标值是字典，序列化为字符串
                    current_dict = None
                    if isinstance(current_value, str) and current_value.strip(): # 确保非空
                        try:
                            current_dict = json.loads(current_value)
                        except json.JSONDecodeError:
                            logging.debug(f"当前字段 '{field}' 的值不是有效的 JSON 字符串: {current_value}")
                            pass # 如果当前值不是有效的 JSON，则直接比较字符串

                    # 比较字典内容（如果可以解析）或原始值
                    if current_dict is not None and isinstance(new_value, dict):
                         if current_dict != new_value:
                             value_changed = True
                             processed_value = json.dumps(new_value) # API 需要字符串
                    elif isinstance(new_value, dict): # 如果当前值无法解析为字典，但目标是字典
                         processed_value = json.dumps(new_value)
                         # 如果 current_value 是 None 或空字符串，而 new_value 是非空字典，则认为改变
                         if current_value != processed_value and (current_value is None or not str(current_value).strip() or current_value == "{}"):
                             value_changed = True
                         elif current_value != processed_value: # 其他情况正常比较
                             value_changed = True
                    elif current_value != new_value: # 如果目标值不是字典，直接比较
                         value_changed = True
                         # 如果 new_value 不是字符串，尝试转为字符串
                         if not isinstance(new_value, str):
                             processed_value = str(new_value)


                except (TypeError, ValueError) as e:
                    logging.warning(f"渠道 {channel_name}: 字段 '{field}' 的值无法序列化为 JSON ({e})，跳过更新")
                    continue # 跳过此字段
            # 处理模型列表（可以是列表或字符串）
            elif field == "models":
                if isinstance(new_value, list):
                    processed_value = ",".join(map(str, new_value))
                elif isinstance(new_value, str):
                    processed_value = new_value
                else:
                    logging.warning(f"渠道 {channel_name}: 字段 'models' 的值格式无效 (应为列表或字符串)，跳过更新")
                    continue
                if current_value != processed_value:
                    value_changed = True
            # 其他字段直接比较
            else:
                # 尝试将新旧值转为相同类型比较（例如都转为字符串）
                try:
                    # 对数字类型进行特殊处理，避免字符串比较导致误判
                    is_numeric = isinstance(current_value, (int, float)) and isinstance(new_value, (int, float, str))
                    # 对布尔类型也特殊处理 (API 可能返回 0/1 或 true/false)
                    is_bool_like = isinstance(current_value, (int, bool)) and isinstance(new_value, (int, bool, str)) and str(new_value).lower() in ['0', '1', 'true', 'false']

                    if is_numeric:
                        try:
                            # 比较浮点数时考虑精度问题，但这里简单比较
                            if float(current_value) != float(new_value):
                                value_changed = True
                                # 尝试保持原始类型
                                if isinstance(current_value, int):
                                    processed_value = int(float(new_value))
                                else:
                                    processed_value = float(new_value)
                        except (ValueError, TypeError): # 如果转换失败，回退到字符串比较
                             if str(current_value) != str(new_value):
                                 value_changed = True
                                 processed_value = new_value
                    elif is_bool_like:
                         current_bool = bool(int(current_value)) if isinstance(current_value, int) else bool(current_value)
                         new_bool_str = str(new_value).lower()
                         new_bool = new_bool_str == 'true' or new_bool_str == '1'
                         if current_bool != new_bool:
                             value_changed = True
                             # API 可能期望 int (0/1)
                             processed_value = 1 if new_bool else 0
                    elif str(current_value) != str(new_value): # 非数字/布尔类型进行字符串比较
                        value_changed = True
                        processed_value = new_value

                except Exception: # 兜底比较原始值
                     if current_value != new_value:
                         value_changed = True
                         processed_value = new_value


            if value_changed:
                logging.info(f"  - {field}: 从 '{current_value}' 更新为 '{processed_value}'")
                channel_data_to_update[field] = processed_value
                updated_fields.append(field)

    # 如果没有任何字段需要更新，则跳过 API 调用
    if not updated_fields:
        logging.info(f"渠道 {channel_name} (ID: {channel_id}) 无需更新。")
        return

    logging.info(f"渠道 {channel_name} (ID: {channel_id}) 将更新以下字段: {', '.join(updated_fields)}")

    headers = {
        "Authorization": f"Bearer {AppConfig.ONE_API_TOKEN}",
        "Content-Type": "application/json",
        "New-Api-User": AppConfig.ONE_API_USER_ID,
    }

    try:
        logging.info(f"发送 PUT 请求更新渠道: {channel_name}")
        base_url = AppConfig.ONE_API_BASE_URL.rstrip('/')
        api_path = "/api/channel/"
        request_url = f"{base_url}{api_path}"
        logging.debug(f"请求 URL: {request_url}")
        # 确保发送的数据是 API 期望的格式，可能需要移除一些本地字段
        # 例如，API 可能不接受 'created_time', 'test_time' 等字段
        fields_to_send = {k: v for k, v in channel_data_to_update.items() if k in [
            'id', 'type', 'key', 'open_ai_organization', 'test_model', 'status',
            'name', 'weight', 'base_url', 'other', 'balance', 'models', 'group',
            'model_mapping', 'status_code_mapping', 'priority', 'auto_ban',
            'other_info', 'tag', 'setting'
            # 根据实际 API 文档调整需要发送的字段
        ]}
        logging.debug(f"请求 Body: {json.dumps(fields_to_send, indent=2)}")

        async with aiohttp.ClientSession() as session:
            async with session.put(
                request_url,
                headers=headers,
                json=fields_to_send, # 发送清理后的数据
                timeout=30
            ) as response:
                response_text = await response.text()
                if 200 <= response.status < 300:
                    logging.info(f"渠道 {channel_name} 更新成功, 响应状态: {response.status}")
                    try:
                        response_data = json.loads(response_text)
                        if response_data.get("success"):
                             logging.debug(f"服务器确认成功: {response_data.get('message', '')}")
                        else:
                            logging.warning(f"更新请求成功 (状态码 {response.status}) 但响应 success 字段为 false 或缺失: {response_text}")
                    except json.JSONDecodeError:
                        logging.warning(f"更新请求成功 (状态码 {response.status}) 但无法解析 JSON 响应: {response_text}")
                else:
                    logging.error(f"更新渠道 {channel_name} 失败: 状态码 {response.status}, 响应: {response_text}")
                    try:
                        response.raise_for_status()
                    except aiohttp.ClientResponseError as e:
                         logging.error(f"  详细错误信息: {e.message}")

    except aiohttp.ClientResponseError as e:
        # 检查 response 是否已定义
        resp_text = await e.response.text() if e.response else '无响应'
        if e.status >= 300:
             logging.error(f"更新渠道 {channel_name} 失败 (ClientResponseError): 状态码 {e.status}, 原因 {e.message}, 响应: {resp_text}")
    except aiohttp.ClientError as e:
        logging.error(f"更新渠道 {channel_name} 时发生客户端错误: {e}")
    except Exception as e:
        logging.error(f"更新渠道 {channel_name} 时发生意外错误: {e}", exc_info=True)

def filter_channels(channel_list):
    """根据 AppConfig.FILTERS 中的配置过滤渠道"""
    filters_config = AppConfig.FILTERS
    name_filters = filters_config.get("name_filters", [])
    group_filters = filters_config.get("group_filters", [])
    model_filters = filters_config.get("model_filters", [])
    tag_filters = filters_config.get("tag_filters", [])
    type_filters = filters_config.get("type_filters", []) # 新增：获取类型过滤器
    match_mode = filters_config.get("match_mode", "any") # 默认为 any

    try:
        validate_match_mode(match_mode) # 在开始过滤前验证一次
    except ValueError as e:
        logging.error(f"配置错误: {e}")
        return [] # 返回空列表表示无法过滤

    filtered_channels = []
    if not channel_list:
        logging.warning("输入的渠道列表为空，无法进行过滤")
        return filtered_channels

    logging.info(f"开始过滤 {len(channel_list)} 个渠道...")
    # 新增：在日志中显示 type_filters
    logging.info(f"筛选条件: 名称={name_filters}, 分组={group_filters}, 模型={model_filters}, 标签={tag_filters}, 类型={type_filters}, 模式='{match_mode}'")

    for channel in channel_list:
        # --- 修改：增加对 channel 是否为字典的检查 ---
        if not isinstance(channel, dict):
            logging.warning(f"跳过无效的渠道数据项 (非字典): {channel}")
            continue

        channel_name = channel.get('name', '未知名称')
        channel_id = channel.get('id', '未知ID')
        channel_type = channel.get('type') # 获取渠道类型
        # --- 新增：明确记录正在检查的渠道及其类型 ---
        logging.info(f"正在检查渠道: ID={channel_id}, 名称='{channel_name}', 类型={channel_type}")

        # --- 执行匹配 ---
        name_matched = match_filter(channel.get("name", ""), name_filters, match_mode) if name_filters else True

        group_value = channel.get("group", "")
        if group_filters:
             group_list = [g.strip() for g in group_value.split(',') if g.strip()] # 处理逗号分隔并去空
             if match_mode == "any":
                 group_matched = any(gf in group_list for gf in group_filters)
             elif match_mode == "exact":
                 # 完全匹配要求分组列表完全一致 (顺序和内容)
                 group_matched = sorted(group_list) == sorted(group_filters) # 忽略顺序比较
             elif match_mode == "none":
                 group_matched = all(gf not in group_list for gf in group_filters)
             else: group_matched = False
             # logging.debug(f"  分组匹配 ('{group_value}' vs {group_filters}, mode='{match_mode}'): {group_matched}")
        else:
             group_matched = True

        models_value = channel.get("models", "")
        if model_filters:
             model_list = [m.strip() for m in models_value.split(',') if m.strip()]
             if match_mode == "any":
                 model_matched = any(mf in model_list for mf in model_filters)
             elif match_mode == "exact":
                 model_matched = sorted(model_list) == sorted(model_filters)
             elif match_mode == "none":
                 model_matched = all(mf not in model_list for mf in model_filters)
             else: model_matched = False
             # logging.debug(f"  模型匹配 ('{models_value}' vs {model_filters}, mode='{match_mode}'): {model_matched}")
        else:
             model_matched = True

        tag_matched = match_filter(channel.get("tag", ""), tag_filters, match_mode) if tag_filters else True

        # --- 新增：类型匹配 ---
        # 类型通常是精确匹配，检查渠道类型是否在 type_filters 列表中
        type_matched = (channel_type in type_filters) if type_filters else True
        # --- 新增：明确记录每个条件的匹配结果 ---
        logging.info(f"  匹配结果: 名称={name_matched}, 分组={group_matched}, 模型={model_matched}, 标签={tag_matched}, 类型={type_matched} (目标类型: {type_filters if type_filters else '无'})")


        # --- 修改：将 type_matched 加入判断条件 ---
        if name_matched and group_matched and model_matched and tag_matched and type_matched:
            logging.info(f"  >>> 匹配成功: ID={channel_id}, 名称='{channel_name}'")
            filtered_channels.append(channel)
        else:
             logging.info(f"  --- 未匹配: ID={channel_id}, 名称='{channel_name}'")

    if not filtered_channels:
        logging.warning("根据当前筛选条件，未匹配到任何渠道")
    else:
        logging.info(f"总共匹配到 {len(filtered_channels)} 个渠道")
    return filtered_channels


async def main():
    """主函数"""
    try:
        AppConfig.load_configs() # 加载所有配置
    except Exception as e:
        logging.critical(f"无法加载配置，程序终止: {e}")
        return

    try:
        logging.info("开始执行主程序")
        channel_list = get_channel_list()
        if channel_list is None:
            logging.error("获取渠道列表失败，程序终止")
            return
        if not channel_list:
            logging.warning("获取到的渠道列表为空，程序结束")
            return

        logging.info(f"成功获取 {len(channel_list)} 个渠道，开始过滤")
        # filter_channels 现在直接使用 AppConfig.FILTERS
        filtered_channels = filter_channels(channel_list)

        if not filtered_channels:
            logging.warning("过滤后无渠道需要更新，程序结束")
            return

        logging.info(f"准备更新 {len(filtered_channels)} 个渠道...")
        tasks = []
        for channel in filtered_channels:
             if isinstance(channel, dict) and "id" in channel:
                logging.info(f"将更新渠道: {channel.get('name')} (ID: {channel.get('id')})")
                # update_channel 现在直接使用 AppConfig.UPDATES
                tasks.append(update_channel(channel))
             else:
                 logging.warning(f"跳过无效或缺少ID的渠道数据: {channel}")

        if tasks:
            logging.info(f"开始并发更新 {len(tasks)} 个渠道...")
            await asyncio.gather(*tasks)
            logging.info("所有选定渠道的更新任务已尝试执行")
        else:
            if filtered_channels:
                 logging.error("已匹配到渠道，但未能创建任何更新任务，请检查渠道数据格式。")
            else:
                 logging.info("没有符合条件的渠道需要更新")

    except ValueError as e: # 主要捕获 validate_match_mode 的错误
        logging.error(f"配置或验证错误: {e}")
    except Exception as e:
        logging.exception(f"主程序执行过程中发生未捕获的错误")
    finally:
        logging.info("主程序执行结束")

if __name__ == "__main__":
    # Windows asyncio policy (保持不变)
    # asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())