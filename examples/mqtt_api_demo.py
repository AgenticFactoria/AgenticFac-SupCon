import os
import sys
import json
import time
from pathlib import Path
from dotenv import load_dotenv

# Ensure project root is on sys.path before importing project modules
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.mqtt_client import MQTTClient  # noqa: E402
from src.utils.topic_manager import TopicManager  # noqa: E402
from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT  # noqa: E402


def log_message(topic: str, payload: bytes) -> None:
    """Simple callback to print incoming MQTT messages."""
    print(f"[{topic}] {payload.decode()}")


def main() -> None:
    """Demonstrate subscribing and publishing to the simulator MQTT topics."""
    load_dotenv()
    # Determine root topic/client id
    root_topic = (
        os.getenv("TOPIC_ROOT")
        or os.getenv("USERNAME")
        or os.getenv("USER")
        or "NLDF_DEMO"
    )
    topic_manager = TopicManager(root_topic)

    # Use a distinct client id for this demo
    client_id = f"{root_topic}_demo"
    mqtt_client = MQTTClient(MQTT_BROKER_HOST, MQTT_BROKER_PORT, client_id)
    mqtt_client.connect()

    # Subscribe to various status topics using wildcards
    for line in ["line1", "line2", "line3"]:
        mqtt_client.subscribe(f"{root_topic}/{line}/station/+/status", log_message)
        mqtt_client.subscribe(f"{root_topic}/{line}/agv/+/status", log_message)
        mqtt_client.subscribe(f"{root_topic}/{line}/conveyor/+/status", log_message)
        mqtt_client.subscribe(f"{root_topic}/{line}/alerts", log_message)
        mqtt_client.subscribe(topic_manager.get_agent_response_topic(line), log_message)

    mqtt_client.subscribe(f"{root_topic}/warehouse/+/status", log_message)
    mqtt_client.subscribe(topic_manager.get_order_topic(), log_message)
    mqtt_client.subscribe(topic_manager.get_kpi_topic(), log_message)
    mqtt_client.subscribe(topic_manager.get_result_topic(), log_message)

    # Publish a sample command to line1's command topic
    command_topic = topic_manager.get_agent_command_topic("line1")
    sample_command = {
        "command_id": "demo_move",
        "action": "move",
        "target": "AGV_1",
        "params": {"target_point": "P1"},
    }
    mqtt_client.publish(command_topic, json.dumps(sample_command))
    print(f"Published sample command to {command_topic}")

    try:
        print("Listening for messages. Press Ctrl+C to exit.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Exiting demo...")
    finally:
        mqtt_client.disconnect()


if __name__ == "__main__":
    main()
