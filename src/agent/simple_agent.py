import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

# Assuming 'agents' is a new library provided by the user.
# If this causes an error, the user needs to install it.
from agents import Agent, AgentOutputSchema, Runner
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
        self.agent = Agent(
            name="FactoryControlAgent",
            instructions=AgentPrompts.SIMPLE_AGENT,
            model="kimi-k2-0711-preview",
            output_type=AgentOutputSchema(AgentCommand, strict_json_schema=False),
        )

    def on_message(self, topic: str, payload: bytes):
        try:
            message = json.loads(payload.decode())
            logging.info(f"Received message on topic {topic}: {message}")

            # Run the agent logic in an async context
            asyncio.run(self.handle_message(topic, message))

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
            logging.info("Running agent with new message...")
            result = await Runner.run(self.agent, input=user_prompt)

            response_content = ""
            if result is None:
                logging.error("Agent returned no result.")
                return
            logging.info("Agent is processing the message...")
            response_content = result.final_output

            logging.info(f"Agent raw response: {response_content}")

            if response_content:
                logging.info(f"Extracted command: {response_content}")
                command_topic = self.topic_manager.get_agent_command_topic(line_id)
                # Convert AgentCommand object to dict for JSON serialization
                command_dict = (
                    response_content.model_dump()
                    if hasattr(response_content, "model_dump")
                    else response_content.__dict__
                )
                self.mqtt_client.publish(command_topic, json.dumps(command_dict))
                logging.info(f"Published command to {command_topic}")
            else:
                logging.error("Agent did not return a valid JSON command.")

        except Exception as e:
            logging.error(f"Failed to process message with agent: {e}")

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
            self.mqtt_client.disconnect()


def main():
    from agents import (
        set_default_openai_api,
        set_default_openai_client,
        set_tracing_disabled,
    )
    from openai import AsyncOpenAI

    load_dotenv()

    set_tracing_disabled(True)
    custom_client = AsyncOpenAI(
        base_url="https://api.moonshot.cn/v1", api_key=os.getenv("MOONSHOT_API_KEY")
    )
    set_default_openai_client(custom_client)
    set_default_openai_api("chat_completions")

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
