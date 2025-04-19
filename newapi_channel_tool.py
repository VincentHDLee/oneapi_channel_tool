# -*- coding: utf-8 -*-
"""
使用 channel_tool_base 模块的 newapi 渠道更新工具实现。
"""
import json
import logging
import aiohttp
import asyncio
import requests # get_all_channels 仍然使用 requests

# 导入基础模块
from channel_tool_base import (
    ChannelToolBase,
    MAX_PAGES_TO_FETCH
)

# 日志记录由主脚本 main_tool.py 配置

class NewApiChannelTool(ChannelToolBase):
    """New API 特定实现的渠道更新工具"""

    def get_all_channels(self):
        """获取 One API 中所有渠道的列表 (newapi 特定实现)"""
        headers = {
            "Authorization": self.api_token, # 使用实例属性
            "New-Api-User": self.user_id,    # 使用实例属性
        }
        all_channels = []
        page = 0 # newapi 从 0 开始
        logging.info(f"开始获取渠道列表 (newapi), 初始页码: {page}")

        while True:
            if page >= MAX_PAGES_TO_FETCH:
                logging.warning(f"已达到最大获取页数限制 ({MAX_PAGES_TO_FETCH}), 停止获取更多渠道。")
                break
            try:
                # 使用实例属性 site_url
                request_url = f"{self.site_url}api/channel/?p={page}&page_size=100"
                logging.debug(f"请求 URL: {request_url}")

                response = self.session.get( # 使用实例的 session
                    request_url,
                    headers=headers,
                    timeout=30
                )
                response.raise_for_status()
                json_data = response.json()

                if not json_data.get("success", False):
                    logging.error(f"获取渠道列表失败 (API success=false): {json_data.get('message', '未知错误')}, 页码: {page}")
                    return None # 返回 None 表示失败

                data = json_data.get("data") # newapi 直接使用 data

                if data is None or not data:
                    logging.info(f"获取所有渠道完成, 最后一页页码: {page}, 总记录数: {len(all_channels)}")
                    break

                if isinstance(data, list):
                    logging.info(f"获取第 {page} 页渠道成功, 记录数: {len(data)}")
                    all_channels.extend(data)
                else:
                    logging.warning(f"API 返回的 data 字段不是列表，页码: {page}, data 类型: {type(data)}。停止获取。")
                    break

                page += 1

            except requests.exceptions.RequestException as e:
                logging.error(f"获取渠道列表时发生网络错误: {e}, 页码: {page}")
                return None
            except json.JSONDecodeError as e:
                logging.error(f"解析渠道列表响应失败: {e}, 页码: {page}, 响应内容: {response.text if 'response' in locals() else 'N/A'}")
                return None
            except Exception as e:
                logging.error(f"获取渠道列表时发生未知错误: {e}", exc_info=True)
                return None

        logging.info(f"最终获取到 {len(all_channels)} 个渠道记录。")
        return all_channels

    async def update_channel_api(self, channel_data_payload):
        """调用 API 更新单个渠道 (newapi 特定实现)"""
        channel_id = channel_data_payload.get('id')
        channel_name = channel_data_payload.get('name', f'ID:{channel_id}')
        headers = {
            "Authorization": self.api_token,
            "Content-Type": "application/json",
            "New-Api-User": self.user_id,
        }
        request_url = f"{self.site_url}api/channel/" # newapi 更新路径

        # newapi 的 PUT 请求通常需要发送完整的渠道对象，或者至少是包含 ID 的对象
        # payload 已经是包含更新后值的完整字典 (由基类 _prepare_update_payload 生成)
        payload_to_send = channel_data_payload
        logging.debug(f"发送 PUT 请求更新渠道 {channel_name} (ID: {channel_id}) 到 {request_url}")
        logging.debug(f"请求 Body: {json.dumps(payload_to_send, indent=2, ensure_ascii=False)}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    request_url,
                    headers=headers,
                    json=payload_to_send,
                    timeout=30
                ) as response:
                    response_text = await response.text()
                    if 200 <= response.status < 300:
                        logging.info(f"渠道 {channel_name} (ID: {channel_id}) 更新成功, 状态: {response.status}")
                        try:
                            response_data = json.loads(response_text)
                            if response_data.get("success"):
                                logging.debug(f"服务器确认成功: {response_data.get('message', '')}")
                            else:
                                logging.warning(f"更新请求成功 ({response.status}) 但响应 success 字段为 false 或缺失: {response_text}")
                        except json.JSONDecodeError:
                            logging.warning(f"更新请求成功 ({response.status}) 但无法解析 JSON 响应: {response_text}")
                        return True # API 调用成功
                    else:
                        logging.error(f"更新渠道 {channel_name} (ID: {channel_id}) 失败: 状态码 {response.status}, 响应: {response_text}")
                        return False # API 调用失败
        except aiohttp.ClientError as e:
            logging.error(f"更新渠道 {channel_name} (ID: {channel_id}) 时发生网络错误: {e}")
            return False
        except Exception as e:
            logging.error(f"更新渠道 {channel_name} (ID: {channel_id}) 时发生意外错误: {e}", exc_info=True)
            return False

    async def get_channel_details(self, channel_id):
        """获取单个渠道的详细信息 (newapi 特定实现)"""
        headers = {
            "Authorization": self.api_token,
            "New-Api-User": self.user_id,
        }
        request_url = f"{self.site_url}api/channel/{channel_id}"
        logging.debug(f"请求渠道详情 URL: {request_url}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(request_url, headers=headers, timeout=15) as response:
                    response_text = await response.text()
                    if response.status == 200:
                        try:
                            json_data = json.loads(response_text)
                            if json_data.get("success") and isinstance(json_data.get("data"), dict):
                                logging.debug(f"获取渠道 {channel_id} 详情成功。")
                                return json_data["data"]
                            else:
                                logging.error(f"获取渠道 {channel_id} 详情失败 (API success=false 或 data 无效): {response_text}")
                                return None
                        except json.JSONDecodeError:
                            logging.error(f"解析渠道 {channel_id} 详情响应失败: {response_text}")
                            return None
                    else:
                        logging.error(f"获取渠道 {channel_id} 详情失败: 状态码 {response.status}, 响应: {response_text}")
                        return None
        except aiohttp.ClientError as e:
            logging.error(f"获取渠道 {channel_id} 详情时发生网络错误: {e}")
            return None
        except Exception as e:
            logging.error(f"获取渠道 {channel_id} 详情时发生意外错误: {e}", exc_info=True)
            return None


# --- main 函数：实例化并运行 ---
async def main(api_config_path, update_config_path, dry_run=False):
    """主函数 (newapi 特定实现)，实例化 NewApiChannelTool 并运行更新"""
    exit_code = 0
    try:
        tool_instance = NewApiChannelTool(api_config_path, update_config_path)
        exit_code = await tool_instance.run_updates(dry_run=dry_run)
    except ValueError as e: # 配置加载错误
        logging.critical(f"配置加载失败，无法继续: {e}")
        exit_code = 2
    except Exception as e:
        logging.critical(f"执行 newapi 更新时发生未处理的严重错误: {e}", exc_info=True)
        exit_code = 3
    return exit_code # 返回退出码给 main_tool.py