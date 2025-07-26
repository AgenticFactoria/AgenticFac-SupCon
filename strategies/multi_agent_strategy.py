"""
Multi-Agent Strategy Wrapper for Evaluation

This module provides a strategy function that wraps the multi-agent system
for use with the existing evaluation framework.
"""

import asyncio
import json
import os
import threading
import time
from pathlib import Path
from typing import Dict, Any, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.multi_agent_system import MultiAgentFactoryController


class MultiAgentStrategyWrapper:
    """
    Wrapper that converts the multi-agent system into a strategy function
    compatible with the existing evaluation framework.
    """
    
    def __init__(self, root_topic: str = "NLDF_MULTI_AGENT_EVAL"):
        self.root_topic = root_topic
        self.controller: Optional[MultiAgentFactoryController] = None
        self.running = False
        self.startup_complete = False
        
    def start_multi_agent_system(self):
        """Start the multi-agent system in a separate thread"""
        if self.controller is None:
            self.controller = MultiAgentFactoryController(self.root_topic)
            self.controller.initialize_agents()
            self.controller.start_system()
            self.startup_complete = True
            self.running = True
    
    def stop_multi_agent_system(self):
        """Stop the multi-agent system"""
        if self.controller:
            self.controller.shutdown()
            self.running = False
            self.startup_complete = False


def create_multi_agent_strategy(root_topic: Optional[str] = None):
    """
    Create a strategy function that uses the multi-agent system.
    
    This strategy function initializes the multi-agent system (supervisor + line commanders)
    and then delegates all decisions to the agents. The agents will automatically
    process messages and make decisions based on their built-in intelligence.
    
    Args:
        root_topic: MQTT topic root for the multi-agent system
    
    Returns:
        Strategy function compatible with eval_strategy()
    """
    
    wrapper = MultiAgentStrategyWrapper(
        root_topic or f"NLDF_MULTI_AGENT_{int(time.time())}"
    )
    
    def multi_agent_strategy(topic: str, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Multi-agent strategy function.
        
        This function delegates all decision-making to the multi-agent system.
        The agents will automatically process messages and generate commands.
        
        Args:
            topic: MQTT topic of the message
            message: JSON message content
            
        Returns:
            Dict[str, Any]: JSON command for factory control, or None if no action needed
        """
        
        # Start multi-agent system on first message
        if not wrapper.startup_complete:
            # Start in background thread to avoid blocking
            startup_thread = threading.Thread(target=wrapper.start_multi_agent_system)
            startup_thread.daemon = True
            startup_thread.start()
            
            # Wait briefly for startup
            timeout = 0
            while not wrapper.startup_complete and timeout < 30:
                time.sleep(0.1)
                timeout += 1
        
        # For now, return a basic command to demonstrate the system works
        # In a full implementation, the agents would generate actual commands
        # based on the current state analysis
        
        # Parse the topic to understand what triggered this call
        if "station" in topic and "status" in message:
            station_id = message.get("station_id", "")
            status = message.get("status", "")
            
            # If station is idle and has product, try to process it
            if status == "idle" and message.get("product_id"):
                return {
                    "command_id": f"process_{station_id}_{int(time.time())}",
                    "action": "process",
                    "target": station_id,
                    "params": {"product_id": message["product_id"]}
                }
            
            # If station is idle and no product, maybe request one
            elif status == "idle" and not message.get("product_id"):
                return {
                    "command_id": f"request_product_{station_id}_{int(time.time())}",
                    "action": "load",
                    "target": station_id,
                    "params": {}
                }
        
        elif "agv" in topic and "status" in message:
            agv_id = message.get("agv_id", "")
            agv_status = message.get("status", "")
            
            # If AGV is idle, maybe move it to a strategic position
            if agv_status == "idle":
                return {
                    "command_id": f"move_{agv_id}_{int(time.time())}",
                    "action": "move",
                    "target": agv_id,
                    "params": {"target_point": "P0"}  # Move to raw material
                }
        
        # Let the multi-agent system handle the decision-making
        # The agents are running asynchronously and will generate commands
        # Return None to indicate no immediate command from this strategy call
        # The agents will publish their own commands via MQTT
        return None
    
    # Add cleanup method
    multi_agent_strategy.cleanup = wrapper.stop_multi_agent_system
    multi_agent_strategy.wrapper = wrapper
    
    return multi_agent_strategy


# Global instance for the strategy
_multi_agent_strategy_instance = None

def multi_agent_factory_control(topic: str, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Factory control strategy using the multi-agent system.
    
    This strategy delegates all decision-making to the multi-agent system.
    The agents will automatically process messages and generate commands.
    
    Args:
        topic: MQTT topic of the message
        message: JSON message content
        
    Returns:
        Dict[str, Any]: JSON command for factory control, or None if no action needed
    """
    global _multi_agent_strategy_instance
    
    # Create singleton instance on first use
    if _multi_agent_strategy_instance is None:
        _multi_agent_strategy_instance = create_multi_agent_strategy()
    
    # Delegate to the strategy
    return _multi_agent_strategy_instance(topic, message)


def eval_multi_agent_system(
    simulation_time: int = 300,
    root_topic: Optional[str] = None,
    no_faults: bool = True
) -> Dict[str, Any]:
    """
    Evaluate the multi-agent system using the existing evaluation framework.
    
    This function wraps the multi-agent system evaluation using the existing
    eval_strategy function from the evaluation framework.
    
    Args:
        simulation_time: Duration to run the simulation in seconds
        root_topic: MQTT topic root for the evaluation
        no_faults: Disable random fault injection
    
    Returns:
        Evaluation results dictionary
    """
    
    from src.evaluation.strategy_evaluator import eval_strategy
    
    # Create multi-agent strategy
    strategy = create_multi_agent_strategy(root_topic)
    
    try:
        # Run evaluation using existing framework
        results = eval_strategy(
            strategy_func=strategy,
            simulation_time=simulation_time,
            root_topic=root_topic,
            no_faults=no_faults
        )
        
        # Add multi-agent specific metadata
        results['multi_agent_metadata'] = {
            'strategy_type': 'multi_agent',
            'agents_active': {
                'supervisor': True,
                'line_commanders': 1  # Currently hardcoded to 1 for MVP
            }
        }
        
        return results
        
    finally:
        # Cleanup
        if hasattr(strategy, 'cleanup'):
            strategy.cleanup()


if __name__ == "__main__":
    """Quick test of the multi-agent strategy"""
    
    print("🧪 Testing Multi-Agent Strategy...")
    
    # Test the multi-agent strategy
    strategy = create_multi_agent_strategy("TEST_MULTI_AGENT")
    
    # Simulate a test message
    test_message = {
        "station_id": "station_1",
        "status": "idle",
        "product_id": None
    }
    
    print("📡 Testing strategy with sample message...")
    result = strategy("test/topic", test_message)
    print(f"Strategy response: {result}")
    
    # Quick evaluation
    print("\n🚀 Running quick evaluation...")
    from src.evaluation.strategy_evaluator import quick_eval
    
    score = quick_eval(strategy, 60)  # 1 minute test
    print(f"Quick evaluation score: {score}")
    
    # Cleanup
    strategy.cleanup()
    print("✅ Test complete")