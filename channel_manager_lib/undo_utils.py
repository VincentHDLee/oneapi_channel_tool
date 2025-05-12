# -*- coding: utf-8 -*-
"""
封装与撤销操作相关的逻辑。
"""
import asyncio
import copy
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal # 用于类型提示

# 从项目模块导入 (使用包内绝对导入)
from channel_manager_lib.config_utils import UNDO_DIR, UPDATE_CONFIG_BACKUP_DIR, load_yaml_config # 假设 load_yaml_config 在 config_utils
# oneapi_tool_utils 位于包外，保持不变
from oneapi_tool_utils.channel_tool_base import ChannelToolBase
from oneapi_tool_utils.newapi_channel_tool import NewApiChannelTool
from oneapi_tool_utils.voapi_channel_tool import VoApiChannelTool

# 类型提示，避免循环导入问题
if TYPE_CHECKING:
    from oneapi_tool_utils.channel_tool_base import ChannelToolBase # Keep this for type hinting


from channel_manager_lib.config_utils import load_script_config # 导入用于获取默认值的函数

def _get_tool_instance(api_type: str, api_config_path: str | Path, update_config_path: str | Path | None = None, script_config: dict | None = None) -> 'ChannelToolBase | None':
    """
    根据 api_type 获取相应的工具实例。
    这是一个辅助函数，主要供撤销逻辑和 cli_handler 内部使用。
    其他模块（如 single_site_handler）可能需要自己的实例化逻辑。

    Args:
        api_type (str): API 类型 ('newapi' 或 'voapi').
        api_config_path (str | Path): 连接配置文件的路径。
        update_config_path (str | Path | None): 更新配置文件的路径 (可选).
        script_config (dict | None): 加载后的脚本通用配置字典 (可选)。

    Returns:
        ChannelToolBase | None: 对应的工具实例，或在失败时返回 None。
    """
    try:
        # 确保路径是 Path 对象
        api_config_path = Path(api_config_path)
        if update_config_path:
            update_config_path = Path(update_config_path)

        # 如果未提供 script_config，加载默认值
        if script_config is None:
            script_config = load_script_config()

        if api_type == "newapi":
            # 将 script_config 传递给构造函数
            return NewApiChannelTool(api_config_path, update_config_path, script_config=script_config)
        elif api_type == "voapi":
            # 将 script_config 传递给构造函数
            return VoApiChannelTool(api_config_path, update_config_path, script_config=script_config)
        else:
            logging.error(f"未知的 API 类型: {api_type}")
            return None
    except ValueError as e: # 配置加载错误 (假设 ChannelTool 初始化时可能抛出)
        logging.error(f"为 API 类型 '{api_type}' 加载配置 '{api_config_path}' 时出错: {e}")
        return None
    except FileNotFoundError as e:
        logging.error(f"配置文件未找到: {e}")
        return None
    except Exception as e:
        logging.error(f"创建 API 类型 '{api_type}' 的工具实例时发生意外错误: {e}", exc_info=True)
        return None

async def save_undo_data(api_type: str, api_config_path: str | Path, update_config_path: str | Path) -> Path | None:
    """
    获取当前匹配渠道的状态并保存以供撤销。
    应在执行更新前调用。

    Args:
        api_type (str): API 类型 ('newapi' 或 'voapi').
        api_config_path (str | Path): 连接配置文件的路径。
        update_config_path (str | Path): 更新配置文件的路径。

    Returns:
        Path | None: 保存的 undo 文件路径 (Path 对象)，或在失败时返回 None。
    """
    logging.info("开始保存撤销数据...")
    tool_instance = _get_tool_instance(api_type, api_config_path, update_config_path)
    if not tool_instance:
        logging.error("无法获取工具实例，无法保存撤销数据。")
        return None

    # 1. 获取所有渠道
    # get_all_channels 现在返回 (list | None, str)
    all_channels, get_list_message = await tool_instance.get_all_channels() # 之前错误地认为是同步的
    if all_channels is None:
        logging.error(f"获取所有渠道失败: {get_list_message}，无法保存撤销数据。")
        return None
    if not all_channels:
        logging.warning(f"渠道列表为空 ({get_list_message})，无需保存撤销数据。")
        return None

    # 2. 加载更新配置以获取筛选条件
    try:
        with open(update_config_path, 'r', encoding='utf-8') as f:
            # 使用 safe_load 避免执行任意代码
            from yaml import safe_load
            update_config = safe_load(f)
        if not update_config:
            raise ValueError("更新配置文件为空或无效")
        filters_config = update_config.get('filters')
        logging.debug(f"[Undo] 从 {update_config_path.name} 加载筛选条件: {filters_config}")
    except Exception as e:
        logging.error(f"[Undo] 加载或解析更新配置文件 '{update_config_path.name}' 失败: {e}，无法准确过滤渠道以保存撤销数据。")
        # 可以选择返回 None 中断，或者继续但不保证撤销数据的准确性
        # 这里选择中断以避免潜在问题
        return None

    # 3. 使用加载的筛选条件过滤渠道
    filtered_channels = tool_instance.filter_channels(all_channels, filters_config)
    if not filtered_channels:
        logging.info("根据更新配置的筛选条件，没有匹配的渠道，无需保存撤销数据。")
        return None

    # 4. 获取这些过滤后渠道的当前详细状态 (带并发和间隔控制)
    channel_ids_to_fetch = [c.get('id') for c in filtered_channels if c.get('id')]
    if not channel_ids_to_fetch:
        logging.warning("过滤后的渠道缺少 ID，无法获取详细信息以保存撤销数据。")
        return None


    # 从 script_config 获取并发和间隔设置
    script_cfg = tool_instance.script_config # 实例应该已经有 script_config
    max_concurrent = script_cfg.get('api_settings', {}).get('max_concurrent_requests', 1) # 默认1防止出错
    request_interval_ms = script_cfg.get('api_settings', {}).get('request_interval_ms', 0)
    interval_seconds = request_interval_ms / 1000.0 if request_interval_ms > 0 else 0

    semaphore = asyncio.Semaphore(max_concurrent)
    original_channels_data = []
    fetch_errors = 0

    logging.info(f"[Undo] 开始逐个获取 {len(channel_ids_to_fetch)} 个渠道的详细状态 (并发: {max_concurrent}, 间隔: {interval_seconds:.3f}s)...")
    for idx, channel_id in enumerate(channel_ids_to_fetch):
        logging.info(f"[Undo] 处理渠道 {idx+1}/{len(channel_ids_to_fetch)}: ID {channel_id}")
        async with semaphore:
            if interval_seconds > 0:
                # 此处 debug 日志可能因 INFO 级别而不显示，但 sleep 会执行
                logging.debug(f"[Undo] 等待 {interval_seconds:.3f} 秒后获取详情 (ID: {channel_id})")
                await asyncio.sleep(interval_seconds)
            
            logging.info(f"[Undo] 正在获取渠道 ID: {channel_id} 的详细信息...")
            try:
                details, message = await tool_instance.get_channel_details(channel_id)
                if isinstance(details, dict):
                    logging.info(f"[Undo] 成功获取渠道 ID: {channel_id} 的状态。原始消息: {message}")
                    original_channels_data.append(details)
                else:
                    logging.error(f"[Undo] 获取渠道 ID: {channel_id} 的原始状态失败: {message}")
                    fetch_errors += 1
            except Exception as e:
                 logging.error(f"[Undo] 获取渠道 ID: {channel_id} 的原始状态时发生异常: {e}", exc_info=True)
                 fetch_errors += 1
    
    logging.info(f"[Undo] 所有渠道详细状态获取尝试完毕。成功: {len(original_channels_data)}, 失败: {fetch_errors}")

    if fetch_errors > 0:
         logging.warning(f"[Undo] {fetch_errors} 个渠道的原始状态获取失败，这些渠道将无法通过此文件撤销。")

    if not original_channels_data:
        logging.error("未能成功获取任何匹配渠道的原始状态，无法保存撤销数据。")
        return None

    # 4. 保存到文件
    # 使用已在顶部导入的 UNDO_DIR
    undo_dir = UNDO_DIR
    try:
        undo_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logging.error(f"创建撤销数据目录 '{undo_dir}' 失败: {e}")
        return None

    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S%f")[:-3]
    # 确保 api_config_path 是 Path 对象以使用 .stem
    config_name = Path(api_config_path).stem
    undo_filename = f"undo_{api_type}_{config_name}_{timestamp}.json"
    undo_file_path = undo_dir / undo_filename

    try:
        with open(undo_file_path, 'w', encoding='utf-8') as f:
            json.dump(original_channels_data, f, indent=2, ensure_ascii=False)
        logging.info(f"成功将 {len(original_channels_data)} 个渠道的原始状态保存到: {undo_file_path}")
        return undo_file_path # 返回实际保存的文件路径
    except Exception as e:
        logging.error(f"保存撤销文件 '{undo_file_path}' 失败: {e}")
        return None

async def perform_undo(api_type: str, api_config_path: str | Path, undo_file_path: str | Path, auto_confirm: bool = False) -> int:
    """
    执行撤销操作。
    读取 undo 文件，并将其中记录的渠道恢复到原始状态。

    Args:
        api_type (str): API 类型 ('newapi' 或 'voapi').
        api_config_path (str | Path): 连接配置文件的路径。
        undo_file_path (str | Path): 要使用的撤销文件的路径。
        auto_confirm (bool): 是否跳过用户确认。

    Returns:
        int: 退出码 (0 表示成功, 1 表示失败)。
    """
    logging.info(f"开始执行撤销操作，使用文件: {undo_file_path}")
    undo_file_path = Path(undo_file_path) # 确保是 Path 对象

    # 1. 读取撤销文件
    try:
        with open(undo_file_path, 'r', encoding='utf-8') as f:
            original_channels_data = json.load(f)
        if not isinstance(original_channels_data, list) or not original_channels_data:
            logging.error(f"撤销文件 '{undo_file_path}' 内容无效或为空列表。")
            print(f"错误：撤销文件 '{undo_file_path.name}' 内容无效或为空。")
            return 1
        logging.info(f"从撤销文件加载了 {len(original_channels_data)} 个渠道的原始数据。")
    except FileNotFoundError:
        logging.error(f"撤销文件未找到: {undo_file_path}")
        print(f"错误：撤销文件 '{undo_file_path.name}' 未找到。")
        return 1
    except json.JSONDecodeError as e:
        logging.error(f"解析撤销文件 '{undo_file_path}' 失败: {e}")
        print(f"错误：无法解析撤销文件 '{undo_file_path.name}' ({e})。")
        return 1
    except Exception as e:
        logging.error(f"读取撤销文件 '{undo_file_path}' 时发生意外错误: {e}", exc_info=True)
        print(f"错误：读取撤销文件时发生意外错误 ({e})。")
        return 1

    # 2. 获取工具实例
    tool_instance = _get_tool_instance(api_type, api_config_path) # 撤销时不需要 update_config
    if not tool_instance:
        logging.error("无法获取工具实例，无法执行撤销。")
        print("错误：无法初始化 API 工具，无法执行撤销。")
        return 1

    # 3. 准备更新任务
    update_tasks = []
    channels_to_restore = []
    for original_data in original_channels_data:
        channel_id = original_data.get('id')
        if not channel_id:
            logging.warning(f"撤销数据中找到一条缺少 ID 的记录，跳过: {original_data.get('name', '<无名称>')}")
            continue

        # 准备用于更新的数据 payload (通常是原始数据的副本)
        # 注意：API 可能不允许直接用获取到的数据去更新，特别是包含只读字段时
        # ChannelToolBase 的 update_channel 应处理好 payload
        payload = copy.deepcopy(original_data)
        # 确保移除或处理掉 API 不接受的字段 (如果 ChannelToolBase 不处理)
        # 例如: payload.pop('created_time', None) # 假设 created_time 是只读的

        channels_to_restore.append(f"ID: {channel_id}, 名称: {original_data.get('name', '<无名称>')}")
        # update_channel_api 期望接收包含 ID 的完整 payload
        update_tasks.append(tool_instance.update_channel_api(payload))

    if not update_tasks:
        logging.warning("没有有效的渠道数据可供撤销。")
        print("警告：撤销文件中没有包含有效 ID 的渠道数据。")
        return 0 # 没有任务执行，不算失败

    # 4. 用户确认
    print("\n将执行以下渠道的撤销操作 (恢复到之前保存的状态):")
    for desc in channels_to_restore:
        print(f"  - {desc}")

    if not auto_confirm:
        try:
            confirm = input("确认要执行撤销吗？ (y/n): ").lower()
            if confirm != 'y':
                logging.info("用户取消了撤销操作。")
                print("撤销操作已取消。")
                return 0
        except EOFError:
            print("\n操作已取消。")
            return 0

    # 5. 执行撤销 (调用更新 API)
    logging.info(f"开始执行 {len(update_tasks)} 个渠道的撤销更新...")
    results = await asyncio.gather(*update_tasks, return_exceptions=True)

    # 6. 处理结果
    success_count = 0
    fail_count = 0
    for i, result in enumerate(results):
        channel_desc = channels_to_restore[i]
        # update_channel 返回 (bool, str)
        if isinstance(result, tuple) and len(result) == 2:
            success, message = result
            if success:
                success_count += 1
                logging.info(f"成功撤销 {channel_desc}: {message}")
            else:
                fail_count += 1
                logging.error(f"撤销失败 {channel_desc}: {message}")
        elif isinstance(result, Exception):
            fail_count += 1
            logging.error(f"撤销时发生异常 {channel_desc}: {result}", exc_info=True)
        else:
            fail_count += 1
            logging.error(f"撤销时返回未知结果 {channel_desc}: {repr(result)}")

    print("\n--- 撤销操作完成 ---")
    print(f"成功恢复: {success_count} 个渠道")
    print(f"失败: {fail_count} 个渠道")

    if fail_count > 0:
        print("部分渠道撤销失败，请检查日志获取详细信息。")
        return 1 # 返回失败码

    # 7. (可选) 成功后删除或重命名撤销文件
    try:
        # 考虑重命名而不是直接删除，例如加上 .undone 后缀
        # done_path = undo_file_path.with_suffix(undo_file_path.suffix + '.undone')
        # undo_file_path.rename(done_path)
        # logging.info(f"已将撤销文件标记为完成: {done_path}")

        # 或者直接删除 (风险较高，如果需要再次撤销)
        # undo_file_path.unlink()
        # logging.info(f"已删除使用过的撤销文件: {undo_file_path}")
        pass # 暂时不自动删除或重命名
    except Exception as e:
         logging.warning(f"处理已完成的撤销文件 '{undo_file_path}' 时出错: {e}")

    return 0 # 全部成功

def find_latest_undo_file() -> Path | None:
    """
    查找 undo_data 目录下最新的撤销文件 (按修改时间)。

    Returns:
        Path | None: 最新的撤销文件的路径，如果找不到则返回 None。
    """
    # 使用已在顶部导入的 UNDO_DIR
    undo_dir = UNDO_DIR
    if not undo_dir.is_dir():
        logging.debug(f"撤销目录 '{undo_dir}' 不存在。")
        return None
    try:
        undo_files = list(undo_dir.glob("undo_*.json"))
        if not undo_files:
            logging.debug(f"在 '{undo_dir}' 中未找到 undo_*.json 文件。")
            return None
        # 按修改时间排序，最新的在最后
        undo_files.sort(key=lambda f: f.stat().st_mtime)
        latest_file = undo_files[-1]
        logging.debug(f"找到最新的撤销文件: {latest_file}")
        return latest_file
    except Exception as e:
        logging.error(f"查找最新撤销文件时出错: {e}", exc_info=True)
        return None

def find_latest_undo_file_for(config_name: str, api_type: str) -> Path | None:
    """
    查找指定连接配置名称和 API 类型对应的最新撤销文件 (按修改时间)。

    Args:
        config_name (str): 连接配置文件的名称 (不含扩展名, e.g., "Astaur.cn").
        api_type (str): API 类型 ('newapi' 或 'voapi').

    Returns:
        Path | None: 对应的最新撤销文件的路径，如果找不到则返回 None。
    """
    # 使用已在顶部导入的 UNDO_DIR
    undo_dir = UNDO_DIR
    if not undo_dir.is_dir():
        logging.debug(f"撤销目录 '{undo_dir}' 不存在。")
        return None

    pattern = f"undo_{api_type}_{config_name}_*.json"
    try:
        undo_files = list(undo_dir.glob(pattern))

        if not undo_files:
            logging.debug(f"在 '{undo_dir}' 中未找到匹配 '{pattern}' 的撤销文件。")
            return None

        # 按修改时间排序，最新的在最后
        undo_files.sort(key=lambda f: f.stat().st_mtime)
        latest_file = undo_files[-1]
        logging.debug(f"找到针对 '{config_name}' ({api_type}) 的最新撤销文件: {latest_file}")
        return latest_file
    except Exception as e:
        logging.error(f"查找针对 '{config_name}' ({api_type}) 的最新撤销文件时出错: {e}", exc_info=True)
        return None

def get_undo_summary(undo_file_path: Path) -> str | None:
    """
    尝试根据撤销文件查找对应的备份更新配置，并生成上次更新内容的摘要。

    Args:
        undo_file_path (Path): 撤销文件的路径对象。

    Returns:
        str | None: 上次更新的摘要信息字符串，或在无法生成时返回 None。
    """
    if not undo_file_path or not undo_file_path.is_file():
        logging.debug(f"提供的撤销文件路径无效或文件不存在: {undo_file_path}")
        return None

    # 1. 从撤销文件名解析时间戳
    try:
        # 文件名格式: undo_<api_type>_<config_name>_YYYY-MM-DD-HHMMSSfff.json
        filename_parts = undo_file_path.stem.split('_')
        if len(filename_parts) < 4:
             logging.warning(f"无法从撤销文件名解析时间戳: {undo_file_path.name}")
             return None
        # 时间戳部分是最后一部分
        timestamp_str = filename_parts[-1]
        # 尝试将字符串转换为 datetime 对象以验证格式并用于比较
        undo_timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d-%H%M%S%f")
        logging.debug(f"从撤销文件 {undo_file_path.name} 解析到时间戳: {undo_timestamp}")
    except (ValueError, IndexError) as e:
        logging.warning(f"从撤销文件名解析时间戳时出错: {undo_file_path.name} - {e}")
        return None

    # 2. 查找对应的备份配置文件
    # 使用已在顶部导入的 UPDATE_CONFIG_BACKUP_DIR 和 load_yaml_config
    backup_dir = UPDATE_CONFIG_BACKUP_DIR
    if not backup_dir.is_dir():
        logging.warning(f"备份目录 '{backup_dir}' 不存在，无法查找更新配置。")
        return None

    candidate_backups = []
    try:
        for backup_file in backup_dir.glob("update_config.*.yaml"):
            try:
                # 备份文件名格式: update_config.YYYY-MM-DD-HHMMSSfff.yaml
                backup_ts_str = backup_file.stem.split('.')[-1]
                backup_timestamp = datetime.strptime(backup_ts_str, "%Y-%m-%d-%H%M%S%f")
                # 我们需要找到时间戳 <= undo_timestamp 的最新备份
                if backup_timestamp <= undo_timestamp:
                    candidate_backups.append((backup_timestamp, backup_file))
            except (ValueError, IndexError) as e:
                logging.debug(f"无法从备份文件名解析时间戳: {backup_file.name} - {e}")
                continue # 跳过无法解析的文件
    except Exception as e:
        logging.error(f"查找备份配置文件时出错: {e}", exc_info=True)
        return None


    if not candidate_backups:
        logging.warning(f"未找到时间戳早于或等于 {undo_timestamp} 的备份更新配置文件。")
        return None

    # 找到时间戳最接近（最大但小于等于）的备份文件
    candidate_backups.sort(key=lambda item: item[0], reverse=True)
    corresponding_backup_path = candidate_backups[0][1]
    logging.debug(f"找到对应的备份配置文件: {corresponding_backup_path.name}")

    # 3. 读取备份配置并生成摘要
    try:
        # 假设 load_yaml_config 返回字典或 None
        backup_config = load_yaml_config(corresponding_backup_path)
        if not backup_config or 'updates' not in backup_config:
            logging.warning(f"备份配置文件 '{corresponding_backup_path.name}' 无效或缺少 'updates' 部分。")
            return None

        update_details = []
        for field, config in backup_config.get('updates', {}).items():
            if isinstance(config, dict) and config.get("enabled") is True:
                # 尝试获取 value，如果不存在或为 None，则显示特殊标记
                value = config.get("value", "<未设置>")
                # 对于字典或列表，使用更紧凑的表示形式
                if isinstance(value, (dict, list)):
                    value_str = json.dumps(value, ensure_ascii=False) # 使用 json.dumps 保证格式
                else:
                    value_str = repr(value) # 使用 repr 保留字符串引号等
                update_details.append(f"{field} = {value_str}")

        if not update_details:
            return "上次操作未启用任何更新字段。"
        else:
            # 将多个设置用逗号和空格连接
            return f"上次操作设置了: {', '.join(update_details)}"

    except Exception as e:
        logging.error(f"读取或解析备份配置文件 '{corresponding_backup_path.name}' 时出错: {e}", exc_info=True)
        return None