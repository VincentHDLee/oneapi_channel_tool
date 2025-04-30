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
        page = 0
        logging.info(f"开始异步获取渠道列表 (newapi), 初始页码: {page}")
        final_message = "未知错误" # Default error message

        page_size = self.script_config.get('api_page_sizes', {}).get('newapi', 100)
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

                            if data is None or not data: # Empty list ends pagination
                                final_message = f"获取所有渠道完成, 最后一页页码: {page}, 总记录数: {len(all_channels)}"
                                logging.info(final_message)
                                break # Normal completion

                            if isinstance(data, list):
                                logging.info(f"获取第 {page} 页渠道成功, 记录数: {len(data)}")
                                if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
                                     for channel in data:
                                         logging.debug(f"渠道详情 (ID: {channel.get('id')}): {json.dumps(channel, indent=2, ensure_ascii=False)}")
                                all_channels.extend(data)
                                page += 1
                            else:
                                error_msg = (
                                    f"获取渠道列表失败：API 响应格式不兼容（预期列表，收到 {type(data).__name__}）。"
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
        payload_to_send = channel_data_payload
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
    def format_list_field_for_api(self, field_name: str, data_set: set) -> str:
        """
        NewAPI 通常期望列表字段（如 models, group, tag）是逗号分隔的字符串。
        """
        # 对集合元素排序以确保一致性
        formatted_value = ",".join(sorted(list(data_set)))
        logging.debug(f"格式化列表字段 '{field_name}' 为逗号分隔字符串: {repr(formatted_value)}")
        return formatted_value

    def format_dict_field_for_api(self, field_name: str, data_dict: dict) -> dict:
        """
        NewAPI 通常期望字典字段（如 model_mapping, setting）在 JSON payload 中是原始字典对象。
        """
        logging.debug(f"格式化字典字段 '{field_name}' 为原始字典对象: {data_dict}")
        # 不需要转换，直接返回字典
        return data_dict

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