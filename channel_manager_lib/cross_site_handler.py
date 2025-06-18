# -*- coding: utf-8 -*-
"""
封装跨站点操作的流程。
"""
import logging
import json # 仍然需要用于错误消息中的 dumps
from pathlib import Path
import asyncio # Needed for async function definition and gather
import yaml # type: ignore # 需要用于更具体的 YAML 错误处理
from typing import TYPE_CHECKING, Dict, Any, Optional, List # 添加类型提示

# 从项目模块导入
from channel_manager_lib.config_utils import CROSS_SITE_ACTION_CONFIG_PATH, load_yaml_config, CONNECTION_CONFIG_DIR
from channel_manager_lib.undo_utils import _get_tool_instance
# 从新的 actions 模块导入执行函数
from channel_manager_lib.cross_site_actions import (
    execute_compare_channel_counts,
    execute_copy_fields,
    execute_compare_fields
)

# 类型提示
if TYPE_CHECKING:
    import argparse
    from oneapi_tool_utils.channel_tool_base import ChannelToolBase


async def run_cross_site_operation(args: 'argparse.Namespace', action: str, script_config: Dict[str, Any]) -> int:
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
        source_config_path = Path(source_config_ref)
        target_config_path = Path(target_config_ref)

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
    source_channels_all: Optional[List[Dict[str, Any]]] = None
    target_channels_all: Optional[List[Dict[str, Any]]] = None
    source_channel_data: Optional[Dict[str, Any]] = None # 将在 copy_fields/compare_fields 中根据筛选结果设置
    matched_target_channels: List[Dict[str, Any]] = [] # 将在 copy_fields/compare_fields 中根据筛选结果设置

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
        # --- 调用比较渠道数量逻辑 ---
        if source_channels_all is None or target_channels_all is None:
             logging.error("内部错误: compare_channel_counts 需要有效的渠道列表，但未能获取。")
             print("错误：未能获取一个或两个站点的渠道列表以进行数量比较。")
             return 1
        # 调用外部函数执行比较和打印
        execute_compare_channel_counts(
            source_channels_all,
            target_channels_all,
            source_config_path,
            target_config_path
        )
        return 0 # 比较数量总是成功返回

    elif action == "copy_fields":
        # --- 调用复制字段逻辑 ---
        if source_channel_data is None:
            logging.error("内部错误: copy_fields 无法执行，因为未能确定唯一的源渠道数据。")
            return 1
        if not matched_target_channels:
             logging.info("没有匹配的目标渠道，无需执行 copy_fields。")
             print("没有匹配到需要更新的目标渠道。")
             return 0

        # 调用外部函数执行复制的完整流程
        exit_code = await execute_copy_fields(
            args=args,
            source_tool=source_tool,
            target_tool=target_tool,
            source_channel_data=source_channel_data,
            matched_target_channels=matched_target_channels,
            fields_to_copy=fields_to_copy,
            copy_mode=copy_mode,
            script_config=script_config,
            target_config_path=target_config_path # 传递目标配置路径
        )
        return exit_code

    elif action == "compare_fields":
        # --- 调用比较字段逻辑 ---
        if source_channel_data is None:
            logging.error("内部错误: compare_fields 无法执行，因为未能确定唯一的源渠道数据。")
            return 1
        if not matched_target_channels:
             logging.info("没有匹配的目标渠道，无需执行 compare_fields。")
             print("没有匹配到需要比较的目标渠道。")
             return 0

        # 调用外部函数执行比较和打印
        await execute_compare_fields(
             source_tool=source_tool,
             target_tool=target_tool,
             source_channel_data=source_channel_data,
             matched_target_channels=matched_target_channels,
             fields_to_compare=fields_to_compare
        )
        return 0 # 比较操作总是成功返回 0
    # else 分支理论上不会执行，因为 CLI Handler 已经校验过 action
    else:
         logging.error(f"内部错误：执行核心逻辑时遇到未知的 action: {action}")
         return 1