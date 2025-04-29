# 开发文档 - One API 渠道批量更新工具

本文档作为开发过程的入口点，概述项目目标、规范和主要开发任务。详细的功能实现、决策和计划记录在 `docs/development/` 子目录下的各个专题文档中。

## 项目目标

提供一个命令行工具，用于批量更新 One API 实例中的渠道配置。支持通过 YAML 文件定义筛选条件和更新规则，并能处理不同版本的 One API (`newapi`, `voapi`)。增加撤销（Undo）功能以提高操作安全性。

## 开发规范

*   **代码行数限制:** 为了保持代码可维护性，规定项目中的单个 Python 文件 (`.py`) 的代码行数原则上不应超过 1000 行。

## 背景与重构

*   **项目背景、早期状态及遇到的障碍:** 详情请参见 [./development/introduction.md](./development/introduction.md)。
*   **`main_tool.py` 重构 (已完成):** 为了解决文件过长和工具执行困难的问题，进行了代码重构。详情请参见 [./development/refactoring.md](./development/refactoring.md)。

## 后续步骤与开发计划

以下是主要的开发任务模块和未来的工作方向。详细内容请参考对应的子文档。

**任务优先级与依赖说明:**

*   **难度:** D0 (高), D1 (中), D2 (低)
*   **重要性:** I0 (关键), I1 (高), I2 (中), I3 (低)

(任务的详细优先级、依赖关系和状态请在各子文档中查看)

1.  **核心功能扩展 (Core Feature Expansion):**
    *   包括配置文件改进 (已完成)、字段支持扩展 (已完成)、字段级操作 (已完成)、自动测试启用 (已完成)、跨站点操作 (进行中)、复制修改 (待办)、渠道级增删 (可选)。
    *   **详情:** [./development/core_features.md](./development/core_features.md)

2.  **健壮性与可维护性 (Robustness & Maintainability):**
    *   包括 API 差异说明、可配置分页 (已添加)、配置验证 (待办)、错误处理 (待办)、自动化测试 (待办)、筛选增强 (待办)、撤销改进 (待办)、交互菜单 (已完成)、安全审计 (待办)、插件化 (可选)、缓存 (可选)。
    *   **详情:** [./development/robustness.md](./development/robustness.md)

3.  **测试与验证 (Testing & Validation):**
    *   包括全面功能测试 (进行中) 和 VO API 适配确认 (待办)。
    *   **详情:** [./development/testing_validation.md](./development/testing_validation.md)

4.  **文档维护 (Documentation Maintenance):**
    *   持续更新用户文档 (`README.md`) 和开发文档。
    *   **详情:** [./development/documentation.md](./development/documentation.md)