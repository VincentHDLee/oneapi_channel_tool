# One API 渠道批量更新工具 (One API Channel Batch Update Tool)

这是一个 Python 脚本，用于批量更新 [One API](https://github.com/songquanpeng/one-api) 实例中的渠道配置。它允许你根据名称、分组、模型或标签筛选渠道，并更新它们的多个属性。

## 功能

*   通过配置文件灵活筛选渠道。
*   支持批量更新以下渠道属性：
    *   模型列表 (`models`)
    *   分组 (`group`)
    *   模型重定向 (`model_mapping`)
    *   标签 (`tag`)
    *   优先级 (`priority`)
    *   权重 (`weight`)
    *   额外设置 (`setting`)
    *   测试模型 (`test_model`)
    *   自动禁用状态 (`auto_ban`)
    *   Base URL / 代理 (`base_url`)
    *   状态码复写 (`status_code_mapping`)
    *   渠道状态 (`status`)
*   使用 `asyncio` 和 `aiohttp` 进行并发更新，提高效率。
*   通过配置文件管理 API 连接信息和更新规则，易于维护和分享。

## 使用方法

1.  **安装依赖**:
    ```bash
    pip install requests aiohttp
    ```
2.  **配置连接**:
    *   将 `connection_config.example.json` 复制为 `connection_config.json`。
    *   编辑 `connection_config.json`，填入你的 One API 实例 URL、管理员 API 令牌和用于记录操作的用户 ID。
    ```json
    {
      "site_url": "https://your-one-api-domain.com",
      "api_token": "YOUR_ONE_API_ADMIN_TOKEN",
      "user_id": "YOUR_ONE_API_USER_ID_FOR_LOGS"
    }
    ```
3.  **配置更新规则**:
    *   将 `update_config.example.json` 复制为 `update_config.json`。
    *   编辑 `update_config.json`：
        *   在 `filters` 部分设置筛选条件 ( `name_filters`, `group_filters`, `model_filters`, `tag_filters`, `match_mode`)。
        *   在 `updates` 部分，将需要更新的属性的 `enabled` 设置为 `true`，并修改 `value` 为目标值。将不需要更新的属性的 `enabled` 设置为 `false`。
4.  **运行脚本**:
    ```bash
    python oneapi_channel_tool.py
    ```
    脚本将输出详细的操作日志。

## 配置文件示例

### `connection_config.example.json`

```json
{
  "site_url": "https://your-one-api-domain.com",
  "api_token": "YOUR_ONE_API_ADMIN_TOKEN",
  "user_id": "YOUR_ONE_API_USER_ID_FOR_LOGS"
}
```

### `update_config.example.json`

```json
{
  "filters": {
    "name_filters": ["Example Channel", "Test"],
    "group_filters": ["default"],
    "model_filters": ["gpt-4", "claude-3-opus"],
    "tag_filters": ["Official"],
    "match_mode": "any"
  },
  "updates": {
    "models": {
      "enabled": false,
      "value": ["gpt-4-turbo", "gpt-4o"]
    },
    "group": {
      "enabled": false,
      "value": "vip,svip"
    },
    // ... 其他更新配置项 ...
    "status": {
      "enabled": false,
      "value": 1
    }
  }
}
```
(请参考 `update_config.example.json` 文件获取完整的配置项列表)

## 注意事项

*   请确保提供的 `api_token` 具有管理员权限以修改渠道。
*   `user_id` 用于在 One API 的操作日志中记录是哪个用户执行了此脚本的操作。
*   批量操作具有风险，请在执行前仔细检查 `update_config.json` 中的筛选条件和更新内容，建议先在测试环境中验证。
*   如果渠道数量非常多，获取渠道列表可能需要一些时间。脚本内置了最大页数限制 (`MAX_PAGES_TO_FETCH`) 以防止因 API 分页问题导致的无限循环。

## 许可证

本项目采用 [MIT 许可证](LICENSE)。