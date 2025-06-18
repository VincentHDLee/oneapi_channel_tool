# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Added `--query` command-line argument for non-interactive channel data querying.

### Fixed
- Fixed a bug in `filtering_utils.py` where `id_filters` was not being correctly applied during channel filtering.
- Fixed a critical bug in `channel_tool_base.py` where the `overwrite` mode did not correctly format list and dictionary values for the target API, which caused update failures on `voapi` instances.

## [0.2.0] - 2025-06-19

### Added
- Implemented cross-site channel operations, allowing fields to be copied from a source channel to multiple target channels across different API instances.
- Added a `--cross-site` command-line argument to directly trigger cross-site operations.
- Introduced a configurable `request_interval_ms` to add delays between concurrent API requests, enhancing stability when updating a large number of channels.

### Fixed
- Resolved a `TypeError` in `undo_utils.py` that occurred when saving undo data for cross-site actions by refactoring the `save_undo_data` function.
- Adapted the tool to handle breaking changes in the `newapi` type API.
- Correctly parses the new paginated structure for the channel list response (`{"items": [...]}`).
- Implemented deduplication logic to prevent processing the same channel multiple times due to API pagination issues.
- Ensured `models` (list) and `model_mapping` (dict) fields are correctly serialized to strings before sending update requests, resolving API errors.