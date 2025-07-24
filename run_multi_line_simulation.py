# run_multi_line_simulation.py
import os
import sys
import argparse
import threading

from dotenv import load_dotenv

from src.utils.mqtt_client import MQTTClient
from src.simulation.factory_multi import Factory
from src.utils.config_loader import load_factory_config
from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT
import logging
from config.settings import LOG_LEVEL
from src.agent_interface.multi_line_command_handler import MultiLineCommandHandler
from src.user_input_multi import menu_input_thread
from typing import Optional
import time

# Add the project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
load_dotenv()


class MultiLineFactorySimulation:
    """
    Main orchestrator class that combines all components of the factory simulation.
    """

    def __init__(self):
        self.factory: Optional[Factory] = None
        self.mqtt_client: Optional[MQTTClient] = None
        self.command_handler: Optional[MultiLineCommandHandler] = None
        self.running = False

    def initialize(self, no_faults=False, no_mqtt=False):
        """Initialize all simulation components."""
        logger.info("🏭 Initializing Multi-Line Factory Simulation...")
        # 优先使用 CLIENT_ID，其次 USERNAME/USER，最后默认值，确保 client_name 一定为 str
        client_name = (
            os.getenv("TOPIC_ROOT")
            or os.getenv("USERNAME")
            or os.getenv("USER")
            or "NLDF_TEST"
        )
        self.mqtt_client = MQTTClient(MQTT_BROKER_HOST, MQTT_BROKER_PORT, client_name)

        # Connect to MQTT
        logger.info(
            f"📡 Connecting to MQTT broker at {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}, client_name: {client_name}"
        )

        if not no_mqtt:
            self.mqtt_client.connect()
            # Wait for MQTT client to be fully connected
            max_retries = 20
            retry_interval = 0.5
            for i in range(max_retries):
                if self.mqtt_client.is_connected():
                    logger.info("✅ MQTT client is fully connected.")
                    break
                logger.info(f"Waiting for MQTT connection... ({i + 1}/{max_retries})")
                time.sleep(retry_interval)
            else:
                logger.error(
                    "❌ Failed to connect to MQTT broker within the given time. Exiting simulation."
                )
                raise ConnectionError("MQTT connection failed.")

        try:
            layout_config = load_factory_config("factory_layout_multi.yml")
            print(
                "✅ Successfully loaded multi-line factory configuration from layout_config"
            )
        except Exception as e:
            print(f"❌ Failed to load multi-line factory configuration: {e}")
            raise e

        self.factory = Factory(
            layout_config, self.mqtt_client, no_faults=no_faults
        )  # no_faults for cleaner testing
        logger.info(f"✅ Factory created with {len(self.factory.lines)} lines")

        # Create command handler (this will start listening for commands)
        self.command_handler = MultiLineCommandHandler(
            self.factory, self.mqtt_client, self.factory.topic_manager
        )
        logger.info("🎯 Command handler initialized and listening for agent commands")

    def run(self, duration: Optional[int] = None):
        """Run the simulation."""
        if self.factory is None:
            logger.error("❌ Factory is not initialized. Call initialize() first.")
            return

        logger.info("🚀 Starting Factory Simulation...")
        self.running = True

        try:
            if duration:
                logger.info(f"⏱️  Running simulation for {duration} seconds")
                self.factory.run(until=duration)
                # For fixed duration, print scores after normal completion
                # self.factory.print_final_scores()
            else:
                logger.info("🔄 Running simulation indefinitely (Ctrl+C to stop)")
                while self.running:
                    # Run simulation for 1 second at a time
                    self.factory.run(until=int(self.factory.env.now) + 1)
                    time.sleep(1)  # Small delay to prevent busy waiting

        except KeyboardInterrupt:
            logger.info("🛑 Simulation interrupted by user")
            # Scores will be printed in shutdown()
        except Exception as e:
            logger.error(f"❌ Simulation error: {e}")
        finally:
            # For indefinite runs or errors, print scores during shutdown
            if not duration:
                self.shutdown()
            else:
                # For fixed duration runs, just clean up without printing scores again
                logger.info("🧹 Cleaning up resources...")
                self.running = False
                if self.mqtt_client:
                    self.mqtt_client.disconnect()
                logger.info("👋 Factory Simulation stopped")

    def shutdown(self):
        """Clean up resources."""
        logger.info("🧹 Shutting down Factory Simulation...")
        self.running = False

        # # Print final scores when shutting down
        # if self.factory:
        #     self.factory.print_final_scores()

        if self.mqtt_client:
            self.mqtt_client.disconnect()

        logger.info("👋 Factory Simulation stopped")


def run_simulation_multi():
    """Runs the multi-line factory simulation."""
    parser = argparse.ArgumentParser(
        description="SUPCON Multi-Line Factory Simulation Launcher"
    )
    parser.add_argument(
        "--menu",
        action="store_true",
        help="Enable the interactive menu for manual control.",
    )
    parser.add_argument(
        "--no-mqtt", action="store_true", help="Ignore mqtt connection for offline test"
    )
    parser.add_argument(
        "--no-fault",
        action="store_true",
        help="Disable random fault injection in the simulation.",
    )
    args = parser.parse_args()

    simulation = MultiLineFactorySimulation()
    simulation.initialize(no_faults=args.no_fault, no_mqtt=args.no_mqtt)

    if args.menu and simulation.factory and simulation.factory.topic_manager:
        threading.Thread(
            target=menu_input_thread,
            args=(
                simulation.mqtt_client,
                simulation.factory,
                simulation.factory.topic_manager,
            ),
            daemon=True,
        ).start()
        logger.info("Interactive menu enabled. Type commands in the console.")

    simulation.run()  # Run indefinitely


if __name__ == "__main__":
    run_simulation_multi()
