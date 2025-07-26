import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

from openai import AsyncOpenAI
import json
from typing import Dict, Any
from dotenv import load_dotenv

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from config.schemas import AgentCommand
from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT
from src.agent.prompts import AgentPrompts
from src.utils.mqtt_client import MQTTClient
from src.utils.topic_manager import TopicManager

# Configure logger
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class SimpleAgent:
    def __init__(self, root_topic):
        self.topic_manager = TopicManager(root_topic)
        self.client_id = f"{root_topic}_simple_agent"
        self.mqtt_client = MQTTClient(
            MQTT_BROKER_HOST, MQTT_BROKER_PORT, self.client_id
        )
        self.client = AsyncOpenAI(
            base_url="https://api.moonshot.cn/v1", api_key=os.getenv("MOONSHOT_API_KEY")
        )

    def on_message(self, topic: str, payload: bytes):
        try:
            message = json.loads(payload.decode())
            logging.info(f"Received message on topic {topic}: {message}")

            # Schedule the async handler to run in the event loop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If loop is already running, schedule as a task
                    asyncio.create_task(self.handle_message(topic, message))
                else:
                    # If no loop is running, run it
                    asyncio.run(self.handle_message(topic, message))
            except RuntimeError:
                # If we can't get the event loop, create a new one
                try:
                    asyncio.run(self.handle_message(topic, message))
                except RuntimeError as e:
                    logging.error(f"Failed to run async handler: {e}")
                    # Fallback: handle synchronously without agent processing
                    logging.warning("Falling back to synchronous processing")

        except json.JSONDecodeError:
            logging.error(f"Could not decode JSON from topic {topic}")
        except Exception as e:
            logging.error(f"An error occurred in on_message: {e}")

    async def handle_message(self, topic: str, message: dict):
        # For this MVP, we'll just handle order messages
        if "orders" not in topic:
            return

        line_id = "line1"  # Defaulting to line1 for MVP
        user_prompt = self.create_prompt(message)

        try:
            logging.info("Running OpenAI API with new message...")
            completion = await self.client.chat.completions.create(
                model="kimi-k2-0711-preview",
                messages=[
                    {"role": "system", "content": AgentPrompts.SIMPLE_AGENT},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                max_tokens=1000,
                temperature=0.1
            )

            response_content = completion.choices[0].message.content
            if not response_content:
                logging.error("OpenAI returned no content.")
                return

            logging.info(f"Agent raw response: {response_content}")

            try:
                command_dict = json.loads(response_content)
                
                # Ensure required fields are present
                required_fields = ["action", "target"]
                if not all(field in command_dict for field in required_fields):
                    logging.error(f"Missing required fields: {[f for f in required_fields if f not in command_dict]}")
                    return

                logging.info(f"Extracted command: {command_dict}")
                command_topic = self.topic_manager.get_agent_command_topic(line_id)
                self.mqtt_client.publish(command_topic, json.dumps(command_dict))
                logging.info(f"Published command to {command_topic}")
                
            except json.JSONDecodeError as e:
                logging.error(f"Failed to parse JSON response: {e}")

        except Exception as e:
            logging.error(f"Failed to process message with OpenAI: {e}")
        finally:
            # Ensure any async resources are properly cleaned up
            try:
                # Give a moment for any pending async operations to complete
                await asyncio.sleep(0.1)
            except Exception:
                pass

    def create_prompt(self, message: dict) -> str:
        """Creates a user prompt for the LLM based on the incoming message."""
        return f"""
        The following message was received:
        {json.dumps(message, indent=2)}
        
        Analyze the message and the current factory state (if available) and decide the next best action.
        Respond with a single, valid JSON command. Do not include any other text or explanation.
        """

    def run(self):
        self.mqtt_client.connect()

        root_topic = self.topic_manager.root
        # Subscribe to all relevant topics
        for line in ["line1", "line2", "line3"]:
            self.mqtt_client.subscribe(
                f"{root_topic}/{line}/station/+/status", self.on_message
            )
            self.mqtt_client.subscribe(
                f"{root_topic}/{line}/agv/+/status", self.on_message
            )
            self.mqtt_client.subscribe(
                f"{root_topic}/{line}/conveyor/+/status", self.on_message
            )
            self.mqtt_client.subscribe(f"{root_topic}/{line}/alerts", self.on_message)
            self.mqtt_client.subscribe(
                self.topic_manager.get_agent_response_topic(line), self.on_message
            )

        self.mqtt_client.subscribe(f"{root_topic}/warehouse/+/status", self.on_message)
        self.mqtt_client.subscribe(
            self.topic_manager.get_order_topic(), self.on_message
        )
        self.mqtt_client.subscribe(self.topic_manager.get_kpi_topic(), self.on_message)
        self.mqtt_client.subscribe(
            self.topic_manager.get_result_topic(), self.on_message
        )

        logging.info(
            f"Agent is running and subscribed to all topics under {root_topic}"
        )

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("Agent shutting down.")
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Properly shutdown the agent and clean up resources."""
        logging.info("Cleaning up agent resources...")
        
        # Disconnect MQTT first
        if self.mqtt_client:
            self.mqtt_client.disconnect()
        
        # Clean up async resources properly
        from src.utils.async_cleanup import cleanup_async_resources
        cleanup_async_resources(timeout=2.0)
        
        logging.info("Agent shutdown complete.")


def main():
    load_dotenv()

    root_topic = (
        os.getenv("TOPIC_ROOT")
        or os.getenv("USERNAME")
        or os.getenv("USER")
        or "NLDF_AGENT_TEST"
    )

    agent = SimpleAgent(root_topic)
    agent.run()


if __name__ == "__main__":
    main()
