# -*- coding: utf-8 -*-
"""
提供数据规范化工具函数，例如将不同类型的值转换为集合或字典。
"""
import json
import logging

def normalize_to_set(value):
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

def normalize_to_dict(value, field_name="未知字段", channel_name="未知渠道"):
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