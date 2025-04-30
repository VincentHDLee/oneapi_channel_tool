# -*- coding: utf-8 -*-
"""
网络请求相关的工具函数，例如创建带重试的 session。
"""
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- 常量 ---
# 定义 requests 重试策略的常量
RETRY_TIMES = 3 # 最大重试次数
RETRY_BACKOFF_FACTOR = 0.5 # 重试之间的等待时间因子
# 遇到这些状态码时触发重试
RETRY_STATUS_FORCELIST = [500, 502, 503, 504]

def create_retry_session():
    """创建带有重试机制的 requests session"""
    session = requests.Session()
    retry_strategy = Retry(
        total=RETRY_TIMES,
        backoff_factor=RETRY_BACKOFF_FACTOR,
        status_forcelist=RETRY_STATUS_FORCELIST,
        allowed_methods=["HEAD", "GET", "OPTIONS", "PUT", "POST"] # 允许重试 PUT/POST
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    logging.debug("创建带有重试机制的 session 成功")
    return session