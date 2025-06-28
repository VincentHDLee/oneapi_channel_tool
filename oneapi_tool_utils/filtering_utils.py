# -*- coding: utf-8 -*-
"""
提供渠道过滤相关的工具函数。
"""
import logging
from .data_helpers import normalize_to_set, normalize_to_dict

def validate_match_mode(match_mode):
    """验证匹配模式是否有效"""
    valid_modes = {"any", "exact", "none", "all"} # 添加 all 模式
    if match_mode not in valid_modes:
        raise ValueError(f"无效的匹配模式: {match_mode}. 有效值为: {valid_modes}")
    logging.debug(f"验证匹配模式成功: {match_mode}")

def match_filter(value, filter_list, match_mode):
    """根据匹配模式和筛选列表判断值是否匹配 (用于字符串类型字段)"""
    # 仅当过滤器列表非空时才进行匹配
    if not filter_list:
        # 根据模式决定：any/all 模式下，空过滤器不应阻止匹配；exact/none 则需要考虑
        if match_mode in ["any", "all"]:
            return True # 没有指定条件，默认满足
        else:
            # 对于 exact/none，如果过滤器为空，则无法匹配/排除
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

def channel_matches_filters(channel, filters_config):
    """判断单个渠道是否符合所有筛选条件"""
    if not isinstance(channel, dict):
        logging.warning(f"跳过无效的渠道数据项 (非字典): {channel}")
        return False

    channel_id = channel.get('id') # 获取当前渠道的 ID

    # --- ID 列表匹配 (最高优先级) ---
    id_filters = filters_config.get('id_filters')
    if id_filters and isinstance(id_filters, list):
        try:
            # 确保列表中的 ID 和渠道 ID 都是整数以便正确比较
            id_filters_int = {int(fid) for fid in id_filters}
            match = int(channel_id) in id_filters_int
            logging.debug(f"  - ID 列表匹配检查: channel_id={channel_id}, id_filters={id_filters_int}, 结果={match}")
            return match
        except (ValueError, TypeError, AttributeError):
            logging.debug(f"  - ID 列表匹配检查时类型转换失败，跳过。channel_id={channel_id}, id_filters={id_filters}")
            return False # 类型不匹配则无法匹配
            
    # --- 单个精确 ID 匹配 (向后兼容) ---
    filter_id_value = filters_config.get('id')
    if filter_id_value is not None:
        try:
            match = int(channel_id) == int(filter_id_value)
            logging.debug(f"  - 单个 ID 精确匹配检查: channel_id={channel_id}, filter_id={filter_id_value}, 结果={match}")
            return match
        except (ValueError, TypeError, AttributeError):
            match = channel_id == filter_id_value
            logging.debug(f"  - 单个 ID 精确匹配检查 (原始类型): channel_id={channel_id}, filter_id={filter_id_value}, 结果={match}")
            return match

    # --- 精确 Key 匹配 (次高优先级，在 ID 之后，常规筛选器之前) ---
    # 主要用于 voapi 实例，但可通用。
    # key_filter 应该是一个字符串值用于精确匹配。
    filter_key_value = filters_config.get('key_filter') # 新增筛选器
    if filter_key_value is not None:
        channel_key_val = channel.get('key')
        if channel_key_val is None: # 如果 'key' 字段不存在或为 None，尝试 'apikey'
            channel_key_val = channel.get('apikey')
        
        match = (channel_key_val == filter_key_value)
        logging.debug(f"  - Key 精确匹配检查: channel_key='{channel_key_val}', filter_key='{filter_key_value}', 结果={match} (渠道ID: {channel_id})")
        return match

    # --- 常规筛选器 (仅在没有精确 ID 或 Key 筛选时应用) ---
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
    channel_name = channel.get('name', '')
    if exclude_name_filters and match_filter(channel_name, exclude_name_filters, "any"): # Use imported function
        logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 因 exclude_name_filters 被排除")
        return False

    channel_groups = normalize_to_set(channel.get('group', ''))
    if exclude_group_filters and any(g in channel_groups for g in exclude_group_filters):
        logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 因 exclude_group_filters 被排除")
        return False

    channel_models = normalize_to_set(channel.get('models', ''))
    if exclude_model_filters and any(m in channel_models for m in exclude_model_filters):
        logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 因 exclude_model_filters 被排除")
        return False

    model_mapping = normalize_to_dict(channel.get('model_mapping'), 'model_mapping', channel_name)
    if exclude_model_mapping_keys and any(key in model_mapping for key in exclude_model_mapping_keys):
        logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 因 exclude_model_mapping_keys 被排除")
        return False

    override_params_key = 'override_params' if 'override_params' in channel else 'param_override'
    override_params = normalize_to_dict(channel.get(override_params_key), override_params_key, channel_name)
    if exclude_override_params_keys and any(key in override_params for key in exclude_override_params_keys):
        logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 因 exclude_override_params_keys 被排除")
        return False

    # --- 包含逻辑 ---
    # 检查是否有任何启用的包含型筛选器 (除了 key_filter，因为它已经处理过了)
    has_include_filter = any([
        name_filters,
        group_filters,
        model_filters,
        tag_filters,
        type_filters
    ])
    if not has_include_filter: # 如果没有其他包含型过滤器了
        logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 因无其他包含过滤器而匹配 (已通过精确ID/Key匹配和排除逻辑)")
        return True # 如果通过了前面的精确匹配和排除，且没有其他包含条件，则算匹配

    if match_mode == "all":
        all_matched = True
        if name_filters and not match_filter(channel_name, name_filters, "any"): all_matched = False
        if group_filters and not any(g in channel_groups for g in group_filters): all_matched = False
        if model_filters and not any(m in channel_models for m in model_filters): all_matched = False
        if tag_filters:
            channel_tags = normalize_to_set(channel.get('tag', ''))
            if not any(t in channel_tags for t in tag_filters): all_matched = False
        if type_filters and channel.get('type') not in type_filters: all_matched = False
        logging.debug(f"渠道 {channel_name} (ID: {channel_id}) 的 'all' 模式匹配结果: {all_matched}")
        return all_matched

    elif match_mode == "any":
        any_matched = False
        if name_filters and match_filter(channel_name, name_filters, "any"): any_matched = True
        elif group_filters and any(g in channel_groups for g in group_filters): any_matched = True
        elif model_filters and any(m in channel_models for m in model_filters): any_matched = True
        elif tag_filters:
            channel_tags = normalize_to_set(channel.get('tag', ''))
            if any(t in channel_tags for t in tag_filters): any_matched = True
        elif type_filters and channel.get('type') in type_filters: any_matched = True
        return any_matched
    elif match_mode == "exact":
        # "exact" 模式下，只处理 name_filters
        if name_filters:
            return match_filter(channel_name, name_filters, "exact")
        else:
            return False # 如果没有 name_filters，则无法进行 exact 匹配
    else: # "none" mode
        logging.warning(f"在 'any'/'all'/'exact' 之外的模式下使用多个过滤器类型，行为未定义，渠道 {channel_name} (ID: {channel_id}) 不匹配")
        return False


def filter_channels(channel_list: list, filters_config: dict | None = None) -> list:
    """
    根据提供的筛选器配置过滤渠道列表。

    Args:
        channel_list (list): 要过滤的原始渠道字典列表。
        filters_config (dict | None, optional): 包含筛选条件的字典。默认为 None。

    Returns:
        list: 过滤后的渠道字典列表。
    """
    if not filters_config:
        logging.info("未提供筛选配置或配置为空，不过滤渠道。")
        return channel_list
    if not channel_list:
        logging.warning("输入的渠道列表为空，无需过滤。")
        return []

    if not isinstance(filters_config, dict):
         logging.error(f"传入的筛选配置 filters_config 不是有效的字典: {type(filters_config)}")
         return []

    match_mode = filters_config.get("match_mode", "any")

    try:
        validate_match_mode(match_mode) # Use the function from this module
    except ValueError as e:
        logging.error(f"筛选配置中的 match_mode 无效: {e}")
        return []

    logging.info(f"开始使用提供的配置过滤 {len(channel_list)} 个渠道...")

    # 构建日志信息
    log_parts = [f"模式='{match_mode}'"]
    known_filters = [
        "id_filters", "id", "key_filter", "name_filters", "exclude_name_filters", # 添加 id_filters 和 key_filter
        "group_filters", "exclude_group_filters",
        "model_filters", "exclude_model_filters",
        "tag_filters", "type_filters",
        "exclude_model_mapping_keys", "exclude_override_params_keys"
    ]
    for key in known_filters:
         filter_value = filters_config.get(key)
         if filter_value is not None:
              log_parts.append(f"{key}={filter_value}")
    logging.info(f"筛选条件: {', '.join(log_parts)}")

    # 执行过滤
    filtered_channels = [
        channel for channel in channel_list
        if channel_matches_filters(channel, filters_config) # Use the function from this module
    ]

    if not filtered_channels:
        logging.warning("根据提供的筛选条件，未匹配到任何渠道。")
    else:
        logging.info(f"根据提供的筛选条件，总共匹配到 {len(filtered_channels)} 个渠道。")
    return filtered_channels