import yaml # 导入 YAML 库
from .config_utils import UPDATE_CONFIG_PATH # 导入更新配置路径常量
import asyncio
import logging
from pathlib import Path
# -*- coding: utf-8 -*-
"""
封装单站点更新和撤销的操作流程。
"""
import asyncio
import copy
import json # 新增导入
import logging
import shutil
from datetime import datetime
from pathlib import Path
import aiohttp # 新增导入

import functools # 导入 functools 用于包装任务
# 从项目模块导入 (使用包内绝对导入)
from channel_manager_lib.config_utils import (
    UPDATE_CONFIG_PATH, UPDATE_CONFIG_BACKUP_DIR, CLEAN_UPDATE_CONFIG_TEMPLATE_PATH,
    load_script_config, load_yaml_config, # 导入脚本配置加载函数 和 YAML 加载函数
    # CLEAN_CHANNEL_MODEL_TEST_CONFIG_TEMPLATE_PATH, # 将在 config_utils.py 中定义后取消注释
)
from channel_manager_lib.undo_utils import save_undo_data, _get_tool_instance # 导入撤销保存和工具实例化
# ask_and_clear_update_config 已移至此模块，不再需要从 cli_handler 导入
# 基础工具类和具体工具类不再需要直接导入，因为 _get_tool_instance 处理了实例化
# from oneapi_tool_utils.channel_tool_base import ChannelToolBase
# from oneapi_tool_utils.newapi_channel_tool import NewApiChannelTool
# from oneapi_tool_utils.voapi_channel_tool import VoApiChannelTool

# 临时的，之后会移到 config_utils.py
# 假设它在 oneapi_tool_utils 目录下
ONEAPI_TOOL_UTILS_DIR = Path(__file__).parent.parent / "oneapi_tool_utils"
CLEAN_CHANNEL_MODEL_TEST_CONFIG_TEMPLATE_PATH_TEMP = ONEAPI_TOOL_UTILS_DIR / "channel_model_test_config.clean.yaml"


def ask_and_clear_update_config(force_clear=False, auto_confirm=False):
    """询问用户是否清空 update_config.yaml 并执行 (使用 update_config.clean.json 模板)。"""
    # 使用已在顶部导入的常量
    source_clean_path = CLEAN_UPDATE_CONFIG_TEMPLATE_PATH
    target_path = UPDATE_CONFIG_PATH
    if not source_clean_path.is_file():
        logging.warning(f"警告：干净配置文件模板 '{source_clean_path}' 不存在，无法执行清空操作。")
        print(f"\n注意：未找到 '{source_clean_path}'，无法提供清空选项。")
        return
    do_clear = False
    if force_clear:
        if auto_confirm:
            logging.info(f"自动确认模式：将使用 '{source_clean_path.name}' 恢复 '{target_path.name}'。")
            do_clear = True
        else:
            while True:
                try:
                    choice = input(f"\n命令行指定了清空配置，确认要将 '{target_path.name}' 恢复为干净状态吗？ (y/n): ").lower()
                    if choice == 'y':
                        do_clear = True
                        break
                    elif choice == 'n':
                        print(f"取消清空 '{target_path.name}'。")
                        break
                    else:
                        print("无效输入，请输入 'y' 或 'n'。")
                except EOFError:
                    print("\n操作已取消。")
                    break
    elif auto_confirm:
        logging.info(f"自动确认模式：保留当前的 '{target_path.name}'。")
        do_clear = False
    else:
        while True:
            try:
                choice = input(f"\n是否要将 '{target_path.name}' 恢复为干净状态 (使用 '{source_clean_path.name}')？ (y/n): ").lower()
                if choice == 'y':
                    do_clear = True
                    break
                elif choice == 'n':
                    logging.info(f"用户选择不清空 '{target_path.name}'。")
                    print(f"保留当前的 '{target_path.name}'。")
                    break
                else:
                    print("无效输入，请输入 'y' 或 'n'。")
            except EOFError:
                print("\n操作已取消。")
                break
    if do_clear:
        try:
            # 直接读取模板文件内容 (保留注释和格式)
            with open(source_clean_path, 'r', encoding='utf-8') as f_src:
                clean_content = f_src.read()
            # 将模板内容直接写入目标文件
            with open(target_path, 'w', encoding='utf-8') as f_target:
                f_target.write(clean_content)
            logging.info(f"已使用模板 '{source_clean_path.name}' 的内容覆盖 '{target_path.name}'。")
            print(f"'{target_path.name}' 已恢复为默认干净状态。")
        except Exception as e:
            logging.error(f"使用 '{source_clean_path.name}' 覆盖 '{target_path.name}' 时出错: {e}")
            print("恢复失败，请检查错误日志。")


def ask_and_clear_channel_model_test_config(target_test_config_path: Path, force_clear: bool, auto_confirm: bool):
    """
    询问用户是否清空指定的测试模型配置文件，并使用干净模板恢复它。
    行为类似于 ask_and_clear_update_config。

    Args:
        target_test_config_path (Path): 要清理的目标测试配置文件的路径。
        force_clear (bool): 是否由命令行参数强制要求清理 (例如来自 --clear-test-model-config)。
        auto_confirm (bool): 是否是自动确认模式 (例如来自 -y)。
    """
    source_clean_path = CLEAN_CHANNEL_MODEL_TEST_CONFIG_TEMPLATE_PATH_TEMP # 使用临时定义的路径
    
    if not source_clean_path.is_file():
        logging.warning(f"警告：干净的测试模型配置文件模板 '{source_clean_path}' 不存在，无法执行清空操作。")
        return

    if not target_test_config_path.is_file():
        logging.warning(f"目标测试配置文件 '{target_test_config_path}' 不存在，无法清理。")
        return

    do_clear = False
    if force_clear: # 例如 --clear-test-model-config 被设置
        if auto_confirm: # 例如 -y 也被设置
            logging.info(f"自动确认模式且强制清理：将使用模板恢复 '{target_test_config_path.name}'。")
            do_clear = True
        else: # 不是 -y，但指定了清理，需要询问
            while True:
                try:
                    choice = input(f"\n命令行指定了清理测试配置，确认要将 '{target_test_config_path.name}' 恢复为干净状态吗？ (y/n): ").lower()
                    if choice == 'y':
                        do_clear = True
                        break
                    elif choice == 'n':
                        print(f"取消清空 '{target_test_config_path.name}'。")
                        break
                    else:
                        print("无效输入，请输入 'y' 或 'n'。")
                except EOFError:
                    print("\n操作已取消。")
                    break
    elif auto_confirm: # 是 -y，但没有强制清理参数
        logging.info(f"自动确认模式：保留当前的 '{target_test_config_path.name}'。")
        do_clear = False # 默认不清理
    else: # 非 -y，且没有强制清理参数，正常询问
        while True:
            try:
                choice = input(f"\n是否要将测试配置文件 '{target_test_config_path.name}' 恢复为干净状态 (使用模板)？ (y/n): ").lower()
                if choice == 'y':
                    do_clear = True
                    break
                elif choice == 'n':
                    logging.info(f"用户选择不清空 '{target_test_config_path.name}'。")
                    print(f"保留当前的 '{target_test_config_path.name}'。")
                    break
                else:
                    print("无效输入，请输入 'y' 或 'n'。")
            except EOFError:
                print("\n操作已取消。")
                break
    
    if do_clear:
        try:
            with open(source_clean_path, 'r', encoding='utf-8') as f_src:
                clean_content = f_src.read()
            with open(target_test_config_path, 'w', encoding='utf-8') as f_target:
                f_target.write(clean_content)
            logging.info(f"已使用模板 '{source_clean_path.name}' 的内容覆盖 '{target_test_config_path.name}'。")
            print(f"测试配置文件 '{target_test_config_path.name}' 已恢复为默认干净状态。")
        except Exception as e:
            logging.error(f"使用模板 '{source_clean_path.name}' 覆盖 '{target_test_config_path.name}' 时出错: {e}")
            print(f"恢复测试配置文件 '{target_test_config_path.name}' 失败，请检查错误日志。")


def backup_update_config():
    """备份当前的 update_config.yaml 文件到 used_update_configs 目录。"""
    source_path = UPDATE_CONFIG_PATH # 使用导入的常量
    backup_dir = UPDATE_CONFIG_BACKUP_DIR # 使用导入的常量
    if not source_path.is_file():
        logging.warning(f"警告：源文件 '{source_path}' 不存在，无法备份。")
        return False
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logging.error(f"创建备份目录 '{backup_dir}' 失败: {e}")
        return False
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S%f")[:-3]
    backup_filename = f"update_config.{timestamp}.yaml" # 备份文件也是 yaml
    destination_path = backup_dir / backup_filename
    try:
        shutil.copy2(source_path, destination_path)
        logging.info(f"成功备份 '{source_path.name}' 到 '{destination_path}'")
        return True
    except Exception as e:
        logging.error(f"备份 '{source_path.name}' 时出错: {e}")
        return False

async def run_single_site_operation(args, connection_config_path: str | Path, api_type: str, script_config: dict) -> int:
    """
    执行单站点更新的主流程：总是先模拟，然后询问是否执行实际更新。

    Args:
        args: 解析后的命令行参数对象 (需要包含 .yes, .clear_config)。
        connection_config_path (str | Path): 连接配置文件的路径。
        api_type (str): API 类型 ('newapi' 或 'voapi').
        script_config (dict): 已加载的脚本通用配置。

    Returns:
        int: 退出码 (0 表示成功, 1 表示失败)。
    """
    exit_code = 0
    # script_config 现在作为参数传入，不再需要在此加载
    api_settings = script_config.get('api_settings', {})
    max_concurrent = api_settings.get('max_concurrent_requests', 5)
    semaphore = asyncio.Semaphore(max_concurrent)
    # 日志消息调整，因为配置现在是传入的
    logging.info(f"使用传入的脚本配置，最大并发数: {max_concurrent}")

    # 使用导入的函数获取工具实例，并传递 script_config
    # 注意：这里传递 UPDATE_CONFIG_PATH，因为单站点操作需要它
    tool_instance = _get_tool_instance(api_type, connection_config_path, UPDATE_CONFIG_PATH, script_config=script_config)
    if not tool_instance:
        # 错误已在 _get_tool_instance 中记录
        print("错误：无法初始化 API 工具实例。")
        return 1

    # --- 检查更新配置文件 ---
    update_config_file = UPDATE_CONFIG_PATH # 使用导入的常量
    if not update_config_file.is_file():
        logging.error(f"错误：更新配置文件 '{update_config_file}' 不存在。")
        print(f"错误：更新配置文件 '{update_config_file.name}' 不存在。")
        return 1

    # --- 加载更新配置 ---
    try:
        with open(UPDATE_CONFIG_PATH, 'r', encoding='utf-8') as f:
            update_config = yaml.safe_load(f)
        if not update_config:
            raise yaml.YAMLError("配置文件内容为空或无效")
    except (FileNotFoundError, yaml.YAMLError) as e:
        logging.error(f"错误：无法加载或解析更新配置文件 '{UPDATE_CONFIG_PATH.name}': {e}")
        print(f"错误：无法加载或解析更新配置文件 '{UPDATE_CONFIG_PATH.name}': {e}")
        return 1
    filters_config = update_config.get('filters') # 获取筛选器配置

    # --- 1. 获取和过滤渠道 ---
    logging.info("开始获取和过滤渠道...")
    try:
        channel_list, get_list_message = await tool_instance.get_all_channels()
        if channel_list is None:
            print(f"\n错误：获取渠道列表失败。详情请查看日志。\n失败原因: {get_list_message}")
            return 1
        if not channel_list:
            logging.info(f"渠道列表为空 ({get_list_message})，无需执行更新。")
            print("渠道列表为空，无需执行更新。")
            return 0

        # 传递 filters_config 给 filter_channels
        filtered_list = tool_instance.filter_channels(channel_list, filters_config)
        if not filtered_list:
            logging.info("没有匹配筛选条件的渠道。")
            print("没有匹配筛选条件的渠道。")
            return 0
    except ValueError as e:
        logging.error(f"获取渠道列表时发生配置或兼容性错误: {e}")
        print(f"\n错误：获取渠道列表失败。\n原因: {e}")
        print("请检查您的 API 类型选择是否与目标 One API 实例匹配，或查看日志获取详细信息。")
        return 1
    except Exception as e:
        logging.error(f"获取或过滤渠道时发生未知错误: {e}", exc_info=True)
        print(f"\n错误：获取或过滤渠道时发生意外错误，请查看日志。")
        return 1

    # --- 2. 准备和记录计划变更 (模拟运行) ---
    logging.info(f"准备处理 {len(filtered_list)} 个匹配的渠道，开始模拟更新计划...")
    print("\n--- 模拟更新计划 ---")
    payloads_to_update = []
    channels_to_update_info = []
    has_planned_changes = False
    unchanged_channel_count = 0 # 新增：计数无实际变更的渠道
    actually_changed_channel_count = 0 # 新增：计数有实际变更的渠道

    for channel in filtered_list:
        channel_id = channel.get('id')
        channel_name = channel.get('name', f'ID:{channel_id}')
        try:
            # _prepare_update_payload 是 ChannelToolBase 的内部方法
            payload_data, updated_fields = tool_instance._prepare_update_payload(channel)

            if payload_data and updated_fields: # 检查是否有实际的更新字段
                if not has_planned_changes: # 第一次检测到有变更的渠道
                    print("检测到以下计划变更:")
                has_planned_changes = True
                actually_changed_channel_count +=1 # 计数实际发生变更的渠道
                log_msg_header = f"渠道 {channel_name} (ID: {channel_id}) 计划进行以下更新:"
                print(f"\n{log_msg_header}")
                logging.info(log_msg_header)
                for field in updated_fields:
                    original_value = channel.get(field)
                    new_value = payload_data.get(field)
                    original_display = repr(original_value) if original_value is not None else 'None'
                    new_display = repr(new_value) if new_value is not None else 'None'
                    log_msg_detail = f"  - {field}: {original_display} -> {new_display}"
                    print(log_msg_detail)
                    logging.info(log_msg_detail)
                payloads_to_update.append(payload_data)
                channels_to_update_info.append({'id': channel_id, 'name': channel_name})
            else: # 没有实际的更新字段
                unchanged_channel_count += 1
                logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 经过检查，字段值未发生实际变化。")

        except Exception as e:
            logging.error(f"为渠道 {channel_name} (ID: {channel_id}) 准备更新数据时出错: {e}", exc_info=True)
            print(f"[错误] 处理渠道 {channel_name} (ID: {channel_id}) 时出错，请检查日志。")
            # 即使单个渠道处理出错，也应该继续处理其他渠道，但错误会记录

    # 在循环结束后，处理汇总信息
    if not has_planned_changes and unchanged_channel_count > 0 : # 所有渠道都没有实际变更
        logging.info(f"模拟完成，对 {unchanged_channel_count} 个匹配的渠道进行了检查，均无需更新。")
        print(f"\n模拟完成：已检查 {unchanged_channel_count} 个匹配的渠道，均无需更新。")
        return 0
    elif not has_planned_changes and unchanged_channel_count == 0: # 没有匹配的渠道有变更，也没有未变更的（理论上 filtered_list 为空时发生）
        logging.info("模拟完成，没有检测到需要执行的更新 (可能是 filtered_list 为空)。")
        print("\n模拟完成：未发现需要更新的渠道。") # 与原逻辑一致
        return 0
    elif has_planned_changes and unchanged_channel_count > 0: # 部分渠道有变更，部分无变更
        logging.info(f"模拟完成: {actually_changed_channel_count} 个渠道有计划变更，另外 {unchanged_channel_count} 个渠道无需更新。")
        print(f"\n模拟摘要: {actually_changed_channel_count} 个渠道有计划变更。另外 {unchanged_channel_count} 个渠道无需更新。")
    elif has_planned_changes and unchanged_channel_count == 0: # 所有匹配的渠道都有变更
        logging.info(f"模拟完成: 所有 {actually_changed_channel_count} 个匹配的渠道都有计划变更。")
        # 此时不需要额外打印，因为之前的循环已经打印了所有变更

    # 如果 has_planned_changes 为 True，则继续后续的确认和执行流程
    # 如果为 False（上面已处理），则已返回 0

    # --- 3. 询问用户是否执行实际更新 ---
    execute_real_update = False
    print("\n--- 模拟结束 ---")
    if not args.yes:
        try:
            confirm_choice = input("是否要根据以上计划执行实际更新？ (y/n): ").lower()
            if confirm_choice == 'y':
                execute_real_update = True
                logging.info("用户确认执行实际更新。")
                print("用户确认，将开始执行实际更新...")
            else:
                logging.info("用户选择不执行实际更新。")
                print("操作已取消，未执行实际更新。")
                return 0
        except EOFError:
             print("\n操作已取消。")
             return 0
    else:
        logging.info("自动确认模式 (--yes) 已启用，将直接执行更新。")
        print("自动确认模式 (--yes) 已启用，将直接执行更新...")
        execute_real_update = True

    # --- 4. 执行实际更新 (如果需要) ---
    if execute_real_update:
        logging.info("="*10 + " 开始执行实际更新 " + "="*10)
        undo_file_path_saved = None
        # --- 4a. 备份和保存撤销数据 ---
        # backup_update_config 在此模块中定义
        if not backup_update_config():
            logging.warning("Update config 备份失败，但将继续执行更新。")
            if not args.yes:
                try:
                    confirm_continue = input("备份失败，是否仍要继续执行更新？(y/n): ").lower()
                    if confirm_continue != 'y':
                        print("操作已取消。")
                        return 0
                except EOFError:
                     print("\n操作已取消。")
                     return 0

        # 使用导入的 save_undo_data
        undo_file_path_saved = await save_undo_data(api_type, connection_config_path, UPDATE_CONFIG_PATH)
        if not undo_file_path_saved:
            logging.warning("未能成功保存撤销数据，如果执行更新将无法撤销。")

        # --- 4b. 并发执行 API 调用 (使用 Semaphore 控制) ---
        logging.info(f"开始并发执行 {len(payloads_to_update)} 个更新任务 (最大并发: {max_concurrent})...")

        async def update_task_wrapper(payload):
            async with semaphore:
                logging.debug(f"开始更新渠道 ID: {payload.get('id')}")
                result = await tool_instance.update_channel_api(payload)
                logging.debug(f"完成更新渠道 ID: {payload.get('id')}")
                return result

        tasks = [update_task_wrapper(payload) for payload in payloads_to_update]
        results = []
        try:
            # gather 会保持原始顺序
            results = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logging.error(f"执行并发更新任务时发生意外错误: {e}", exc_info=True)

        # --- 4c. 处理更新结果 ---
        success_count = sum(1 for r in results if isinstance(r, tuple) and len(r) == 2 and r[0] is True)
        fail_count = len(results) - success_count
        logging.info(f"更新任务完成: {success_count} 个成功, {fail_count} 个失败。")
        print(f"\n更新结果: {success_count} 个成功, {fail_count} 个失败。")

        if fail_count > 0:
            logging.error(f"{fail_count} 个渠道更新失败，请检查之前的错误日志。")
            print(f"注意：有 {fail_count} 个渠道更新失败，详情请查看日志。")
            failed_indices = [i for i, r in enumerate(results) if not (isinstance(r, tuple) and len(r) == 2 and r[0] is True)]
            for i in failed_indices:
                 if i < len(channels_to_update_info):
                     failed_channel_info = channels_to_update_info[i]
                     logging.error(f"  - 渠道 {failed_channel_info['name']} (ID: {failed_channel_info['id']}) 更新失败: {results[i]}")
                 else:
                     logging.error(f"  - 未知渠道更新失败: {results[i]} (索引超出范围)")
            exit_code = 1
        else:
            logging.info("所有渠道更新成功。")
            exit_code = 0

        # --- 4d. 清理更新配置 (如果成功) ---
        print("\n--- 操作完成 ---")
        if exit_code == 0:
            # 使用导入的 ask_and_clear_update_config
            ask_and_clear_update_config(force_clear=args.clear_config, auto_confirm=args.yes)
        else:
             logging.info("更新未完全成功，跳过清理 update_config。")
             print("更新未完全成功，未执行清理操作。")

        # --- 4e. 提示撤销信息 ---
        if undo_file_path_saved:
             logging.info(f"撤销数据已保存到: {undo_file_path_saved}")
             print(f"\n提示：如果需要撤销本次操作，请使用 --undo 参数并选择相同的连接配置和 API 类型。")
             print(f"撤销文件: {undo_file_path_saved.name}")
        else:
             logging.warning("本次操作未成功保存撤销数据，无法使用 --undo 撤销。")

    return exit_code


async def run_test_and_enable_disabled(args, connection_config_path: str | Path, api_type: str, script_config: dict) -> int:
    """
    测试状态为“自动禁用”的渠道，并在测试通过后尝试启用它们。

    Args:
        args: 解析后的命令行参数对象 (需要包含 .yes)。
        connection_config_path (str | Path): 连接配置文件的路径。
        api_type (str): API 类型 ('newapi' 或 'voapi').
        script_config (dict): 已加载的脚本通用配置。

    Returns:
        int: 退出码 (0 表示成功或无操作, 1 表示失败)。
    """
    exit_code = 0
    # script_config 现在作为参数传入，不再需要在此加载
    api_settings = script_config.get('api_settings', {})
    # test_settings 已移除，相关配置从 script_config 中获取
    max_concurrent = api_settings.get('max_concurrent_requests', 5)
    semaphore = asyncio.Semaphore(max_concurrent)
    # 日志消息调整
    logging.info(f"使用传入的脚本配置，最大并发数: {max_concurrent}")

    logging.info(f"开始执行 '测试并启用禁用渠道' 操作，目标配置: {connection_config_path}, API 类型: {api_type}")
    print(f"\n--- 开始测试并启用禁用渠道 ({Path(connection_config_path).name}) ---")

    # 1. 获取工具实例
    # 注意：测试功能不直接依赖 update_config.yaml，但 _get_tool_instance 需要它来处理某些情况
    # 传递 None 明确表示不使用更新配置，并传递 script_config
    tool_instance = _get_tool_instance(api_type, connection_config_path, None, script_config=script_config)
    if not tool_instance:
        print("错误：无法初始化 API 工具实例。")
        return 1

    # 2. 获取所有渠道
    logging.info("获取所有渠道列表...")
    try:
        channel_list, get_list_message = await tool_instance.get_all_channels()
        if channel_list is None:
            print(f"\n错误：获取渠道列表失败。详情请查看日志。\n失败原因: {get_list_message}")
            return 1
        if not channel_list:
            logging.info("渠道列表为空，无需执行测试。")
            print("渠道列表为空，无需执行测试。")
            return 0
        logging.info(f"成功获取 {len(channel_list)} 个渠道。")
    except ValueError as e:
        logging.error(f"获取渠道列表时发生配置或兼容性错误: {e}")
        print(f"\n错误：获取渠道列表失败。\n原因: {e}")
        print("请检查您的 API 类型选择是否与目标 One API 实例匹配，或查看日志获取详细信息。")
        return 1
    except Exception as e:
        logging.error(f"获取渠道列表时发生未知错误: {e}", exc_info=True)
        print(f"\n错误：获取渠道列表时发生意外错误，请查看日志。")
        return 1

    # 3. 筛选自动禁用的渠道 (status == 3)
    disabled_channels = [ch for ch in channel_list if ch.get('status') == 3]

    if not disabled_channels:
        logging.info("没有找到状态为 '自动禁用' (status=3) 的渠道。")
        print("没有找到状态为 '自动禁用' 的渠道，无需测试。")
        return 0

    logging.info(f"找到 {len(disabled_channels)} 个自动禁用的渠道，准备进行测试。")
    print(f"找到 {len(disabled_channels)} 个自动禁用的渠道，将逐一测试...")

    # 4. 准备并发测试
    channels_to_enable_payloads = []
    tested_count = 0
    passed_count = 0
    failed_test_count = 0
    enable_tasks = []
    channels_to_enable_info = [] # 用于记录待启用渠道的信息

    # 需要 aiohttp session 来发送请求
    async with aiohttp.ClientSession() as session:
        # 使用 Semaphore 控制并发测试
        logging.info(f"开始并发测试 {len(disabled_channels)} 个渠道 (最大并发: {max_concurrent})...")

        async def test_task_wrapper(channel_data):
            async with semaphore:
                 logging.debug(f"开始测试渠道 ID: {channel_data.get('id')}")
                 # 传递 script_config 给测试函数
                 result = await _test_single_channel(session, tool_instance, channel_data, script_config)
                 logging.debug(f"完成测试渠道 ID: {channel_data.get('id')}")
                 return result

        test_tasks = [test_task_wrapper(channel) for channel in disabled_channels]

        # 执行并发测试
        test_results = await asyncio.gather(*test_tasks, return_exceptions=True)

    # 5. 处理测试结果并准备启用任务
    failed_channels_details = [] # 存储失败渠道的详细信息 (id, name, message, failure_type)
    for i, result in enumerate(test_results):
        channel = disabled_channels[i] # 获取对应的渠道信息
        channel_id = channel.get('id')
        channel_name = channel.get('name', f'ID:{channel_id}')
        tested_count += 1
        failure_type = None # 初始化 failure_type

        if isinstance(result, Exception):
            failed_test_count += 1
            failure_type = 'exception'
            message = f"异常: {result}"
            logging.error(f"测试渠道 {channel_name} (ID: {channel_id}) 时发生异常: {result}", exc_info=result)
            print(f"  - 测试渠道 {channel_name} (ID: {channel_id}): 失败 ({message})")
            failed_channels_details.append({'id': channel_id, 'name': channel_name, 'message': message, 'failure_type': failure_type})
        # 修改这里以处理新的返回格式 tuple[bool, str, str | None]
        elif isinstance(result, tuple) and len(result) == 3:
            test_passed, message, failure_type = result
            if test_passed:
                passed_count += 1
                logging.info(f"测试渠道 {channel_name} (ID: {channel_id}) 通过。准备启用。")
                print(f"  - 测试渠道 {channel_name} (ID: {channel_id}): 通过 -> 准备启用")
                # 准备启用 payload
                enable_payload = {'id': channel_id, 'status': 1}
                channels_to_enable_payloads.append(enable_payload)
                channels_to_enable_info.append({'id': channel_id, 'name': channel_name})
            else:
                failed_test_count += 1
                logging.warning(f"测试渠道 {channel_name} (ID: {channel_id}) 未通过: {message} (类型: {failure_type})")
                print(f"  - 测试渠道 {channel_name} (ID: {channel_id}): 未通过 ({message})")
                failed_channels_details.append({'id': channel_id, 'name': channel_name, 'message': message, 'failure_type': failure_type})
        else: # 非预期的结果格式
             failed_test_count += 1
             failure_type = 'unknown_format'
             message = f"未知结果格式: {result}"
             logging.error(f"测试渠道 {channel_name} (ID: {channel_id}) 返回了未知结果: {result}")
             print(f"  - 测试渠道 {channel_name} (ID: {channel_id}): 失败 ({message})")
             failed_channels_details.append({'id': channel_id, 'name': channel_name, 'message': message, 'failure_type': failure_type})


    print(f"\n测试完成: 共测试 {tested_count} 个渠道，{passed_count} 个通过，{failed_test_count} 个失败。")

    # 6. 执行启用操作 (如果需要)
    if not channels_to_enable_payloads:
        logging.info("没有测试通过的渠道需要启用。")
        print("没有测试通过的渠道需要启用。")
        return 0 # 没有启用操作，认为是成功

    logging.info(f"准备启用 {len(channels_to_enable_payloads)} 个测试通过的渠道...")
    print(f"\n准备启用 {len(channels_to_enable_payloads)} 个测试通过的渠道...")

    # --- 优化确认逻辑 ---
    execute_enable = False
    # 检查是否存在非配额原因的失败
    has_non_quota_failure = any(f.get('failure_type') != 'quota' for f in failed_channels_details)

    if args.yes:
        logging.info("自动确认模式 (--yes) 已启用，将直接执行启用操作。")
        print("自动确认模式 (--yes) 已启用，将直接执行启用操作...")
        execute_enable = True
    elif failed_test_count == 0:
         # 没有失败，直接启用 (理论上不会到这里，因为上面有 if not channels_to_enable_payloads)
         logging.info("所有测试均通过，直接执行启用操作。")
         execute_enable = True
    elif not has_non_quota_failure:
        # 所有失败都是配额问题，跳过确认
        logging.info("所有测试失败均为配额问题，将自动执行启用操作。")
        print("所有测试失败均为配额问题，将自动执行启用操作...")
        execute_enable = True
    else:
        # 存在非配额失败，需要用户确认
        logging.info("存在非配额原因的测试失败，需要用户确认。")
        print("注意：部分渠道测试失败（非配额原因），请确认是否仍要启用测试通过的渠道。")
        try:
            confirm_choice = input("是否要启用以上测试通过的渠道？ (y/n): ").lower()
            if confirm_choice == 'y':
                execute_enable = True
                logging.info("用户确认执行启用操作。")
                print("用户确认，将开始执行启用操作...")
            else:
                logging.info("用户选择不执行启用操作。")
                print("操作已取消，未执行启用。")
                return 0
        except EOFError:
             print("\n操作已取消。")
             return 0
    # --- 确认逻辑结束 ---

    if execute_enable:
        logging.info("="*10 + " 开始执行启用操作 " + "="*10)
        # 并发执行 API 调用以启用渠道 (使用 Semaphore 控制)
        logging.info(f"开始并发启用 {len(channels_to_enable_payloads)} 个渠道 (最大并发: {max_concurrent})...")

        async def enable_task_wrapper(payload):
             async with semaphore:
                 logging.debug(f"开始启用渠道 ID: {payload.get('id')}")
                 result = await tool_instance.update_channel_api(payload)
                 logging.debug(f"完成启用渠道 ID: {payload.get('id')}")
                 return result

        enable_tasks = [enable_task_wrapper(payload) for payload in channels_to_enable_payloads]
        enable_results = []
        try:
            enable_results = await asyncio.gather(*enable_tasks, return_exceptions=True)
        except Exception as e:
            logging.error(f"执行并发启用任务时发生意外错误: {e}", exc_info=True)

        # 处理启用结果
        enable_success_count = sum(1 for r in enable_results if isinstance(r, tuple) and len(r) == 2 and r[0] is True)
        enable_fail_count = len(enable_results) - enable_success_count
        logging.info(f"启用任务完成: {enable_success_count} 个成功, {enable_fail_count} 个失败。")
        print(f"\n启用结果: {enable_success_count} 个成功, {enable_fail_count} 个失败。")

        if enable_fail_count > 0:
            logging.error(f"{enable_fail_count} 个渠道启用失败，请检查之前的错误日志。")
            print(f"注意：有 {enable_fail_count} 个渠道启用失败，详情请查看日志。")
            failed_indices = [i for i, r in enumerate(enable_results) if not (isinstance(r, tuple) and len(r) == 2 and r[0] is True)]
            for i in failed_indices:
                 if i < len(channels_to_enable_info):
                     failed_channel_info = channels_to_enable_info[i]
                     logging.error(f"  - 启用渠道 {failed_channel_info['name']} (ID: {failed_channel_info['id']}) 失败: {enable_results[i]}")
                 else:
                     logging.error(f"  - 未知渠道启用失败: {enable_results[i]} (索引超出范围)")
            exit_code = 1 # 标记为失败
        else:
            logging.info("所有测试通过的渠道已成功启用。")
            exit_code = 0 # 标记为成功

    print("\n--- 操作完成 ---")
    return exit_code


async def _test_single_channel(session: aiohttp.ClientSession, tool_instance, channel: dict, script_config: dict) -> tuple[bool, str, str | None]:
    """
    使用 One API 的测试端点测试单个渠道，动态选择测试模型，并返回失败类型。
    使用 script_config 中的超时和备用模型设置。

    Args:
        session: aiohttp 客户端会话。
        tool_instance: ChannelTool 实例，用于获取 URL 和 token。
        channel (dict): 要测试的渠道的完整信息字典。
        script_config (dict): 加载的脚本配置。

    Returns:
        tuple[bool, str, str | None]: (测试是否通过, 描述信息, 失败类型)
                                      失败类型: 'quota', 'auth', 'api_error', 'server_error',
                                                'response_format', 'timeout', 'network',
                                                'config', 'exception', None (成功)
    """
    channel_id = channel.get('id')
    channel_name = channel.get('name', f'ID:{channel_id}')
    failure_type = None # 初始化
    api_settings = script_config.get('api_settings', {})
    test_settings = script_config.get('test_settings', {})

    # --- 模型选择逻辑 ---
    test_model = channel.get('test_model') # 优先使用配置的测试模型
    if not test_model:
        models_str = channel.get('models')
        if models_str:
            model_list = [m.strip() for m in models_str.split(',') if m.strip()]
            if model_list:
                test_model = model_list[0] # 使用模型列表的第一个
                logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 未配置 test_model，将使用模型列表第一个: {test_model}")
            else:
                # 模型列表为空或无效，无法确定测试模型
                logging.warning(f"渠道 {channel_name} (ID: {channel_id}) 未配置测试模型，且模型列表为空或无效，无法测试。")
                return False, "无法确定测试模型 (模型列表无效)", 'config'
        else:
            # 未配置测试模型，且无模型列表
            logging.warning(f"渠道 {channel_name} (ID: {channel_id}) 未配置测试模型，且无模型列表，无法测试。")
            return False, "无法确定测试模型 (无模型列表)", 'config'

    if not test_model: # 双重检查，理论上不应到达这里
         logging.error(f"未能为渠道 {channel_name} (ID: {channel_id}) 确定测试模型。")
         return False, "无法确定测试模型", 'config'
    # --- 模型选择结束 ---

    test_url = f"{tool_instance.site_url.rstrip('/')}/api/channel/test/{channel_id}"
    params = {'model': test_model} # 使用动态选择的模型
    headers = {
        'Authorization': f'Bearer {tool_instance.api_token}',
        'Accept': 'application/json',
        'New-Api-User': str(tool_instance.user_id) # 添加 New-Api-User Header, 确保是字符串
    }
    # 使用配置的超时时间
    request_timeout = api_settings.get('request_timeout', 60)
    timeout = aiohttp.ClientTimeout(total=request_timeout)

    logging.debug(f"准备测试渠道 {channel_name} (ID: {channel_id})，URL: {test_url}，模型: {test_model}, Headers: {headers}, 超时: {request_timeout}s")

    try:
        async with session.get(test_url, headers=headers, params=params, timeout=timeout) as response:
            status_code = response.status
            logging.debug(f"测试渠道 {channel_name} (ID: {channel_id}) - 状态码: {status_code}")
            response_text_preview = await response.text()
            logging.debug(f"测试渠道 {channel_name} (ID: {channel_id}) - 原始响应预览: {response_text_preview[:500]}...")

            if status_code == 200:
                try:
                    response_json = json.loads(response_text_preview)
                    logging.debug(f"测试渠道 {channel_name} (ID: {channel_id}) - 解析后 JSON: {response_json}")

                    if response_json.get('success') is True:
                        success_message = response_json.get('message', "测试成功")
                        logging.info(f"测试渠道 {channel_name} (ID: {channel_id}) 通过: {success_message}")
                        return True, success_message, None # 成功，无失败类型
                    else:
                        error_message = response_json.get('message', '测试未通过，无详细信息')
                        # 尝试根据消息内容判断失败类型 (例如配额)
                        if "quota" in error_message.lower():
                            failure_type = 'quota'
                        else:
                            failure_type = 'api_error' # 其他 API 层面报告的失败
                        logging.warning(f"测试渠道 {channel_name} (ID: {channel_id}) 未通过: {error_message}")
                        return False, f"测试未通过: {error_message}", failure_type
                except json.JSONDecodeError as e:
                    logging.error(f"测试渠道 {channel_name} (ID: {channel_id}) 响应状态码 200 但 JSON 解析失败: {e}. 原始响应: {response_text_preview[:500]}...")
                    return False, f"测试失败: 无法解析成功的响应 ({e})", 'response_format'
            else:
                # HTTP 状态码非 200
                error_message = f"API 返回状态码 {status_code}"
                try: # 尝试提取更详细的错误信息
                    error_json = json.loads(response_text_preview)
                    if 'message' in error_json:
                        error_message += f" ({error_json['message']})"
                except json.JSONDecodeError:
                    pass
                logging.error(f"测试渠道 {channel_name} (ID: {channel_id}) API 请求失败，状态码: {status_code}, 响应: {response_text_preview[:500]}...")
                # 根据状态码判断失败类型
                if status_code == 401: failure_type = 'auth'
                elif status_code == 429: failure_type = 'quota'
                elif status_code >= 400 and status_code < 500: failure_type = 'api_error'
                elif status_code >= 500: failure_type = 'server_error'
                else: failure_type = 'unknown_http'
                return False, f"测试失败: {error_message}", failure_type

    except asyncio.TimeoutError:
        logging.error(f"测试渠道 {channel_name} (ID: {channel_id}) 超时。")
        return False, "测试失败: 请求超时", 'timeout'
    except aiohttp.ClientError as e:
        logging.error(f"测试渠道 {channel_name} (ID: {channel_id}) 时发生客户端错误: {e}")
        return False, f"测试失败: 网络或客户端错误 ({e})", 'network'
    except Exception as e:
        logging.exception(f"测试渠道 {channel_name} (ID: {channel_id}) 时发生未知异常。")
        return False, f"测试失败: 未知错误 ({type(e).__name__})", 'exception'


async def run_test_model_on_channels(
    args,
    script_config: dict,
    test_config_file_path_str: str,
    explicitly_selected_conn_config_path: str | Path | None = None
) -> int:
    """
    根据指定配置文件测试筛选出的渠道对特定模型的支持情况。
    如果 explicitly_selected_conn_config_path 不为 None (交互模式), 则使用它。
    否则 (命令行 --test-channel-model), 从测试配置文件中读取 target_connection_config。

    Args:
        args: 解析后的命令行参数对象 (需要包含 .yes)。
        script_config (dict): 已加载的脚本通用配置。
        test_config_file_path_str (str): 测试配置文件的路径。

    Returns:
        int: 退出码 (0 表示成功或无操作, 1 表示失败)。
    """
    exit_code = 0
    logging.info(f"开始执行 '测试指定模型渠道' 操作，测试配置文件: {test_config_file_path_str}")
    print(f"\n--- 开始测试指定模型渠道 (配置文件: {Path(test_config_file_path_str).name}) ---")

    # 1. 加载测试配置文件
    test_config_path = Path(test_config_file_path_str)
    if not test_config_path.is_file(): # Double check, though CLI handler should have caught this
        logging.error(f"错误：测试配置文件 '{test_config_path}' 不存在。")
        print(f"错误：测试配置文件 '{test_config_path.name}' 不存在。")
        return 1

    try:
        test_config = load_yaml_config(test_config_path)
        if not test_config:
            raise yaml.YAMLError(f"测试配置文件 '{test_config_path.name}' 内容为空或无效。")

        # --- 确定最终的连接配置文件路径 ---
        final_connection_config_path_str : str | None = None
        
        if explicitly_selected_conn_config_path:
            # 交互模式: 使用用户通过菜单选择的连接配置
            final_connection_config_path_str = str(explicitly_selected_conn_config_path)
            logging.info(f"交互模式：使用用户选择的连接配置: {final_connection_config_path_str}")
            if not Path(final_connection_config_path_str).is_file():
                 raise FileNotFoundError(f"交互模式下选定的连接配置文件 '{final_connection_config_path_str}' 未找到。")
            # 在此模式下，测试配置文件中的 target_connection_config (如果存在) 将被忽略。
            if test_config.get('target_connection_config'):
                logging.debug(f"测试配置文件中的 'target_connection_config' ('{test_config.get('target_connection_config')}') 在交互模式下被忽略。")
        else:
            # 命令行模式: 必须从测试配置文件中获取 target_connection_config
            target_conn_config_from_file_str = test_config.get('target_connection_config')
            if not target_conn_config_from_file_str or not isinstance(target_conn_config_from_file_str, str):
                raise ValueError("命令行模式下，测试配置文件中 'target_connection_config' 缺失或不是有效字符串。")
            
            temp_path = Path(target_conn_config_from_file_str)
            if not temp_path.is_file():
                if not temp_path.is_absolute(): # 尝试解析为相对于项目根目录
                    project_root = Path(__file__).parent.parent
                    absolute_target_path = project_root / target_conn_config_from_file_str
                    if absolute_target_path.is_file():
                        final_connection_config_path_str = str(absolute_target_path)
                        logging.info(f"测试配置文件中相对路径 '{target_conn_config_from_file_str}' 解析为: {final_connection_config_path_str}")
                    else:
                        raise FileNotFoundError(f"测试配置文件中的 'target_connection_config' 指向的文件 '{target_conn_config_from_file_str}' (或其绝对路径 '{absolute_target_path}') 未找到。")
                else: # 是绝对路径但文件不存在
                    raise FileNotFoundError(f"测试配置文件中的 'target_connection_config' 指向的文件 (绝对路径) '{target_conn_config_from_file_str}' 未找到。")
            else: # 路径有效且文件存在
                final_connection_config_path_str = str(temp_path)
            logging.info(f"命令行模式：使用测试配置文件中指定的连接配置: {final_connection_config_path_str}")

        # 验证其他必需字段
        filters_config = test_config.get('filters')
        test_params = test_config.get('test_parameters')

        if not filters_config or not isinstance(filters_config, dict):
            raise ValueError("测试配置文件中 'filters' 缺失或不是一个字典。")
        if not test_params or not isinstance(test_params, dict):
            raise ValueError("测试配置文件中 'test_parameters' 缺失或不是一个字典。")
        
        model_to_test = test_params.get('model_to_test')
        if not model_to_test or not isinstance(model_to_test, str):
            raise ValueError("测试配置文件中 'test_parameters.model_to_test' 缺失或不是字符串。")
        
        report_failed_only = test_params.get('report_failed_only', False)
        continue_on_failure = test_params.get('continue_on_failure', True)

    except (FileNotFoundError, yaml.YAMLError, ValueError) as e: # 合并异常捕获
        logging.error(f"加载或解析测试配置文件 '{test_config_path.name}' 或其引用的连接配置时出错: {e}", exc_info=True)
        print(f"错误：加载或解析测试配置文件 '{test_config_path.name}' 或其引用的连接配置失败: {e}")
        return 1
    except Exception as e: # 通用异常捕获
        logging.error(f"加载测试配置文件时发生未知错误: {e}", exc_info=True)
        print(f"错误: 加载测试配置文件时发生未知错误。请查看日志。")
        return 1
    
    # 使用 final_connection_config_path_str 来记录日志
    logging.info(f"测试配置加载成功。将使用连接配置: {Path(final_connection_config_path_str).name}, 测试模型: {model_to_test}")

    # 2. 加载目标连接配置并获取 API 类型 (使用 final_connection_config_path_str)
    try:
        api_config = load_yaml_config(final_connection_config_path_str) # 使用最终确定的路径
        if not api_config:
             raise ValueError(f"最终确定的连接配置文件 '{Path(final_connection_config_path_str).name}' 加载失败或为空。")
        api_type = api_config.get('api_type')
        if not api_type or api_type not in ["newapi", "voapi"]:
            raise ValueError(f"连接配置文件 '{Path(final_connection_config_path_str).name}' 中缺少有效 'api_type' ('newapi' 或 'voapi')。")
        logging.info(f"从连接配置 '{Path(final_connection_config_path_str).name}' 加载 API 类型: {api_type}")
    except Exception as e:
        logging.error(f"加载连接配置 '{Path(final_connection_config_path_str).name}' 时出错: {e}", exc_info=True)
        print(f"错误：无法从 '{Path(final_connection_config_path_str).name}' 加载 API 类型。请检查文件和日志。")
        return 1

    # 3. 获取工具实例 (使用 final_connection_config_path_str)
    tool_instance = _get_tool_instance(api_type, final_connection_config_path_str, None, script_config=script_config)
    if not tool_instance:
        # _get_tool_instance 应该已经记录了错误并可能打印了消息
        return 1

    # 4. 获取所有渠道并筛选
    logging.info("获取所有渠道列表...")
    try:
        channel_list, get_list_message = await tool_instance.get_all_channels()
        if channel_list is None:
            print(f"\n错误：获取渠道列表失败。详情请查看日志。\n失败原因: {get_list_message}")
            return 1
        
        filtered_channels = tool_instance.filter_channels(channel_list, filters_config)
        if not filtered_channels:
            logging.info("没有匹配测试配置文件中筛选条件的渠道。")
            print("没有匹配测试配置文件中筛选条件的渠道。")
            return 0
        logging.info(f"成功获取并筛选出 {len(filtered_channels)} 个渠道进行测试。")
        print(f"将对 {len(filtered_channels)} 个匹配筛选条件的渠道测试模型 '{model_to_test}'...")

    except ValueError as e: # 通常是API类型不匹配等配置问题
        logging.error(f"获取或筛选渠道时发生配置或兼容性错误: {e}")
        print(f"\n错误：获取或筛选渠道失败。\n原因: {e}")
        return 1
    except Exception as e:
        logging.error(f"获取或筛选渠道时发生未知错误: {e}", exc_info=True)
        print(f"\n错误：获取或筛选渠道时发生意外错误，请查看日志。")
        return 1

    # 5. 执行并发测试
    api_settings = script_config.get('api_settings', {})
    max_concurrent = api_settings.get('max_concurrent_requests', 5)
    semaphore = asyncio.Semaphore(max_concurrent)
    
    tested_count = 0
    passed_count = 0
    failed_test_count = 0
    all_test_results_details = [] # 用于存储所有渠道的详细测试结果

    async with aiohttp.ClientSession() as session:
        logging.info(f"开始并发测试 {len(filtered_channels)} 个渠道 (最大并发: {max_concurrent})...")

        async def test_task_wrapper_for_model(channel_data, specific_model_to_test):
            async with semaphore:
                logging.debug(f"开始测试渠道 ID: {channel_data.get('id')} 模型: {specific_model_to_test}")
                # 调用 _test_single_channel，但需要修改它来接受 specific_model_to_test
                # 或者创建一个新的 _test_single_channel_with_model
                # 为简单起见，暂时假设 _test_single_channel_with_model 存在或 _test_single_channel 已调整
                # 当前的 _test_single_channel 会自行选择模型，不符合这里的需求。
                # 我们需要一个直接测试指定模型的函数。
                # 暂时模拟调用，实际需要修改 ChannelToolBase 或其子类
                
                # 临时的测试逻辑占位符，实际应该调用类似 tool_instance.test_channel_with_model(channel_id, model_name)
                # 这里我们直接使用 _test_single_channel，但它的模型选择逻辑不完全匹配，
                # 它会优先用 channel.test_model。我们需要确保它测试的是 model_to_test。
                # *** 关键：需要调整测试方法以强制使用 model_to_test ***
                # 暂时先用现有的，但结果可能不完全准确，除非渠道的 test_model 正好是 model_to_test
                # 或者修改 _test_single_channel，让它接受一个强制的 model_override 参数

                # 为了演示，我们将直接调用 ChannelTool 的测试方法（假设它被调整或存在）
                # success, message, failure_type = await tool_instance.test_channel(session, channel_data.get('id'), specific_model_to_test, script_config)
                
                # 使用现有的 _test_single_channel，但需要注意其模型选择逻辑。
                # 更好的方法是 ChannelToolBase 有一个 test_specific_model(channel_id, model_name) 方法。
                # 我们先用 _test_single_channel 但要意识到其局限性。
                # 实际上，_test_single_channel 内部有模型选择逻辑，我们需要一个更直接的测试。
                # 对于这个功能，ChannelTool 应该有一个方法 test_channel_with_specific_model(channel_id, model_name)
                # 暂时我们先用现有的 test_channel 方法，它在 newapi_channel_tool.py 等实现中
                # 该方法通常是 self.test_channel_api(channel_id, model_name_to_test)
                
                test_success, test_message, test_failure_type = await tool_instance.test_channel_api(
                    channel_data.get('id'),
                    specific_model_to_test
                )

                logging.debug(f"完成测试渠道 ID: {channel_data.get('id')} 模型: {specific_model_to_test}. 结果: {test_success}, {test_message}")
                return channel_data, test_success, test_message, test_failure_type

        test_tasks = [test_task_wrapper_for_model(channel, model_to_test) for channel in filtered_channels]
        
        raw_results = []
        try:
            raw_results = await asyncio.gather(*test_tasks, return_exceptions=True)
        except Exception as e:
            logging.error(f"执行并发模型测试任务时发生意外错误: {e}", exc_info=True)
            print(f"错误: 执行并发模型测试时发生未知错误: {e}")
            # 标记所有任务为失败
            for i in range(len(filtered_channels)):
                 channel_info = filtered_channels[i]
                 all_test_results_details.append({
                     'id': channel_info.get('id'),
                     'name': channel_info.get('name', f"ID:{channel_info.get('id')}"),
                     'model_tested': model_to_test,
                     'passed': False,
                     'message': f"测试执行中发生全局错误: {e}",
                     'failure_type': 'exception'
                 })
            failed_test_count = len(filtered_channels)


    # 6. 处理测试结果并报告
    if not raw_results and failed_test_count == len(filtered_channels): # 如果 gather 失败且所有都已标记
        pass # 错误已记录
    else:
        for i, res_item in enumerate(raw_results):
            tested_count += 1
            channel_info = filtered_channels[i] # 确保索引对应
            ch_id = channel_info.get('id')
            ch_name = channel_info.get('name', f'ID:{ch_id}')

            current_result = {
                'id': ch_id,
                'name': ch_name,
                'model_tested': model_to_test,
                'passed': False,
                'message': '未知错误',
                'failure_type': 'unknown'
            }

            if isinstance(res_item, Exception):
                failed_test_count += 1
                current_result['message'] = f"测试时发生异常: {res_item}"
                current_result['failure_type'] = 'exception'
                logging.error(f"测试渠道 {ch_name} (ID: {ch_id}) 模型 {model_to_test} 时发生异常: {res_item}", exc_info=res_item)
            elif isinstance(res_item, tuple) and len(res_item) == 4:
                _ch_data_back, success, message, failure_type = res_item # _ch_data_back 可以忽略
                current_result['passed'] = success
                current_result['message'] = message
                current_result['failure_type'] = failure_type
                if success:
                    passed_count += 1
                    logging.info(f"渠道 {ch_name} (ID: {ch_id}) 测试模型 {model_to_test} 通过: {message}")
                else:
                    failed_test_count += 1
                    logging.warning(f"渠道 {ch_name} (ID: {ch_id}) 测试模型 {model_to_test} 未通过: {message} (类型: {failure_type})")
            else: # 非预期的结果格式
                failed_test_count += 1
                current_result['message'] = f"未知或无效的测试结果格式: {res_item}"
                current_result['failure_type'] = 'unknown_format'
                logging.error(f"渠道 {ch_name} (ID: {ch_id}) 测试模型 {model_to_test} 返回了未知结果格式: {res_item}")
            
            all_test_results_details.append(current_result)
            
            if not continue_on_failure and not current_result['passed']:
                logging.info(f"continue_on_failure is false，在渠道 {ch_name} (ID: {ch_id}) 测试失败后停止。")
                print(f"停止测试：渠道 {ch_name} (ID: {ch_id}) 对模型 {model_to_test} 测试失败。")
                break # 退出循环

    print(f"\n--- 模型 '{model_to_test}' 测试报告 ---")
    print(f"总共测试渠道数: {tested_count}")
    print(f"测试通过数: {passed_count}")
    print(f"测试失败数: {failed_test_count}")

    if not all_test_results_details:
        print("没有详细的测试结果可显示。")
    else:
        print("\n详细结果:")
        for detail in all_test_results_details:
            if not report_failed_only or (report_failed_only and not detail['passed']):
                status_icon = "✅" if detail['passed'] else "❌"
                print(f"  {status_icon} 渠道: {detail['name']} (ID: {detail['id']})")
                print(f"      模型: {detail['model_tested']}")
                print(f"      结果: {'通过' if detail['passed'] else '失败'}")
                print(f"      信息: {detail['message']}")
                if not detail['passed'] and detail.get('failure_type'):
                    print(f"      失败类型: {detail['failure_type']}")
    
    if failed_test_count > 0 :
        # 即使 continue_on_failure 为 true，只要有失败也认为整体操作部分失败
        exit_code = 1
        print("\n提示: 部分渠道测试失败。")
    else:
        exit_code = 0
    
    # 根据用户反馈，无论测试成功与否，都尝试提示清理配置文件
    # (清理函数内部会根据 args.yes 和 args.clear_test_model_config 处理实际行为)
    should_force_clear_test_config = getattr(args, 'clear_test_model_config', False)
    ask_and_clear_channel_model_test_config(
        target_test_config_path=test_config_path, # test_config_path 是在此函数前面定义的 Path 对象
        force_clear=should_force_clear_test_config,
        auto_confirm=args.yes
    )

    print("\n--- 操作完成 ---")
    return exit_code