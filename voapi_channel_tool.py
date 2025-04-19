# -*- coding: utf-8 -*-
"""
使用 channel_tool_base 模块的 voapi 渠道更新工具实现。
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

class VoApiChannelTool(ChannelToolBase):
    """VO API 特定实现的渠道更新工具"""

    def get_all_channels(self):
        """获取 One API 中所有渠道的列表 (voapi 特定实现)"""
        headers = {
            "Authorization": f"Bearer {self.api_token}", # voapi: Bearer Token
            "New-Api-User": self.user_id,
        }
        all_channels = []
        page = 0 # 内部计数器
        logging.info(f"开始获取渠道列表 (voapi), 最大页数限制: {MAX_PAGES_TO_FETCH}")

        while True:
            if page >= MAX_PAGES_TO_FETCH:
                logging.warning(f"已达到最大获取页数限制 ({MAX_PAGES_TO_FETCH}), 停止获取更多渠道。")
                break
            try:
                # voapi: 请求 p=1, p=2 ...
                request_url = f"{self.site_url}api/channel/?p={page + 1}&page_size=100"
                logging.debug(f"请求 URL: {request_url}")

                response = self.session.get(
                    request_url,
                    headers=headers,
                    timeout=30
                )
                response.raise_for_status()
                json_data = response.json()

                if not json_data.get("success", False):
                    logging.error(f"获取渠道列表失败: {json_data.get('message', '未知错误')}, 页码参数: {page + 1}")
                    # 检查是否是最后一页的正常失败 (例如 code 400 且 message 包含 'page')
                    if response.status == 400 and 'page' in json_data.get('message', '').lower():
                         logging.info(f"获取所有渠道完成 (API 报告页码无效), 最后一页参数: {page + 1}, 总记录数: {len(all_channels)}")
                         break
                    else:
                         return None # 其他错误

                data = json_data.get("data")
                if data is None:
                     logging.error(f"获取渠道列表时 API 返回的 data 为 null, 页码参数: {page + 1}")
                     break # data 为 null 通常意味着结束或错误

                # voapi: 尝试从 data 中提取 'records' 或 'list'
                channel_records = data.get('records', data if isinstance(data, list) else data.get('list'))

                if channel_records is None:
                     logging.error(f"在 API 响应的 data 字段中未找到 'records' 或 'list'，且 data 本身不是列表, 页码参数: {page + 1}, data 内容: {data}")
                     break # 无法解析数据，停止

                if not channel_records: # 如果记录列表为空，说明是最后一页
                    logging.info(f"获取所有渠道完成, 最后一页参数: {page + 1}, 总记录数: {len(all_channels)}")
                    break

                logging.info(f"获取第 {page + 1} 页渠道成功, 记录数: {len(channel_records)}")
                all_channels.extend(channel_records)
                page += 1

            except requests.exceptions.RequestException as e:
                logging.error(f"获取渠道列表失败: {e}, 页码参数: {page + 1}")
                return None
            except json.JSONDecodeError as e:
                logging.error(f"解析渠道列表响应失败: {e}, 页码参数: {page + 1}, 响应内容: {response.text if 'response' in locals() else 'N/A'}")
                return None
            except Exception as e:
                logging.error(f"获取渠道列表时发生未知错误: {e}", exc_info=True)
                return None

        logging.info(f"最终获取到 {len(all_channels)} 个渠道记录。")
        return all_channels

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
                        try:
                            response_data = json.loads(response_text)
                            if response_data.get("success"):
                                logging.debug(f"服务器确认成功: {response_data.get('message', '')}")
                            else:
                                logging.warning(f"更新请求成功 ({response.status}) 但响应 success 字段为 false 或缺失: {response_text}")
                        except json.JSONDecodeError:
                            logging.warning(f"更新请求成功 ({response.status}) 但无法解析 JSON 响应: {response_text}")
                        return True
                    else:
                        logging.error(f"更新渠道 {channel_name} (ID: {channel_id}) 失败: 状态码 {response.status}, 响应: {response_text}")
                        return False
        except aiohttp.ClientError as e:
            logging.error(f"更新渠道 {channel_name} (ID: {channel_id}) 时发生网络错误: {e}")
            return False
        except Exception as e:
            logging.error(f"更新渠道 {channel_name} (ID: {channel_id}) 时发生意外错误: {e}", exc_info=True)
            return False

    async def get_channel_details(self, channel_id):
        """获取单个渠道的详细信息 (voapi 特定实现)"""
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "New-Api-User": self.user_id,
        }
        # 假设 VO API 获取详情的端点与 newapi 相同
        request_url = f"{self.site_url}api/channel/{channel_id}"
        logging.debug(f"请求渠道详情 URL: {request_url}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(request_url, headers=headers, timeout=15) as response:
                    response_text = await response.text()
                    if response.status == 200:
                        try:
                            json_data = json.loads(response_text)
                            # VO API 的响应结构可能不同，需要适配
                            if json_data.get("success") and isinstance(json_data.get("data"), dict):
                                logging.debug(f"获取渠道 {channel_id} 详情成功。")
                                return json_data["data"]
                            # 尝试另一种可能的结构
                            elif isinstance(json_data, dict) and 'id' in json_data:
                                 logging.debug(f"获取渠道 {channel_id} 详情成功 (直接返回字典)。")
                                 return json_data
                            else:
                                logging.error(f"获取渠道 {channel_id} 详情失败 (API success=false 或 data 无效): {response_text}")
                                return None
                        except json.JSONDecodeError:
                            logging.error(f"解析渠道 {channel_id} 详情响应失败: {response_text}")
                            return None
                    elif response.status == 404:
                         logging.warning(f"获取渠道 {channel_id} 详情失败: 未找到 (404)。")
                         return None # 404 可能是正常情况
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
    """主函数 (voapi 特定实现)，实例化 VoApiChannelTool 并运行更新"""
    exit_code = 0
    try:
        tool_instance = VoApiChannelTool(api_config_path, update_config_path)
        exit_code = await tool_instance.run_updates(dry_run=dry_run)
    except ValueError as e: # 配置加载错误
        logging.critical(f"配置加载失败，无法继续: {e}")
        exit_code = 2
    except Exception as e:
        logging.critical(f"执行 voapi 更新时发生未处理的严重错误: {e}", exc_info=True)
        exit_code = 3
    return exit_code # 返回退出码给 main_tool.py