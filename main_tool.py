# -*- coding: utf-8 -*-
"""
主入口脚本，提供交互式界面选择配置和 API 类型，并支持命令行参数。
"""
import os
import json
import logging
import logging.handlers # 导入 handlers
import asyncio
from pathlib import Path
import shutil
from datetime import datetime
import argparse # 导入 argparse
import sys # 用于退出脚本
import aiohttp # 需要 aiohttp 用于 undo

# 导入需要调用的工具脚本的类
from newapi_channel_tool import NewApiChannelTool
from voapi_channel_tool import VoApiChannelTool
# 导入基础工具类 (虽然子类继承了，但这里可能需要它的类型信息)
from channel_tool_base import ChannelToolBase

# --- 配置常量 ---
CONNECTION_CONFIG_DIR = "connection_configs"
UPDATE_CONFIG_PATH = "update_config.json" # 默认更新配置文件
UPDATE_CONFIG_BACKUP_DIR = "used_update_configs" # 备份目录
CLEAN_UPDATE_CONFIG_PATH = "update_config.clean.json" # 干净的配置文件
LOGS_DIR = "logs" # 日志文件存放目录
DEFAULT_LOG_FILE_BASENAME = "channel_updater.log" # 默认日志文件名基础部分
UNDO_DIR = "undo_data" # 撤销数据存放目录

# --- 日志设置函数 ---
def setup_logging(log_level_str="INFO", log_file_path=None):
    """配置日志记录器"""
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)
    logger = logging.getLogger()
    logger.setLevel(log_level)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    if log_file_path:
        try:
            log_file_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            print(f"[ERROR] 无法配置日志文件处理器 ({log_file_path}): {e}")
            print(f"错误：无法设置日志文件 '{log_file_path}'。请检查权限或路径。")

# --- 交互式选择函数 ---
def list_connection_configs():
    """列出 connection_configs 目录下的可用 JSON 配置文件 (排除 example)。"""
    config_dir = Path(CONNECTION_CONFIG_DIR)
    if not config_dir.is_dir():
        logging.error(f"错误：连接配置目录 '{CONNECTION_CONFIG_DIR}' 不存在。")
        return []
    configs = []
    for item in config_dir.glob("*.json"):
        if item.is_file() and "example" not in item.name.lower():
            configs.append(item)
    return configs

def select_config(configs, auto_confirm=False):
    """让用户通过数字选择配置文件，或在自动确认模式下跳过确认。"""
    if not configs:
        logging.error(f"错误：在 '{CONNECTION_CONFIG_DIR}' 目录下未找到可用的连接配置文件。")
        return None
    print("\n请选择要使用的连接配置:")
    for i, config_path in enumerate(configs):
        print(f"  {i + 1}: {config_path.name}")
    while True:
        try:
            choice = input(f"请输入选项编号 (1-{len(configs)}): ")
            index = int(choice) - 1
            if 0 <= index < len(configs):
                selected_path = configs[index]
                print(f"\n您选择了: {selected_path.name}")
                try:
                    with open(selected_path, 'r', encoding='utf-8') as f:
                        content = json.load(f)
                        print("--- 配置内容 ---")
                        print(json.dumps(content, indent=2, ensure_ascii=False))
                        print("-----------------")
                    if auto_confirm:
                        logging.info("自动确认模式：已选择此配置。")
                        return selected_path
                    else:
                        confirm = input("确认使用此配置吗？(y/n): ").lower()
                        if confirm == 'y':
                            return selected_path
                        else:
                            print("请重新选择。")
                            print("\n请选择要使用的连接配置:")
                            for i, config_path in enumerate(configs):
                                print(f"  {i + 1}: {config_path.name}")
                except (FileNotFoundError, json.JSONDecodeError, Exception) as e:
                     logging.error(f"读取或解析配置文件 '{selected_path}' 时出错: {e}")
                     print("无法读取或解析此配置文件，请重新选择。")
                     print("\n请选择要使用的连接配置:")
                     for i, config_path in enumerate(configs):
                         print(f"  {i + 1}: {config_path.name}")
            else:
                print(f"无效选项，请输入 1 到 {len(configs)} 之间的数字。")
        except ValueError:
            print("无效输入，请输入数字。")
        except EOFError:
            print("\n操作已取消。")
            return None

def select_api_type(auto_confirm=False):
    """让用户选择 API 类型，或在自动确认模式下跳过确认。"""
    print("\n请选择您的 One API 实例类型:")
    print("  1: New API (通常指较新版本的 One API)")
    print("  2: VO API (可能指特定分支或旧版本)")
    while True:
        try:
            choice = input("请输入选项编号 (1-2): ")
            if choice == '1':
                api_type = "newapi"
                print(f"\n您选择了: {api_type}")
                if auto_confirm:
                    logging.info("自动确认模式：已选择此 API 类型。")
                    return api_type
                else:
                    confirm = input("确认使用此 API 类型吗？(y/n): ").lower()
                    if confirm == 'y':
                        return api_type
                    else:
                        print("请重新选择。")
                        print("\n请选择您的 One API 实例类型:")
                        print("  1: New API")
                        print("  2: VO API")
            elif choice == '2':
                api_type = "voapi"
                print(f"\n您选择了: {api_type}")
                if auto_confirm:
                    logging.info("自动确认模式：已选择此 API 类型。")
                    return api_type
                else:
                    confirm = input("确认使用此 API 类型吗？(y/n): ").lower()
                    if confirm == 'y':
                        return api_type
                    else:
                        print("请重新选择。")
                        print("\n请选择您的 One API 实例类型:")
                        print("  1: New API")
                        print("  2: VO API")
            else:
                print("无效选项，请输入 1 或 2。")
        except ValueError:
            print("无效输入，请输入数字。")
        except EOFError:
            print("\n操作已取消。")
            return None

# --- 文件操作函数 ---
def backup_update_config():
    """备份当前的 update_config.json 文件到 used_update_configs 目录。"""
    source_path = Path(UPDATE_CONFIG_PATH)
    backup_dir = Path(UPDATE_CONFIG_BACKUP_DIR)
    if not source_path.is_file():
        logging.warning(f"警告：源文件 '{UPDATE_CONFIG_PATH}' 不存在，无法备份。")
        return False
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logging.error(f"创建备份目录 '{backup_dir}' 失败: {e}")
        return False
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S%f")[:-3]
    backup_filename = f"update_config.{timestamp}.json"
    destination_path = backup_dir / backup_filename
    try:
        shutil.copy2(source_path, destination_path)
        logging.info(f"成功备份 '{source_path.name}' 到 '{destination_path}'")
        return True
    except Exception as e:
        logging.error(f"备份 '{source_path.name}' 时出错: {e}")
        return False

def ask_and_clear_update_config(force_clear=False, auto_confirm=False):
    """询问用户是否清空 update_config.json 并执行。"""
    source_clean_path = Path(CLEAN_UPDATE_CONFIG_PATH)
    target_path = Path(UPDATE_CONFIG_PATH)
    if not source_clean_path.is_file():
        logging.warning(f"警告：干净的配置文件 '{CLEAN_UPDATE_CONFIG_PATH}' 不存在，无法执行清空操作。")
        print(f"\n注意：未找到 '{CLEAN_UPDATE_CONFIG_PATH}'，无法提供清空选项。")
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
            shutil.copyfile(source_clean_path, target_path)
            logging.info(f"已使用 '{source_clean_path.name}' 覆盖 '{target_path.name}'。")
            print(f"'{target_path.name}' 已恢复为干净状态。")
        except Exception as e:
            logging.error(f"使用 '{source_clean_path.name}' 覆盖 '{target_path.name}' 时出错: {e}")
            print("恢复失败，请检查错误日志。")

# --- Undo 相关函数 ---
def _get_tool_instance(api_type, api_config_path, update_config_path=None) -> ChannelToolBase | None:
    """根据 api_type 获取相应的工具实例"""
    try:
        if api_type == "newapi":
            return NewApiChannelTool(api_config_path, update_config_path)
        elif api_type == "voapi":
            return VoApiChannelTool(api_config_path, update_config_path)
        else:
            logging.error(f"未知的 API 类型: {api_type}")
            return None
    except ValueError as e: # 配置加载错误
        logging.error(f"为 API 类型 '{api_type}' 加载配置时出错: {e}")
        return None
    except Exception as e:
        logging.error(f"创建 API 类型 '{api_type}' 的工具实例时出错: {e}", exc_info=True)
        return None

async def save_undo_data(api_type, api_config_path, update_config_path):
    """
    获取当前匹配渠道的状态并保存以供撤销。
    应在执行更新前调用。
    返回保存的 undo 文件路径 (Path 对象) 或 None。
    """
    logging.info("开始保存撤销数据...")
    tool_instance = _get_tool_instance(api_type, api_config_path, update_config_path)
    if not tool_instance:
        logging.error("无法获取工具实例，无法保存撤销数据。")
        return None

    # 1. 获取所有渠道
    all_channels = tool_instance.get_all_channels() # 这是同步的
    if all_channels is None:
        logging.error("获取所有渠道失败，无法保存撤销数据。")
        return None
    if not all_channels:
        logging.warning("渠道列表为空，无需保存撤销数据。")
        return None

    # 2. 过滤将要更新的渠道
    filtered_channels = tool_instance.filter_channels(all_channels)
    if not filtered_channels:
        logging.info("没有匹配筛选条件的渠道，无需保存撤销数据。")
        return None

    # 3. 获取这些渠道的当前详细状态
    channel_ids_to_fetch = [c.get('id') for c in filtered_channels if c.get('id')]
    if not channel_ids_to_fetch:
        logging.warning("匹配的渠道缺少 ID，无法获取详细信息以保存撤销数据。")
        return None

    logging.info(f"将获取 {len(channel_ids_to_fetch)} 个匹配渠道的当前状态以用于撤销...")
    tasks = [tool_instance.get_channel_details(channel_id) for channel_id in channel_ids_to_fetch]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    original_channels_data = []
    fetch_errors = 0
    for i, result in enumerate(results):
        channel_id = channel_ids_to_fetch[i]
        if isinstance(result, dict):
            original_channels_data.append(result)
        else:
            fetch_errors += 1
            logging.error(f"获取渠道 {channel_id} 的原始状态失败: {result}")

    if fetch_errors > 0:
        logging.warning(f"{fetch_errors} 个渠道的原始状态获取失败，这些渠道将无法通过此文件撤销。")

    if not original_channels_data:
        logging.error("未能成功获取任何匹配渠道的原始状态，无法保存撤销数据。")
        return None

    # 4. 保存到文件
    undo_dir = Path(UNDO_DIR)
    try:
        undo_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logging.error(f"创建撤销数据目录 '{UNDO_DIR}' 失败: {e}")
        return None

    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S%f")[:-3]
    config_name = Path(api_config_path).stem # 从文件名提取配置名
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

async def perform_undo(api_type, api_config_path, undo_file_path, auto_confirm=False):
     """
     执行撤销操作。
     读取 undo 文件，并将其中记录的渠道恢复到原始状态。
     返回退出码 (0 表示成功)。
     """
     logging.info(f"开始执行撤销操作，使用文件: {undo_file_path}")
     tool_instance = _get_tool_instance(api_type, api_config_path) # 撤销时不需要 update_config
     if not tool_instance:
         logging.error("无法获取工具实例，无法执行撤销。")
         return 1

     # 1. 读取撤销文件
     try:
         with open(undo_file_path, 'r', encoding='utf-8') as f:
             original_channels_data = json.load(f)
         if not isinstance(original_channels_data, list):
             logging.error(f"撤销文件 '{undo_file_path}' 格式错误：顶层应为列表。")
             return 1
         if not original_channels_data:
              logging.warning(f"撤销文件 '{undo_file_path}' 为空，无需执行操作。")
              return 0
     except FileNotFoundError:
         logging.error(f"撤销文件未找到: {undo_file_path}")
         return 1
     except json.JSONDecodeError as e:
         logging.error(f"撤销文件格式错误: {undo_file_path} - {e}")
         return 1
     except Exception as e:
         logging.error(f"读取撤销文件失败: {undo_file_path} - {e}")
         return 1

     logging.info(f"将尝试恢复 {len(original_channels_data)} 个渠道的状态...")

     # 2. 并发执行恢复操作
     tasks = []
     valid_channels_for_undo = []
     for original_data in original_channels_data:
         if isinstance(original_data, dict) and 'id' in original_data:
             tasks.append(tool_instance.update_channel_api(original_data)) # 使用原始数据调用更新 API
             valid_channels_for_undo.append(original_data.get('id'))
         else:
             logging.warning(f"跳过撤销文件中无效的渠道数据项: {original_data}")

     if not tasks:
         logging.error("撤销文件中没有有效的渠道数据可供恢复。")
         return 1

     results = await asyncio.gather(*tasks, return_exceptions=True)

     # 3. 处理结果
     success_count = sum(1 for r in results if isinstance(r, bool) and r)
     fail_count = len(results) - success_count

     logging.info(f"撤销操作完成: {success_count} 个成功, {fail_count} 个失败。")

     if fail_count > 0:
         logging.error(f"{fail_count} 个渠道恢复失败，请检查之前的错误日志。")
         for i, result in enumerate(results):
             if not isinstance(result, bool) or not result:
                  failed_channel_id = valid_channels_for_undo[i]
                  logging.error(f"  - 渠道 ID {failed_channel_id} 恢复失败: {result}")
         return 1 # 部分失败
     else:
         logging.info("所有渠道状态已成功恢复。")
         # 成功撤销后，可以考虑删除或归档该撤销文件
         try:
              # undo_file_path.unlink() # 暂时不自动删除
              # logging.info(f"已删除使用过的撤销文件: {undo_file_path}")
              pass
         except Exception as e:
              logging.warning(f"删除撤销文件 '{undo_file_path}' 失败: {e}")
         return 0 # 全部成功

def find_latest_undo_file():
    """查找 undo_data 目录下最新的撤销文件。"""
    undo_dir = Path(UNDO_DIR)
    if not undo_dir.is_dir():
        logging.debug(f"撤销目录 '{undo_dir}' 不存在。")
        return None
    undo_files = list(undo_dir.glob("undo_*.json"))
    if not undo_files:
        logging.debug(f"在 '{undo_dir}' 中未找到 undo_*.json 文件。")
        return None
    try:
        undo_files.sort(key=lambda f: f.stat().st_mtime)
        latest_file = undo_files[-1]
        logging.debug(f"找到最新的撤销文件: {latest_file}")
        return latest_file
    except Exception as e:
        logging.error(f"查找最新撤销文件时出错: {e}")
        return None


# --- 主执行函数 (更新流程) ---
async def run_update_tool(args):
    """主执行流程，用于更新或 Dry Run"""
    exit_code = 0
    tool_instance = _get_tool_instance(args.api_type, args.connection_config, UPDATE_CONFIG_PATH)
    if not tool_instance:
        return 1 # 错误已在 _get_tool_instance 中记录

    # --- 检查更新配置文件 (虽然 tool_instance 加载了，但主流程也明确检查下) ---
    update_config_file = Path(UPDATE_CONFIG_PATH)
    if not update_config_file.is_file():
        logging.error(f"错误：更新配置文件 '{UPDATE_CONFIG_PATH}' 不存在。")
        return 1

    # --- 备份更新配置 & 保存撤销数据 ---
    undo_file_path_saved = None
    if not args.dry_run:
        if not backup_update_config():
            logging.warning("Update config 备份失败，但将继续执行工具。")
            if not args.yes:
                try:
                    confirm_continue = input("备份失败，是否仍要继续执行更新？(y/n): ").lower()
                    if confirm_continue != 'y':
                        print("操作已取消。")
                        return 0
                except EOFError:
                     print("\n操作已取消。")
                     return 0
            else:
                logging.info("自动确认模式：即使备份失败也继续执行。")

        # 保存撤销数据 (在备份之后，执行之前)
        # 注意：save_undo_data 需要 api_type, api_config_path, update_config_path
        undo_file_path_saved = await save_undo_data(args.api_type, args.connection_config, UPDATE_CONFIG_PATH)
        if not undo_file_path_saved: # save_undo_data 返回 None 表示失败
            logging.warning("未能成功保存撤销数据，如果执行更新将无法撤销。")
            # 考虑是否需要在此处停止？目前不停止

    else: # Dry run 模式
        logging.info("Dry run 模式：跳过备份 update_config.json 和保存撤销数据。")


    # --- 执行核心工具 (或 Dry Run) ---
    if args.dry_run:
        logging.info("="*10 + " Dry Run 模式启动 " + "="*10)
        logging.info("将模拟执行流程，不会实际更新任何渠道。")
        print("\n--- Dry Run 模式 ---")
        print("将显示会被筛选并计划更新的渠道信息，但不会发送实际请求。")

    logging.info(f"准备使用 '{Path(args.connection_config).name}' 和 '{UPDATE_CONFIG_PATH}' 为 '{args.api_type}' 类型的 API 执行更新{' (Dry Run)' if args.dry_run else ''}...")

    try:
        # 直接调用 tool_instance 的 run_updates 方法
        exit_code = await tool_instance.run_updates(dry_run=args.dry_run)

    except Exception as e:
        # run_updates 内部应该已经处理了大部分错误并返回了 exit_code
        # 这里捕获未预料的错误
        logging.error(f"执行更新流程时发生意外错误: {e}", exc_info=True)
        exit_code = 3 # 未知严重错误

    finally:
        # --- 清理更新配置 (可选, Dry run 模式不清理) ---
        print("\n--- 操作完成 ---")
        if not args.dry_run and exit_code == 0: # 仅在非 dry run 且成功时清理
            ask_and_clear_update_config(force_clear=args.clear_config, auto_confirm=args.yes)
        elif args.dry_run:
            logging.info("Dry run 模式：跳过清理 update_config.json。")
            print("Dry run 模式：未执行清理操作。")
        else: # 更新失败或部分失败
             logging.info("更新未完全成功，跳过清理 update_config.json。")
             print("更新未完全成功，未执行清理操作。")


    # 如果保存了撤销数据，给出提示
    if undo_file_path_saved:
         logging.info(f"撤销数据已保存到: {undo_file_path_saved}")
         print(f"\n提示：如果需要撤销本次操作，请使用 --undo 参数并选择相同的连接配置和 API 类型。")
         print(f"撤销文件: {undo_file_path_saved.name}")
    elif not args.dry_run:
         logging.warning("本次操作未成功保存撤销数据，无法使用 --undo 撤销。")


    return exit_code

# --- 顶层异步封装 ---
async def main_async_wrapper(args):
    """异步包装器，用于调用 run_update_tool 或 perform_undo"""
    final_exit_code = 0
    if args.undo:
        # --- 执行撤销 ---
        logging.info("开始执行撤销操作...")
        print("\n--- 撤销模式 ---")
        # 撤销也需要连接配置和 API 类型
        undo_connection_config_path = None
        if args.connection_config:
             config_path = Path(args.connection_config)
             if config_path.is_file():
                 undo_connection_config_path = str(config_path)
             else:
                  logging.error(f"错误：撤销操作指定的连接配置文件不存在: {args.connection_config}")
                  return 1 # 返回错误码
        else:
             available_configs = list_connection_configs()
             if not available_configs: return 1
             selected_path = select_config(available_configs, auto_confirm=args.yes)
             if not selected_path: return 0
             undo_connection_config_path = str(selected_path)

        undo_api_type = None
        if args.api_type:
             if args.api_type in ["newapi", "voapi"]:
                 undo_api_type = args.api_type
             else:
                  logging.error(f"错误：撤销操作指定的 API 类型无效: {args.api_type}")
                  return 1
        else:
             undo_api_type = select_api_type(auto_confirm=args.yes)
             if not undo_api_type: return 0

        latest_undo_file = find_latest_undo_file()
        if not latest_undo_file:
            logging.error("错误：在 '{UNDO_DIR}' 目录下未找到实际保存的撤销文件。")
            print(f"错误：未找到撤销文件，无法执行撤销操作。请先成功执行一次更新。")
            final_exit_code = 1
        else:
            # 检查找到的撤销文件是否与当前选择的 API 类型和连接配置（文件名中包含）匹配
            expected_stem_part = f"{undo_api_type}_{Path(undo_connection_config_path).stem}"
            if expected_stem_part not in latest_undo_file.stem:
                 logging.warning(f"找到的最新撤销文件 '{latest_undo_file.name}' 可能不匹配当前选择的 API 类型 ({undo_api_type}) 或连接配置 ({Path(undo_connection_config_path).stem})。")
                 print(f"警告：找到的最新撤销文件 '{latest_undo_file.name}' 可能不适用于当前选择。")
                 if not args.yes:
                     try:
                         confirm_mismatch = input("仍要尝试使用此文件进行撤销吗？(y/n): ").lower()
                         if confirm_mismatch != 'y':
                             print("撤销操作已取消。")
                             return 0 # 用户取消
                     except EOFError:
                          print("\n撤销操作已取消。")
                          return 0

            logging.info(f"找到最新的撤销文件: {latest_undo_file}")
            print(f"将使用文件 '{latest_undo_file.name}' 进行撤销。")
            confirmed_undo = False
            if not args.yes:
                try:
                    confirm = input("确认要执行撤销操作吗？这将覆盖当前渠道状态。(y/n): ").lower()
                    if confirm == 'y':
                        confirmed_undo = True
                    else:
                        print("撤销操作已取消。")
                except EOFError:
                     print("\n撤销操作已取消。")
            else:
                confirmed_undo = True
                logging.info("自动确认模式：执行撤销操作。")

            if confirmed_undo:
                # 调用实际的撤销函数
                final_exit_code = await perform_undo(undo_api_type, undo_connection_config_path, latest_undo_file, args.yes)
    else:
        # --- 执行正常更新或 Dry Run ---
        # 确保传递 connection_config 路径给 run_update_tool
        if not args.connection_config: # 如果是交互模式选择的
             available_configs = list_connection_configs()
             if not available_configs: return 1
             selected_path = select_config(available_configs, auto_confirm=args.yes)
             if not selected_path: return 0
             args.connection_config = str(selected_path)
        if not args.api_type: # 如果是交互模式选择的
             args.api_type = select_api_type(auto_confirm=args.yes)
             if not args.api_type: return 0

        final_exit_code = await run_update_tool(args) # 调用更新流程函数

    return final_exit_code


# --- 程序入口 ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="One API 渠道批量更新工具",
        formatter_class=argparse.RawTextHelpFormatter
    )
    # --- 操作模式参数组 ---
    mode_group = parser.add_argument_group('运行模式 (选择一种)')
    mode_action = mode_group.add_mutually_exclusive_group() # 确保 --update 和 --undo 互斥
    mode_action.add_argument(
        "--update",
        action="store_true",
        help="执行更新操作 (默认行为)。"
    )
    mode_action.add_argument(
        "--undo",
        action="store_true",
        help="执行撤销操作，恢复到上次执行更新前的状态。\n需要选择或指定连接配置和 API 类型。"
    )

    # --- 更新/撤销共享参数 ---
    shared_group = parser.add_argument_group('更新/撤销目标')
    shared_group.add_argument(
        "--connection-config",
        metavar="<path>",
        help=f"指定连接配置文件的路径。\n(例如: {CONNECTION_CONFIG_DIR}/my_config.json)\n如果未提供，将进入交互模式选择。"
    )
    shared_group.add_argument(
        "--api-type",
        choices=["newapi", "voapi"],
        help="指定目标 One API 的类型。\n如果未提供，将进入交互模式选择。"
    )

    # --- 更新特定参数 ---
    update_group = parser.add_argument_group('更新选项 (仅在 --update 模式下有效)')
    update_group.add_argument(
        "--clear-config",
        action="store_true",
        help=f"在更新成功完成后，使用 '{CLEAN_UPDATE_CONFIG_PATH}'\n覆盖 '{UPDATE_CONFIG_PATH}'。"
    )
    update_group.add_argument(
        "--dry-run",
        action="store_true",
        help="执行模拟更新，显示将要更新的渠道和更改，\n但不实际执行 API 调用、备份、保存撤销或清理配置。"
    )

    # --- 通用控制参数 ---
    control_group = parser.add_argument_group('通用控制')
    control_group.add_argument(
        "-y", "--yes",
        action="store_true",
        help="自动确认所有提示 (用于非交互式运行)。"
    )

    # --- 日志参数组 ---
    log_group = parser.add_argument_group('日志选项')
    log_group.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="设置日志记录级别 (默认为 INFO)。"
    )
    log_group.add_argument(
        "--log-file",
        metavar="<path>",
        default=None, # 由后续逻辑处理默认值
        help=f"指定日志文件的具体路径或目录。\n默认为在 '{LOGS_DIR}/' 目录下创建带时间戳的日志文件\n(例如: {LOGS_DIR}/{DEFAULT_LOG_FILE_BASENAME.replace('.log', '')}_YYYY-MM-DD-HHMMSSmmm.log)。\n如果提供空字符串 '' 或 'none'，则不写入文件。"
    )


    args = parser.parse_args()

    # 如果用户未明确指定 --update 或 --undo，则默认为 --update
    if not args.undo and not args.update:
        args.update = True

    # 如果是 undo 模式，禁用 dry-run 和 clear-config
    if args.undo:
        if args.dry_run:
            print("警告：--dry-run 在 --undo 模式下无效，将被忽略。")
            args.dry_run = False
        if args.clear_config:
            print("警告：--clear-config 在 --undo 模式下无效，将被忽略。")
            args.clear_config = False


    # *** 确定并设置日志文件路径 ***
    log_dir_path = Path(LOGS_DIR)
    log_file_path_to_use = None
    disable_file_logging = args.log_file is not None and args.log_file.lower() in ["", "none"]

    if not disable_file_logging:
        try:
            log_dir_path.mkdir(parents=True, exist_ok=True) # 确保日志目录存在

            if args.log_file: # 用户指定了 --log-file 参数 (且不是空或none)
                log_arg_path = Path(args.log_file)
                if log_arg_path.is_dir(): # 如果指定的是目录
                    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S%f")[:-3]
                    log_filename = f"{DEFAULT_LOG_FILE_BASENAME.replace('.log', '')}_{timestamp}.log"
                    log_file_path_to_use = log_arg_path / log_filename
                else: # 用户指定了具体的文件路径
                    log_file_path_to_use = log_arg_path
                    log_file_path_to_use.parent.mkdir(parents=True, exist_ok=True)
            else: # 用户未指定 --log-file，使用默认行为
                timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S%f")[:-3]
                log_filename = f"{DEFAULT_LOG_FILE_BASENAME.replace('.log', '')}_{timestamp}.log"
                log_file_path_to_use = log_dir_path / log_filename

        except Exception as e:
             print(f"[ERROR] 处理日志路径时出错: {e}")
             log_file_path_to_use = None # 出错则不写入文件

    # *** 设置日志记录器 ***
    setup_logging(args.log_level, log_file_path_to_use)

    # 记录启动信息
    logging.info("="*20 + " Channel Updater 启动 " + "="*20)
    logging.info(f"命令行参数: {vars(args)}")
    if log_file_path_to_use:
        logging.info(f"日志将记录到文件: {log_file_path_to_use}")
    elif disable_file_logging:
        logging.info("已禁用文件日志记录。")
    else:
        logging.info("未指定日志文件或写入失败，日志仅输出到控制台。")

    # --- 交互式 Dry Run 询问 (仅在执行更新操作时) ---
    is_update_mode = args.update # 使用明确的标志
    is_fully_interactive_update = is_update_mode and not (
        args.connection_config or
        args.api_type or
        args.dry_run or # 如果命令行指定了 dry-run，则不问
        args.yes
    )
    if is_fully_interactive_update:
        try:
            dry_run_choice = input("\n是否要执行 Dry Run (模拟运行，不实际更改)? (y/n): ").lower()
            if dry_run_choice == 'y':
                args.dry_run = True # 在交互模式下启用 dry_run
                logging.info("用户选择在交互模式下执行 Dry Run。")
                print("将执行 Dry Run 模式。")
            else:
                logging.info("用户选择执行实际更新。")
                print("将执行实际更新。")
        except EOFError:
            print("\n操作已取消。")
            sys.exit(0)


    # --- 运行主逻辑或撤销逻辑 ---
    exit_status = 0
    try:
        # 使用 asyncio.run() 运行顶层异步函数
        exit_status = asyncio.run(main_async_wrapper(args))

    except KeyboardInterrupt:
        logging.warning("用户中断操作 (Ctrl+C)。")
        print("\n操作已由用户中断。")
        exit_status = 130
    except Exception as e:
        logging.critical(f"脚本顶层发生未捕获的严重错误: {e}", exc_info=True)
        log_dest = f"日志 '{log_file_path_to_use}'" if log_file_path_to_use else "控制台输出"
        print(f"\n发生严重错误，请检查{log_dest}。")
        exit_status = 3
    finally:
        logging.info("="*20 + " Channel Updater 结束 " + "="*20 + "\n")
        sys.exit(exit_status)