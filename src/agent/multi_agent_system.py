"""
Multi-Agent Factory Control System using openai-agents

This module implements a hierarchical multi-agent system for factory control:
- Supervisor Agent: Manages global order allocation and KPI monitoring
- Line Commander Agents: Control individual production lines
"""

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from config.agent_config import get_mqtt_config
from src.utils.mqtt_client import MQTTClient
from src.utils.topic_manager import TopicManager

from .line_commander_agent import LineCommanderAgent

# Import agent implementations
from .supervisor_agent import SupervisorAgent


class AgentRole(Enum):
    SUPERVISOR = "supervisor"
    LINE_COMMANDER = "line_commander"


@dataclass
class FactoryState:
    """Maintains the current state of the factory"""

    orders: List[Dict] = None
    kpi_metrics: Dict = None
    line_states: Dict[str, Dict] = None  # line_id -> line_state
    warehouse_status: Dict = None

    def __post_init__(self):
        if self.orders is None:
            self.orders = []
        if self.line_states is None:
            self.line_states = {}
        if self.kpi_metrics is None:
            self.kpi_metrics = {}
        if self.warehouse_status is None:
            self.warehouse_status = {}


class MultiAgentFactoryController:
    """
    Main controller for the multi-agent factory system
    """

    def __init__(self, root_topic: str):
        self.root_topic = root_topic
        self.topic_manager = TopicManager(root_topic)
        self.client_id = f"{root_topic}_multi_agent_controller"
        mqtt_config = get_mqtt_config()
        self.mqtt_client = MQTTClient(
            mqtt_config.host, mqtt_config.port, self.client_id
        )

        # Global factory state
        self.factory_state = FactoryState()

        # Agent instances
        self.supervisor_agent = None
        self.line_commanders: Dict[str, Any] = {}  # line_id -> agent

        # Configure logging
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
        )
        self.logger = logging.getLogger(__name__)

    def initialize_agents(self):
        """Initialize all agents in the system"""
        self.logger.info("Initializing multi-agent system...")

        # Initialize Supervisor Agent
        self.supervisor_agent = SupervisorAgent(
            llm=None,  # Will use the agent's internal LLM configuration
            factory_state=self.factory_state,
            topic_manager=self.topic_manager,
            mqtt_client=self.mqtt_client,
        )

        # Initialize Line Commander Agents
        # For MVP, we'll start with line1 only
        for line_id in ["line1"]:  # TODO: Extend to ["line1", "line2", "line3"]
            self.line_commanders[line_id] = LineCommanderAgent(
                line_id=line_id,
                llm=None,  # Will use the agent's internal LLM configuration
                factory_state=self.factory_state,
                topic_manager=self.topic_manager,
                mqtt_client=self.mqtt_client,
            )

        self.logger.info(
            f"Initialized {len(self.line_commanders)} line commander agents"
        )

    def start_system(self):
        """Start the multi-agent system"""
        self.mqtt_client.connect()
        self._setup_mqtt_subscriptions()

        # Start all agents
        self.supervisor_agent.start()
        for line_commander in self.line_commanders.values():
            line_commander.start()

        self.logger.info("Multi-agent factory system started successfully")

    def _setup_mqtt_subscriptions(self):
        """Setup MQTT subscriptions for global coordination"""
        root_topic = self.topic_manager.root

        # Global subscriptions handled by supervisor
        self.mqtt_client.subscribe(
            f"{root_topic}/orders/status", self._on_global_message
        )
        self.mqtt_client.subscribe(f"{root_topic}/kpi/status", self._on_global_message)
        self.mqtt_client.subscribe(
            f"{root_topic}/result/status", self._on_global_message
        )
        self.mqtt_client.subscribe(
            f"{root_topic}/warehouse/+/status", self._on_global_message
        )

    def _on_global_message(self, topic: str, payload: bytes):
        """Handle global messages and route to appropriate agents"""
        try:
            message = json.loads(payload.decode())
            self.logger.info(f"Received global message on {topic}: {message}")

            # Update factory state
            self._update_factory_state(topic, message)

            # Route to supervisor agent
            if self.supervisor_agent:
                asyncio.create_task(
                    self.supervisor_agent.handle_message(topic, message)
                )

        except Exception as e:
            self.logger.error(f"Error handling global message: {e}")

    def _update_factory_state(self, topic: str, message: Dict):
        """Update the global factory state"""
        if "orders" in topic:
            self.factory_state.orders.append(message)
        elif "kpi" in topic:
            self.factory_state.kpi_metrics.update(message)
        elif "warehouse" in topic:
            self.factory_state.warehouse_status.update(message)

    def shutdown(self):
        """Shutdown the multi-agent system"""
        self.logger.info("Shutting down multi-agent system...")

        # Stop all agents
        if self.supervisor_agent:
            self.supervisor_agent.stop()

        for line_commander in self.line_commanders.values():
            line_commander.stop()

        self.mqtt_client.disconnect()
        self.logger.info("Multi-agent system shutdown complete")


def main():
    """Main entry point for the multi-agent system"""
    # Setup agent environment
    from agents import (
        set_default_openai_api,
        set_default_openai_client,
        set_tracing_disabled,
    )
    from dotenv import load_dotenv
    from openai import AsyncOpenAI

    load_dotenv()

    # Configure openai-agents
    set_tracing_disabled(True)
    custom_client = AsyncOpenAI(
        base_url="https://api.moonshot.cn/v1", api_key=os.getenv("MOONSHOT_API_KEY")
    )
    set_default_openai_client(custom_client)
    set_default_openai_api("chat_completions")

    # Get root topic
    root_topic = (
        os.getenv("TOPIC_ROOT")
        or os.getenv("USERNAME")
        or os.getenv("USER")
        or "NLDF_MULTI_AGENT"
    )

    # Initialize and start the multi-agent system
    controller = MultiAgentFactoryController(root_topic)
    controller.initialize_agents()

    try:
        controller.start_system()

        # Keep the system running
        print("🏭 Multi-Agent Factory System Started")
        print(f"📡 Root Topic: {root_topic}")
        print(
            f"🤖 Agents: 1 Supervisor + {len(controller.line_commanders)} Line Commanders"
        )
        print("🚀 System is running... Press Ctrl+C to stop")

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n🛑 Received shutdown signal")
    finally:
        controller.shutdown()


if __name__ == "__main__":
    main()
