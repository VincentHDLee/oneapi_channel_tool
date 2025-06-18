# One API 渠道批量更新工具 (One API Channel Batch Update Tool)

这是一个 Python 脚本，用于批量更新 [One API](https://github.com/songquanpeng/one-api) 实例中的渠道配置。它允许你根据名称、分组、模型或标签筛选渠道，并更新它们的多个属性。支持多种 One API 版本（通过 `newapi` 和 `voapi` 类型区分）和灵活的配置方式。

## 功能

*   **多 API 类型支持**: 通过在连接配置中指定 `api_type` (`newapi` 或 `voapi`)，适配不同版本的 One API 接口。
*   **灵活配置**:
    *   使用 `connection_configs` 目录管理多个 One API 实例的连接信息。
    *   使用 `update_config.yaml` 定义渠道筛选规则和要应用的更新。
*   **交互式与非交互式运行**:
    *   直接运行 `python main_tool.py` 进入交互模式，引导选择连接配置（API 类型将从配置中自动读取）。
    *   **交互式主菜单**: 在交互模式下，如果检测到上次操作的撤销文件，会显示菜单让用户选择执行新更新、撤销上次操作（并显示上次更新摘要）、查询所有渠道（可配合 `query_config.yaml` 进行筛选和自定义字段显示）或退出。
    *   支持命令行参数，方便自动化和脚本调用，包括新增的 `--find-key` 用于直接查询特定 API Key 的渠道。
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
    *   **测试指定模型的渠道**: 新增功能，允许用户通过专用配置文件 (`channel_model_test_config.yaml`) 筛选渠道，并针对这些渠道测试特定模型的可用性，输出详细的测试结果。

## 更新日志 (Changelog)

项目的详细变更历史记录在 [CHANGELOG.md](CHANGELOG.md) 文件中。

## One API, New API, VoAPI 项目概述与本工具的关联

本节旨在澄清 `One API`、`New API` 和 `VoAPI` 这三个项目之间的关系，并说明本批量更新工具如何有效地管理基于这些系统的实例。我们之前的 README 可能对此存在一些估计偏差，现根据官方（或项目自身）文档进行修正。

### 项目简述

1.  **One API (`songquanpeng/one-api`)**
    *   **定位:** **基础与核心**。这是一个开源项目，旨在提供一个统一的、兼容 OpenAI API 标准的接口，用于访问多种大型语言模型（如 OpenAI、Azure、Claude、Gemini、国内模型、Ollama 本地模型等）。
    *   **核心特性:** 强大的**渠道管理**（支持多种源、负载均衡、模型列表）、**令牌管理**（额度、有效期、权限控制）、**用户与分组管理**（支持不同计费倍率）、兑换码系统、日志记录、模型映射、多实例部署、基本的 Web UI 用于配置管理。
    *   **许可证:** MIT 许可证，但**要求在页面底部保留署名和项目链接**。
    *   **关键价值:** 稳定、通用、可扩展的 API 聚合与分发基础平台。

2.  **New API (`Calcium-Ion/new-api`)**
    *   **定位:** **功能增强型分支**。基于 `One API` 进行二次开发的开源项目，重点在于添加新功能和集成。
    *   **核心特性 (相比 One API 增加/增强):** 全新的 UI 界面、在线充值（易支付）、通过 Key 查询额度、支持按次计费、渠道加权随机、数据看板、更多登录方式（LinuxDO、Telegram、OIDC）、支持 Rerank/OpenAI Realtime/Claude Messages 等特定 API 格式、缓存计费、支持更多第三方渠道（如 Midjourney-Proxy, Suno API, Dify）。
    *   **许可证:** 继承 MIT 许可证（也应遵循 One API 的署名要求）。
    *   **关键价值:** 在 One API 基础上提供更多前沿功能、特定模型/服务集成和更灵活的运营选项。

3.  **VoAPI (`VoAPI/VoAPI`)**
    *   **定位:** **UI/UX 与特定运营功能优化型分支**。根据其 README，它基于 `New API` 和 `One API` 进行二次开发，但其性质为**闭源**，仅供个人学习使用，禁止商业用途。
    *   **核心特性 (相比 New API 增加/优化):** 显著的**界面风格差异与美化**、更好的国际化 (i18n) 支持、服务监控页、签到功能、易支付自定义渠道、模型价格页增强（单位/倍率切换、模型信息展示）、敏感词风控、全局速率限制、用户余额每日清空、自定义主题色、SEO 支持、Playground 优化、后台 JSON 编辑器、API 多线路支持、自定义菜单等。**明确不支持** New API 中的某些第三方渠道（如 Midj, Suno）。
    *   **许可证:** 项目声明为闭源，仅供个人学习，禁止商用。
    *   **关键价值:** 提供高度优化的用户界面和针对特定运营场景（如签到、风控、多语言）的功能增强，但牺牲了部分 New API 的第三方集成和开源特性。

### 本工具如何服务于这些项目

本 "One API 渠道批量更新工具" 旨在**极大简化和提升**对上述任一系统（One API、New API、VoAPI）中**渠道（Channels）的管理效率**，尤其是在拥有大量渠道需要维护时。其核心价值体现在：

1.  **通用渠道管理:** 所有这三个项目都依赖“渠道”来对接上游 API 供应商。本工具的核心功能——**批量查询、筛选和更新渠道属性**——对它们都至关重要。
2.  **精细化筛选:** 通过名称、分组、模型、标签、类型、ID 以及 **API Key (使用 `key_filter`，尤其对 `voapi` 实例有效)** 等多种条件筛选渠道，方便您精确地定位需要修改的目标，无论您使用的是哪个系统。
3.  **批量属性更新:** 支持批量修改渠道的常见且关键的属性，例如：
    *   `models`: 管理渠道支持的模型列表。
    *   `group`: 批量调整渠道所属分组。
    *   `base_url`: 统一更新代理地址或接口节点。
    *   `status`: 批量启用或禁用渠道。
    *   `priority` / `weight`: 调整渠道的负载均衡优先级和权重。
    *   `model_mapping`: 批量设置模型重定向规则。
    *   `headers`: 统一添加或修改请求头。
    *   `name`: 支持覆盖或使用正则表达式批量重命名。
    *   以及其他如 `tag`, `setting`, `test_model`, `auto_ban`, `status_code_mapping`, `openai_organization`, `override_params` 等（具体字段支持取决于目标 API 版本）。
4.  **适配不同 API 分支:** 工具通过在 `connection_configs` 中设置 `api_type` (`newapi` 或 `voapi`) 来适配不同分支版本可能存在的 API Endpoint 差异（例如 `newapi` 通常使用 `/api/channel/` 路径，而 `voapi` 可能使用 `/api/v1/channel/` 或其他特定路径）。**您需要根据您目标实例的实际接口结构选择正确的 `api_type`**。
5.  **安全与效率:**
    *   **模拟运行与确认:** 强制的模拟运行步骤让您在实际更改前预览所有变更，防止误操作。
    *   **撤销功能:** 为单站点更新提供了一层保障，允许回滚到上次成功更新前的状态。
    *   **并发处理:** 利用异步请求提高处理大量渠道时的效率。
6.  **高级维护功能:**
    *   **测试并启用禁用渠道 (`--test-and-enable-disabled`):** 自动化地检查自动禁用的渠道是否恢复可用，并根据测试结果（智能处理 429 错误）决定是否重新启用，极大减轻了渠道维护负担。
    *   **跨站点操作:** 支持在不同实例间复制或比较渠道配置，便于环境同步或迁移。

总之，无论您运营的是原版 One API、功能丰富的 New API，还是界面优化的 VoAPI，只要您需要管理超过少量渠道，本工具都能提供强大的、自动化的批量管理能力，显著提升您的运营效率和准确性。只需确保在连接配置中正确设置 `api_type` 以匹配您所管理的实例即可。
## 目录结构

```
.
├── channel_manager_lib/      # 工具核心逻辑库
│   ├── __init__.py           # 将此目录标记为 Python 包
│   ├── cli_handler.py        # 命令行和交互逻辑
│   ├── config_utils.py       # 配置加载和路径常量
│   ├── cross_site_handler.py # 跨站点操作流程协调器 (加载配置、调用 actions)
│   ├── cross_site_actions.py # 跨站点具体操作的执行逻辑 (复制、比较等)
│   ├── log_utils.py          # 日志设置
│   ├── single_site_handler.py # 单站点操作逻辑
│   └── undo_utils.py         # 撤销逻辑
├── connection_configs/       # 存放用户定义的 One API 实例连接配置 (YAML)
│   └── your_connection_config.yaml # 示例：你的连接配置
├── oneapi_tool_utils/        # One API 通信层、工具函数和运行时数据
│   ├── channel_tool_base.py  # API 通信的抽象基类
│   ├── newapi_channel_tool.py # New API (v0.6.0+) 类型实现
│   ├── voapi_channel_tool.py # VoAPI 类型实现
│   ├── config_loaders.py     # 配置加载和缓存逻辑
│   ├── data_helpers.py       # 数据规范化函数 (例如转为 set/dict)
│   ├── filtering_utils.py    # 渠道过滤逻辑
│   ├── network_utils.py      # 网络请求 (例如带重试的 session)
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
├── docs/                     # 文档目录
│   └── DEVELOPMENT.md        # 主要开发文档
│   └── ...                   # 其他开发相关文档
├── tests/                    # 测试文件目录
│   └── test_config_utils.py  # 示例测试文件
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
    # "newapi": 指 One API 的一个分支，通常使用 /api/channel/ 端点路径。
    # "voapi": 指 One API 的另一个分支，可能使用 /api/v1/channel/ 或其他特定端点路径。
    api_type: "newapi" # 或 "voapi"
    ```
    *   你可以创建多个 `.yaml` 连接配置文件来管理不同的 One API 实例。

3.  **配置操作规则**:
    *   **单站点批量更新**: 编辑根目录下的 `update_config.yaml` 文件（如果不存在，可以从 `update_config.example` 复制）。
        *   在 `filters` 部分设置筛选条件 (支持 `id`, `name_filters`, `group_filters`, `model_filters`, `tag_filters`, `type_filters` 以及新增的 `key_filter` 用于精确匹配 API Key)。
        *   在 `updates` 部分定义要应用的更新。
    *   **跨站点渠道操作**: 编辑根目录下的 `cross_site_config.yaml` 文件（如果不存在，可以从 `cross_site_config.example` 复制）。
        *   定义 `action` (例如 `copy_fields`)。
        *   配置 `source` 和 `target` 实例的连接配置路径和精确的渠道筛选器。
        *   根据所选 `action` 配置相应的参数（例如 `copy_fields_params`）。
        *   `compare_fields`: 比较源渠道和目标渠道指定字段的值，不进行修改。
        *   **测试指定模型的渠道**: 编辑根目录下的 `channel_model_test_config.yaml` 文件 (如果不存在，可以从 `channel_model_test_config.example` 复制)。
            *   设置 `target_connection_config` (在通过命令行参数 `--test-channel-model` 模式下必需；在交互式菜单模式下，此字段将被忽略，程序会使用菜单中选择的连接配置) 指向目标实例的连接配置。
            *   在 `filters` 部分设置筛选条件以选择要测试的渠道。
            *   在 `test_parameters` 部分指定 `model_to_test` (要测试的模型名称) 以及可选的报告参数。
    
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

        # 测试指定模型的渠道：使用指定的测试配置，自动确认 (API 类型从目标连接配置读取)
        ./run_tool.sh --test-channel-model channel_model_test_config.yaml -y
        ```

## 命令行参数

```
usage: run_tool.sh [-h] [--update | --undo | --test-and-enable-disabled | --find-key <API_KEY_TO_FIND> | --test-channel-model <test_config_path>]
                   [--connection-config <path>] [--clear-config] [-y]
                   [--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}] [--log-file <path>]

One API 渠道批量更新工具

运行模式 (选择一种):
  --update              执行更新操作 (默认行为，需要 --connection-config)。
  --undo                执行撤销操作 (需要 --connection-config)。
  --test-and-enable-disabled
                        测试自动禁用的渠道并尝试启用 (需要 --connection-config)。
  --find_key <API_KEY_TO_FIND>
                        查找指定 API Key 所在的渠道并打印其信息 (需要 --connection-config)。
  --test-channel-model <test_config_path>
                        根据指定的测试配置文件测试渠道对特定模型的支持情况。
                        (例如: channel_model_test_config.yaml)

连接配置 (部分模式需要):
  --connection-config <path>
                        指定目标连接配置文件路径 (用于 --update, --undo, --test-and-enable-disabled, --find-key)。
                        (例如: connection_configs/my_config.yaml)

更新操作特定选项 (当使用 --update 时):
  --clear-config        在 --update 操作成功完成后，将 'update_config.yaml'
                        恢复为默认干净状态。

测试模型操作特定选项 (当使用 --test-channel-model 时):
  --clear-test-model-config
                        在 --test-channel-model 操作成功完成后，将指定的测试配置文件
                        恢复为默认干净状态。
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
#   "newapi": 指 One API 的一个分支，通常使用 /api/channel/ 端点路径。
#   "voapi": 指 One API 的另一个分支，可能使用 /api/v1/channel/ 或其他特定端点路径。
# 请根据你的 One API 实例版本选择正确的值。
# 示例: "newapi" 或 "voapi"
api_type: "newapi" # 或 "voapi"
```

### `update_config.example` (位于根目录)

```yaml
# 筛选条件: 用于选择要执行更新操作的目标渠道
# 注意: 所有启用的筛选器和排除器都会生效。
filters:
  # --- 包含性筛选器 ---
  # 如果启用了以下任何一个过滤器，渠道必须满足该过滤器中的 *至少一个* 条件才会被考虑。

  # 渠道 ID 精确匹配: 如果提供，则仅匹配此 ID 的渠道，其他筛选器将被忽略。
  # id: 123 # 示例：只操作 ID 为 123 的渠道

  # API Key 精确匹配: 如果提供 (且 id 未提供)，则仅匹配此 API Key 的渠道。
  # 主要用于 voapi 实例，因为 newapi 实例通常不在渠道列表 API 中返回 key。
  # key_filter: "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" # 示例：替换为实际的 API Key

  # 渠道名称过滤器: 列表中的字符串会被用于 *部分匹配* 渠道名称 (区分大小写)。
  name_filters: ["Example Channel", "Test"]

  # 渠道分组过滤器: 列表中的字符串会与渠道所属的分组进行 *完全匹配*。
  group_filters: ["default"]

  # 支持模型过滤器: 列表中的模型名称会与渠道支持的模型列表进行 *完全匹配*。
  model_filters: ["gpt-4", "claude-3-opus"]

  # 渠道标签过滤器: 列表中的标签会与渠道设置的标签进行 *完全匹配*。
  tag_filters: ["Official"]

  # 渠道类型过滤器: 列表中的数字会与渠道的类型 ID 进行 *完全匹配*。
  type_filters: [0, 9]

  # --- 排除性筛选器 (在包含性筛选器之后应用，具有否决权) ---
  exclude_name_filters: ["_复制", "_backup"]
  exclude_group_filters: ["test", "deprecated"]
  exclude_model_filters: ["gpt-3.5-turbo-instruct"]
  exclude_model_mapping_keys: ["gpt-3.5-turbo"]
  exclude_override_params_keys: ["temperature"]

  # --- 筛选逻辑模式 (适用于多个启用的包含性筛选器之间的关系) ---
  match_mode: "any" # "any" 或 "all"

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

### `channel_model_test_config.example` (位于根目录)

```yaml
# channel_model_test_config.example
# 用于配置“测试指定模型的渠道”功能的配置文件

# (在通过命令行参数 --test-channel-model 模式下必需；
#  在交互式菜单模式下，此字段将被忽略，程序会使用菜单中选择的连接配置)
target_connection_config: "connection_configs/your_connection_config_here.yaml"

# (必需) 筛选条件，结构与 update_config.yaml 中的 filters 部分完全相同。
filters:
  name_filters: ["FreeGemini"] # 示例
  match_mode: "any"

# (必需) 测试参数
test_parameters:
  model_to_test: "gemini-1.5-flash-8b-latest" # (必需) 要测试的模型
  report_failed_only: false # (可选) 是否只报告失败的渠道
  continue_on_failure: true # (可选) 是否在失败后继续测试其他渠道
```
(请参考 `channel_model_test_config.example` 文件获取完整的配置项列表和详细注释)


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

## 常见HTTP错误码及处理建议

在使用本工具或与 One API 实例交互时，了解常见的 HTTP 状态码有助于快速定位和解决问题。

*   **429 Too Many Requests**:
    *   **原因**: 本工具为非侵入式工具，尽可能模拟人工操作。当设置的并发请求数量 (`max_concurrent_requests` in `script_config.yaml`) 过大，或者短时间内对同一 One API 实例执行过多操作时，可能会超出服务器的速率限制，导致服务器返回 429 错误，拒绝部分或全部请求。
    *   **建议**:
        *   适当降低 `script_config.yaml` 中的 `max_concurrent_requests` 值。
        *   如果问题依然存在，请检查 One API 实例本身是否有全局或针对特定 IP 的速率限制配置。
        *   部分 API 供应商可能会在响应头中包含 `Retry-After` 信息，指示需要等待多久才能重试。

### 其他可供参考的 HTTP 状态码

#### 4xx 客户端错误 (Client Errors)
这些错误通常表示客户端发送的请求有问题：
*   **400 Bad Request**: 请求格式错误，服务器无法理解（例如，参数缺失或格式不正确）。
    *   **建议**: 检查 `update_config.yaml` 或其他配置文件的语法和参数是否正确，参照示例文件。
*   **401 Unauthorized**: 未授权，通常表示 `api_token` 无效或缺失。
    *   **建议**: 确认 `connection_configs/` 下对应连接配置文件中的 `api_token` 是否正确且具有管理员权限。
*   **403 Forbidden**: 服务器理解请求，但拒绝执行。这可能意味着 `api_token` 有效但权限不足以执行特定操作（例如，只读权限无法进行更新）。
    *   **建议**: 确保使用的 `api_token` 对应的用户拥有足够的权限。
*   **404 Not Found**: 请求的资源不存在。例如，尝试访问一个不存在的渠道 ID，或者 `site_url` 配置错误导致 API 端点不正确。
    *   **建议**: 检查 `site_url` 和请求的资源标识（如渠道 ID）是否正确。
*   **408 Request Timeout**: 客户端请求超时，服务器未在规定时间内收到完整请求。
    *   **建议**: 检查网络连接，或适当增加 `script_config.yaml` 中的 `request_timeout` 值。
*   **413 Payload Too Large**: 请求体过大，服务器无法处理。
    *   **建议**: 如果在更新包含大量数据的字段（如 `model_mapping` 或 `headers`），尝试分批更新。
*   **414 URI Too Long**: 请求的URI过长，服务器拒绝处理。
    *   **建议**: 一般不常见于此工具，但如果发生，请检查配置。
*   **415 Unsupported Media Type**: 请求的媒体类型不被服务器支持。
    *   **建议**: 工具通常使用 `application/json`，此错误不常见。

#### 5xx 服务器错误 (Server Errors)
这些错误表示服务器端出现问题：
*   **500 Internal Server Error**: 服务器内部错误，这是一个通用的错误码，表示服务器遇到了未预料到的情况。
    *   **建议**: 查看 One API 实例的服务器日志以获取更详细的错误信息。
*   **502 Bad Gateway**: 网关或代理服务器从上游服务器收到了无效的响应。如果 One API 部署在反向代理后面，可能是代理配置问题。
    *   **建议**: 检查代理服务器配置和 One API 实例的健康状况。
*   **503 Service Unavailable**: 服务器暂时无法处理请求，通常是由于过载或正在进行维护。
    *   **建议**: 稍后重试。检查 One API 实例的运行状态和资源占用。
*   **504 Gateway Timeout**: 网关或代理服务器未及时从上游服务器获得响应。
    *   **建议**: 检查网络连接和上游服务器（One API 实例）的响应能力。

#### 其他常见状态码
*   **200 OK**: 请求成功（非错误码，但常用于对比）。
*   **201 Created**: 请求成功并且服务器创建了新的资源。
*   **204 No Content**: 请求成功，但没有内容返回（例如，删除操作成功后）。
*   **301 Moved Permanently**: 请求的资源已被永久移动到新位置。
    *   **建议**: 更新 `site_url` 为新的正确地址。
*   **302 Found** (或 307 Temporary Redirect): 资源临时重定向。
    *   **建议**: 检查 `site_url` 是否正确，或网络中是否存在透明代理。

如果遇到未列出的错误码，建议查阅相关 HTTP 规范或 One API 项目的文档。
## 定时任务示例 (Scheduled Task Examples)

你可以使用操作系统的任务调度器来定期执行某些维护任务，例如自动测试并启用已禁用的渠道。

### Linux (使用 cron)

1.  打开你的 crontab 进行编辑：
    ```bash
    crontab -e
    ```
2.  添加一行来定义任务。以下示例表示每天凌晨 3:00 执行一次“测试并启用禁用渠道”任务，目标是 `connection_configs/my_config.yaml`，并将日志附加到 `/var/log/oneapi_channel_test_enable.log`：
    ```cron
    0 3 * * * cd /path/to/oneapi_channel_tool && ./run_tool.sh --test-and-enable-disabled --connection-config connection_configs/my_config.yaml -y >> /var/log/oneapi_channel_test_enable.log 2>&1
    ```
    *   **重要:** 将 `/path/to/oneapi_channel_tool` 替换为本项目的实际绝对路径。
    *   将 `connection_configs/my_config.yaml` 替换为你的目标连接配置文件路径。
    *   确保运行 `cron` 的用户有权限进入项目目录、执行 `run_tool.sh` 并写入指定的日志文件。
    *   `-y` 参数用于自动确认，因为定时任务无法进行交互。
    *   `>> /var/log/oneapi_channel_test_enable.log 2>&1` 将标准输出和标准错误都附加到日志文件中。

### Windows (使用任务计划程序 Task Scheduler)

1.  打开“任务计划程序”（可以通过在开始菜单搜索 "Task Scheduler" 找到）。
2.  在右侧操作栏中，点击“创建基本任务...”。
3.  **名称:** 给任务起一个描述性的名称，例如 "OneAPI Channel Test & Enable"。
4.  **触发器:** 选择任务执行的频率（例如，“每天”）。设置具体的执行时间（例如，凌晨 3:00）。
5.  **操作:** 选择“启动程序”。
6.  **程序或脚本:** 浏览并找到你的 `python.exe` 或你环境中用于运行 Python 脚本的可执行文件（如果使用了虚拟环境，路径可能不同）。
7.  **添加参数 (可选):**
    *   在这里输入脚本的完整路径和所需的命令行参数。你需要将整个 `./run_tool.sh ...` 命令转换为直接调用 `main_tool.py` 的形式，因为 Task Scheduler 通常直接运行可执行文件。
    *   示例： `C:\path\to\oneapi_channel_tool\main_tool.py --test-and-enable-disabled --connection-config connection_configs\my_config.yaml -y`
    *   **重要:** 将 `C:\path\to\oneapi_channel_tool\` 替换为项目的实际路径。使用 Windows 风格的反斜杠 `\`。
    *   将 `connection_configs\my_config.yaml` 替换为你的目标连接配置文件路径。
8.  **起始位置 (可选):**
    *   输入项目的根目录路径，例如 `C:\path\to\oneapi_channel_tool\`。这确保脚本能正确找到相对路径的配置文件。
9.  **完成:** 查看设置并点击“完成”。
10. **(推荐) 配置日志记录:** 由于直接在参数中重定向输出比较复杂，建议在脚本内部或通过修改 `run_tool.sh` (如果 Windows 环境支持 shell 脚本) 来处理日志记录，或者依赖脚本默认的日志文件功能 (`oneapi_tool_utils/runtime_data/logs/`)。你也可以配置任务计划程序将操作输出记录到其历史记录中。

**注意:** 确保运行任务的用户具有执行 Python 脚本和访问项目文件所需的权限。
## 许可证

本项目采用 [MIT 许可证](LICENSE)。