# -*- coding: utf-8 -*-
"""
封装跨站点操作的流程。
"""
import copy
import json
import logging
from pathlib import Path
import asyncio # Needed for async function definition and gather
from asyncio import Semaphore # 需要用于并发控制
import yaml # type: ignore # 需要用于更具体的 YAML 错误处理

# 从项目模块导入 (使用包内绝对导入)
from channel_manager_lib.config_utils import CROSS_SITE_ACTION_CONFIG_PATH, load_yaml_config, CONNECTION_CONFIG_DIR # 修正常量名
from channel_manager_lib.undo_utils import _get_tool_instance # 导入工具实例化函数
from channel_manager_lib.undo_utils import save_undo_data # 导入保存撤销数据的函数
# 基础工具类和具体工具类不再需要直接导入，因为 _get_tool_instance 处理了实例化
# from oneapi_tool_utils.channel_tool_base import ChannelToolBase
# from oneapi_tool_utils.newapi_channel_tool import NewApiChannelTool
# from oneapi_tool_utils.voapi_channel_tool import VoApiChannelTool


async def run_cross_site_operation(args, action: str, script_config: dict) -> int:
    """
    执行跨站点渠道操作的核心逻辑，支持基于灵活筛选器的源/目标选择。

    Args:
        args: 解析后的命令行参数对象 (需要 .yes).
        action (str): 要执行的操作 ('copy_fields', 'compare_fields', 'compare_channel_counts').
        script_config (dict): 已加载的脚本通用配置。

    Returns:
        int: 退出码 (0 表示成功, 1 表示失败)。
    """
    logging.info(f"开始执行跨站点操作: {action}")
    print(f"\n--- 执行跨站点操作: {action} ---")

    # 1. 加载跨站点操作配置
    try:
        cross_site_config = load_yaml_config(CROSS_SITE_ACTION_CONFIG_PATH)
        if not cross_site_config:
            logging.error(f"错误：跨站点动作配置文件 '{CROSS_SITE_ACTION_CONFIG_PATH}' 为空或加载失败。")
            print(f"错误：请检查跨站点动作配置文件 '{CROSS_SITE_ACTION_CONFIG_PATH}' 的内容。")
            return 1
    except FileNotFoundError:
        logging.error(f"错误：跨站点动作配置文件 '{CROSS_SITE_ACTION_CONFIG_PATH}' 未找到。")
        print(f"错误：文件 '{CROSS_SITE_ACTION_CONFIG_PATH}' 不存在。请根据 cross_site_action.example 创建该文件。")
        return 1
    except Exception as e:
        # 捕获可能的解析错误
        try:
            # import yaml # type: ignore # 已移到文件顶部
            if isinstance(e, yaml.YAMLError):
                 logging.error(f"解析跨站点动作配置文件 '{CROSS_SITE_ACTION_CONFIG_PATH}' 时发生 YAML 错误: {e}", exc_info=True)
                 print(f"错误：解析 '{CROSS_SITE_ACTION_CONFIG_PATH}' 时出错。请检查 YAML 语法。")
            else:
                 raise e # 重新抛出非 YAML 错误
        except ImportError:
             # 如果 yaml 库未安装
             logging.error(f"加载或解析 '{CROSS_SITE_ACTION_CONFIG_PATH}' 时发生未知错误（且 PyYAML 未安装）: {e}", exc_info=True)
             print(f"错误：加载或解析 '{CROSS_SITE_ACTION_CONFIG_PATH}' 时出错。请检查文件内容和日志（可能需要安装 PyYAML）。")
        except Exception as e: # 捕获其他可能的异常
             logging.error(f"加载或解析 '{CROSS_SITE_ACTION_CONFIG_PATH}' 时发生未知错误: {e}", exc_info=True)
             print(f"错误：加载或解析 '{CROSS_SITE_ACTION_CONFIG_PATH}' 时出错。请检查文件内容和日志。")
        return 1

    # 2. 提取并验证源/目标配置和 action 参数
    source_config = cross_site_config.get('source')
    target_config = cross_site_config.get('target')
    action_params = cross_site_config.get(f'{action}_params', {}) # 获取对应 action 的参数

    if not source_config or not target_config:
        logging.error(f"错误：'{CROSS_SITE_ACTION_CONFIG_PATH}' 中必须包含 'source' 和 'target' 配置块。")
        print(f"错误：请在 '{CROSS_SITE_ACTION_CONFIG_PATH}' 中完整配置 'source' 和 'target'。")
        return 1

    source_config_ref = source_config.get('connection_config')
    target_config_ref = target_config.get('connection_config')
    source_filter_config = source_config.get('channel_filter', {}) # 默认为空字典，不过滤
    target_filter_config = target_config.get('channel_filter', {}) # 默认为空字典

    if not source_config_ref or not target_config_ref:
        logging.error(f"错误：'source' 和 'target' 配置块中必须包含 'connection_config'。")
        print(f"错误：请在 '{CROSS_SITE_ACTION_CONFIG_PATH}' 的 'source' 和 'target' 中指定 'connection_config'。")
        return 1

    # 验证 action 特定参数
    fields_to_copy = []
    fields_to_compare = []
    copy_mode = "overwrite" # 默认值

    if action == "copy_fields":
        fields_to_copy = action_params.get('fields_to_copy')
        copy_mode = action_params.get('copy_mode', 'overwrite') # 保留默认值
        if not fields_to_copy or not isinstance(fields_to_copy, list):
            logging.error(f"错误：操作 'copy_fields' 需要一个非空的 'fields_to_copy' 列表参数。")
            print(f"错误：请在 '{CROSS_SITE_ACTION_CONFIG_PATH}' 的 'copy_fields_params' 中配置 'fields_to_copy'。")
            return 1
        if copy_mode not in ["overwrite", "append", "remove", "merge", "delete_keys"]:
             logging.warning(f"配置的 copy_mode '{copy_mode}' 不是预设支持的模式，可能会导致字段处理跳过。")
             # 不直接退出，因为不同字段类型支持不同模式
        logging.info(f"操作参数 (copy_fields): 待复制字段={fields_to_copy}, 复制模式={copy_mode}")
    elif action == "compare_fields":
        fields_to_compare = action_params.get('fields_to_compare')
        if not fields_to_compare or not isinstance(fields_to_compare, list):
            logging.error(f"错误：操作 'compare_fields' 需要一个非空的 'fields_to_compare' 列表参数。")
            print(f"错误：请在 '{CROSS_SITE_ACTION_CONFIG_PATH}' 的 'compare_fields_params' 中配置 'fields_to_compare'。")
            return 1
        logging.info(f"操作参数 (compare_fields): 待比较字段={fields_to_compare}")
    elif action == "compare_channel_counts":
        logging.info(f"操作参数 (compare_channel_counts): 无需额外参数。")
    # CLI Handler 应该已经阻止了未知 action

    # 3. 加载连接配置并获取 API 类型
    try:
        source_config_path = CONNECTION_CONFIG_DIR / f"{source_config_ref}.yaml"
        target_config_path = CONNECTION_CONFIG_DIR / f"{target_config_ref}.yaml"

        source_conn_config = load_yaml_config(source_config_path)
        source_api_type = source_conn_config.get('api_type')
        if not source_api_type or source_api_type not in ["newapi", "voapi"]:
            logging.error(f"错误：源连接配置文件 '{source_config_path}' 中缺少有效 'api_type' (newapi 或 voapi)。")
            print(f"错误：源连接配置文件 '{Path(source_config_path).name}' 中缺少有效 'api_type'。")
            return 1

        target_conn_config = load_yaml_config(target_config_path)
        target_api_type = target_conn_config.get('api_type')
        if not target_api_type or target_api_type not in ["newapi", "voapi"]:
            logging.error(f"错误：目标连接配置文件 '{target_config_path}' 中缺少有效 'api_type' (newapi 或 voapi)。")
            print(f"错误：目标连接配置文件 '{Path(target_config_path).name}' 中缺少有效 'api_type'。")
            return 1
        logging.info(f"源 API 类型: {source_api_type} ({source_config_ref}), 目标 API 类型: {target_api_type} ({target_config_ref})")
        logging.info(f"源渠道筛选器: {source_filter_config}")
        logging.info(f"目标渠道筛选器: {target_filter_config}")

    except FileNotFoundError as e:
         logging.error(f"加载连接配置时文件未找到: {e}")
         print(f"错误：无法找到连接配置文件 '{e.filename}'。请确认 '{CROSS_SITE_ACTION_CONFIG_PATH}' 中的名称与 '{CONNECTION_CONFIG_DIR}' 下的文件名匹配。")
         return 1
    except (ValueError) as e: # load_yaml_config 可能抛出 ValueError
        logging.error(f"加载连接配置时出错: {e}")
        print(f"错误：加载连接配置文件时出错。请检查相关 YAML 文件内容。")
        return 1
    except Exception as e:
        logging.error(f"加载连接配置时发生意外错误: {e}", exc_info=True)
        print(f"错误：加载连接配置时发生意外错误。")
        return 1


    # 4. 创建源/目标工具实例
    # _get_tool_instance 的第三个参数 update_config_path 在跨站操作中通常不需要，传 None
    source_tool = _get_tool_instance(source_api_type, str(source_config_path), None, script_config=script_config)
    target_tool = _get_tool_instance(target_api_type, str(target_config_path), None, script_config=script_config)
    if not source_tool or not target_tool:
        logging.error("无法创建源或目标工具实例。")
        print("错误：无法初始化 API 工具实例。")
        return 1

    # 5. 获取源和目标渠道列表
    source_channels_all = None
    target_channels_all = None
    source_channel_data = None # 将在 copy_fields/compare_fields 中根据筛选结果设置
    matched_target_channels = [] # 将在 copy_fields/compare_fields 中根据筛选结果设置

    try:
        logging.info("开始异步获取源和目标站点的所有渠道列表...")
        # 并发获取源和目标列表
        # TODO: 确认 get_all_channels 是 async 方法
        results = await asyncio.gather(
            source_tool.get_all_channels(),
            target_tool.get_all_channels(),
            return_exceptions=True # 捕获单个任务的异常，而不是让 gather 失败
        )

        # 处理源结果
        if isinstance(results[0], Exception):
            logging.error(f"获取源渠道列表时发生异常: {results[0]}", exc_info=results[0])
            print(f"错误：获取源渠道列表失败。详情请查看日志。")
            return 1
        else:
            source_channels_all, msg_src = results[0]
            if source_channels_all is None:
                logging.error(f"获取源渠道列表失败: {msg_src}")
                print(f"错误：获取源渠道列表失败: {msg_src}")
                return 1
            logging.info(f"源站点 ({source_config_ref}) 共获取 {len(source_channels_all)} 个渠道。")

        # 处理目标结果
        if isinstance(results[1], Exception):
            logging.error(f"获取目标渠道列表时发生异常: {results[1]}", exc_info=results[1])
            print(f"错误：获取目标渠道列表失败。详情请查看日志。")
            return 1
        else:
            target_channels_all, msg_tgt = results[1]
            if target_channels_all is None:
                logging.error(f"获取目标渠道列表失败: {msg_tgt}")
                print(f"错误：获取目标渠道列表失败: {msg_tgt}")
                return 1
            logging.info(f"目标站点 ({target_config_ref}) 共获取 {len(target_channels_all)} 个渠道。")

        # 如果是需要筛选的操作 (copy_fields, compare_fields)
        if action in ["copy_fields", "compare_fields"]:
            logging.info("开始筛选源渠道...")
            # 假设 _filter_channels 是一个内部方法，接受 channel 列表和 filter 配置
            # 注意：这个方法需要添加到 ChannelToolBase 或其子类中
            # TODO: 确保 ChannelTool 类有 _filter_channels(self, channels: list, filters: dict) 方法
            try:
                # 我们需要将 filter 配置传递给工具实例，以便 filter_channels 使用
                # 或者 ChannelToolBase.filter_channels 需要接受 filter 配置作为参数
                # 暂时修改为后者，即 filter_channels(channels, filter_config)
                # TODO: 检查并调整 ChannelToolBase.filter_channels 的签名和实现
                matched_source_channels = source_tool.filter_channels(source_channels_all, source_filter_config)
            except AttributeError:
                 # 如果 filter_channels 不存在或不接受第二个参数，会触发此错误
                 logging.error(f"内部错误：源工具实例 ({type(source_tool).__name__}) 的 'filter_channels' 方法不符合预期（需要接受筛选配置）。")
                 print(f"错误：代码内部错误，源 API 工具的筛选功能不兼容。")
                 return 1
            except Exception as filter_e:
                 logging.error(f"筛选源渠道时出错: {filter_e}", exc_info=True)
                 print(f"错误：筛选源渠道时发生内部错误。")
                 return 1

            if not matched_source_channels:
                logging.error(f"错误：源筛选器未匹配到任何渠道。筛选器: {json.dumps(source_filter_config, ensure_ascii=False)}")
                print(f"错误：源筛选器未匹配到任何渠道。请检查 '{CROSS_SITE_ACTION_CONFIG_PATH}' 中的 source.channel_filter。")
                return 1
            elif len(matched_source_channels) > 1:
                num_matched = len(matched_source_channels)
                logging.warning(f"源筛选器匹配到 {num_matched} 个渠道。根据规则，将使用第一个匹配的渠道 (ID: {matched_source_channels[0].get('id')}, Name: '{matched_source_channels[0].get('name')}') 作为配置源。")
                print(f"\n注意：源筛选器匹配到 {num_matched} 个渠道，将使用第一个作为源:")
                print(f"  - ID: {matched_source_channels[0].get('id', 'N/A'):<4} Name: '{matched_source_channels[0].get('name', 'N/A')}'")
                source_channel_data = matched_source_channels[0]
            else:
                source_channel_data = matched_source_channels[0]
                logging.info(f"源筛选器精确匹配到一个渠道: ID={source_channel_data.get('id')}, Name='{source_channel_data.get('name')}'")
                print(f"源渠道: ID={source_channel_data.get('id', 'N/A'):<4} Name='{source_channel_data.get('name', 'N/A')}'")

            logging.info("开始筛选目标渠道...")
            try:
                # TODO: 同样需要检查 target_tool.filter_channels
                matched_target_channels = target_tool.filter_channels(target_channels_all, target_filter_config)
            except AttributeError:
                 logging.error(f"内部错误：目标工具实例 ({type(target_tool).__name__}) 的 'filter_channels' 方法不符合预期（需要接受筛选配置）。")
                 print(f"错误：代码内部错误，目标 API 工具的筛选功能不兼容。")
                 return 1
            except Exception as filter_e:
                 logging.error(f"筛选目标渠道时出错: {filter_e}", exc_info=True)
                 print(f"错误：筛选目标渠道时发生内部错误。")
                 return 1

            if not matched_target_channels:
                 # 对于 copy_fields 和 compare_fields，如果目标列表为空，操作无意义
                 logging.warning(f"目标筛选器未匹配到任何渠道。筛选器: {json.dumps(target_filter_config, ensure_ascii=False)}")
                 print(f"\n警告：目标筛选器未匹配到任何渠道。无法执行 '{action}' 操作。")
                 # 返回 0 表示操作完成，但无事可做
                 return 0
            else:
                 logging.info(f"目标筛选器匹配到 {len(matched_target_channels)} 个渠道。")
                 print(f"目标筛选器匹配到 {len(matched_target_channels)} 个渠道。")
                 # 不需要选择第一个，后续逻辑会处理列表

    except Exception as e:
        # 捕获 gather 之外或处理过程中的其他异常
        logging.error(f"获取或筛选渠道时发生未预料的错误: {e}", exc_info=True)
        print(f"错误：获取或筛选渠道时发生意外错误。")
        return 1

    # 6. 根据 action 执行核心逻辑
    if action == "compare_channel_counts":
        # --- 比较渠道数量逻辑 ---
        # Ensure we have the counts (should have been fetched in step 5)
        if source_channels_all is None or target_channels_all is None:
             logging.error("内部错误: compare_channel_counts 需要有效的渠道列表，但未能获取。")
             print("错误：未能获取一个或两个站点的渠道列表以进行数量比较。")
             return 1
        print("\n--- 渠道数量比较结果 ---")
        source_count = len(source_channels_all) if source_channels_all is not None else "获取失败"
        target_count = len(target_channels_all) if target_channels_all is not None else "获取失败"
        print(f"源站点 ({Path(source_config_path).name}): {source_count} 个渠道")
        print(f"目标站点 ({Path(target_config_path).name}): {target_count} 个渠道")
        if isinstance(source_count, int) and isinstance(target_count, int):
             if source_count == target_count:
                 print("渠道数量相同。")
             else:
                 print(f"渠道数量不同 (相差 {abs(source_count - target_count)} 个)。")
        print("------------------------")
        return 0 # 比较数量总是成功返回

    elif action == "copy_fields":
        # --- 复制字段逻辑 (增强版) ---
        if source_channel_data is None:
            logging.error("内部错误: copy_fields 无法执行，因为未能确定唯一的源渠道数据。")
            return 1
        if not matched_target_channels:
             logging.info("没有匹配的目标渠道，无需执行 copy_fields。")
             print("没有匹配到需要更新的目标渠道。")
             return 0

        # 1. 准备更新计划
        update_plan = []
        # 提取源值，排除 id/key。这些值将在循环外标准化一次（如果需要）
        source_data_to_copy = {field: source_channel_data.get(field) for field in fields_to_copy if field not in ['id', 'key']}

        logging.info(f"将使用源渠道 ID: {source_channel_data.get('id')}, Name: '{source_channel_data.get('name')}' 的数据进行复制。")
        logging.info(f"准备对 {len(matched_target_channels)} 个匹配的目标渠道计算更新计划...")

        # 定义字段类型 (这些可以在工具类中定义为常量或方法)
        # TODO: 将这些字段类型定义移到 ChannelToolBase 或 utils 中
        list_fields = ["models", "group", "tag"]
        dict_fields = ["model_mapping", "status_code_mapping", "setting", "headers", "override_params"]

        # 预先标准化源数据（用于列表和字典）
        normalized_source_data = {}
        source_name_for_log = source_channel_data.get('name', f"ID:{source_channel_data.get('id')}")
        try:
             for field, value in source_data_to_copy.items():
                 if field in list_fields:
                     # TODO: 确保 source_tool 有 _normalize_to_set 方法
                     normalized_source_data[field] = source_tool._normalize_to_set(value)
                 elif field in dict_fields:
                     # TODO: 确保 source_tool 有 _normalize_to_dict 方法
                     normalized_source_data[field] = source_tool._normalize_to_dict(value, field, source_name_for_log)
                 # else: 简单类型不需要预标准化
        except AttributeError as e:
             logging.error(f"标准化源渠道字段时缺少方法: {e}", exc_info=True)
             print(f"错误：代码内部错误，源工具缺少标准化方法 ({e})。无法准备更新计划。")
             return 1
        except Exception as norm_e:
             logging.error(f"标准化源渠道字段时出错: {norm_e}", exc_info=True)
             print(f"错误：标准化源渠道数据时出错，无法准备更新计划。")
             return 1

        # 遍历每个目标渠道，计算变更
        for target_channel in matched_target_channels:
            target_id = target_channel.get('id')
            target_name = target_channel.get('name')
            target_name_for_log = target_name or f"ID:{target_id}"
            logging.debug(f"开始为目标渠道 ID: {target_id}, Name: '{target_name}' 准备更新...")

            changes_summary = {} # 记录人类可读的变更
            payload_for_api = {'id': target_id} # API 更新通常只需要 ID 和变化的字段
            field_processing_errors = False # 标记此渠道是否有字段处理错误

            for field in fields_to_copy:
                 if field in ['id', 'key']: continue # 再次确认跳过

                 source_value = source_data_to_copy.get(field) # 原始源值，用于 delete_keys 等模式判断
                 original_target_value = target_channel.get(field)
                 field_changed = False
                 new_value = original_target_value # 默认不改变

                 try:
                     # --- 列表字段处理 ---
                     if field in list_fields:
                         # TODO: 确保 target_tool 有 _normalize_to_set 方法
                         current_target_set = target_tool._normalize_to_set(original_target_value)
                         source_set = normalized_source_data.get(field, set()) # 使用标准化的源值
                         resulting_set = current_target_set

                         if copy_mode == "overwrite":
                             if source_set != current_target_set: resulting_set = source_set; field_changed = True
                         elif copy_mode == "append":
                             resulting_set = current_target_set.union(source_set)
                             if resulting_set != current_target_set: field_changed = True
                         elif copy_mode == "remove":
                             resulting_set = current_target_set.difference(source_set)
                             if resulting_set != current_target_set: field_changed = True
                         else:
                             logging.debug(f"目标 {target_name_for_log}: 列表字段 '{field}' 不支持模式 '{copy_mode}'，跳过。")
                             continue
                         if field_changed:
                             try:
                                 new_value = target_tool.format_list_field_for_api(field, resulting_set)
                                 logging.debug(f"目标 {target_name_for_log}: 字段 '{field}' 格式化列表结果: {repr(new_value)}")
                             except AttributeError:
                                 logging.error(f"目标工具 {type(target_tool).__name__} 缺少 format_list_field_for_api 方法！")
                                 field_processing_errors = True; continue # 跳过此字段
                             except Exception as fmt_e:
                                 logging.error(f"格式化列表字段 '{field}' 时出错: {fmt_e}", exc_info=True)
                                 field_processing_errors = True; continue # 跳过此字段

                     # --- 字典字段处理 ---
                     elif field in dict_fields:
                         # TODO: 确保 target_tool 有 _normalize_to_dict 方法
                         current_target_dict = target_tool._normalize_to_dict(original_target_value, field, target_name_for_log)
                         source_dict = normalized_source_data.get(field, {}) # 使用标准化的源值
                         resulting_dict = current_target_dict.copy()

                         if copy_mode == "overwrite":
                              if source_dict != current_target_dict: resulting_dict = source_dict; field_changed = True
                         elif copy_mode == "merge":
                              temp_dict = current_target_dict.copy()
                              temp_dict.update(source_dict) # 合并，源覆盖目标
                              if temp_dict != current_target_dict: resulting_dict = temp_dict; field_changed = True
                         elif copy_mode == "delete_keys":
                              keys_to_delete = []
                              # delete_keys 使用的是原始 source_value (需要是列表或字符串)
                              if isinstance(source_value, list): keys_to_delete = source_value
                              elif isinstance(source_value, str): keys_to_delete = [k.strip() for k in source_value.split(',') if k.strip()]
                              else:
                                   logging.warning(f"目标 {target_name_for_log}: 字典字段 '{field}' 的 'delete_keys' 模式需源值为列表/字符串，收到 {type(source_value)}，跳过。")
                                   continue
                              original_len = len(resulting_dict)
                              deleted_keys_count = 0
                              for key in keys_to_delete:
                                   if key in resulting_dict:
                                        del resulting_dict[key]
                                        deleted_keys_count += 1
                              if deleted_keys_count > 0: field_changed = True # 只要删除了key就算改变
                         else:
                             logging.debug(f"目标 {target_name_for_log}: 字典字段 '{field}' 不支持模式 '{copy_mode}'，跳过。")
                             continue
                         if field_changed:
                             try:
                                 new_value = target_tool.format_dict_field_for_api(field, resulting_dict)
                                 logging.debug(f"目标 {target_name_for_log}: 字段 '{field}' 格式化字典结果: {repr(new_value)}")
                             except AttributeError:
                                 logging.error(f"目标工具 {type(target_tool).__name__} 缺少 format_dict_field_for_api 方法！")
                                 field_processing_errors = True; continue # 跳过此字段
                             except Exception as fmt_e:
                                 logging.error(f"格式化字典字段 '{field}' 时出错: {fmt_e}", exc_info=True)
                                 field_processing_errors = True; continue # 跳过此字段

                     # --- 简单字段处理 (仅支持 overwrite) ---
                     else:
                         if copy_mode == "overwrite":
                             # 直接比较原始值
                             if source_value != original_target_value:
                                 new_value = source_value
                                 field_changed = True
                         else:
                             logging.debug(f"目标 {target_name_for_log}: 简单字段 '{field}' 仅支持 'overwrite' 模式，模式 '{copy_mode}' 无效，跳过。")
                             continue

                     # --- 记录变更 ---
                     if field_changed:
                         try:
                              # 调用最终格式化方法，确保类型等符合 API 要求
                              formatted_new_value = target_tool.format_field_value_for_api(field, new_value)
                              logging.debug(f"目标 {target_name_for_log}: 字段 '{field}' 最终格式化值: {repr(formatted_new_value)}")
                         except AttributeError:
                              logging.error(f"目标工具 {type(target_tool).__name__} 缺少 format_field_value_for_api 方法！")
                              field_processing_errors = True; continue # 跳过此字段
                         except Exception as format_e:
                              logging.error(f"最终格式化字段 '{field}' 值时出错: {format_e}", exc_info=True)
                              field_processing_errors = True; continue # 跳过此字段

                         # 将最终格式化后的值放入 payload
                         payload_for_api[field] = formatted_new_value
                         # 变更摘要仍然使用处理过程中的 new_value，因为它更易读
                         change_str = f"'{repr(original_target_value)}' -> '{repr(new_value)}' ({copy_mode})"
                         changes_summary[field] = change_str
                         logging.debug(f"目标 {target_name_for_log}: 字段 '{field}' 将修改为: {change_str} (API值: {repr(formatted_new_value)})")

                 except AttributeError as e:
                      # 捕获 _normalize 或 format 方法缺失
                      logging.error(f"处理目标 {target_name_for_log} 字段 '{field}' 时缺少方法: {e}", exc_info=True)
                      print(f"警告：处理目标 '{target_name}' (ID: {target_id}) 字段 '{field}' 时代码内部错误 (缺少方法)，已跳过。查日志。")
                      field_processing_errors = True
                      continue # 跳到下一个字段
                 except Exception as e:
                     logging.error(f"处理目标 {target_name_for_log} 的字段 '{field}' 时出错: {e}", exc_info=True)
                     print(f"警告：处理目标 '{target_name}' (ID: {target_id}) 字段 '{field}' 时出错，已跳过。查日志。")
                     field_processing_errors = True
                     continue # 跳到下一个字段

            # 如果计算出此目标渠道有变更，则加入计划
            if changes_summary:
                 logging.info(f"为目标 ID: {target_id}, Name: '{target_name}' 计算出 {len(changes_summary)} 项变更。")
                 update_plan.append({
                     "target_id": target_id,
                     "target_name": target_name,
                     "payload": payload_for_api, # 只包含 ID 和变更字段的字典
                     "changes_summary": changes_summary, # 变更描述字典
                     "original_data": copy.deepcopy(target_channel) # 保存原始数据以供撤销
                 })
            elif not field_processing_errors: # 没有变更且没有字段处理错误
                 logging.info(f"目标 ID: {target_id}, Name: '{target_name}' 无需更新。")
            # 如果有字段处理错误但无变更，则不加入 plan，日志中应有记录

        # 2. 模拟运行与确认
        if not update_plan:
            print("\n经过计算，没有检测到任何需要应用的变更。")
            logging.info("没有需要应用的变更。")
            return 0

        print("\n--- 计划变更 (模拟运行) ---")
        print(f"将从源渠道 ID: {source_channel_data.get('id')}, Name: '{source_channel_data.get('name')}' 复制字段")
        print(f"共计划更新 {len(update_plan)} 个目标渠道:")
        for item in update_plan:
            print(f"\n -> 目标渠道: ID={item['target_id']}, Name='{item['target_name']}'")
            for field, change_desc in item['changes_summary'].items():
                print(f"    - {field}: {change_desc}")
        print("--------------------------")

        confirmed = False
        if args.yes:
            confirmed = True
            logging.info("自动确认模式 (-y)：将执行以上所有变更。")
        else:
            try:
                confirm_input = input(f"确认要将以上变更应用到 {len(update_plan)} 个目标渠道吗？ (y/n): ").lower()
                if confirm_input == 'y':
                    confirmed = True
                else:
                    print("操作已取消。")
                    return 0
            except EOFError: # 处理管道或重定向输入结束的情况
                print("\n输入结束，操作已取消。")
                return 0

        # 3. 执行更新 (如果确认)
        if confirmed:
            success_count = 0
            failure_count = 0
            failed_updates = [] # 存储失败的 (id, name, reason)

            # --- 先保存撤销数据 ---
            original_targets_for_undo = [item['original_data'] for item in update_plan]
            if original_targets_for_undo:
                 try:
                     target_config_name = Path(target_config_path).stem
                     logging.info(f"尝试为目标站点 '{target_config_name}' (类型: {target_api_type}) 保存 {len(original_targets_for_undo)} 条撤销数据...")
                     # TODO: 确认 save_undo_data 是 async
                     await save_undo_data(target_api_type, target_config_name, original_targets_for_undo)
                     logging.info(f"为目标站点 '{target_config_name}' 成功保存撤销数据。")
                     print(f"\n已为目标站点 '{target_config_name}' 保存 {len(original_targets_for_undo)} 条撤销信息。")
                 except Exception as undo_e:
                     logging.error(f"为目标站点 '{target_config_name}' 保存撤销数据时出错: {undo_e}", exc_info=True)
                     print(f"\n警告：未能保存撤销数据！如果继续执行更新，将无法撤销。")
                     # 撤销失败时，再次向用户确认是否继续
                     if not args.yes:
                          try:
                              continue_anyway = input("无法保存撤销数据。是否仍要继续执行更新操作？ (y/n): ").lower()
                              if continue_anyway != 'y':
                                   print("操作已取消。")
                                   return 0
                              else:
                                   print("警告：将继续执行更新，但无法撤销。")
                                   logging.warning("用户选择在撤销数据保存失败后继续执行更新。")
                          except EOFError:
                              print("\n输入结束，操作已取消。")
                              return 0
                     else:
                          print("警告：自动确认模式下，即使撤销数据保存失败，也将继续执行更新。")
                          logging.warning("自动确认模式：撤销数据保存失败，但继续执行更新。")

            # --- 并发执行更新 ---
            concurrency_limit = script_config.get('concurrency_limit', 5) # 从 script_config 获取并发数，默认 5
            semaphore = Semaphore(concurrency_limit)
            update_tasks = []

            # 内部 async 函数用于执行单个更新任务
            async def update_single_channel_task(item):
                target_id = item['target_id']
                target_name = item['target_name']
                payload = item['payload'] # 包含 ID 和变更字段
                async with semaphore: # 控制并发
                    logging.info(f"开始更新目标渠道 ID: {target_id}, Name: '{target_name}'...")
                    logging.debug(f"发送到 API 的载荷 (ID: {target_id}): {json.dumps(payload, indent=2, ensure_ascii=False)}")
                    try:
                        # TODO: 确认 update_channel_api 是 async 且接受部分更新 payload
                        success, message = await target_tool.update_channel_api(payload)
                        if success:
                            logging.info(f"成功更新目标 ID: {target_id}, Name: '{target_name}': {message}")
                            return True, target_id, target_name, None # 返回成功状态和标识
                        else:
                            logging.error(f"更新目标 ID: {target_id}, Name: '{target_name}' 失败: {message}")
                            return False, target_id, target_name, message # 返回失败状态和原因
                    except Exception as e:
                         logging.error(f"更新目标 ID: {target_id}, Name: '{target_name}' 时意外错误: {e}", exc_info=True)
                         err_msg = f"发生意外错误: {e}"
                         return False, target_id, target_name, err_msg # 返回失败状态和原因

            # 创建所有更新任务
            for item in update_plan:
                update_tasks.append(update_single_channel_task(item))

            # 执行任务并等待结果
            print(f"\n开始并发更新 {len(update_tasks)} 个目标渠道 (并发数: {concurrency_limit})...")
            results = await asyncio.gather(*update_tasks) # results 是 (success, id, name, reason) 的列表
            print("所有更新任务已完成。")

            # 处理结果
            for success, tid, tname, reason in results:
                if success:
                    success_count += 1
                else:
                    failure_count += 1
                    failed_updates.append((tid, tname, reason))

            # 4. 报告结果
            print("\n--- 更新结果 ---")
            print(f"成功更新: {success_count} 个渠道")
            print(f"更新失败: {failure_count} 个渠道")
            if failed_updates:
                print("\n失败详情:")
                for fid, fname, freason in failed_updates:
                    print(f"  - ID: {fid}, Name: '{fname}', 原因: {freason}")
            print("----------------")

            return 1 if failure_count > 0 else 0 # 如果有失败则返回 1

        else:
             return 0 # 用户未确认

    elif action == "compare_fields":
        # --- 比较字段逻辑 (增强版) ---
        if source_channel_data is None:
            logging.error("内部错误: compare_fields 无法执行，因为未能确定唯一的源渠道数据。")
            return 1
        if not matched_target_channels:
             logging.info("没有匹配的目标渠道，无需执行 compare_fields。")
             print("没有匹配到需要比较的目标渠道。")
             return 0

        print("\n--- 字段比较结果 ---")
        print(f"源渠道: ID={source_channel_data.get('id', 'N/A'):<4} Name='{source_channel_data.get('name', 'N/A')}'")
        print(f"将与以下 {len(matched_target_channels)} 个目标渠道进行比较:")
        overall_differences_found = False # 标记在所有比较中是否发现差异

        # 预先标准化源数据一次
        normalized_source_data = {}
        # TODO: 将这些字段类型定义移到 ChannelToolBase 或 utils 中
        list_fields = ["models", "group", "tag"]
        dict_fields = ["model_mapping", "status_code_mapping", "setting", "headers", "override_params"]
        source_name_for_log = source_channel_data.get('name', f"ID:{source_channel_data.get('id')}")
        try:
             for field in fields_to_compare:
                  source_value = source_channel_data.get(field)
                  if field in list_fields:
                      # TODO: 确保 source_tool 有 _normalize_to_set 方法
                      normalized_source_data[field] = source_tool._normalize_to_set(source_value)
                  elif field in dict_fields:
                      # TODO: 确保 source_tool 有 _normalize_to_dict 方法
                      normalized_source_data[field] = source_tool._normalize_to_dict(source_value, field, source_name_for_log)
                  else:
                      normalized_source_data[field] = source_value # 简单值直接用
        except AttributeError as e:
             logging.error(f"标准化源渠道字段时缺少方法: {e}", exc_info=True)
             print(f"错误：代码内部错误，源工具缺少标准化方法 ({e})。无法进行比较。")
             return 1
        except Exception as norm_e:
             logging.error(f"标准化源渠道字段时出错: {norm_e}", exc_info=True)
             print(f"错误：标准化源渠道数据时出错，无法进行比较。")
             return 1

        # 遍历每个目标渠道进行比较
        for target_channel in matched_target_channels:
            target_id = target_channel.get('id')
            target_name = target_channel.get('name', f"ID:{target_id}")
            print(f"\n -> 比较目标: ID={target_id}, Name='{target_name}'")
            target_differences_found = False # 标记此目标是否有差异

            for field in fields_to_compare:
                normalized_source_value = normalized_source_data.get(field) # 使用预先标准化的源值
                target_value = target_channel.get(field)
                target_name_for_log = target_name # 用于日志/错误

                try:
                     # 标准化目标值并比较
                     if field in list_fields:
                         # TODO: 确保 target_tool 有 _normalize_to_set 方法
                         target_set = target_tool._normalize_to_set(target_value)
                         if normalized_source_value == target_set:
                             pass # 相同则不打印
                         else:
                             target_differences_found = True
                             overall_differences_found = True
                             print(f"    - {field}: 不同")
                             print(f"      源: {','.join(sorted(list(normalized_source_value)))}")
                             print(f"      目标: {','.join(sorted(list(target_set)))}")
                     elif field in dict_fields:
                         # TODO: 确保 target_tool 有 _normalize_to_dict 方法
                         target_dict = target_tool._normalize_to_dict(target_value, field, target_name_for_log)
                         if normalized_source_value == target_dict:
                              pass # 相同则不打印
                         else:
                             target_differences_found = True
                             overall_differences_found = True
                             print(f"    - {field}: 不同")
                             print(f"      源: {json.dumps(normalized_source_value, ensure_ascii=False, indent=2)}")
                             print(f"      目标: {json.dumps(target_dict, ensure_ascii=False, indent=2)}")
                     else: # 简单字段
                         # 直接比较原始值 (源值已在 normalized_source_data 中)
                         if normalized_source_value == target_value:
                              pass # 相同则不打印
                         else:
                             target_differences_found = True
                             overall_differences_found = True
                             print(f"    - {field}: 不同")
                             print(f"      源: {repr(normalized_source_value)}")
                             print(f"      目标: {repr(target_value)}")
                except AttributeError as e:
                     logging.error(f"比较目标 {target_name_for_log} 字段 '{field}' 时缺少标准化方法: {e}", exc_info=True)
                     print(f"    - {field}: 比较时出错 (代码内部错误，缺少方法，查日志)")
                     target_differences_found = True # 出错也算作差异
                     overall_differences_found = True
                     continue # 继续比较下一个字段
                except Exception as comp_e:
                     logging.error(f"比较目标 {target_name_for_log} 的字段 '{field}' 时出错: {comp_e}", exc_info=True)
                     print(f"    - {field}: 比较时出错 (详情见日志)")
                     target_differences_found = True # 出错也算作差异
                     overall_differences_found = True
                     continue # 继续比较下一个字段

            if not target_differences_found:
                print("    (所有比较字段均与源相同)")

        print("\n--- 比较总结 ---")
        if not overall_differences_found:
            print("所有目标渠道的所有待比较字段均与源渠道相同。")
        else:
            print("在比较中发现字段差异。")
        print("----------------")

        return 0 # 比较操作（即使有差异）总是成功返回 0
    # else 分支理论上不会执行，因为 CLI Handler 已经校验过 action
    else:
         logging.error(f"内部错误：执行核心逻辑时遇到未知的 action: {action}")
         return 1