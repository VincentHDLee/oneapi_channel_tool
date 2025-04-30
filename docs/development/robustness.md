# 健壮性与可维护性

本文档记录了为提高工具健壮性和可维护性所做的改进和计划。

## 1. API 类型差异说明 (项目关系与技术细节)

*   **项目关系概述:** 本工具支持管理基于 `songquanpeng/one-api` (核心), `Calcium-Ion/new-api` (开源增强分支), 以及 `VoAPI/VoAPI` (闭源 UI/UX 优化分支) 的实例。理解它们的派生关系有助于理解潜在的 API 差异。`VoAPI` 是闭源项目，其 API 可能与 `New API` 或 `One API` 有更多未知差异。更详细的项目关系说明，请参见 `README.md` 中的 "One API, New API, VoAPI 项目概述与本工具的关联" 章节。

*(技术差异详细信息)* **(D2, I1)**

*   **主要差异点总结:**
    *   **认证 (Authentication):**
        *   `newapi`: `Authorization: <api_token>` (无 `Bearer` 前缀)
        *   `voapi`: `Authorization: Bearer <api_token>`
    *   **获取渠道列表 (Get Channels List - `GET /api/channel/`):**
        *   `newapi`:
            *   分页参数 `p` 从 0 开始计数。
            *   响应结构通常为 `{"success": true, "data": [channel_list]}`。
            *   **不返回**渠道的 `key` 字段。
        *   `voapi`:
            *   分页参数 `p` 从 1 开始计数。
            *   响应结构可能为 `{"success": true, "data": {"records": [channel_list]}}` 或 `{"success": true, "data": {"list": [channel_list]}}` 或 `{"success": true, "data": [channel_list]}`。脚本已尝试兼容这些结构。
            *   结束分页的判断逻辑更复杂，需要检查特定错误码 (400 且 message 含 'page') 或 `data` 为空/无效。
            *   **通常返回**渠道的 `key` 字段。
    *   **更新渠道 (Update Channel):**
        *   `newapi`: 使用 `PUT /api/channel/`，请求体包含渠道 ID。
        *   `voapi`: 端点和方法不确定，代码暂时假设使用 `PUT /api/channel/`，但实际可能不同（例如 `POST /api/vo/channel/update`），且可能只接受部分字段。需要进一步测试确认。
    *   **获取渠道详情 (Get Channel Details):**
        *   `newapi`: 使用 `GET /api/channel/{id}`，响应结构 `{"success": true, "data": {channel_details}}`。
        *   `voapi`: 端点不确定，代码暂时假设使用 `GET /api/channel/{id}`，但响应结构可能直接是 `{channel_details}` 或 `{"success": true, "data": {channel_details}}`。脚本已尝试兼容。
*   **影响:**
    *   获取密钥的差异会影响依赖密钥的操作，如跨站复制时的密钥处理（目标站需要手动设置）和某些测试场景。
    *   API 端点和响应结构的不确定性增加了 `voapi` 适配的复杂性，需要更多测试（见 `testing_validation.md`）。
    *   脚本中的错误处理和数据解析逻辑需要同时考虑两种 API 的行为。
*   **文档:** 已在 `README.md` 和本开发文档中记录这些差异。

## 2. 可配置的分页大小 (Configurable Page Size)

*(已添加)* **(D2, I2)**

*   **目标:** 允许用户通过 `script_config.yaml` 控制获取渠道列表时的分页大小，以优化大量渠道的获取效率并减少 API 调用次数。
*   **实现:** 在 `script_config.yaml` 中添加了 `api_page_sizes` 配置项，包含 `newapi` 和 `voapi` 两个子键，默认值均为 100。脚本在调用列表 API 时会使用对应 `api_type` 的分页大小。
*   **影响:** 提高了获取大量渠道时的性能和稳定性。
*   **注意:** 部分 `voapi` 类型的实例可能不支持或忽略 `page_size` 参数。

## 3. 配置验证

*(待办)* **(D2, I1)**

*   **目标:** 在脚本执行早期阶段，增加对所有加载的 YAML 配置文件 (`connection_config.yaml`, `update_config.yaml`, `cross_site_config.yaml`, `script_config.yaml`) 中值的类型、格式和逻辑有效性的校验。
*   **示例:**
    *   检查 `site_url` 是否为合法的 URL 格式。
    *   检查 `api_token` 是否非空。
    *   检查 `api_type` 是否为 "newapi" 或 "voapi"。
    *   检查 `update_config.yaml` 中 `updates` 下各字段的 `mode` 是否为该字段类型所支持的模式。
    *   检查 `filters` 中的值是否为预期的列表或字符串。
    *   检查 `cross_site_config.yaml` 中的 `action` 是否为支持的操作。
*   **实现:** 可以利用如 `Pydantic` 或 `Cerberus` 等库进行结构化验证，或者编写自定义的验证函数。在 `channel_manager_lib/config_utils.py` 中实现加载和验证逻辑。
*   **好处:** 提早发现配置错误，避免在后续流程中因配置问题导致意外失败，提供更友好的错误提示。

## 4. 更健壮的错误处理与报告

*(待办)* **(D1, I1)**

*   **目标:** 改进脚本在遇到 API 调用失败或其他运行时错误时的处理和报告机制。
*   **具体措施:**
    *   **解析 API 错误:** 尝试解析 One API 返回的错误响应体（通常是 JSON），提取其中的错误消息 (`message` 字段等)，并在日志和控制台输出中显示更具体的失败原因，而不仅仅是 HTTP 状态码。
    *   **配置文件错误定位:** 在配置验证失败时，尽可能指出错误发生在哪个配置文件的哪一行或哪个具体的键。
    *   **网络错误处理:** 对 `aiohttp` 可能抛出的常见网络异常（如连接超时、DNS 解析失败等）进行捕获和更友好的提示。
    *   **一致的错误日志格式:** 确保所有错误日志都包含足够上下文信息（例如正在处理哪个渠道、哪个 API 端点、相关的配置等）。

## 5. 自动化测试 (Automation Testing)

*(进行中)* **(D0, I1)**

*   **目标:** 引入自动化测试框架，确保核心逻辑的正确性和代码变更后的回归防护。
*   **测试类型:**
    *   **单元测试 (Unit Tests):** 针对 `channel_manager_lib` 中的各个模块和函数进行测试，特别是配置加载/验证、筛选逻辑、更新模式计算、API 参数构建等。可以使用 `pytest` 和 `unittest.mock`。
    *   **集成测试 (Integration Tests):** 测试模块间的交互，例如 `cli_handler` 调用 `single_site_handler` 的流程。可能需要模拟 `aiohttp` 的响应。
    *   **端到端测试 (End-to-End Tests):** (复杂度高，暂不实现) 运行真实的脚本命令，连接到一个测试用的 One API 实例（可能通过 Docker 启动）来验证完整的流程。
*   **挑战:** 测试依赖于外部 API 的部分比较困难，需要良好的 Mocking 策略或专门的测试环境。
*   **优先级:** 优先实现单元测试和关键流程的集成测试。

## 6. 增强筛选功能

*(待办)* **(D2, I1)**

*   **目标:** 完善 `update_config.yaml` 中的 `filters` 功能。
*   **具体措施:**
    *   **实现 "all" 匹配模式:** 当前 `match_mode: "all"` 的行为类似 "any"。需要修改筛选逻辑，确保当设置为 "all" 时，渠道必须满足**所有**启用的筛选器类型（`name_filters`, `group_filters`, `model_filters`, `tag_filters`, `type_filters`）中至少一个条件才会被选中。
    *   **考虑增加更多筛选字段:** 例如按 `status` (状态)、`priority` (优先级) 或 `base_url` 包含特定字符串等进行筛选。需要评估常用场景和实现复杂度。

## 7. 改进撤销功能

*(待办)* **(D2, I1)**

*   **目标:** 增强撤销功能的灵活性和用户体验。
*   **具体措施:**
    *   **选择性撤销 (Selective Undo):** (较复杂) 考虑允许用户在撤销时，只选择恢复部分被修改的渠道，而不是全部。这需要在撤销文件中记录更详细的信息，并修改撤销逻辑。
    *   **撤销预览:** 在执行撤销前，显示将要恢复的渠道列表和它们将被恢复成的状态。
    *   **更清晰的撤销文件管理:** 考虑在撤销成功后是否自动删除或归档对应的撤销文件。

## 8. 实现交互式主菜单

*(已完成)* **(D2, I1)**

*   **目标:** 在交互模式启动时，提供更清晰的操作入口，特别是当存在上次操作的撤销数据时。
*   **行为:**
    *   当用户在交互模式下选择完连接配置后，脚本会自动检查是否存在对应的最新撤销文件 (`oneapi_tool_utils/runtime_data/undo_data/undo_<api_type>_<config_name>_*.json`)。
    *   如果找到撤销文件：
        *   显示上次更新的摘要信息（例如时间、更新了多少渠道）。
        *   提示用户选择后续操作：`[1] 查询所有渠道`, `[2] 执行新更新`, `[3] 撤销上次操作`, `[4] 测试并启用禁用渠道`, `[0] 退出`。
    *   如果未找到撤销文件：
        *   提示用户选择后续操作：`[1] 查询所有渠道`, `[2] 执行新更新`, `[3] 测试并启用禁用渠道`, `[0] 退出`。
*   **实现位置:** 主要逻辑位于 `channel_manager_lib/cli_handler.py`。

## 9. 安全性审计

*(待办)* **(D2, I1)**

*   **目标:** 确保脚本在运行过程中不会意外泄露敏感信息，特别是 API 密钥。
*   **检查点:**
    *   **日志:** 检查所有级别的日志输出，确保不会记录完整的 `api_token` 或渠道的 `key` 字段。可以使用脱敏处理（例如只显示部分字符）。
    *   **屏幕输出:** 检查模拟运行和最终报告的输出，确保不显示敏感信息。
    *   **撤销文件:** 检查保存的撤销数据 (`undo_*.json`)，确保其中不包含明文密钥（理想情况下，撤销操作应只恢复非密钥字段，或者依赖 One API 自身机制处理密钥）。
## 10. (待办) 拆分跨站点处理模块 (Refactor Cross-Site Handler)

*(待办)* **(D1, I1)**

*   **目标:** 遵循项目规范（单文件不超过 1000 行，并在接近 500 行时考虑优化），对当前行数较多（约 720 行）的 `channel_manager_lib/cross_site_handler.py` 文件进行拆分，以提高可维护性。
*   **背景:** 该模块负责处理所有跨站点操作逻辑，随着功能增加（如 `copy_fields`, `compare_fields`），其复杂度也在增长。
*   **思路:** 考虑将不同的 `action` 处理逻辑（例如 `copy_fields` 的详细实现、`compare_fields` 的实现）或辅助函数（如渠道匹配、数据准备等）提取到新的辅助模块中。
*   **计划:** 在完成当前文档更新和代码提交后，着手分析 `cross_site_handler.py` 的结构，并执行拆分。
    *   **配置文件缓存:** 检查 `loaded_connection_configs/` 下缓存的 JSON 文件是否包含敏感信息（目前看应该还好，因为是内部使用）。

## 10. (可选) API 类型插件化

*(待办, 较复杂)* **(D0, I3)**

*   **目标:** 使添加对新版本或变种 One API（或其他类似 API）的支持更加容易，而无需修改大量核心代码。
*   **思路:**
    *   将 `NewApiChannelTool` 和 `VoApiChannelTool` 重构为插件类，实现共同的接口（例如 `get_channels`, `update_channel`, `test_channel` 等）。
    *   脚本在启动时动态发现和加载可用的 API 类型插件。
    *   `api_type` 配置用于选择加载哪个插件。
*   **复杂度:** 需要对现有 `oneapi_tool_utils` 结构进行较大调整，涉及依赖注入或插件管理机制。优先级较低。

## 11. (可选) 状态管理与缓存

*(待办)* **(D1, I3)**

*   **目标:** 对于拥有大量渠道（成千上万）的 One API 实例，减少重复获取渠道列表的开销。
*   **思路:**
    *   实现一个本地缓存机制（例如存储在文件或简单的数据库中），用于存储获取到的渠道列表。
    *   在执行操作前检查缓存是否有效（例如基于时间戳或实例状态），如果有效则从缓存读取，否则从 API 获取并更新缓存。
*   **挑战:** 需要处理缓存失效、数据一致性等问题。对于大多数用户场景可能不是必需的。