# One API 渠道批量更新工具 (One API Channel Batch Update Tool)

这是一个 Python 脚本，用于批量更新 [One API](https://github.com/songquanpeng/one-api) 实例中的渠道配置。它允许你根据名称、分组、模型或标签筛选渠道，并更新它们的多个属性。支持多种 One API 版本（通过 `newapi` 和 `voapi` 类型区分）和灵活的配置方式。

## 功能

*   **多 API 类型支持**: 通过在连接配置中指定 `api_type` (`newapi` 或 `voapi`)，适配不同版本的 One API 接口。
*   **灵活配置**:
    *   使用 `connection_configs` 目录管理多个 One API 实例的连接信息。
    *   使用 `update_config.yaml` 定义渠道筛选规则和要应用的更新。
*   **交互式与非交互式运行**:
    *   直接运行 `python main_tool.py` 进入交互模式，引导选择连接配置（API 类型将从配置中自动读取）。
    *   **交互式主菜单**: 在交互模式下，如果检测到上次操作的撤销文件，会显示菜单让用户选择执行新更新、撤销上次操作（并显示上次更新摘要）或退出。
    *   支持命令行参数，方便自动化和脚本调用。
*   **强制模拟与确认**:
    *   脚本在执行更新前，**总是**先进行模拟运行，显示详细的计划变更。
    *   模拟运行后，除非使用 `-y` / `--yes` 参数，否则会**询问用户确认**是否执行实际更新。
*   **撤销 (Undo) 功能**:
    *   通过 `--undo` 参数，可以尝试将渠道恢复到上次成功执行更新操作**之前**的状态。
    *   依赖于 `oneapi_tool_utils/runtime_data/undo_data/` 目录下自动保存的撤销文件。
*   **批量更新**: 支持批量更新以下渠道属性（具体支持情况取决于目标 API 版本）：
    *   名称 (`name`) - 支持覆盖和正则表达式替换 (`regex_replace`)
    *   模型列表 (`models`) - 支持覆盖、追加、移除
    *   分组 (`group`) - 支持覆盖、追加、移除
    *   模型重定向 (`model_mapping`) - 支持覆盖、合并、删除键
    *   标签 (`tag`) - 支持覆盖、追加、移除
    *   优先级 (`priority`) - 仅覆盖
    *   权重 (`weight`) - 仅覆盖
    *   额外设置 (`setting`) - 支持覆盖、合并、删除键
    *   测试模型 (`test_model`) - 仅覆盖
    *   自动禁用状态 (`auto_ban`) - 仅覆盖
    *   Base URL / 代理 (`base_url`) - 仅覆盖
    *   状态码复写 (`status_code_mapping`) - 支持覆盖、合并、删除键
    *   渠道状态 (`status`) - 仅覆盖
    *   请求头 (`headers`) - 支持覆盖、合并、删除键
    *   OpenAI Organization (`openai_organization`) - 仅覆盖
    *   覆盖参数 (`override_params`) - 支持覆盖、合并、删除键
*   **并发处理**: 使用 `asyncio` 和 `aiohttp` 进行并发 API 请求，可通过 `script_config.yaml` 配置最大并发数，提高效率并减少服务器压力。
*   **安全备份**: 在执行实际更新前，自动将当前的 `update_config.yaml` 备份到 `oneapi_tool_utils/runtime_data/used_update_configs/` 目录（带时间戳）。
*   **配置清理**: 可选在更新成功结束后，将 `update_config.yaml` 恢复为默认干净状态 (使用内部模板 `oneapi_tool_utils/update_config.clean.json`)。
*   **脚本通用配置**: 新增 `script_config.yaml` 文件，用于配置脚本行为，如最大并发请求数、API 请求超时时间等。
*   **增强日志**:
*   同时输出到控制台和日志文件（默认保存在 `oneapi_tool_utils/runtime_data/logs/` 目录下，带时间戳）。
    *   **日志轮转**: 自动保留最近 20 个日志文件 (每个最大 5MB)。
    *   可通过命令行参数控制日志级别和日志文件路径（或禁用文件日志）。
    *   更新日志现在会详细显示每个字段的变更：`'旧值' -> '新值'`。
    *   **跨站点渠道操作**: 支持在不同 One API 实例间执行操作（例如复制字段），使用独立的 `cross_site_config.yaml` 进行配置。
    *   **测试并启用禁用渠道**: 新增功能，用于自动测试状态为“自动禁用”的渠道，并在测试通过后将其启用。现在支持 `newapi` 和 `voapi` 类型。
    *   **智能确认**: 在“测试并启用”模式下，如果测试失败的原因仅为配额问题 (HTTP 429)，脚本将自动启用测试通过的渠道（除非使用 `--yes`）。只有当存在其他类型的错误时，才会提示用户确认。

## 目录结构

```
.
├── channel_manager_lib/      # 工具核心逻辑库
│   ├── __init__.py           # 将此目录标记为 Python 包
│   ├── cli_handler.py        # 命令行和交互逻辑
│   ├── config_utils.py       # 配置加载和路径常量
│   ├── cross_site_handler.py # 跨站点操作逻辑
│   ├── log_utils.py          # 日志设置
│   ├── single_site_handler.py # 单站点操作逻辑
│   └── undo_utils.py         # 撤销逻辑
├── connection_configs/       # 存放用户定义的 One API 实例连接配置 (YAML)
│   └── your_connection_config.yaml # 示例：你的连接配置
├── oneapi_tool_utils/        # One API 通信层和运行时数据
│   ├── channel_tool_base.py  # 基础工具类和抽象基类
│   ├── newapi_channel_tool.py # New API 类型实现
│   ├── voapi_channel_tool.py # VO API 类型实现
│   ├── update_config.clean.json # 内部使用的干净配置模板 (JSON)
│   └── runtime_data/         # 运行时生成的数据 (日志、备份等)
│       ├── logs/             # 日志文件存放目录
│       ├── undo_data/        # 撤销数据文件存放目录
│       ├── used_update_configs/ # 已使用的更新配置备份目录
│       └── loaded_connection_configs/ # 缓存的 JSON 连接配置 (内部使用)
├── main_tool.py              # 主入口脚本
├── run_tool.sh               # 推荐的启动脚本
├── connection_config.example # 连接配置示例 (YAML, 位于根目录)
├── update_config.yaml        # 用户当前使用的更新规则 (YAML, 位于根目录)
├── update_config.example     # 更新规则示例 (YAML, 位于根目录)
├── cross_site_config.yaml    # 用户当前使用的跨站操作配置 (YAML, 位于根目录)
├── cross_site_config.example # 跨站操作配置示例 (YAML, 位于根目录)
├── script_config.yaml        # (可选) 脚本通用配置文件 (YAML, 位于根目录)
├── requirements.txt          # Python 依赖
├── README.md                 # 本文档
├── DEVELOPMENT.md            # 开发文档
├── REFACTORING_PLAN.md       # (可选) 重构计划文档
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
    *   **复制示例:** 从项目根目录复制 `connection_config.example` 文件。
    *   **重命名并移动:** 将复制的文件放入 `connection_configs/` 目录，并将其重命名为你想要的名称，确保文件扩展名为 `.yaml` (例如: `connection_configs/my_instance.yaml`)。
    *   **编辑内容:** 打开你新创建的 `.yaml` 文件，根据文件内的注释，填入你的 One API 实例的 `site_url`、`api_token` 和 **必需的 `api_type`** (`newapi` 或 `voapi`)。`user_id` 是可选的。
    ```yaml
    # connection_configs/my_server.yaml
    # One API 实例的访问地址
    site_url: "https://your-one-api-domain.com"
    # One API 管理员令牌
    api_token: "YOUR_ONE_API_ADMIN_TOKEN"
    # 用于记录操作日志的用户 ID (可选, 默认为 '1')
    user_id: "YOUR_ONE_API_USER_ID_FOR_LOGS"
    # 目标 One API 实例的接口类型 (必需)
    # "newapi": 适用于较新版本 (通常含 /api/channel/)
    # "voapi": 适用于较旧版本 (通常含 /api/v1/channel/)
    api_type: "newapi" # 或 "voapi"
    ```
    *   你可以创建多个 `.yaml` 连接配置文件来管理不同的 One API 实例。

3.  **配置操作规则**:
    *   **单站点批量更新**: 编辑根目录下的 `update_config.yaml` 文件（如果不存在，可以从 `update_config.example` 复制）。
        *   在 `filters` 部分设置筛选条件。
        *   在 `updates` 部分定义要应用的更新。
    *   **跨站点渠道操作**: 编辑根目录下的 `cross_site_config.yaml` 文件（如果不存在，可以从 `cross_site_config.example` 复制）。
        *   定义 `action` (例如 `copy_fields`)。
        *   配置 `source` 和 `target` 实例的连接配置路径和精确的渠道筛选器。
        *   根据所选 `action` 配置相应的参数（例如 `copy_fields_params`）。
        *   `compare_fields`: 比较源渠道和目标渠道指定字段的值，不进行修改。

4.  **(可选) 配置脚本行为**:
    *   编辑根目录下的 `script_config.yaml` 文件（如果不存在，脚本会使用默认值）。
    *   调整 `max_concurrent_requests` 来控制并发 API 请求数量。较低的值（如 5）可以减少对本地或负载敏感 API 的压力。
    *   调整 `request_timeout` 来设置 API 请求的超时时间（秒）。
    *   调整 `api_page_sizes` 下的 `newapi` 和 `voapi` 值来控制获取渠道列表时的分页大小，以优化大量渠道的获取效率 (默认为 100)。

5.  **运行脚本**:

    *   **交互模式**:
        ```bash
        ./run_tool.sh
        ```
        (如果提示权限不足，请先执行 `chmod +x run_tool.sh`)
        脚本会引导你：
        1.  **选择操作模式**: [1] 单站点批量更新/撤销 [2] 跨站点渠道操作。
        2.  **单站点模式**:
            *   从 `connection_configs` 目录中选择要操作的连接配置。
            *   **检查撤销状态**: 如果检测到撤销文件，提示选择：[1] 查询所有渠道 [2] 执行新更新 [3] 撤销上次操作 [4] 测试并启用禁用渠道 [0] 退出。
            *   **执行更新流程** (如果选择 2 或未检测到撤销文件且选择执行更新):
                *   读取 `update_config.yaml`。
                *   模拟运行 -> 确认 -> 执行更新 -> 保存撤销 -> 清理配置 (可选)。
            *   **执行撤销流程** (如果选择 3):
                *   确认 -> 执行撤销。
            *   **执行测试并启用流程** (如果选择 4):
                *   筛选状态为 3 的渠道 -> 并发测试 -> 确认 -> 启用测试通过的渠道。
        3.  **跨站点模式**:
            *   读取 `cross_site_config.yaml`。
            *   **显示二级菜单**: 提示选择 [1] 查询源/目标渠道 (仅验证筛选器并显示匹配的渠道) [2] 执行配置的操作 (继续执行 `cross_site_config.yaml` 中定义的 `action`) [0] 退出。
            *   执行指定的操作（例如 `copy_fields`）。
            *   模拟运行 -> 确认 -> 执行操作。
            *   (注意: 跨站操作目前不支持撤销)。
        4.  **执行更新流程** (如果选择 1 或未检测到撤销文件):
            *   脚本会**自动进行模拟运行**，显示计划变更。
            *   （如果模拟有变更且未使用 `-y`）**询问是否确认执行**实际更新。
            *   （如果确认执行或使用 `-y`）执行实际更新，备份 `update_config.yaml`，并尝试保存撤销数据。
            *   （如果更新成功）询问是否将 `update_config.yaml` 恢复为默认干净状态（除非使用 `-y` 或 `--clear-config`）。
        5.  **执行撤销流程** (如果选择 2):
            *   （除非使用 `-y`）**询问是否确认执行**撤销操作。
            *   （如果确认执行或使用 `-y`）尝试恢复渠道状态。

    *   **非交互模式 (使用命令行参数)**:
        ```bash
        ./run_tool.sh [OPTIONS]
        ```
        常用的参数组合：
        ```bash
        # 执行更新：使用指定配置，自动确认，结束后清理 (API 类型从配置读取)
        ./run_tool.sh --update --connection-config connection_configs/my_server.yaml --clear-config -y

        # 执行撤销：使用指定配置对应的最新撤销文件，自动确认 (API 类型从配置读取)
        ./run_tool.sh --undo --connection-config connection_configs/my_server.yaml -y

        # 测试并启用自动禁用的渠道：使用指定配置，自动确认 (API 类型从配置读取)
        ./run_tool.sh --test-and-enable-disabled --connection-config connection_configs/my_server.yaml -y

        # 更新并以 DEBUG 级别记录日志到指定文件，不清理配置 (API 类型从配置读取)
        ./run_tool.sh --update --connection-config connection_configs/my_server.yaml --log-level DEBUG --log-file /var/log/oneapi_updater.log -y
        ```

## 命令行参数

```
usage: run_tool.sh [-h] [--update | --undo | --test-and-enable-disabled] [--connection-config <path>] [--clear-config] [-y]
                   [--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}] [--log-file <path>]

One API 渠道批量更新工具

运行模式 (选择一种):
  --update              执行更新操作 (默认行为)。
  --undo                执行撤销操作，恢复到上次执行更新前的状态。
                        需要选择或指定连接配置 (API 类型将从配置中读取)。
  --test-and-enable-disabled
                        测试自动禁用的渠道并尝试启用它们 (需要指定 --connection-config)。
                        支持 newapi 和 voapi 类型。
单站点目标:
  --connection-config <path>
                        指定单站点操作的目标连接配置文件路径。
                        (例如: connection_configs/my_config.yaml)
                        如果未提供，将进入交互模式选择。
  # --api-type 参数已被移除，API 类型现在从连接配置文件中读取。

更新选项 (仅在 --update 模式下有效):
  --clear-config        在更新成功完成后，将 'update_config.yaml'
                        恢复为默认的干净状态。

通用控制:
 -y, --yes             自动确认所有提示 (包括模拟运行后的执行确认)。

日志选项:
  --log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        设置日志记录级别 (默认为 INFO)。
  --log-file <path>     指定日志文件的具体路径或目录。
                        默认为在 'oneapi_tool_utils/runtime_data/logs/' 目录下创建带时间戳的轮转日志文件
                        (例如: .../logs/channel_updater.log)。
                        如果提供空字符串 '' 或 'none'，则不写入文件。

options:
  -h, --help            show this help message and exit

```

## 配置文件示例

### `connection_config.example` (位于根目录)

```yaml
# One API 实例的访问地址
site_url: "https://your-one-api-domain.com"

# One API 管理员令牌
api_token: "YOUR_ONE_API_ADMIN_TOKEN"

# 用于记录操作日志的用户 ID (可选, 默认为 '1')
user_id: "YOUR_ONE_API_USER_ID_FOR_LOGS"

# 目标 One API 实例的接口类型 (必需)
# 用于指定脚本应使用哪种 API 协议与你的 One API 实例通信。
# 有效值:
#   "newapi": 适用于较新版本的 One API (通常指包含 /api/channel/ 接口的版本)。
#   "voapi": 适用于较旧版本的 One API (通常指包含 /api/v1/channel/ 接口的版本)。
# 请根据你的 One API 实例版本选择正确的值。
# 示例: "newapi" 或 "voapi"
api_type: "newapi" # 或 "voapi"
```

### `update_config.example` (位于根目录)

```yaml
# 筛选条件
filters:
  # 渠道名称包含列表中的任意一个字符串
  name_filters: ["Example Channel", "Test"]
  # 渠道分组属于列表中的任意一个
  group_filters: ["default"]
  # 渠道支持的模型包含列表中的任意一个
  model_filters: ["gpt-4", "claude-3-opus"]
  # 渠道标签包含列表中的任意一个
  tag_filters: ["Official"]
  # 渠道类型为列表中的任意一个数字 (例如 0: OpenAI, 1: Anthropic, 8: 自定义)
  type_filters: [0, 1, 8]
  # 筛选模式:
  # "any": 满足任一启用的筛选器类型内部的任一条件即可
  # "all": (暂未完全实现，目前行为类似 any) 要求所有启用的过滤器类型都必须至少匹配一个条件
  match_mode: "any"

# 要应用的更新
updates:
  # 更新渠道名称 (支持 overwrite 和 regex_replace 模式)
  name:
    enabled: false
    # --- 模式 1: overwrite (默认) ---
    # mode: "overwrite"
    # value: "New Channel Name" # 提供新的渠道名称字符串

    # --- 模式 2: regex_replace ---
    # 使用正则表达式查找并替换名称中的部分内容。
    mode: "regex_replace"
    value:
      # pattern: 要查找的正则表达式模式。
      pattern: "Prefix-"
      # replacement: 用于替换匹配项的字符串。空字符串表示删除。
      replacement: ""
  # 更新模型列表 (支持 overwrite, append, remove 模式)
  models:
    enabled: false # 是否启用此项更新
    mode: "overwrite" # 或 "append", "remove"
    # 更新后的模型列表 (会被转换为逗号分隔字符串提交给 API)
    value: ["gpt-4-turbo", "gpt-4o"]
  # 更新分组 (支持 overwrite, append, remove 模式)
  group:
    enabled: false
    mode: "overwrite" # 或 "append", "remove"
    # 更新后的分组 (逗号分隔字符串)
    value: "vip,svip"
  # 更新模型映射 (支持 overwrite, merge, delete_keys 模式)
  model_mapping:
    enabled: false
    # 更新后的模型映射 (字典)
    value:
      gpt-3.5-turbo: gpt-4
      claude-3-opus: claude-3-haiku
  # 更新标签 (支持 overwrite, append, remove 模式)
  tag:
    enabled: false
    mode: "overwrite" # 或 "append", "remove"
    # 更新后的标签列表 (会被转换为逗号分隔字符串提交给 API)
    value: ["Internal", "Stable"]
  # 更新优先级 (仅 overwrite 模式)
  priority:
    enabled: false
    # 更新后的优先级 (数字)
    value: 10
  # 更新权重 (仅 overwrite 模式)
  weight:
    enabled: false
    # 更新后的权重 (数字)
    value: 5
  # 更新额外设置 (支持 overwrite, merge, delete_keys 模式)
  setting:
    enabled: false
    # 更新后的额外设置 (字典)
    value:
      temperature: 0.8
      top_p: 0.9
  # 更新测试模型 (仅 overwrite 模式)
  # 注意: 测试模型用于渠道编辑界面的手动测试按钮。
  # 脚本的 "--test-and-enable-disabled" 功能会自动选择测试模型：
  # 优先使用渠道配置的 test_model，其次使用 models 列表的第一个。
  test_model:
    enabled: false
    # 更新后的测试模型 (字符串)
    value: "gpt-3.5-turbo"
  # 更新自动禁用状态 (仅 overwrite 模式)
  auto_ban:
    enabled: false
    # 更新后的自动禁用状态 (0: 禁用自动禁用, 1: 启用自动禁用)
    value: 0 # 示例：禁用自动禁用
  # 更新 Base URL / 代理 (仅 overwrite 模式)
  base_url:
    enabled: false
    # 更新后的 Base URL (空字符串表示移除)
    value: ""
  # 更新状态码映射 (支持 overwrite, merge, delete_keys 模式)
  status_code_mapping:
    enabled: false
    # 更新后的状态码映射 (字典)
    value:
      "429": "500"
      "401": "403"
  # 更新渠道状态 (仅 overwrite 模式)
  status:
    enabled: false
    # 更新后的状态 (1: 启用, 2: 手动禁用, 3: 自动禁用)
    value: 1
  # 更新请求头 (支持 overwrite, merge, delete_keys 模式)
  headers:
    enabled: false
    mode: "overwrite" # 或 "merge", "delete_keys"
    value: {"X-Custom-Header": "Value"}
  # 更新 OpenAI Organization (仅 overwrite 模式)
  openai_organization:
    enabled: false
    value: "org-xxxxxxxxxxxx"
  # 更新覆盖参数 (支持 overwrite, merge, delete_keys 模式)
  override_params:
    enabled: false
    mode: "overwrite" # 或 "merge", "delete_keys"
    value: {"temperature": 0.5}
  # ... 可以添加其他 API 支持的字段

  # "append": (适用于列表字段如 models, group, tag) 将源字段的值追加到目标字段 (去重)
  # "remove": (适用于列表字段) 从目标字段中移除源字段包含的值
  # "merge": (适用于字典字段如 model_mapping, setting) 合并源字段到目标字段 (源优先)
  # "delete_keys": (适用于字典字段) 从目标字段中删除源字段包含的键
  copy_mode: "overwrite"

```
(请参考 `update_config.example` 文件获取最新的配置项列表和注释)


### `cross_site_config.example` (位于根目录)

```yaml
# cross_site_config.example
# 用于配置跨 One API 实例的渠道操作

# --- 操作定义 ---
# 目前支持的操作类型:
#   - copy_fields: 从源渠道复制指定字段到目标渠道
action: "copy_fields" # (必需) 指定要执行的操作类型

# --- 源实例配置 ---
source:
  connection_config: "connection_configs/source_instance.yaml" # (必需) 源实例的连接配置文件路径
  channel_filter: # (必需) 用于精确匹配单个源渠道的筛选器
    # 示例: 使用名称匹配
    name_filters: ["PaidOpenAI_Source"]
    # 可以添加其他筛选器 (group_filters, model_filters, tag_filters, type_filters) 确保唯一性

# --- 目标实例配置 ---
# 目前支持 1 对 1 操作，未来可能扩展为列表支持 1 对 N
target:
  connection_config: "connection_configs/target_instance.yaml" # (必需) 目标实例的连接配置文件路径
  channel_filter: # (必需) 用于精确匹配单个目标渠道的筛选器
    # 示例: 使用名称匹配
    name_filters: ["PaidOpenAI_Target"]

# --- 操作特定参数 ---
# 参数内容取决于上面定义的 'action'

# == 参数 for action: "copy_fields" ==
copy_fields_params:
  fields_to_copy: ["models", "group"] # (必需) 要复制的字段列表
  copy_mode: "overwrite" # (可选, 默认 "overwrite") 复制模式: overwrite, append, remove, merge, delete_keys (具体支持取决于字段类型)

# == (未来可以添加其他 action 的参数段) ==
# compare_fields_params:
#   fields_to_compare: ["models", "base_url"]
#   report_format: "diff"

# == 参数 for action: "compare_fields" ==
compare_fields_params:
  fields_to_compare: ["models", "group", "priority"] # (必需) 要比较值的字段列表

```
(请参考 `cross_site_config.example` 文件获取最新的配置项列表和注释)


## 注意事项

*   请确保提供的 `api_token` 具有管理员权限以修改渠道。
*   批量操作具有风险，请在执行前仔细检查 `update_config.yaml` 中的筛选条件和更新内容。
*   **强烈建议仔细查看模拟运行阶段显示的计划变更**，确认筛选结果和计划的更改符合预期，然后再确认执行实际更新。
*   **撤销功能**:
    *   撤销操作依赖于上次成功执行更新时自动保存在 `oneapi_tool_utils/runtime_data/undo_data/` 目录下的文件。
    *   如果 `save_undo_data` 步骤失败（例如 API 访问或文件写入问题），则该次更新无法被撤销。
    *   撤销会尝试恢复文件中记录的所有渠道的状态，如果某个渠道在保存后被手动删除，撤销操作可能会失败或产生非预期结果。
    *   执行撤销前，请确保选择了与上次更新时相同的 `--connection-config` (API 类型将从配置中自动读取)。
*   如果渠道数量非常多，获取渠道列表可能需要一些时间。脚本内置了最大页数限制以防止因 API 分页问题导致的无限循环。
*   `newapi` 和 `voapi` 支持的更新字段可能略有不同，脚本会尝试应用所有在 `updates` 中启用的字段，目标 API 不支持的字段会被忽略或报错（具体行为取决于目标 API）。
*   **并发、超时与分页**: 可以通过编辑根目录下的 `script_config.yaml` 文件来调整最大并发请求数 (`max_concurrent_requests`)、请求超时时间 (`request_timeout`) 以及获取渠道列表时的分页大小 (`api_page_sizes`)，以优化脚本性能和稳定性，特别是在与本地或网络不稳定的 API 交互时，或处理大量渠道时。**注意**: 部分较旧的 `voapi` 实例可能不支持或忽略获取渠道列表时的 `page_size` 参数，即使配置了较大的值，服务器仍可能只返回默认数量（通常是 10 条）的记录。

## 许可证

本项目采用 [MIT 许可证](LICENSE)。