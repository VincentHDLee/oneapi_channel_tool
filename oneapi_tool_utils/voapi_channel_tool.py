# -*- coding: utf-8 -*-
"""
使用 channel_tool_base 模块的 'voapi' API 类型渠道更新工具实现。
"""
import json
import logging
import aiohttp
import asyncio
import requests # get_all_channels 仍然使用 requests

# 导入基础模块 (使用相对导入)
from .channel_tool_base import (
    ChannelToolBase,
    MAX_PAGES_TO_FETCH
)

# 日志记录由主脚本 main_tool.py 配置

class VoApiChannelTool(ChannelToolBase):
    """VO API 特定实现的渠道更新工具"""

    async def get_all_channels(self):
        """获取 One API 中所有渠道的列表 (voapi 特定实现, 异步)"""
        headers = {
            "Authorization": f"Bearer {self.api_token}", # voapi: Bearer Token
            "New-Api-User": self.user_id, # 这个头可能对 voapi 无效，但保留以防万一
        }
        all_channels = []
        page = 0 # 内部页码计数器
        logging.info(f"开始异步获取渠道列表 (voapi), 最大页数限制: {MAX_PAGES_TO_FETCH}")
        final_message = "未知错误"

        page_size = self.script_config.get('api_page_sizes', {}).get('voapi', 100)
        logging.info(f"使用分页大小 (voapi): {page_size}")

        async with aiohttp.ClientSession(headers=headers) as session:
            while True:
                if page >= MAX_PAGES_TO_FETCH:
                    final_message = f"已达到最大获取页数限制 ({MAX_PAGES_TO_FETCH}), 可能未获取全部渠道。"
                    logging.warning(final_message)
                    break

                request_url = f"{self.site_url}api/channel/?p={page + 1}&page_size={page_size}"
                logging.debug(f"请求 URL: {request_url}")

                # --- 添加请求间隔 ---
                request_interval_ms = self.script_config.get('api_settings', {}).get('request_interval_ms', 0)
                if request_interval_ms > 0:
                    interval_seconds = request_interval_ms / 1000.0
                    logging.debug(f"[VOAPI] 等待 {interval_seconds:.3f} 秒后发送 GET 请求 (页码参数: {page + 1}) (配置间隔: {request_interval_ms}ms)")
                    await asyncio.sleep(interval_seconds)
                # --- 结束添加请求间隔 ---
                try:
                    async with session.get(request_url, timeout=30) as response:
                        response_status = response.status
                        response_text = await response.text()

                        if 200 <= response_status < 300:
                            try:
                                json_data = json.loads(response_text)
                            except json.JSONDecodeError as e:
                                final_message = f"解析渠道列表响应失败: {e}, 页码参数: {page + 1}, 响应内容: {response_text[:500]}..."
                                logging.error(final_message)
                                return None, final_message

                            if not json_data.get("success", False):
                                error_message = json_data.get('message', '未知 API 错误')
                                # 检查是否是正常的页码结束错误
                                if response_status == 400 and 'page' in error_message.lower():
                                    final_message = f"获取所有渠道完成 (API 报告页码无效), 最后一页参数: {page + 1}, 总记录数: {len(all_channels)}"
                                    logging.info(final_message)
                                    break # Normal completion
                                else:
                                    final_message = f"获取渠道列表失败 (API success=false): {error_message}, 页码参数: {page + 1}"
                                    logging.error(final_message)
                                    return None, final_message

                            data = json_data.get("data")
                            if data is None:
                                logging.warning(f"获取渠道列表时 API 返回的 data 为 null, 页码参数: {page + 1}，可能已到达末尾。")
                                final_message = f"获取所有渠道完成 (data is null), 最后一页参数: {page + 1}, 总记录数: {len(all_channels)}"
                                break # Treat null data as end

                            try:
                                # 尝试提取 'records' 或 'list'
                                channel_records = data.get('records', data if isinstance(data, list) else data.get('list'))

                                if channel_records is None:
                                    error_msg = f"在 API 响应的 data 字段中未找到 'records' 或 'list'，且 data 本身不是列表, 页码参数: {page + 1}"
                                    logging.error(error_msg + f", data 内容: {str(data)[:200]}...")
                                    # 假设这是API行为改变或类型错误，不再继续分页
                                    final_message = f"无法解析渠道记录，停止获取, 页码参数: {page + 1}"
                                    break

                                if not channel_records: # 空列表表示结束
                                    final_message = f"获取所有渠道完成 (空记录列表), 最后一页参数: {page + 1}, 总记录数: {len(all_channels)}"
                                    logging.info(final_message)
                                    break

                                logging.info(f"获取第 {page + 1} 页渠道成功, 记录数: {len(channel_records)}")
                                if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
                                    for channel in channel_records:
                                        logging.debug(f"渠道详情 (ID: {channel.get('id')}): {json.dumps(channel, indent=2, ensure_ascii=False)}")
                                all_channels.extend(channel_records)
                                page += 1 # Increment page only if successful

                            except AttributeError as e:
                                if "'list' object has no attribute 'get'" in str(e) and isinstance(data, list):
                                    error_msg = (
                                        "获取渠道列表失败：API 响应格式不兼容（预期字典结构，但收到了列表）。"
                                        "请确认 API 类型 (voapi) 与目标实例匹配。"
                                    )
                                    logging.error(error_msg + f" 页码参数: {page + 1}, 响应 data 类型: {type(data)}")
                                    raise ValueError(error_msg) from e
                                else:
                                    error_msg = f"处理渠道数据时发生意外属性错误: {e}"
                                    logging.error(error_msg, exc_info=True)
                                    return None, error_msg # Return error

                        elif response_status == 400 and 'page' in (await response.text(errors='ignore')).lower():
                             # 特殊处理 voapi 可能在最后一页返回 400 Bad Request 的情况
                             final_message = f"获取所有渠道完成 (API 报告页码无效 400), 最后一页参数: {page + 1}, 总记录数: {len(all_channels)}"
                             logging.info(final_message)
                             break # Normal completion due to pagination end
                        else:
                            final_message = f"获取渠道列表时发生 HTTP 错误: 状态码 {response_status}, 页码参数: {page + 1}, 响应: {response_text[:500]}..."
                            logging.error(final_message)
                            return None, final_message # Return None for HTTP errors

                except aiohttp.ClientError as e:
                    final_message = f"获取渠道列表时发生网络错误: {e}, 页码参数: {page + 1}"
                    logging.error(final_message)
                    return None, final_message
                except asyncio.TimeoutError:
                     final_message = f"获取渠道列表时请求超时, 页码参数: {page + 1}"
                     logging.error(final_message)
                     return None, final_message
                except ValueError as e: # Catches ValueError from inner block
                    logging.error(f"处理渠道数据时出错: {e}")
                    return None, str(e) # Pass ValueError message
                except Exception as e:
                    final_message = f"获取渠道列表时发生未知错误: {e}, 页码参数: {page + 1}"
                    logging.error(final_message, exc_info=True)
                    return None, final_message

        logging.info(f"最终获取到 {len(all_channels)} 个渠道记录。")
        # 如果循环是因为达到 MAX_PAGES 而中断，final_message 会是警告信息
        # 如果是正常结束，final_message 会是成功信息
        return all_channels, final_message

    async def update_channel_api(self, channel_data_payload):
        """调用 API 更新单个渠道 (voapi 特定实现)"""
        channel_id = channel_data_payload.get('id')
        channel_name = channel_data_payload.get('name', f'ID:{channel_id}')
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "New-Api-User": self.user_id,
        }
        # VO API 的更新端点可能是不同的，例如 /api/vo/channel/update
        # 假设它使用 POST 并且只接受部分字段
        # request_url = f"{self.site_url}api/vo/channel/update" # 假设的 VO API 更新路径
        # 暂时假设路径与 newapi 相同，使用 PUT
        request_url = f"{self.site_url}api/channel/"

        # VO API 可能只需要发送 ID 和已更改的字段，或者特定的字段集
        # 这里我们仍然发送由 _prepare_update_payload 生成的完整 payload
        # 如果 VO API 只接受部分字段，它应该忽略多余的字段
        payload_to_send = channel_data_payload
        logging.debug(f"发送 PUT 请求更新渠道 {channel_name} (ID: {channel_id}) 到 {request_url}")
        logging.debug(f"请求 Body: {json.dumps(payload_to_send, indent=2, ensure_ascii=False)}")

        try:
            async with aiohttp.ClientSession() as session:
                 # --- 添加请求间隔 ---
                request_interval_ms = self.script_config.get('api_settings', {}).get('request_interval_ms', 0)
                if request_interval_ms > 0:
                    interval_seconds = request_interval_ms / 1000.0
                    logging.debug(f"[VOAPI] 等待 {interval_seconds:.3f} 秒后发送 PUT 请求 (ID: {channel_id}) (配置间隔: {request_interval_ms}ms)")
                    await asyncio.sleep(interval_seconds)
                # --- 结束添加请求间隔 ---
                # 假设 VO API 也使用 PUT
                async with session.put(
                    request_url,
                    headers=headers,
                    json=payload_to_send,
                    timeout=30
                ) as response:
                    response_text = await response.text()
                    if 200 <= response.status < 300:
                        logging.info(f"渠道 {channel_name} (ID: {channel_id}) 更新成功, 状态: {response.status}")
                        success_message = f"渠道 {channel_name} (ID: {channel_id}) 更新成功, 状态: {response.status}"
                        api_message = ""
                        try:
                            response_data = json.loads(response_text)
                            api_message = response_data.get('message', '')
                            if response_data.get("success"):
                                success_message += f" 服务器消息: {api_message}" if api_message else ""
                                logging.debug(f"服务器确认成功: {api_message}")
                            else:
                                # 成功状态码但 success=false，视为失败
                                error_message = f"{success_message} 但服务器响应 success=false。响应: {response_text[:500]}..."
                                logging.warning(error_message)
                                return False, error_message # 返回 False 和错误信息
                        except json.JSONDecodeError:
                            # 成功状态码但无法解析 JSON，记录警告但仍视为成功
                            warning_message = f"{success_message} 但无法解析 JSON 响应: {response_text[:500]}..."
                            logging.warning(warning_message)
                            return True, warning_message # 返回 True 但带警告信息
                        return True, success_message # API 调用成功且服务器确认
                    else:
                        error_message = f"更新渠道 {channel_name} (ID: {channel_id}) 失败: 状态码 {response.status}, 响应: {response_text[:500]}..."
                        logging.error(error_message)
                        return False, error_message
        except aiohttp.ClientError as e:
            error_message = f"更新渠道 {channel_name} (ID: {channel_id}) 时发生网络错误: {e}"
            logging.error(error_message)
            return False, error_message
        except Exception as e:
            error_message = f"更新渠道 {channel_name} (ID: {channel_id}) 时发生意外错误: {e}"
            logging.error(error_message, exc_info=True)
            return False, error_message

    async def get_channel_details(self, channel_id):
        """获取单个渠道的详细信息 (voapi 特定实现)"""
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "New-Api-User": self.user_id,
        }
        # 假设 VO API 获取详情的端点与 newapi 相同
        request_url = f"{self.site_url}api/channel/{channel_id}"
        logging.debug(f"请求渠道详情 URL: {request_url}")

        import random  # For backoff in retries

        async def fetch_with_retry(session, request_url, headers, max_retries=3):
            for attempt in range(max_retries):
                try:
                    # --- 添加请求间隔 ---
                    request_interval_ms = self.script_config.get('api_settings', {}).get('request_interval_ms', 0)
                    if request_interval_ms > 0:
                        interval_seconds = request_interval_ms / 1000.0
                        logging.debug(f"[VOAPI] 等待 {interval_seconds:.3f} 秒后发送 GET 请求 (ID: {channel_id}) (配置间隔: {request_interval_ms}ms)")
                        await asyncio.sleep(interval_seconds)
                    # --- 结束添加请求间隔 ---
                    async with session.get(request_url, headers=headers, timeout=15) as response:
                        response_text = await response.text()
                        if response.status == 200:
                            try:
                                json_data = json.loads(response_text)
                                if json_data.get("success") and isinstance(json_data.get("data"), dict):
                                    success_message = f"获取渠道 {channel_id} 详情成功 (结构: success/data)。"
                                    logging.debug(success_message)
                                    return json_data["data"], success_message
                                elif isinstance(json_data, dict) and 'id' in json_data:
                                    success_message = f"获取渠道 {channel_id} 详情成功 (结构: 直接字典)。"
                                    logging.debug(success_message)
                                    return json_data, success_message
                                else:
                                    error_message = f"获取渠道 {channel_id} 详情失败: API 响应结构不符合预期。"
                                    logging.error(f"{error_message} 状态码: {response.status}, 响应: {response_text[:1000]}...")
                                    return None, error_message
                            except json.JSONDecodeError as e:
                                error_message = f"解析渠道 {channel_id} 详情 JSON 响应失败: {e}."
                                logging.error(f"{error_message} 状态码: {response.status}, 响应: {response_text[:1000]}...")
                                return None, error_message
                        elif response.status == 404:
                            error_message = f"获取渠道 {channel_id} 详情失败: 未找到 (404)."
                            logging.warning(f"{error_message} 响应: {response_text[:500]}...")
                            return None, error_message
                        else:
                            error_message = f"获取渠道 {channel_id} 详情失败: HTTP 状态码 {response.status}."
                            logging.error(f"{error_message} 响应: {response_text[:1000]}...")
                            return None, error_message
                except asyncio.TimeoutError:
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt) + random.uniform(0, 1)  # Exponential backoff
                        logging.warning(f"请求超时 (尝试 {attempt + 1}/{max_retries})，等待 {wait_time:.1f} 秒后重试。")
                        await asyncio.sleep(wait_time)
                    else:
                        logging.error(f"请求超时，重试 {max_retries} 次后失败。")
                        raise
                except aiohttp.ClientError as e:
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt) + random.uniform(0, 1)
                        logging.warning(f"网络错误 (尝试 {attempt + 1}/{max_retries})，等待 {wait_time:.1f} 秒后重试。")
                        await asyncio.sleep(wait_time)
                    else:
                        logging.error(f"网络错误，重试 {max_retries} 次后失败。")
                        raise
            return None, "重试后仍失败"

        try:
            async with aiohttp.ClientSession() as session:
                return await fetch_with_retry(session, request_url, headers)
# --- 添加请求间隔 ---
                request_interval_ms = self.script_config.get('api_settings', {}).get('request_interval_ms', 0)
                if request_interval_ms > 0:
                    interval_seconds = request_interval_ms / 1000.0
                    logging.debug(f"[VOAPI] 等待 {interval_seconds:.3f} 秒后发送 GET 请求 (ID: {channel_id}) (配置间隔: {request_interval_ms}ms)")
                    await asyncio.sleep(interval_seconds)
                # --- 结束添加请求间隔 ---
                async with session.get(request_url, headers=headers, timeout=15) as response:
                    response_text = await response.text()
                    if response.status == 200:
                        try:
                            json_data = json.loads(response_text)
                            # VO API 的响应结构可能不同，需要适配
                            if json_data.get("success") and isinstance(json_data.get("data"), dict):
                                success_message = f"获取渠道 {channel_id} 详情成功 (结构: success/data)。"
                                logging.debug(success_message)
                                return json_data["data"], success_message # 返回元组
                            # 尝试另一种可能的结构
                            elif isinstance(json_data, dict) and 'id' in json_data:
                                 success_message = f"获取渠道 {channel_id} 详情成功 (结构: 直接字典)。"
                                 logging.debug(success_message)
                                 return json_data, success_message # 返回元组
                            else:
                                # Log the unexpected structure before returning None
                                error_message = f"获取渠道 {channel_id} 详情失败: API 响应结构不符合预期。"
                                logging.error(f"{error_message} 状态码: {response.status}, 响应: {response_text[:1000]}...") # Log more details
                                return None, error_message # 返回 None 和错误消息
                        except json.JSONDecodeError as e:
                            error_message = f"解析渠道 {channel_id} 详情 JSON 响应失败: {e}."
                            logging.error(f"{error_message} 状态码: {response.status}, 响应: {response_text[:1000]}...") # Log more details
                            return None, error_message # 返回 None 和错误消息
                    elif response.status == 404:
                         error_message = f"获取渠道 {channel_id} 详情失败: 未找到 (404)."
                         logging.warning(f"{error_message} 响应: {response_text[:500]}...") # Log response even for 404
                         return None, error_message # 返回 None 和错误消息
                    else:
                        # Log non-200/404 errors with more detail
                        error_message = f"获取渠道 {channel_id} 详情失败: HTTP 状态码 {response.status}."
                        logging.error(f"{error_message} 响应: {response_text[:1000]}...")
                        return None, error_message # 返回 None 和错误消息
        except aiohttp.ClientError as e:
            # Log network errors
            error_message = f"获取渠道 {channel_id} 详情时发生网络错误: {e}"
            logging.error(error_message)
            return None, error_message # 返回 None 和错误消息
        except Exception as e:
            # Log other unexpected errors
            error_message = f"获取渠道 {channel_id} 详情时发生未预期的错误: {e}"
            logging.error(error_message, exc_info=True)
            return None, error_message # 返回 None 和错误消息


    # --- 实现抽象的格式化方法 ---
    def format_list_field_for_api(self, field_name: str, data_input: set | list) -> str:
        """
        VO API 的 'models' 字段期望一个逗号分隔的字符串。
        其他列表字段的行为可能不同，但为了安全，默认也使用字符串。
        如果输入是列表 (例如 models 字段为了保持顺序)，则直接用逗号连接。
        如果输入是集合 (例如其他列表类字段的旧处理方式)，则排序后连接以确保一致性。
        """
        if isinstance(data_input, list):
            # 当输入是列表时，假定顺序是重要的，直接连接
            # 确保所有元素都转换为字符串并去除空值
            formatted_value = ",".join(str(item).strip() for item in data_input if str(item).strip())
        elif isinstance(data_input, set):
            # 对集合元素排序以确保一致性
            # 确保所有元素都转换为字符串并去除空值
            formatted_value = ",".join(sorted(list(str(s).strip() for s in data_input if str(s).strip())))
        else:
            logging.warning(f"字段 '{field_name}' 的 format_list_field_for_api (VOAPI) 接收到意外类型: {type(data_input)}。将尝试按集合处理。")
            try:
                # 尝试将其视为可迭代对象并转换为集合处理
                temp_set = set(str(item).strip() for item in data_input if str(item).strip())
                formatted_value = ",".join(sorted(list(temp_set)))
            except TypeError:
                logging.error(f"无法将字段 '{field_name}' (VOAPI) 的值 {data_input} 转换为集合或列表进行格式化。返回空字符串。")
                return ""
        
        logging.debug(f"格式化列表/集合字段 '{field_name}' (VOAPI, 输入类型: {type(data_input).__name__}) 为逗号分隔字符串: {repr(formatted_value)}")
        return formatted_value

    def format_dict_field_for_api(self, field_name: str, data_dict: dict) -> str:
        """
        VO API 与 NewAPI 类似，期望字典字段是 JSON 字符串。
        """
        if not data_dict:
            return "" # Return empty string if dict is empty
        formatted_value = json.dumps(data_dict, ensure_ascii=False)
        logging.debug(f"格式化字典字段 '{field_name}' (VOAPI) 为 JSON 字符串: {formatted_value}")
        return formatted_value

    def format_field_value_for_api(self, field_name: str, value: any) -> any:
        """
        对 VO API 的字段值进行最终格式化。
        """
        # 假设 VO API 对简单类型没有特殊要求，直接返回
        # 可以根据 VO API 的具体行为添加转换逻辑
        logging.debug(f"格式化字段 '{field_name}' 的最终值 (类型: {type(value).__name__}): {repr(value)}")
        return value

    async def test_channel_api(self, channel_id: int, model_name: str) -> tuple[bool, str, str | None]:
        """
        使用指定的模型测试单个渠道 (VoAPI 特定实现)。
        VoAPI 的测试端点和响应格式通常与 NewAPI 类似。

        Args:
            channel_id (int): 要测试的渠道的 ID。
            model_name (str): 用于测试的模型名称。

        Returns:
            tuple[bool, str, str | None]: (测试是否通过, 描述信息, 失败类型)
        """
        failure_type = None
        channel_name_for_log = f"ID:{channel_id}" # 日志中使用的渠道标识

        api_settings = self.script_config.get('api_settings', {})
        request_timeout_seconds = api_settings.get('request_timeout', 60)
        request_interval_ms = api_settings.get('request_interval_ms', 0)

        # VoAPI 测试端点通常与 NewAPI 相同
        test_url = f"{self.site_url.rstrip('/')}/api/channel/test/{channel_id}"
        params = {'model': model_name}
        headers = {
            'Authorization': f'Bearer {self.api_token}', # VoAPI 通常需要 Bearer 前缀
            'Accept': 'application/json',
            'New-Api-User': str(self.user_id) # 保留，以防部分 VoAPI 分支支持
        }
        timeout = aiohttp.ClientTimeout(total=request_timeout_seconds)

        logging.debug(f"[VOAPI] 准备测试渠道 {channel_name_for_log}，URL: {test_url}，模型: {model_name}, 超时: {request_timeout_seconds}s")

        try:
            async with aiohttp.ClientSession() as session:
                if request_interval_ms > 0:
                    interval_seconds = request_interval_ms / 1000.0
                    logging.debug(f"[VOAPI] 等待 {interval_seconds:.3f} 秒后为渠道 {channel_name_for_log} 发送测试请求 (间隔: {request_interval_ms}ms)")
                    await asyncio.sleep(interval_seconds)

                async with session.get(test_url, headers=headers, params=params, timeout=timeout) as response:
                    status_code = response.status
                    response_text_preview = await response.text()
                    logging.debug(f"[VOAPI] 测试渠道 {channel_name_for_log} - 状态码: {status_code}, 响应预览: {response_text_preview[:500]}...")

                    if status_code == 200:
                        try:
                            response_json = json.loads(response_text_preview)
                            if response_json.get('success') is True:
                                success_message = response_json.get('message', "测试成功")
                                logging.info(f"[VOAPI] 测试渠道 {channel_name_for_log} (模型: {model_name}) 通过: {success_message}")
                                return True, success_message, None
                            else:
                                error_message = response_json.get('message', '测试未通过，无详细信息')
                                if "quota" in error_message.lower() or "insufficient quota" in error_message.lower():
                                    failure_type = 'quota'
                                else:
                                    failure_type = 'api_error'
                                logging.warning(f"[VOAPI] 测试渠道 {channel_name_for_log} (模型: {model_name}) 未通过: {error_message}")
                                return False, f"测试未通过: {error_message}", failure_type
                        except json.JSONDecodeError as e:
                            logging.error(f"[VOAPI] 测试渠道 {channel_name_for_log} (模型: {model_name}) 响应状态码 200 但 JSON 解析失败: {e}.")
                            return False, f"测试失败: 无法解析成功的响应 ({e})", 'response_format'
                    else:
                        error_message_detail = f"API 返回状态码 {status_code}"
                        try:
                            error_json = json.loads(response_text_preview)
                            if 'message' in error_json: error_message_detail += f" ({error_json['message']})"
                        except json.JSONDecodeError: pass
                        
                        if status_code == 401: failure_type = 'auth'
                        elif status_code == 429: failure_type = 'quota'
                        elif status_code >= 400 and status_code < 500: failure_type = 'api_error'
                        elif status_code >= 500: failure_type = 'server_error'
                        else: failure_type = 'unknown_http'
                        logging.error(f"[VOAPI] 测试渠道 {channel_name_for_log} (模型: {model_name}) API 请求失败: {error_message_detail}")
                        return False, f"测试失败: {error_message_detail}", failure_type

        except asyncio.TimeoutError:
            logging.error(f"[VOAPI] 测试渠道 {channel_name_for_log} (模型: {model_name}) 超时。")
            return False, "测试失败: 请求超时", 'timeout'
        except aiohttp.ClientError as e:
            logging.error(f"[VOAPI] 测试渠道 {channel_name_for_log} (模型: {model_name}) 时发生客户端错误: {e}")
            return False, f"测试失败: 网络或客户端错误 ({e})", 'network'
        except Exception as e:
            logging.exception(f"[VOAPI] 测试渠道 {channel_name_for_log} (模型: {model_name}) 时发生未知异常。")
            return False, f"测试失败: 未知错误 ({type(e).__name__})", 'exception'

# --- main 函数（示例，实际由 main_tool.py 调用）---
# async def main(api_config_path, update_config_path, dry_run=False):
#     """主函数 (voapi 特定实现)，实例化 VoApiChannelTool 并运行更新"""
#     exit_code = 0
#     try:
#         script_cfg = load_script_config() # 加载通用配置
#         tool_instance = VoApiChannelTool(api_config_path, update_config_path, script_config=script_cfg)
#         # run_updates 是基类的方法，不再直接从这里调用
#         # exit_code = await tool_instance.run_updates(dry_run=dry_run)
#         print("请通过 main_tool.py 运行此工具。")
#         exit_code = 1
#     except ValueError as e: # 配置加载错误
#         logging.critical(f"配置加载失败，无法继续: {e}")
#         exit_code = 2
#     except Exception as e:
#         logging.critical(f"执行 voapi 准备工作时发生未处理的严重错误: {e}", exc_info=True)
#         exit_code = 3
#     return exit_code # 返回退出码给 main_tool.py