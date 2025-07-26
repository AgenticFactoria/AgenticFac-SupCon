"""
Agent Configuration Management

This module provides centralized configuration management for the factory control system.
It replaces scattered environment variable usage with a structured configuration approach.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@dataclass
class MQTTConfig:
    """MQTT Broker Configuration"""

    host: str = field(default_factory=lambda: os.getenv("MQTT_HOST", "supos-ce-instance4.supos.app"))
    port: int = field(default_factory=lambda: int(os.getenv("MQTT_PORT", "8083")))
    username: Optional[str] = field(default_factory=lambda: os.getenv("MQTT_USERNAME"))
    password: Optional[str] = field(default_factory=lambda: os.getenv("MQTT_PASSWORD"))
    keepalive: int = 60
    clean_session: bool = True


@dataclass
class LLMConfig:
    """Large Language Model Configuration"""

    provider: str = "moonshot"  # moonshot, openai, azure, etc.
    base_url: str = "https://api.moonshot.cn/v1"
    api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("MOONSHOT_API_KEY")
    )
    model: str = "kimi-k2-0711-preview"
    temperature: float = 0.1
    max_tokens: Optional[int] = None
    timeout: int = 30


@dataclass
class TopicConfig:
    """MQTT Topic Configuration"""

    root: str = field(
        default_factory=lambda: (
            os.getenv("TOPIC_ROOT")
            or os.getenv("USERNAME")
            or os.getenv("USER")
            or "NLDF_DEFAULT"
        )
    )

    # Topic templates
    orders_topic: str = field(init=False)
    kpi_topic: str = field(init=False)
    result_topic: str = field(init=False)
    warehouse_topic: str = field(init=False)

    def __post_init__(self):
        """Initialize derived topic names"""
        self.orders_topic = f"{self.root}/orders/status"
        self.kpi_topic = f"{self.root}/kpi/status"
        self.result_topic = f"{self.root}/result/status"
        self.warehouse_topic = f"{self.root}/warehouse/+/status"

    def get_line_topics(self, line_id: str) -> Dict[str, str]:
        """Get all topics for a specific production line"""
        return {
            "station_status": f"{self.root}/{line_id}/station/+/status",
            "agv_status": f"{self.root}/{line_id}/agv/+/status",
            "conveyor_status": f"{self.root}/{line_id}/conveyor/+/status",
            "alerts": f"{self.root}/{line_id}/alerts",
            "command": f"{self.root}/command/{line_id}",
            "response": f"{self.root}/response/{line_id}",
        }


@dataclass
class FactoryConfig:
    """Factory Layout and Production Configuration"""

    production_lines: List[str] = field(
        default_factory=lambda: ["line1", "line2", "line3"]
    )
    agvs_per_line: int = 2
    supported_products: List[str] = field(default_factory=lambda: ["P1", "P2", "P3"])

    # MVP Configuration - only line1 for initial deployment
    mvp_lines: List[str] = field(default_factory=lambda: ["line1"])
    mvp_products: List[str] = field(default_factory=lambda: ["P1", "P2"])

    # Path points configuration
    path_points: Dict[str, str] = field(
        default_factory=lambda: {
            "P0": "RawMaterial",
            "P1": "StationA",
            "P2": "Conveyor_AB",
            "P3": "StationB",
            "P4": "Conveyor_BC",
            "P5": "StationC",
            "P6": "Conveyor_CQ",
            "P7": "QualityCheck",
            "P8": "QualityCheck",
            "P9": "Warehouse",
        }
    )

    # KPI thresholds
    kpi_thresholds: Dict[str, float] = field(
        default_factory=lambda: {
            "production_efficiency_min": 0.7,
            "first_pass_yield_min": 0.8,
            "agv_utilization_min": 0.6,
            "battery_level_min": 20.0,
            "battery_level_target": 80.0,
        }
    )


@dataclass
class AgentConfig:
    """Individual Agent Configuration"""

    name: str
    role: str  # supervisor, line_commander, quality_inspector, etc.
    enabled: bool = True
    log_level: str = "INFO"

    # Agent-specific settings
    decision_timeout: int = 30  # seconds
    retry_attempts: int = 3
    batch_size: int = 1  # for batch processing

    # Line-specific configuration (for line commanders)
    line_id: Optional[str] = None


@dataclass
class SystemConfig:
    """Overall System Configuration"""

    # Component configurations
    mqtt: MQTTConfig = field(default_factory=MQTTConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    topics: TopicConfig = field(default_factory=TopicConfig)
    factory: FactoryConfig = field(default_factory=FactoryConfig)

    # System settings
    debug_mode: bool = field(
        default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true"
    )
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    max_concurrent_agents: int = 10

    # Agent configurations
    agents: Dict[str, AgentConfig] = field(default_factory=dict)

    def __post_init__(self):
        """Initialize default agent configurations"""
        if not self.agents:
            self._setup_default_agents()

    def _setup_default_agents(self):
        """Setup default agent configurations"""
        # Supervisor Agent
        self.agents["supervisor"] = AgentConfig(
            name="SupervisorAgent",
            role="supervisor",
            enabled=True,
            log_level=self.log_level,
        )

        # Line Commander Agents (MVP: only line1)
        for line_id in self.factory.mvp_lines:
            self.agents[f"line_commander_{line_id}"] = AgentConfig(
                name=f"LineCommander_{line_id}",
                role="line_commander",
                enabled=True,
                log_level=self.log_level,
                line_id=line_id,
            )

    def get_enabled_agents(self) -> Dict[str, AgentConfig]:
        """Get only enabled agents"""
        return {k: v for k, v in self.agents.items() if v.enabled}

    def get_line_commanders(self) -> Dict[str, AgentConfig]:
        """Get line commander agents"""
        return {
            k: v
            for k, v in self.agents.items()
            if v.role == "line_commander" and v.enabled
        }

    def validate_config(self) -> List[str]:
        """Validate configuration and return list of issues"""
        issues = []

        # Check required API keys
        if not self.llm.api_key:
            issues.append("LLM API key is not configured")

        # Check MQTT configuration
        if not self.mqtt.host:
            issues.append("MQTT host is not configured")

        # Check topic root
        if not self.topics.root:
            issues.append("Topic root is not configured")

        # Check factory configuration
        if not self.factory.mvp_lines:
            issues.append("No production lines configured for MVP")

        return issues


class ConfigManager:
    """Configuration Manager for the Factory Control System"""

    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file
        self._config = None

    @property
    def config(self) -> SystemConfig:
        """Get system configuration (lazy loading)"""
        if self._config is None:
            self._config = self._load_config()
        return self._config

    def _load_config(self) -> SystemConfig:
        """Load configuration from file or environment"""
        if self.config_file and Path(self.config_file).exists():
            # TODO: Implement loading from JSON/YAML file
            pass

        # Load from environment and defaults
        return SystemConfig()

    def save_config(self, filepath: str):
        """Save current configuration to file"""
        # TODO: Implement saving to JSON/YAML file
        pass

    def update_config(self, **kwargs):
        """Update configuration parameters"""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)

    def print_config_summary(self):
        """Print configuration summary"""
        config = self.config

        print("🔧 Factory Control System Configuration")
        print("=" * 50)
        print(f"📡 MQTT Broker: {config.mqtt.host}:{config.mqtt.port}")
        print(f"🤖 LLM Provider: {config.llm.provider} ({config.llm.model})")
        print(f"📢 Topic Root: {config.topics.root}")
        print(f"🏭 Production Lines: {config.factory.mvp_lines}")
        print(f"📦 Supported Products: {config.factory.mvp_products}")
        print(f"🔍 Debug Mode: {config.debug_mode}")
        print(f"📊 Log Level: {config.log_level}")
        print(f"🤖 Enabled Agents: {len(config.get_enabled_agents())}")

        # Validation
        issues = config.validate_config()
        if issues:
            print("\n⚠️ Configuration Issues:")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print("\n✅ Configuration is valid")


# Global configuration instance
_config_manager = ConfigManager()


def get_config() -> SystemConfig:
    """Get the global system configuration"""
    return _config_manager.config


def get_mqtt_config() -> MQTTConfig:
    """Get MQTT configuration"""
    return get_config().mqtt


def get_llm_config() -> LLMConfig:
    """Get LLM configuration"""
    return get_config().llm


def get_topic_config() -> TopicConfig:
    """Get topic configuration"""
    return get_config().topics


def get_factory_config() -> FactoryConfig:
    """Get factory configuration"""
    return get_config().factory


def print_config():
    """Print configuration summary"""
    _config_manager.print_config_summary()


# Configuration validation
def validate_environment():
    """Validate that required environment is properly configured"""
    config = get_config()
    issues = config.validate_config()

    if issues:
        print("❌ Configuration validation failed:")
        for issue in issues:
            print(f"  - {issue}")
        return False

    print("✅ Configuration validation passed")
    return True


if __name__ == "__main__":
    # Test configuration
    print_config()
    validate_environment()
