# 重构 `main_tool.py` (已完成)

为了解决 `main_tool.py` 文件过长（超过 1400 行）和相关工具执行困难的问题，进行了代码重构。

## 目标

将 `main_tool.py` 的功能拆分到多个独立的、职责更单一的模块中，以提高代码的可维护性、可读性，并解决工具执行困难的问题。

## 重要性

(I0 - 关键) 这是继续开发其他功能（包括修复跨站点查询）和保证项目健康度的前提。

## 重构结果

*   创建了 `channel_manager_lib` 包来存放核心逻辑模块。
*   **`channel_manager_lib/cli_handler.py`:** 负责处理命令行参数解析 (`argparse`) 和主要的交互式菜单逻辑（模式选择、配置选择等）。
*   **`channel_manager_lib/single_site_handler.py`:** 封装单站点更新和撤销的操作流程，包括加载 `update_config.yaml`、调用 `ChannelTool` 实例执行模拟、确认、更新、保存撤销等。
*   **`channel_manager_lib/cross_site_handler.py`:** 封装跨站点操作的流程，包括加载 `cross_site_config.yaml`、处理查询、复制字段 (`copy_fields`)、比较字段 (`compare_fields`) 等逻辑。
*   **`channel_manager_lib/config_utils.py`:** 提供加载和验证各种 YAML 配置文件（连接配置、更新配置、跨站配置）的辅助函数，以及路径常量。
*   **`channel_manager_lib/log_utils.py`:** 负责日志设置。
*   **`channel_manager_lib/undo_utils.py`:** 封装撤销相关逻辑。
*   **`main_tool.py` (重构后):** 作为程序的简洁入口点，初始化日志，调用 `channel_manager_lib.cli_handler` 获取用户意图和配置，然后根据模式委托给相应的处理器执行具体任务。
*   **`run_tool.sh`:** 新增的推荐启动脚本。