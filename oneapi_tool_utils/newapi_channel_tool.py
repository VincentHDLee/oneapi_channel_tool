# -*- coding: utf-8 -*-
"""
使用 channel_tool_base 模块的 'newapi' API 类型渠道更新工具实现。
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

class NewApiChannelTool(ChannelToolBase):
    """New API 特定实现的渠道更新工具"""

    async def get_all_channels(self):
        """
        获取 One API 中所有渠道的列表 (newapi 特定实现, 异步)。
        返回: tuple[list | None, str]: (渠道列表或None, 消息或错误信息)
        """
        headers = {
            "Authorization": self.api_token,
            "New-Api-User": self.user_id,
        }
        all_channels = []
        seen_channel_ids = set() # 用于跟踪已添加的渠道ID，防止重复
        page = 0
        logging.info(f"开始异步获取渠道列表 (newapi), 初始页码: {page}")
        final_message = "未知错误" # Default error message

        page_size = self.script_config.get('api_page_sizes', {}).get('newapi', 20)
        logging.info(f"使用分页大小 (newapi): {page_size}")

        # 使用 aiohttp session
        async with aiohttp.ClientSession(headers=headers) as session:
            while True:
                if page >= MAX_PAGES_TO_FETCH:
                    final_message = f"已达到最大获取页数限制 ({MAX_PAGES_TO_FETCH}), 可能未获取全部渠道。"
                    logging.warning(final_message)
                    break # Reached limit

                request_url = f"{self.site_url}api/channel/?p={page}&page_size={page_size}"
                logging.debug(f"请求 URL: {request_url}")

                # --- 添加请求间隔 ---
                request_interval_ms = self.script_config.get('api_settings', {}).get('request_interval_ms', 0)
                if request_interval_ms > 0:
                    interval_seconds = request_interval_ms / 1000.0
                    logging.debug(f"等待 {interval_seconds:.3f} 秒后发送请求 (配置间隔: {request_interval_ms}ms)")
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
                                final_message = f"解析渠道列表响应失败: {e}, 页码: {page}, 响应内容: {response_text[:500]}..."
                                logging.error(final_message)
                                return None, final_message

                            if not json_data.get("success", False):
                                api_message = json_data.get('message', '未知 API 错误')
                                final_message = f"获取渠道列表失败 (API success=false): {api_message}, 页码: {page}"
                                logging.error(final_message)
                                return None, final_message

                            data = json_data.get("data")

                            channels_list = None
                            if isinstance(data, dict) and 'items' in data:
                                channels_list = data.get('items')
                                logging.debug("从 'items' 键提取渠道列表")
                            elif isinstance(data, list):
                                channels_list = data
                                logging.debug("直接使用列表作为渠道列表")

                            if channels_list is None or not channels_list: # Empty list ends pagination
                                final_message = f"获取所有渠道完成, 最后一页页码: {page}, 总记录数: {len(all_channels)}"
                                logging.info(final_message)
                                break # Normal completion
                            
                            if isinstance(channels_list, list):
                                new_channels_count = 0
                                for channel in channels_list:
                                    channel_id = channel.get('id')
                                    if channel_id and channel_id not in seen_channel_ids:
                                        seen_channel_ids.add(channel_id)
                                        all_channels.append(channel)
                                        new_channels_count += 1
                                        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
                                            logging.debug(f"添加新渠道 (ID: {channel_id}): {json.dumps(channel, indent=2, ensure_ascii=False)}")
                                    else:
                                        logging.warning(f"检测到重复或无效的渠道ID: {channel_id}，已跳过。")

                                logging.info(f"获取第 {page} 页渠道成功, 记录数: {len(channels_list)}, 新增记录数: {new_channels_count}")

                                # 如果返回的记录数小于分页大小，说明是最后一页
                                if len(channels_list) < page_size:
                                    final_message = f"获取所有渠道完成 (最后一页记录数小于分页大小), 总页数: {page + 1}, 总记录数: {len(all_channels)}"
                                    logging.info(final_message)
                                    break
                                
                                page += 1
                            else:
                                error_msg = (
                                    f"获取渠道列表失败：API 响应格式不兼容（预期列表或含 'items' 的字典，收到 {type(data).__name__}）。"
                                    f"请确认 API 类型 (newapi) 与目标实例匹配。"
                                )
                                logging.error(error_msg + f" 页码: {page}, 响应 data 内容: {str(data)[:200]}...")
                                raise ValueError(error_msg) # Raise error for incompatible format
                        else:
                            final_message = f"获取渠道列表时发生 HTTP 错误: 状态码 {response_status}, 页码: {page}, 响应: {response_text[:500]}..."
                            logging.error(final_message)
                            return None, final_message # Return None for HTTP errors

                except aiohttp.ClientError as e:
                    final_message = f"获取渠道列表时发生网络错误: {e}, 页码: {page}"
                    logging.error(final_message)
                    return None, final_message
                except asyncio.TimeoutError:
                     final_message = f"获取渠道列表时请求超时, 页码: {page}"
                     logging.error(final_message)
                     return None, final_message
                except Exception as e:
                    final_message = f"获取渠道列表时发生未知错误: {e}, 页码: {page}"
                    logging.error(final_message, exc_info=True)
                    return None, final_message

        logging.info(f"最终获取到 {len(all_channels)} 个渠道记录。")
        return all_channels, final_message

    async def update_channel_api(self, channel_data_payload):
        """
        调用 API 更新单个渠道 (newapi 特定实现)。
        返回: tuple[bool, str]: (是否成功, 消息或错误信息)
        """
        channel_id = channel_data_payload.get('id')
        channel_name = channel_data_payload.get('name', f'ID:{channel_id}')
        headers = {
            "Authorization": self.api_token,
            "Content-Type": "application/json",
            "New-Api-User": self.user_id,
        }
        request_url = f"{self.site_url}api/channel/" # newapi 更新路径

        # 在发送前，对需要特殊格式化的字段进行处理
        payload_to_send = channel_data_payload.copy() # 创建副本以避免修改原始数据
        if 'models' in payload_to_send and isinstance(payload_to_send['models'], list):
            payload_to_send['models'] = self.format_list_field_for_api('models', payload_to_send['models'])
        
        # NewAPI 可能需要将字典序列化为 JSON 字符串
        dict_fields_to_serialize = ['model_mapping', 'setting', 'headers']
        for field in dict_fields_to_serialize:
            if field in payload_to_send and isinstance(payload_to_send[field], dict):
                payload_to_send[field] = self.format_dict_field_for_api(field, payload_to_send[field])

        success_message = f"渠道 {channel_name} (ID: {channel_id}) 更新成功。"
        error_message = f"更新渠道 {channel_name} (ID: {channel_id}) 失败。" # Default error

        logging.debug(f"发送 PUT 请求更新渠道 {channel_name} (ID: {channel_id}) 到 {request_url}")
        logging.debug(f"请求 Body: {json.dumps(payload_to_send, indent=2, ensure_ascii=False)}")

        try:
            # 使用 aiohttp 创建 session
            async with aiohttp.ClientSession() as session:
                 # --- 添加请求间隔 ---
                request_interval_ms = self.script_config.get('api_settings', {}).get('request_interval_ms', 0)
                if request_interval_ms > 0:
                    interval_seconds = request_interval_ms / 1000.0
                    logging.debug(f"等待 {interval_seconds:.3f} 秒后发送 PUT 请求 (ID: {channel_id}) (配置间隔: {request_interval_ms}ms)")
                    await asyncio.sleep(interval_seconds)
                # --- 结束添加请求间隔 ---
                async with session.put(
                    request_url,
                    headers=headers,
                    json=payload_to_send,
                    timeout=30 # 设置超时
                ) as response:
                    response_text = await response.text()
                    response_status = response.status

                    if 200 <= response_status < 300:
                        logging.info(f"{success_message} 状态: {response_status}")
                        api_message = ""
                        try:
                            response_data = json.loads(response_text)
                            api_message = response_data.get('message', '')
                            if response_data.get("success"):
                                success_message += f" 服务器消息: {api_message}" if api_message else ""
                                logging.debug(f"服务器确认成功: {api_message}")
                            else:
                                # 成功状态码但 success=false
                                error_message = f"{success_message} 但服务器响应 success=false。响应: {response_text[:500]}..."
                                logging.warning(error_message)
                                return False, error_message # 视为失败，因为服务器逻辑未成功
                        except json.JSONDecodeError:
                            # 成功状态码但无法解析 JSON
                            error_message = f"{success_message} 但无法解析 JSON 响应: {response_text[:500]}..."
                            logging.warning(error_message)
                            # 仍然可以认为是 API 调用成功，但记录警告
                            return True, error_message # 返回 True 但带警告信息
                        return True, success_message # API 调用成功且服务器确认
                    else:
                        # HTTP 错误状态码
                        error_message = f"{error_message} 状态码 {response_status}, 响应: {response_text[:500]}..."
                        logging.error(error_message)
                        return False, error_message
        except aiohttp.ClientError as e:
            error_message = f"{error_message} 发生网络错误: {e}"
            logging.error(error_message)
            return False, error_message
        except asyncio.TimeoutError:
             error_message = f"{error_message} 请求超时。"
             logging.error(error_message)
             return False, error_message
        except Exception as e:
            error_message = f"{error_message} 发生意外错误: {e}"
            logging.error(error_message, exc_info=True)
            return False, error_message

    async def get_channel_details(self, channel_id):
        """
        获取单个渠道的详细信息 (newapi 特定实现)。
        返回: tuple[dict | None, str]: (渠道详情字典或None, 消息或错误信息)
        """
        headers = {
            "Authorization": self.api_token,
            "New-Api-User": self.user_id,
        }
        request_url = f"{self.site_url}api/channel/{channel_id}"
        success_message = f"获取渠道 {channel_id} 详情成功。"
        error_message = f"获取渠道 {channel_id} 详情失败。" # Default error

        logging.debug(f"请求渠道详情 URL: {request_url}")

        try:
            async with aiohttp.ClientSession() as session:
                # --- 添加请求间隔 ---
                request_interval_ms = self.script_config.get('api_settings', {}).get('request_interval_ms', 0)
                if request_interval_ms > 0:
                    interval_seconds = request_interval_ms / 1000.0
                    logging.debug(f"等待 {interval_seconds:.3f} 秒后发送 GET 请求 (ID: {channel_id}) (配置间隔: {request_interval_ms}ms)")
                    await asyncio.sleep(interval_seconds)
                # --- 结束添加请求间隔 ---
                async with session.get(request_url, headers=headers, timeout=15) as response:
                    response_text = await response.text()
                    response_status = response.status

                    if response_status == 200:
                        try:
                            json_data = json.loads(response_text)
                            if json_data.get("success") and isinstance(json_data.get("data"), dict):
                                logging.debug(success_message)
                                return json_data["data"], success_message
                            else:
                                api_message = json_data.get('message', 'API success=false 或 data 无效')
                                # 添加状态码到日志
                                error_message = f"{error_message} ({api_message}). 状态码: {response_status}, 响应: {response_text[:1000]}..."
                                logging.error(error_message)
                                return None, error_message
                        except json.JSONDecodeError as e:
                            # 添加状态码到日志
                            error_message = f"{error_message} 解析 JSON 响应失败: {e}. 状态码: {response_status}, 响应: {response_text[:1000]}..."
                            logging.error(error_message)
                            return None, error_message
                    elif response_status == 404:
                         # 处理 404 为警告
                         error_message = f"{error_message} 未找到 (404). 响应: {response_text[:500]}..."
                         logging.warning(error_message) # 使用 warning 级别
                         return None, error_message # 仍然返回 None 和消息
                    else:
                        # 其他 HTTP 错误，增加响应长度
                        error_message = f"{error_message} 状态码 {response_status}, 响应: {response_text[:1000]}..."
                        logging.error(error_message)
                        return None, error_message
        except aiohttp.ClientError as e:
            error_message = f"{error_message} 发生网络错误: {e}"
            logging.error(error_message)
            return None, error_message
        except asyncio.TimeoutError:
             error_message = f"{error_message} 请求超时。"
             logging.error(error_message)
             return None, error_message
        except Exception as e:
            error_message = f"{error_message} 发生意外错误: {e}"
            logging.error(error_message, exc_info=True)
            return None, error_message


    # --- 实现抽象的格式化方法 ---
    def format_list_field_for_api(self, field_name: str, data_input: set | list) -> str:
        """
        NewAPI 通常期望列表字段（如 models, group, tag）是逗号分隔的字符串。
        如果输入是列表 (例如 models 字段为了保持顺序)，则直接用逗号连接。
        如果输入是集合 (例如其他列表类字段的旧处理方式)，则排序后连接以确保一致性。
        """
        if isinstance(data_input, list):
            # 当输入是列表时，假定顺序是重要的，直接连接
            # 确保所有元素都转换为字符串
            formatted_value = ",".join(str(item).strip() for item in data_input if str(item).strip())
        elif isinstance(data_input, set):
            # 对集合元素排序以确保一致性
            # 确保所有元素都转换为字符串并去除空值
            formatted_value = ",".join(sorted(list(str(s).strip() for s in data_input if str(s).strip())))
        else:
            logging.warning(f"字段 '{field_name}' 的 format_list_field_for_api 接收到意外类型: {type(data_input)}。将尝试按集合处理。")
            try:
                # 尝试将其视为可迭代对象并转换为集合处理
                temp_set = set(str(item).strip() for item in data_input if str(item).strip())
                formatted_value = ",".join(sorted(list(temp_set)))
            except TypeError:
                logging.error(f"无法将字段 '{field_name}' 的值 {data_input} 转换为集合或列表进行格式化。返回空字符串。")
                return ""
        
        logging.debug(f"格式化列表/集合字段 '{field_name}' (输入类型: {type(data_input).__name__}) 为逗号分隔字符串: {repr(formatted_value)}")
        return formatted_value

    def format_dict_field_for_api(self, field_name: str, data_dict: dict) -> str:
        """
        NewAPI 通常期望字典字段（如 model_mapping, setting）是 JSON 字符串。
        """
        if not data_dict:
            return "" # Return empty string if dict is empty
        formatted_value = json.dumps(data_dict, ensure_ascii=False)
        logging.debug(f"格式化字典字段 '{field_name}' 为 JSON 字符串: {formatted_value}")
        return formatted_value

    def format_field_value_for_api(self, field_name: str, value: any) -> any:
        """
        对 NewAPI 的字段值进行最终格式化。
        主要确保简单类型正确，列表/字典由其他方法处理。
        """
        # 对于 NewAPI，通常不需要对简单类型做特殊转换，直接返回值即可
        # 这里可以添加特定字段的类型检查和转换，例如确保 priority 是整数
        if field_name == "priority":
            try:
                return int(value)
            except (ValueError, TypeError):
                logging.warning(f"字段 'priority' 的值 '{value}' 无法转换为整数，将使用原始值。")
                return value
        # 可以根据需要添加更多字段的特定格式化逻辑
        logging.debug(f"格式化字段 '{field_name}' 的最终值 (类型: {type(value).__name__}): {repr(value)}")
        return value

    async def test_channel_api(self, channel_id: int, model_name: str) -> tuple[bool, str, str | None]:
        """
        使用指定的模型测试单个渠道 (NewAPI 特定实现)。

        Args:
            channel_id (int): 要测试的渠道的 ID。
            model_name (str): 用于测试的模型名称。

        Returns:
            tuple[bool, str, str | None]: (测试是否通过, 描述信息, 失败类型)
        """
        failure_type = None
        channel_name_for_log = f"ID:{channel_id}" # 尝试获取名称，如果失败则用 ID
        try:
            # 尝试从缓存或一次性获取中获取名称，如果实现允许
            # 否则，在日志中仅使用 ID
            pass # Placeholder for potential name fetching optimization
        except:
            pass

        api_settings = self.script_config.get('api_settings', {})
        request_timeout_seconds = api_settings.get('request_timeout', 60)
        request_interval_ms = api_settings.get('request_interval_ms', 0)

        test_url = f"{self.site_url.rstrip('/')}/api/channel/test/{channel_id}"
        params = {'model': model_name}
        headers = {
            'Authorization': f'Bearer {self.api_token}',
            'Accept': 'application/json',
            'New-Api-User': str(self.user_id)
        }
        timeout = aiohttp.ClientTimeout(total=request_timeout_seconds)

        logging.debug(f"准备测试渠道 {channel_name_for_log}，URL: {test_url}，模型: {model_name}, 超时: {request_timeout_seconds}s")

        try:
            async with aiohttp.ClientSession() as session:
                if request_interval_ms > 0:
                    interval_seconds = request_interval_ms / 1000.0
                    logging.debug(f"等待 {interval_seconds:.3f} 秒后为渠道 {channel_name_for_log} 发送测试请求 (间隔: {request_interval_ms}ms)")
                    await asyncio.sleep(interval_seconds)

                async with session.get(test_url, headers=headers, params=params, timeout=timeout) as response:
                    status_code = response.status
                    response_text_preview = await response.text()
                    logging.debug(f"测试渠道 {channel_name_for_log} - 状态码: {status_code}, 响应预览: {response_text_preview[:500]}...")

                    if status_code == 200:
                        try:
                            response_json = json.loads(response_text_preview)
                            if response_json.get('success') is True:
                                success_message = response_json.get('message', "测试成功")
                                logging.info(f"测试渠道 {channel_name_for_log} (模型: {model_name}) 通过: {success_message}")
                                return True, success_message, None
                            else:
                                error_message = response_json.get('message', '测试未通过，无详细信息')
                                if "quota" in error_message.lower() or "insufficient quota" in error_message.lower():
                                    failure_type = 'quota'
                                else:
                                    failure_type = 'api_error'
                                logging.warning(f"测试渠道 {channel_name_for_log} (模型: {model_name}) 未通过: {error_message}")
                                return False, f"测试未通过: {error_message}", failure_type
                        except json.JSONDecodeError as e:
                            logging.error(f"测试渠道 {channel_name_for_log} (模型: {model_name}) 响应状态码 200 但 JSON 解析失败: {e}.")
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
                        logging.error(f"测试渠道 {channel_name_for_log} (模型: {model_name}) API 请求失败: {error_message_detail}")
                        return False, f"测试失败: {error_message_detail}", failure_type

        except asyncio.TimeoutError:
            logging.error(f"测试渠道 {channel_name_for_log} (模型: {model_name}) 超时。")
            return False, "测试失败: 请求超时", 'timeout'
        except aiohttp.ClientError as e:
            logging.error(f"测试渠道 {channel_name_for_log} (模型: {model_name}) 时发生客户端错误: {e}")
            return False, f"测试失败: 网络或客户端错误 ({e})", 'network'
        except Exception as e:
            logging.exception(f"测试渠道 {channel_name_for_log} (模型: {model_name}) 时发生未知异常。")
            return False, f"测试失败: 未知错误 ({type(e).__name__})", 'exception'

# --- main 函数（示例，实际由 main_tool.py 调用） ---
# async def main(api_config_path, update_config_path, dry_run=False):
#     """主函数 (newapi 特定实现)，实例化 NewApiChannelTool 并运行更新"""
#     exit_code = 0
#     try:
#         # 需要传递 script_config
#         script_cfg = load_script_config() # 加载通用配置
#         tool_instance = NewApiChannelTool(api_config_path, update_config_path, script_config=script_cfg)
#         # run_updates 是基类的方法，现在不再直接从这里调用
#         # exit_code = await tool_instance.run_updates(dry_run=dry_run)
#         print("请通过 main_tool.py 运行此工具。")
#         exit_code = 1 # 表示不能直接运行
#     except ValueError as e: # 配置加载错误
#         logging.critical(f"配置加载失败，无法继续: {e}")
#         exit_code = 2
#     except Exception as e:
#         logging.critical(f"执行 newapi 准备工作时发生未处理的严重错误: {e}", exc_info=True)
#         exit_code = 3
#     return exit_code # 返回退出码给 main_tool.py