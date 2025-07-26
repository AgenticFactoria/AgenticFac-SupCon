"""
Strategy Evaluation Framework for NLDF Factory Simulation

This module provides an evaluation function that abstracts the testing process 
for LLM Agent strategies. It allows testing different strategy functions against
the factory simulation and returns KPI results.
"""

import os
import sys
import json
import time
import logging
import threading
from pathlib import Path
from typing import Callable, Dict, Any, Optional, List
from dotenv import load_dotenv

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.mqtt_client import MQTTClient
from src.utils.topic_manager import TopicManager
from src.simulation.factory_multi import Factory
from src.utils.config_loader import load_factory_config
from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT
from src.agent_interface.multi_line_command_handler import MultiLineCommandHandler

# Configure logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()


class StrategyEvaluator:
    """
    Evaluates strategy functions against the factory simulation.
    """
    
    def __init__(self, root_topic: Optional[str] = None, no_mqtt: bool = False):
        """
        Initialize the strategy evaluator.
        
        Args:
            root_topic: MQTT topic root. If None, uses environment variables.
            no_mqtt: If True, disables MQTT communication for offline testing.
        """
        self.root_topic = root_topic or (
            os.getenv("TOPIC_ROOT") or 
            os.getenv("USERNAME") or 
            os.getenv("USER") or 
            "NLDF_EVAL_TEST"
        )
        self.no_mqtt = no_mqtt
        self.topic_manager = TopicManager(self.root_topic)
        self.mqtt_client = None
        self.factory = None
        self.command_handler = None
        self.message_buffer = []
        self.strategy_function = None
        self.running = False
        
    def _initialize_simulation(self, no_faults: bool = True):
        """Initialize the factory simulation components."""
        logger.info("Initializing Factory Simulation for evaluation...")
        
        # Print topic manager info like simple agent
        print(f"✅ TopicManager initialized with root topic: '{self.root_topic}'")
        
        # Initialize MQTT client with authentication
        from config.agent_config import get_mqtt_config
        mqtt_config = get_mqtt_config()
        self.mqtt_client = MQTTClient(
            mqtt_config.host, 
            mqtt_config.port, 
            f"{self.root_topic}_evaluator",
            username=mqtt_config.username,
            password=mqtt_config.password
        )
        
        if not self.no_mqtt:
            logger.info(f"Connecting to MQTT Broker at {mqtt_config.host}:{mqtt_config.port}...")
            self.mqtt_client.connect()
            # Wait for MQTT connection
            max_retries = 20
            retry_interval = 0.5
            for i in range(max_retries):
                if self.mqtt_client.is_connected():
                    logger.info("Successfully connected to MQTT Broker")
                    break
                logger.debug(f"Waiting for MQTT connection... ({i + 1}/{max_retries})")
                time.sleep(retry_interval)
            else:
                raise ConnectionError("MQTT connection failed during evaluation setup.")
        else:
            logger.info("Offline mode - skipping MQTT connection")
        
        # Load factory configuration
        try:
            layout_config = load_factory_config("factory_layout_multi.yml")
            logger.info("Factory configuration loaded for evaluation")
        except Exception as e:
            logger.error(f"Failed to load factory configuration: {e}")
            raise
        
        # Create factory
        self.factory = Factory(layout_config, self.mqtt_client, no_faults=no_faults)
        logger.info(f"Factory created with {len(self.factory.lines)} lines")
        
        # Create command handler
        self.command_handler = MultiLineCommandHandler(
            self.factory, self.mqtt_client, self.topic_manager
        )
        logger.info("Command handler initialized for evaluation")
        
    def _setup_message_subscriptions(self):
        """Subscribe to all relevant MQTT topics and collect messages."""
        if self.no_mqtt:
            logger.info("Offline mode - skipping MQTT subscriptions")
            return
            
        # Subscribe to all status topics like simple agent does
        for line in ["line1", "line2", "line3"]:
            topics = [
                f"{self.root_topic}/{line}/station/+/status",
                f"{self.root_topic}/{line}/agv/+/status", 
                f"{self.root_topic}/{line}/conveyor/+/status",
                f"{self.root_topic}/{line}/alerts",
                self.topic_manager.get_agent_response_topic(line)
            ]
            
            for topic in topics:
                self.mqtt_client.subscribe(topic, self._collect_message)
                logger.info(f"Subscribing to topic: {topic}")
        
        # Subscribe to global topics
        global_topics = [
            f"{self.root_topic}/warehouse/+/status",
            self.topic_manager.get_order_topic(),
            self.topic_manager.get_kpi_topic(),
            self.topic_manager.get_result_topic()
        ]
        
        for topic in global_topics:
            self.mqtt_client.subscribe(topic, self._collect_message)
            logger.info(f"Subscribing to topic: {topic}")
        
        logger.info(f"Agent is running and subscribed to all topics under {self.root_topic}")
    
    def _collect_message(self, topic: str, payload: bytes):
        """Collect incoming messages for strategy processing."""
        try:
            message = json.loads(payload.decode())
            self.message_buffer.append({
                'topic': topic,
                'message': message,
                'timestamp': time.time()
            })
            
            # Log message reception like simple agent does
            logger.info(f"Received message on topic {topic}: {message}")
            
            # Process message with strategy if available
            if self.strategy_function and self.running:
                self._process_with_strategy(topic, message)
                
        except json.JSONDecodeError:
            logger.error(f"Could not decode JSON from topic {topic}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def _process_with_strategy(self, topic: str, message: Dict[str, Any]):
        """Process a message using the strategy function."""
        try:
            # Call strategy function with the message
            command = self.strategy_function(topic, message)
            
            if command and isinstance(command, dict):
                # Determine which line to send command to
                line_id = self._determine_line_id(topic, command)
                command_topic = self.topic_manager.get_agent_command_topic(line_id)
                
                if not self.no_mqtt:
                    self.mqtt_client.publish(command_topic, json.dumps(command))
                    logger.info(f"Published command to {command_topic}")
                    logger.debug(f"Command details: {command}")
                else:
                    logger.info(f"Offline mode - would publish command: {command}")
                
        except Exception as e:
            logger.error(f"Failed to process message with strategy: {e}")
    
    def _determine_line_id(self, topic: str, command: Dict[str, Any]) -> str:
        """Determine which line to send the command to based on topic or command content."""
        # Try to extract line_id from topic
        topic_parts = topic.split('/')
        for i, part in enumerate(topic_parts):
            if part.startswith('line') and i + 1 < len(topic_parts):
                return part
        
        # Default to line1 if can't determine
        return "line1"
    
    def _get_final_results(self) -> Dict[str, Any]:
        """Get final KPI results from the factory using get_result command only."""
        if not self.factory:
            logger.error("Factory not available")
            return {}
        
        try:
            # Send get_result command to trigger KPI calculation
            command = {
                "command_id": "eval_get_result",
                "action": "get_result",
                "target": "factory",
                "params": {}
            }
            
            if not self.no_mqtt:
                command_topic = self.topic_manager.get_agent_command_topic("line1")
                logger.info(f"Sending get_result command to {command_topic}")
                self.mqtt_client.publish(command_topic, json.dumps(command))
                
                # Wait for command confirmation first, then get result/status
                response_topic = self.topic_manager.get_agent_response_topic("line1")
                result_topic = self.topic_manager.get_result_topic()
                logger.info(f"Waiting for command confirmation on: {response_topic}")
                logger.info(f"Then will get result from: {result_topic}")
                
                start_wait = time.time()
                check_count = 0
                command_confirmed = False
                
                while True:
                    check_count += 1
                    
                    # First, wait for the get_result command to be confirmed
                    if not command_confirmed:
                        for msg in reversed(self.message_buffer):
                            if (msg['topic'] == response_topic and 
                                msg['message'].get('command_id') == 'eval_get_result'):
                                logger.info(f"✅ get_result command confirmed: {msg['message'].get('response')}")
                                command_confirmed = True
                                break
                    
                    # After confirmation, look for the result in result/status topic
                    if command_confirmed:
                        for msg in reversed(self.message_buffer):
                            if msg['topic'] == result_topic and 'total_score' in msg['message']:
                                elapsed = time.time() - start_wait
                                logger.info(f"✅ Found result after {elapsed:.1f}s: {msg['message']['total_score']}")
                                return msg['message']
                    
                    # Log progress every 10 checks (5 seconds)
                    if check_count % 10 == 0:
                        elapsed = time.time() - start_wait
                        if not command_confirmed:
                            logger.info(f"⏳ Waiting for command confirmation... ({elapsed:.1f}s elapsed)")
                        else:
                            logger.info(f"⏳ Command confirmed, waiting for result/status... ({elapsed:.1f}s elapsed)")
                        
                        # Show recent topics for debugging
                        if len(self.message_buffer) > 0:
                            recent_topics = [msg['topic'] for msg in self.message_buffer[-5:]]
                            logger.info(f"Recent topics: {recent_topics}")
                    
                    # Wait a bit before checking again
                    time.sleep(0.5)
            else:
                # In offline mode, we need to trigger the command handler directly
                logger.info("Offline mode - triggering get_result command directly")
                if hasattr(self, 'command_handler') and self.command_handler:
                    try:
                        # Create AgentCommand object for the command handler
                        from config.schemas import AgentCommand
                        agent_command = AgentCommand(
                            command_id=command["command_id"],
                            action=command["action"],
                            target=command["target"],
                            params=command["params"]
                        )
                        
                        # Call the command handler's execute method directly
                        self.command_handler._execute_command("line1", agent_command)
                        logger.info("get_result command executed in offline mode")
                        
                        # Get the KPI result directly since we're offline
                        if self.factory and self.factory.kpi_calculator:
                            final_scores = self.factory.kpi_calculator.get_final_score()
                            logger.info(f"Offline mode - got scores directly: {final_scores.get('total_score', 0)}")
                            return final_scores
                    except Exception as e:
                        logger.error(f"Error in offline mode command handling: {e}")
                        # Fallback: get scores directly without command processing
                        if self.factory and self.factory.kpi_calculator:
                            logger.info("Fallback: getting scores directly from KPI calculator")
                            final_scores = self.factory.kpi_calculator.get_final_score()
                            return final_scores
                
                logger.warning("Offline mode result retrieval failed")
                return {}
            
        except Exception as e:
            logger.error(f"Error getting final results: {e}")
            return {}
    
    def _cleanup(self):
        """Clean up resources."""
        logger.info("🧹 Cleaning up evaluation resources...")
        self.running = False
        
        if self.mqtt_client and not self.no_mqtt:
            self.mqtt_client.disconnect()
        
        # Clear message buffer
        self.message_buffer.clear()
        
        logger.info("✅ Evaluation cleanup completed")


def eval_strategy(
    strategy_func: Callable[[str, Dict[str, Any]], Optional[Dict[str, Any]]], 
    simulation_time: int,
    root_topic: Optional[str] = None,
    no_mqtt: bool = False,
    no_faults: bool = True
) -> Dict[str, Any]:
    """
    Evaluate a strategy function against the factory simulation.
    
    Args:
        strategy_func: A function that takes (topic, message) and returns a command dict.
                      The function should process MQTT messages and return JSON commands
                      in the format specified in the README.
        simulation_time: Duration to run the simulation in seconds.
        root_topic: MQTT topic root. If None, uses environment variables.
        no_mqtt: If True, disables MQTT communication for offline testing.
        no_faults: If True, disables random fault injection.
    
    Returns:
        Dict containing KPI results and evaluation metrics.
    
    Example:
        def my_strategy(topic: str, message: dict) -> dict:
            if "orders" in topic:
                return {
                    "action": "move",
                    "target": "AGV_1", 
                    "params": {"target_point": "P0"}
                }
            return None
        
        results = eval_strategy(my_strategy, 300)  # Run for 5 minutes
        print(f"Total score: {results['total_score']}")
    """
    evaluator = StrategyEvaluator(root_topic, no_mqtt)
    
    try:
        # Initialize simulation
        evaluator._initialize_simulation(no_faults)
        
        # Set up message subscriptions
        evaluator._setup_message_subscriptions()
        
        # Set strategy function
        evaluator.strategy_function = strategy_func
        evaluator.running = True
        
        logger.info(f"🚀 Starting strategy evaluation for {simulation_time} seconds (real time)...")
        
        # Wait a moment for MQTT subscriptions to be fully established
        if not evaluator.no_mqtt:
            time.sleep(2)
            logger.info("MQTT subscriptions established, starting simulation...")
        
        # Run simulation synchronized with real time (like the original simulation)
        start_time = time.time()
        evaluator.running = True
        
        try:
            while evaluator.running and (time.time() - start_time) < float(simulation_time):
                # Run simulation for 1 second at a time, synchronized with real time
                current_sim_time = int(evaluator.factory.env.now)
                evaluator.factory.run(until=current_sim_time + 1)
                
                # Sleep for 1 second to synchronize with real time
                time.sleep(1)
                
                # Check if we should continue
                elapsed_real_time = time.time() - start_time
                if elapsed_real_time >= float(simulation_time):
                    break
                    
        except KeyboardInterrupt:
            logger.info("🛑 Evaluation interrupted by user")
        
        evaluator.running = False
        final_sim_time = evaluator.factory.env.now
        elapsed_real_time = time.time() - start_time
        
        logger.info(f"⏱️ Evaluation completed after {elapsed_real_time:.1f} real seconds (simulation time: {final_sim_time:.1f})")
        
        # Wait a moment for final messages to be processed
        if not evaluator.no_mqtt:
            time.sleep(1)
        
        # Get final results
        results = evaluator._get_final_results()
        
        # Add evaluation metadata
        results['evaluation_metadata'] = {
            'simulation_time': simulation_time,
            'root_topic': evaluator.root_topic,
            'messages_processed': len(evaluator.message_buffer),
            'no_mqtt': no_mqtt,
            'no_faults': no_faults
        }
        
        logger.info(f"✅ Evaluation completed. Total score: {results.get('total_score', 'N/A')}")
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Evaluation failed: {e}")
        raise
    finally:
        evaluator._cleanup()


# Convenience function for quick testing
def quick_eval(strategy_func: Callable, time_seconds: int = 180) -> float:
    """
    Quick evaluation that returns just the total score.
    
    Args:
        strategy_func: Strategy function to evaluate
        time_seconds: Evaluation time in real seconds (default: 3 minutes)
    
    Returns:
        Total KPI score as float
    """
    results = eval_strategy(strategy_func, time_seconds, no_mqtt=True, no_faults=True)
    return results.get('total_score', 0.0)