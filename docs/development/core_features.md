# 核心功能扩展

本文档记录了工具核心功能的开发细节。

## 1. 配置文件改进 (Configuration File Improvement)

*(已完成)* **(D1, I0)**

*   **采用 YAML 格式:** (已完成) 用户配置文件已迁移到 YAML (`connection_config.yaml`, `update_config.yaml`, `cross_site_config.yaml`)。
*   **实现 YAML 加载与转换:** (已完成) 代码已更新以加载 YAML。连接配置在加载后会被缓存为 JSON (`oneapi_tool_utils/runtime_data/loaded_connection_configs/`) 以提高后续读取性能。
*   **更新示例文件和文档:** (已完成) 相应的 `.example` 文件、README 和 `.gitignore` 已更新。

## 2. 添加更多字段更新支持

*(已完成)* **(D2, I0)**

*   **目标:** 确保脚本能够更新 One API UI 中可见的大部分常用渠道字段。
*   **已添加支持:** `name`, `type`, `models`, `group`, `model_mapping`, `tag`, `priority`, `weight`, `setting`, `test_model`, `auto_ban`, `base_url`, `status_code_mapping`, `status`, `headers`, `openai_organization`, `override_params`。
*   **注意:** 出于安全考虑，不支持通过此工具更新 `key` (API 密钥)。
*   **前置条件:** 完成此任务是实现更精细的字段级操作的基础。

## 3. 实现字段级新增/消减/合并操作

*(已完成)* **(D1, I0)**

*   **依赖:** 已添加更多字段更新支持。
*   **目标:** 对现有渠道的特定字段进行更精细的操作，而不是简单的完全覆盖。这通过在 `update_config.yaml` 的 `updates` 部分为每个字段增加一个可选的 `mode` 参数来实现。
*   **列表字段 (`models`, `group`, `tag`):**
    *   `mode: "overwrite"` (默认): 完全覆盖目标字段的值。
    *   `mode: "append"`: 将 `value` 中的项追加到目标字段（自动去重）。
    *   `mode: "remove"`: 从目标字段中移除 `value` 中包含的项。
*   **映射/字典字段 (`model_mapping`, `setting`, `status_code_mapping`, `headers`, `override_params`):**
    *   `mode: "overwrite"` (默认): 完全覆盖目标字段的值。
    *   `mode: "merge"`: 将 `value` 中的键值对合并到目标字段。如果键已存在，则更新其值；如果键不存在，则添加。
    *   `mode: "delete_keys"`: 从目标字段中删除 `value` 中列出的键（注意：`value` 此时应为一个键的列表，而不是字典）。

## 4. 实现复制并修改渠道功能 (Clone & Modify)

*(待办)* **(D1, I2)**

*   **目标:** 基于现有渠道快速创建具有不同配置的新渠道，无需手动处理 API 密钥。
*   **流程设想:**
    1.  允许用户在 `update_config.yaml` (或特定配置文件) 中定义一个源渠道筛选器和针对新渠道的修改规则。
    2.  脚本找到源渠道。
    3.  **关键依赖:** 调用 One API 的**复制渠道**端点（如果存在，需研究 API 文档确认）。如果不存在专门的复制 API，则需要先调用**创建渠道 API**，然后手动将源渠道的密钥等信息设置到新渠道，这会增加复杂性和安全风险。
    4.  获取新创建（或复制）渠道的 ID。
    5.  使用本工具现有的**更新逻辑**，根据用户定义的规则，修改这个**新渠道**的字段 (例如 `name`, `group`, `models` 等)。
*   **场景:** 适用于快速创建测试渠道、不同模型分组的渠道等。

## 5. (可选) 实现渠道级新增/删除功能

*(待办, 优先级较低)* **(D1, I2)**

*   **新增 (Create):**
    *   设计 `update_config.yaml` 或新配置格式来定义要创建的新渠道的完整属性（包括名称、类型、模型、分组、**密钥**等）。
    *   可能需要添加 `--create` 命令行参数。
    *   实现调用 One API 的 `create_channel` 接口的逻辑。
*   **删除 (Delete):**
    *   复用 `update_config.yaml` 中的 `filters` 逻辑来筛选要删除的渠道。
    *   添加 `--delete` 命令行参数。
    *   实现调用 One API 的 `delete_channel` 接口的逻辑。
    *   **高风险:** 必须设计非常严格的用户确认机制，例如多次确认、输入特定字符串等，以防止误删。

## 6. 实现自动测试并启用已禁用渠道功能

*(已完成)* **(D1, I1)**

*   **目标:** 自动恢复因临时问题（如配额耗尽、网络波动）而被 One API 系统自动禁用（状态 `status=3`）的渠道。
*   **触发方式:** 通过命令行参数 `--test-and-enable-disabled` 或交互模式下的相应选项触发。
*   **流程:**
    1.  使用指定的连接配置连接到 One API 实例。
    2.  筛选出所有 `status` 为 3 的渠道。
    3.  对每个筛选出的渠道执行并发测试：
        *   **选择测试模型:** 优先使用渠道配置的 `test_model` 字段；如果未设置，则使用 `models` 列表中的第一个模型。
        *   向 One API 的测试端点 (`/api/channel/test/{id}?model=...` 或 `/api/v1/channel/test/{id}?model=...`，取决于 `api_type`) 发送测试请求。
        *   **获取密钥:** 由于 `newapi` 不返回 `key`，此功能目前依赖于 `voapi` 或需要用户在测试前通过其他方式确保渠道密钥有效（或在未来版本中考虑其他测试方式）。*(注：根据 README，此功能现在支持 `newapi` 和 `voapi`，需要确认 `newapi` 的测试实现方式，是否依赖于 One API `/test` 接口本身不需要密钥？或是实现细节有调整？)*
    4.  **检查测试结果:** 解析测试请求的响应。
        *   如果响应表示成功 (`success: true`)，则认为该渠道已恢复。
        *   如果测试失败，记录失败原因。
    5.  **智能确认:**
        *   如果所有测试失败的原因**仅为**配额问题（HTTP 状态码 429），并且至少有一个渠道测试成功，脚本将自动标记这些成功的渠道进行启用（除非使用了 `-y` 参数，否则会在最后汇总显示并请求最终确认）。
        *   如果存在**任何其他类型**的测试失败（例如无效密钥、网络错误等），脚本将在汇总显示所有计划的启用操作后，**强制要求用户确认**。
    6.  **执行启用:** 对于确认要启用的渠道（测试通过且用户已确认），调用 API 将其 `status` 更新为 1 (启用)。
*   **配置:** 并发数和超时时间由 `script_config.yaml` 中的 `max_concurrent_requests` 和 `request_timeout` 控制。

## 7. 实现跨站点渠道操作功能 (Cross-Site Channel Operation)

*(进行中)* **(D1, I1)**

*   **目标:** 允许用户在不同的 One API 实例（例如开发环境和生产环境）之间执行渠道相关的操作，主要是将一个实例的渠道配置迁移或同步到另一个实例。
*   **触发方式:** 交互模式下选择“跨站点操作”。
*   **配置:** 使用项目根目录下的 `cross_site_config.yaml` 文件进行配置。
    *   **`action`:** (必需) 指定要执行的操作，目前计划支持：
        *   `copy_fields`: **(核心需求)** 模拟将源渠道的信息（**不包括 ID 和密钥**）复制到目标渠道。此操作涉及：
            *   从源渠道获取指定或全部字段的值。
            *   将这些值（根据 `copy_mode`）应用到目标渠道。这本质上是在目标实例上执行一次**更新**操作。
            *   **需要为目标实例生成并保存撤销 (Undo) 数据**，以便可以回滚此次“复制”（更新）操作。
        *   `compare_fields`: 比较源渠道和目标渠道指定字段的值，不进行修改，仅报告差异。
    *   **`source`:** (必需) 定义源实例。
        *   `connection_config`: 指向源实例的 `connection_configs/` 下的 YAML 文件路径。
        *   `channel_filter`: (必需) **筛选器**，用于匹配**一个或多个**源渠道。可以使用与单站点更新 (`update_config.yaml`) 类似的完整筛选器 (`name_filters`, `group_filters`, `model_filters`, `exclude_name_filters` 等)。
    *   **`target`:** (必需) 定义目标实例。
    *   `connection_config`: 指向目标实例的 `connection_configs/` 下的 YAML 文件路径。
    *   `channel_filter`: (必需) **筛选器**，用于匹配**一个或多个**目标渠道。可以使用与单站点更新类似的完整筛选器。
    *   **操作特定参数:** 根据 `action` 的值配置。
        *   **`copy_fields_params`:** (当 `action: "copy_fields"`)
            *   `fields_to_copy`: (必需) 要复制的字段名称列表 (字符串列表)。
            *   `copy_mode`: (可选, 默认 "overwrite") 复制模式，同单站点更新的 `mode` (overwrite, append, remove, merge, delete_keys)。脚本会根据字段类型选择合适的模式子集。
        *   **`compare_fields_params`:** (当 `action: "compare_fields"`)
            *   `fields_to_compare`: (必需) 要比较值的字段名称列表。
*   **流程:**
    1.  用户选择交互模式下的“跨站点操作”。
    2.  加载并验证 `cross_site_config.yaml`。
    3.  加载 `source` 和 `target` 的连接配置。
    4.  创建 `source` 和 `target` 的 `ChannelTool` 实例。
    5.  **获取匹配渠道:** 分别使用 `source` 和 `target` 的 `channel_filter` 获取匹配的渠道列表。
    6.  **执行操作 (如果选择 2):**
        *   **`copy_fields`:**
            *   **匹配逻辑 (初步设想):**
                *   找到所有符合 `source.channel_filter` 的源渠道。
                *   找到所有符合 `target.channel_filter` 的目标渠道。
                *   **对于每个匹配的目标渠道:**
                    *   找到**第一个**匹配 `source.channel_filter` 的源渠道。
                    *   从这个源渠道提取 `fields_to_copy` 中指定的字段值。
                    *   根据 `copy_mode` 计算将要对**当前目标渠道**进行的变更。
                    *   将此变更添加到更新计划中。
            *   **模拟运行:** 显示将对**所有匹配的目标渠道**进行的详细变更汇总。
            *   **用户确认:** (除非使用 `-y`) 询问用户是否确认执行。
            *   **执行 API 调用:** 并发调用目标实例的更新 API 应用所有计划的变更。
            *   **生成撤销数据:** 为目标实例上所有**成功**的更新操作生成统一的撤销文件。
*   **(待办) 增强跨站点 `copy_fields` 详细实现逻辑:**

            1.  **配置文件 (`cross_site_config.yaml`) 调整**:
                *   修改 `source.channel_filter` 和 `target.channel_filter` 结构，使其能够接受与 `update_config.yaml` 中 `filters` 部分完全相同的结构。这意味着可以包含 `name_filters`, `group_filters`, `model_filters`, `exclude_name_filters` 等所有筛选器，以及 `match_mode`。这将取代之前要求精确匹配唯一渠道的限制。
                *   保留 `action: "copy_fields"` 和 `copy_fields_params` (`fields_to_copy`, `copy_mode`) 不变。

            2.  **核心处理逻辑 (`cross_site_handler.py` 中的 `run_cross_site_operation`)**:
                *   **加载配置**: 加载 `cross_site_config.yaml`，以及其中指定的 `source` 和 `target` 的连接配置文件。
                *   **实例化工具**: 为源和目标实例分别创建 `ChannelTool` 对象（例如 `source_tool` 和 `target_tool`）。
                *   **筛选源渠道**: 调用 `source_tool._filter_channels()` 方法（利用其内部完整的筛选逻辑），传入 `source.channel_filter` 配置，获取所有匹配的源渠道列表 (`matched_source_channels`)。
                *   **筛选目标渠道**: 调用 `target_tool._filter_channels()` 方法，传入 `target.channel_filter` 配置，获取所有匹配的目标渠道列表 (`matched_target_channels`)。
                *   **处理源匹配**:
                    *   如果 `matched_source_channels` 为空，记录错误并中止。
                    *   如果 `matched_source_channels` 包含多个渠道，记录一个警告信息，说明将使用列表中的**第一个**渠道作为配置源。选择第一个匹配的源渠道作为 `source_channel_data`。
                    *   如果只匹配到一个源渠道，则直接使用它作为 `source_channel_data`。
                *   **准备更新计划**:
                    *   初始化一个空的更新计划列表 `update_plan`。
                    *   从 `source_channel_data` 中提取 `copy_fields_params.fields_to_copy` 指定的所有字段的值。
                    *   遍历 `matched_target_channels` 列表中的**每一个** `target_channel`。
                    *   对于当前的 `target_channel`，调用 `target_tool._prepare_update_payload()` 方法（或类似逻辑）。此方法需要能够接收源数据（提取的字段值）、`copy_fields_params.copy_mode` 以及目标渠道的当前数据 `target_channel` 作为输入。它会计算出需要发送给目标 API 的具体更新 `payload` 以及描述变更的 `updated_fields` 摘要。
                    *   如果 `_prepare_update_payload` 返回了有效的 `payload`（即计算出需要变更），则将包含目标渠道 ID、`payload` 和 `updated_fields` 摘要的对象添加到 `update_plan` 列表中。
                *   **模拟运行与确认**:
                    *   如果 `update_plan` 为空，则告知用户没有检测到需要进行的变更。
                    *   如果 `update_plan` 不为空，遍历该列表，向用户清晰地展示将要对**哪些目标渠道**（按 ID 或名称）进行**哪些字段**的**具体变更**。
                    *   除非命令行使用了 `-y` 参数，否则询问用户是否确认执行这些更新。
                *   **执行更新**:
                    *   如果用户确认执行：
                        *   在执行任何更新前，调用 `undo_utils` 相关函数，获取 `matched_target_channels` 中所有即将被更新（即在 `update_plan` 中有对应条目）的渠道的**当前状态**，并将这些原始数据保存到目标实例对应的撤销文件中。**必须先保存撤销数据再执行更新**。
                        *   使用 `asyncio.gather` 和 `asyncio.Semaphore`（并发数来自 `script_config.yaml`），并发地调用 `target_tool.update_channel()` 方法，对 `update_plan` 中的每一个条目执行 API 更新请求。
                        *   收集每个更新操作的结果（成功/失败及原因）。
                *   **报告结果**: 汇总并报告成功和失败的更新数量。如果存在失败，列出失败的渠道 ID 和原因。告知用户撤销文件已生成（如果保存成功）。

            3.  **重要考虑**:
                *   **错误处理**: 在筛选、准备、执行的各个阶段都需要健壮的错误处理和清晰的日志记录。
                *   **撤销**: `copy_fields` 操作本质上是在目标实例上执行更新，因此撤销数据**只为目标实例生成**，记录的是目标渠道被修改前的状态。源实例不受影响。
                *   **日志**: 日志应清楚地表明使用了哪个源渠道的数据，以及更新了哪些目标渠道。
        *   **`compare_fields` (需调整):**
            *   **匹配逻辑 (初步设想):**
                *   找到所有符合 `source.channel_filter` 的源渠道。
                *   找到所有符合 `target.channel_filter` 的目标渠道。
                *   **(需要定义比较策略)** 如何比较多个源和多个目标？是比较第一个源和所有目标？还是尝试按名称或其他标识符进行配对比较？最简单的是比较第一个源和第一个目标的指定字段。
            *   生成并显示比较报告。
*   **注意:**
    *   `compare_fields` 操作本身不产生撤销数据。
    *   `copy_fields` 操作因为本质上是在**目标实例**上执行更新，所以**必须为目标实例生成和保存撤销数据**。源实例保持不变。
*   **场景:**
    *   将开发环境中测试通过的渠道配置（模型、分组、费率等，但不包括密钥）迁移到生产环境。
    *   比较不同供应商或不同环境下的渠道设置差异。
*   **未来扩展:**
    *   支持更多 `action` (例如 `sync_fields`，可能需要更复杂的双向比较逻辑)。
    *   **支持更灵活的筛选器:** (当前需求) 允许使用类似单站点更新的完整筛选器匹配多个源/目标渠道。
    *   定义更清晰的多对多匹配和操作逻辑（例如，按名称配对进行复制/比较）。
## 8. 测试渠道模型可用性 (Test Channel Models)

*(已中止)*

*   **原目标:** 解决渠道配置中的 `models` 列表可能包含实际不可用模型的问题，提供验证和清理功能。
*   **中止原因:** 发现标准 One API 测试端点 (`/api/channel/test/...`) 对于需要特定输入（如图像、音频）的模型类型（例如文生图、图生视频、语音合成等）无法有效测试。直接调用该端点会因缺少必要输入而返回错误，无法准确反映模型本身的可用性。要实现对此类模型的可靠测试，需要更复杂的逻辑，可能涉及为不同模型类型构造特定的测试请求负载，这超出了当前工具的范围。
*   **(保留的原始设想，供未来参考):**
    *   *触发方式:* 命令行 `--test-models --channel-id <ID>` 或交互模式选项。
    *   *流程:* 获取渠道模型列表 -> 对每个模型调用标准测试端点 -> 报告结果 -> 可选移除失败模型。
    *   *依赖:* 渠道获取、更新、撤销逻辑。