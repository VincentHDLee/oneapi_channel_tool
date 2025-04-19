# One API 渠道批量更新工具 (One API Channel Batch Update Tool)

这是一个 Python 脚本，用于批量更新 [One API](https://github.com/songquanpeng/one-api) 实例中的渠道配置。它允许你根据名称、分组、模型或标签筛选渠道，并更新它们的多个属性。支持多种 One API 版本（通过 `newapi` 和 `voapi` 类型区分）和灵活的配置方式。

## 功能

*   **多 API 类型支持**: 通过选择 `newapi` 或 `voapi` 类型，适配不同版本的 One API 接口。
*   **灵活配置**:
    *   使用 `connection_configs` 目录管理多个 One API 实例的连接信息。
    *   使用 `update_config.json` 定义渠道筛选规则和要应用的更新。
*   **交互式与非交互式运行**:
    *   直接运行 `python main_tool.py` 进入交互模式，引导选择配置、API 类型和运行模式。
    *   支持命令行参数，方便自动化和脚本调用。
*   **Dry Run 模式**:
    *   通过 `--dry-run` 参数或交互式选择，可以模拟更新流程，查看将受影响的渠道和计划的更改，而**不会**实际执行 API 调用、备份或清理配置。
*   **撤销 (Undo) 功能**:
    *   通过 `--undo` 参数，可以尝试将渠道恢复到上次成功执行更新操作**之前**的状态。
    *   依赖于 `undo_data/` 目录下自动保存的撤销文件。
*   **批量更新**: 支持批量更新以下渠道属性（具体支持情况取决于目标 API 版本）：
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
*   **并发处理**: 使用 `asyncio` 和 `aiohttp` 进行并发 API 请求，提高效率。
*   **安全备份**: 在执行实际更新前，自动将当前的 `update_config.json` 备份到 `used_update_configs` 目录（带时间戳）。
*   **配置清理**: 可选在更新成功结束后，将 `update_config.json` 恢复为 `update_config.clean.json` 的内容。
*   **增强日志**:
    *   同时输出到控制台和日志文件（默认保存在 `logs/` 目录下，带时间戳）。
    *   可通过命令行参数控制日志级别和日志文件路径（或禁用文件日志）。

## 目录结构

```
.
├── connection_configs/       # 存放不同 One API 实例的连接配置
│   ├── connection_config.example.json
│   └── your_connection_config.json
├── logs/                     # 存放日志文件 (自动创建)
├── undo_data/                # 存放撤销数据文件 (自动创建)
├── used_update_configs/      # 自动备份执行前的 update_config.json (自动创建)
├── channel_tool_base.py      # 基础工具类和抽象基类
├── main_tool.py              # 主入口脚本
├── newapi_channel_tool.py    # New API 类型实现
├── voapi_channel_tool.py     # VO API 类型实现
├── update_config.json        # 当前使用的更新规则
├── update_config.example.json # 更新规则示例
├── update_config.clean.json  # 用于恢复的干净更新规则（可选）
├── requirements.txt          # Python 依赖
├── README.md                 # 本文档
├── DEVELOPMENT.md            # 开发文档
└── .gitignore
└── LICENSE
```

## 使用方法

1.  **安装依赖**:
    ```bash
    pip install -r requirements.txt
    ```
    (主要依赖 `requests` 和 `aiohttp`)

2.  **配置连接**:
    *   在 `connection_configs` 目录下，复制 `connection_config.example.json` 或创建一个新的 `.json` 文件（例如 `my_server.json`）。
    *   编辑你的连接配置文件，填入对应 One API 实例的 URL 和管理员 API 令牌。`user_id` 是可选的，用于某些 API 版本记录操作日志。
    ```json
    // connection_configs/my_server.json
    {
      "site_url": "https://your-one-api-domain.com",
      "api_token": "YOUR_ONE_API_ADMIN_TOKEN",
      "user_id": "YOUR_ONE_API_USER_ID_FOR_LOGS" // 可选, 默认为 '1'
    }
    ```
    *   你可以创建多个连接配置文件来管理不同的 One API 实例。

3.  **配置更新规则**:
    *   编辑根目录下的 `update_config.json` 文件（如果不存在，可以从 `update_config.example.json` 复制）。
    *   在 `filters` 部分设置筛选条件 ( `name_filters`, `group_filters`, `model_filters`, `tag_filters`, `type_filters`, `match_mode`)。
    *   在 `updates` 部分，将需要更新的属性的 `enabled` 设置为 `true`，并修改 `value` 为目标值。将不需要更新的属性的 `enabled` 设置为 `false`。

4.  **运行脚本**:

    *   **交互模式**:
        ```bash
        python main_tool.py
        ```
        脚本会引导你：
        1.  选择是否执行 Dry Run（仅在更新模式下）。
        2.  从 `connection_configs` 目录中选择要使用的连接配置。
        3.  选择目标 One API 的类型 (`newapi` 或 `voapi`)。
        4.  （如果执行更新且非 Dry Run）执行更新，备份 `update_config.json`，并尝试保存撤销数据。
        5.  （如果执行更新且非 Dry Run 且成功）询问是否将 `update_config.json` 恢复为 `update_config.clean.json` 的内容。
        6.  （如果执行撤销）确认操作并尝试恢复。

    *   **非交互模式 (使用命令行参数)**:
        ```bash
        python main_tool.py [OPTIONS]
        ```
        常用的参数组合：
        ```bash
        # 执行更新：使用指定配置和类型，自动确认，结束后清理
        python main_tool.py --update --connection-config connection_configs/my_server.json --api-type newapi --clear-config -y

        # 执行 Dry Run 测试
        python main_tool.py --update --connection-config connection_configs/other_server.json --api-type voapi --dry-run

        # 执行撤销：使用上次更新 my_server (newapi) 时生成的最新撤销文件，自动确认
        python main_tool.py --undo --connection-config connection_configs/my_server.json --api-type newapi -y

        # 更新并以 DEBUG 级别记录日志到指定文件，不清理配置
        python main_tool.py --update --connection-config connection_configs/my_server.json --api-type newapi --log-level DEBUG --log-file /var/log/oneapi_updater.log -y
        ```

## 命令行参数

```
usage: main_tool.py [-h] [--update | --undo] [--connection-config <path>] [--api-type {newapi,voapi}] [--clear-config] [--dry-run] [-y]
                    [--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}] [--log-file <path>]

One API 渠道批量更新工具

运行模式 (选择一种):
  --update              执行更新操作 (默认行为)。
  --undo                执行撤销操作，恢复到上次执行更新前的状态。
                        需要选择或指定连接配置和 API 类型。

更新/撤销目标:
  --connection-config <path>
                        指定连接配置文件的路径。
                        (例如: connection_configs/my_config.json)
                        如果未提供，将进入交互模式选择。
  --api-type {newapi,voapi}
                        指定目标 One API 的类型。
                        如果未提供，将进入交互模式选择。

更新选项 (仅在 --update 模式下有效):
  --clear-config        在更新成功完成后，使用 'update_config.clean.json'
                        覆盖 'update_config.json'。
  --dry-run             执行模拟更新，显示将要更新的渠道和更改，
                        但不实际执行 API 调用、备份、保存撤销或清理配置。

通用控制:
  -y, --yes             自动确认所有提示 (用于非交互式运行)。

日志选项:
  --log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        设置日志记录级别 (默认为 INFO)。
  --log-file <path>     指定日志文件的具体路径或目录。
                        默认为在 'logs/' 目录下创建带时间戳的日志文件
                        (例如: logs/channel_updater_YYYY-MM-DD-HHMMSSmmm.log)。
                        如果提供空字符串 '' 或 'none'，则不写入文件。

options:
  -h, --help            show this help message and exit

```

## 配置文件示例

### `connection_configs/connection_config.example.json`

```json
{
  "site_url": "https://your-one-api-domain.com",
  "api_token": "YOUR_ONE_API_ADMIN_TOKEN",
  "user_id": "YOUR_ONE_API_USER_ID_FOR_LOGS" // 可选, 默认为 '1'
}
```

### `update_config.example.json`

```json
{
  "filters": {
    "name_filters": ["Example Channel", "Test"], // 包含这些名称之一的渠道
    "group_filters": ["default"],              // 属于这些分组之一的渠道
    "model_filters": ["gpt-4", "claude-3-opus"], // 支持这些模型之一的渠道
    "tag_filters": ["Official"],               // 包含这些标签之一的渠道
    "type_filters": [0, 1, 8],                 // 渠道类型为这些值之一 (例如 0: OpenAI, 1: Anthropic, 8: 自定义)
    "match_mode": "any"                        // "any": 满足任一筛选器类型内部的任一条件即可; "all": (暂未完全实现，目前行为类似 any)
                                               // 注意：目前是要求所有启用的过滤器类型都必须至少匹配一个条件
  },
  "updates": {
    "models": {
      "enabled": false,                        // 是否启用此项更新
      "value": ["gpt-4-turbo", "gpt-4o"]       // 更新后的模型列表 (会被转换为逗号分隔字符串)
    },
    "group": {
      "enabled": false,
      "value": "vip,svip"                      // 更新后的分组 (逗号分隔字符串)
    },
    "model_mapping": {
      "enabled": false,
      "value": {"gpt-3.5-turbo":"gpt-4"}       // 更新后的模型映射 (字典或 JSON 字符串)
    },
    "tag": {
      "enabled": false,
      "value": ["Internal", "Stable"]          // 更新后的标签列表 (会被转换为逗号分隔字符串)
    },
    "priority": {
      "enabled": false,
      "value": 10                              // 更新后的优先级 (数字)
    },
    "weight": {
      "enabled": false,
      "value": 5                               // 更新后的权重 (数字)
    },
    "setting": {
      "enabled": false,
      "value": {"temperature": 0.8}            // 更新后的额外设置 (字典或 JSON 字符串)
    },
    "test_model": {
      "enabled": false,
      "value": "gpt-3.5-turbo"                 // 更新后的测试模型 (字符串)
    },
    "auto_ban": {
      "enabled": false,
      "value": 0                               // 更新后的自动禁用状态 (0: 启用, 1: 禁用)
    },
    "base_url": {
      "enabled": false,
      "value": ""                              // 更新后的 Base URL (空字符串表示移除)
    },
    "status_code_mapping": {
      "enabled": false,
      "value": {"429":"500"}                   // 更新后的状态码映射 (字典或 JSON 字符串)
    },
    "status": {
      "enabled": false,
      "value": 1                               // 更新后的状态 (1: 启用, 2: 手动禁用, 3: 自动禁用)
    }
    // ... 可以添加其他 API 支持的字段
  }
}
```
(请参考 `update_config.example.json` 文件获取最新的配置项列表和注释)

## 注意事项

*   请确保提供的 `api_token` 具有管理员权限以修改渠道。
*   批量操作具有风险，请在执行前仔细检查 `update_config.json` 中的筛选条件和更新内容。
*   **强烈建议先使用 `--dry-run` 模式进行测试**，确认筛选结果和计划的更改符合预期，然后再执行实际更新。
*   **撤销功能**:
    *   撤销操作依赖于上次成功执行 `--update` 时自动保存在 `undo_data/` 目录下的文件。
    *   如果 `save_undo_data` 步骤失败（例如 API 访问或文件写入问题），则该次更新无法被撤销。
    *   撤销会尝试恢复文件中记录的所有渠道的状态，如果某个渠道在保存后被手动删除，撤销操作可能会失败或产生非预期结果。
    *   执行撤销前，请确保选择了与上次更新时相同的 `--connection-config` 和 `--api-type`。
*   如果渠道数量非常多，获取渠道列表可能需要一些时间。脚本内置了最大页数限制以防止因 API 分页问题导致的无限循环。
*   `newapi` 和 `voapi` 支持的更新字段可能略有不同，脚本会尝试应用所有在 `updates` 中启用的字段，目标 API 不支持的字段会被忽略或报错（具体行为取决于目标 API）。

## 许可证

本项目采用 [MIT 许可证](LICENSE)。