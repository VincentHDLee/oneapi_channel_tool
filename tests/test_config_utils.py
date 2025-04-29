# -*- coding: utf-8 -*-
"""
单元测试 for channel_manager_lib.config_utils
"""

import pytest
import yaml
from pathlib import Path
from channel_manager_lib.config_utils import load_yaml_config # 假设函数路径正确

# TODO: 添加更多测试用例

def test_load_yaml_config_success(tmp_path: Path):
    """
    测试 load_yaml_config 函数能否成功加载有效的 YAML 文件。
    """
    # 创建一个临时的 YAML 文件
    valid_yaml_content = {
        "key1": "value1",
        "key2": [1, 2, 3],
        "nested": {
            "subkey": True
        }
    }
    yaml_file = tmp_path / "valid_config.yaml"
    with open(yaml_file, 'w', encoding='utf-8') as f:
        yaml.dump(valid_yaml_content, f)

    # 调用被测试函数
    loaded_config = load_yaml_config(str(yaml_file))

    # 断言结果是否符合预期
    assert loaded_config == valid_yaml_content

# 可以在这里添加更多测试，例如测试文件不存在、文件格式错误等情况
def test_load_yaml_config_file_not_found(tmp_path: Path):
    """
    测试当 YAML 文件不存在时，load_yaml_config 是否抛出 FileNotFoundError。
    """
    non_existent_file = tmp_path / "non_existent.yaml"

    # 使用 pytest.raises 来检查是否抛出了预期的异常
    with pytest.raises(FileNotFoundError):
        load_yaml_config(str(non_existent_file))

def test_load_yaml_config_invalid_yaml(tmp_path: Path):
    """
    测试当 YAML 文件内容无效时，load_yaml_config 是否抛出 yaml.YAMLError。
    """
    # 创建一个包含无效 YAML 内容的文件 (例如，未闭合的括号)
    invalid_yaml_content = "key: {value: [1, 2"
    yaml_file = tmp_path / "invalid_config.yaml"
    yaml_file.write_text(invalid_yaml_content, encoding='utf-8')

    # 检查是否抛出了 yaml.YAMLError
    with pytest.raises(yaml.YAMLError):
        load_yaml_config(str(yaml_file))