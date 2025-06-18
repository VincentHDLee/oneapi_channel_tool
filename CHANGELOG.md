# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Adapted the tool to handle breaking changes in the `newapi` type API.
- Correctly parses the new paginated structure for the channel list response (`{"items": [...]}`).
- Implemented deduplication logic to prevent processing the same channel multiple times due to API pagination issues.
- Ensured `models` (list) and `model_mapping` (dict) fields are correctly serialized to strings before sending update requests, resolving API errors.