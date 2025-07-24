"""
Configuration loader for SUPCON Factory Simulation
Loads configuration from YAML files and provides typed access to configuration data.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional


class ConfigLoader:
    """simplified config loader - load yaml file to dict"""

    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)

    def load_factory_layout(
        self, config_file_name: str = "factory_layout.yml"
    ) -> Dict[str, Any]:
        """load factory layout from yaml file"""
        config_file = self.config_dir / config_file_name

        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")

        with open(config_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        # # simple validation for required fields
        # required_sections = ['stations', 'agvs', 'conveyors', 'warehouses']
        # for section in required_sections:
        #     if section not in config:
        #         raise ValueError(f"Missing required section: {section}")

        return config


# global config loader instance
_config_loader: Optional[ConfigLoader] = None


def get_config_loader() -> ConfigLoader:
    """get global config loader instance"""
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader()
    return _config_loader


def load_factory_config(config_file_name: str = "factory_layout.yml") -> Dict[str, Any]:
    """convenient function - load factory config"""
    return get_config_loader().load_factory_layout(config_file_name)
