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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from queue import Queue
from typing import Any, Dict, List, Optional

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

    orders: Optional[List[Dict]] = None
    kpi_metrics: Optional[Dict] = None
    line_states: Optional[Dict[str, Dict]] = None  # line_id -> line_state
    warehouse_status: Optional[Dict] = None

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

        # Event loop management
        self.loop = None
        self.message_queue = Queue()
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.running = False

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
        self.running = True

        # Get or create event loop
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

        # Start message processing task
        self.loop.create_task(self._message_processor())

        # Connect MQTT and setup subscriptions
        self.mqtt_client.connect()
        self._setup_mqtt_subscriptions()

        # Start all agents
        if self.supervisor_agent:
            self.supervisor_agent.start()
        for line_commander in self.line_commanders.values():
            line_commander.start()

        self.logger.info("Multi-agent factory system started successfully")

    async def _message_processor(self):
        """Process queued messages asynchronously"""
        while self.running:
            try:
                # Check for new messages every 100ms
                await asyncio.sleep(0.1)

                # Process all queued messages
                while not self.message_queue.empty():
                    topic, message = self.message_queue.get()
                    await self._process_message_async(topic, message)

            except Exception as e:
                self.logger.error(f"Error in message processor: {e}")

    async def _process_message_async(self, topic: str, message: Dict):
        """Process a single message asynchronously"""
        try:
            self.logger.info(f"Processing async message on {topic}: {message}")

            # Update factory state
            self._update_factory_state(topic, message)

            # Route to supervisor agent
            if self.supervisor_agent:
                await self.supervisor_agent.handle_message(topic, message)

        except Exception as e:
            self.logger.error(f"Error processing async message: {e}")

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
        """Handle global messages and route to appropriate agents (thread-safe)"""
        try:
            message = json.loads(payload.decode())
            self.logger.info(f"Received global message on {topic}: {message}")

            # Queue message for async processing
            self.message_queue.put((topic, message))

        except Exception as e:
            self.logger.error(f"Error handling global message: {e}")

    def _update_factory_state(self, topic: str, message: Dict):
        """Update the global factory state"""
        if "orders" in topic and self.factory_state.orders is not None:
            self.factory_state.orders.append(message)
        elif "kpi" in topic and self.factory_state.kpi_metrics is not None:
            self.factory_state.kpi_metrics.update(message)
        elif "warehouse" in topic and self.factory_state.warehouse_status is not None:
            self.factory_state.warehouse_status.update(message)

    def shutdown(self):
        """Shutdown the multi-agent system"""
        self.logger.info("Shutting down multi-agent system...")
        self.running = False

        # Stop all agents
        if self.supervisor_agent:
            self.supervisor_agent.stop()

        for line_commander in self.line_commanders.values():
            line_commander.stop()

        # Disconnect MQTT first
        self.mqtt_client.disconnect()

        # Shutdown executor
        self.executor.shutdown(wait=False)

        # Clean up async resources properly
        from src.utils.async_cleanup import cleanup_async_resources
        cleanup_async_resources(timeout=2.0)

        self.logger.info("Multi-agent system shutdown complete")


async def async_main():
    """Async main entry point for the multi-agent system"""
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

        # Run until interrupted
        while controller.running:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("\n🛑 Received shutdown signal")
    finally:
        controller.shutdown()


def main():
    """Main entry point for the multi-agent system"""
    try:
        # Run the async main function
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\n🛑 Multi-Agent Factory System stopped by user")
    except Exception as e:
        print(f"\n❌ Failed to start Multi-Agent Factory System: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
