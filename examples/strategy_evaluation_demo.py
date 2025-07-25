"""
Example demonstrating how to use the strategy evaluation framework.

This file shows how to create strategy functions and evaluate them using
the eval_strategy function.
"""

import sys
import json
import random
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.strategy_evaluator import eval_strategy, quick_eval


def simple_strategy(topic: str, message: dict) -> dict:
    """
    A simple strategy that responds to orders by moving AGV_1 to raw materials.
    
    Args:
        topic: MQTT topic where the message was received
        message: The message content as a dictionary
    
    Returns:
        Command dictionary or None if no action needed
    """
    # Only respond to new orders
    if "orders" in topic and "status" in topic:
        return {
            "command_id": f"simple_{random.randint(1000, 9999)}",
            "action": "move",
            "target": "AGV_1",
            "params": {"target_point": "P0"}
        }
    
    return None


def reactive_strategy(topic: str, message: dict) -> dict:
    """
    A more reactive strategy that responds to different types of messages.
    
    Args:
        topic: MQTT topic where the message was received
        message: The message content as a dictionary
    
    Returns:
        Command dictionary or None if no action needed
    """
    command_id = f"reactive_{random.randint(1000, 9999)}"
    
    # Respond to new orders
    if "orders" in topic:
        return {
            "command_id": command_id,
            "action": "move",
            "target": "AGV_1",
            "params": {"target_point": "P0"}
        }
    
    # Respond to AGV status updates
    if "agv" in topic and "status" in topic:
        agv_status = message.get("status", "")
        current_point = message.get("current_point", "")
        battery_level = message.get("battery_level", 100)
        
        # If AGV is idle at raw materials, load a product
        if agv_status == "IDLE" and current_point == "P0":
            return {
                "command_id": command_id,
                "action": "load",
                "target": message.get("agv_id", "AGV_1"),
                "params": {}
            }
        
        # If AGV has low battery, charge it
        if battery_level < 30:
            return {
                "command_id": command_id,
                "action": "charge",
                "target": message.get("agv_id", "AGV_1"),
                "params": {"target_level": 80.0}
            }
    
    # Respond to station status updates
    if "station" in topic and "status" in topic:
        station_status = message.get("status", "")
        
        # If station is idle, we might want to move an AGV there
        if station_status == "IDLE":
            return {
                "command_id": command_id,
                "action": "move",
                "target": "AGV_1",
                "params": {"target_point": "P1"}  # Move to Station A
            }
    
    return None


def advanced_strategy(topic: str, message: dict) -> dict:
    """
    An advanced strategy that maintains state and makes more intelligent decisions.
    
    Note: In a real implementation, you'd want to maintain state between calls,
    possibly using a class-based approach or external state management.
    """
    command_id = f"advanced_{random.randint(1000, 9999)}"
    
    # This is a simplified example - in practice you'd maintain state
    # about AGV positions, current tasks, etc.
    
    if "orders" in topic:
        # Analyze the order and decide which AGV to use
        products = message.get("products", [])
        if products:
            # For simplicity, always use AGV_1 for first product
            return {
                "command_id": command_id,
                "action": "move",
                "target": "AGV_1",
                "params": {"target_point": "P0"}
            }
    
    if "agv" in topic and "status" in topic:
        agv_id = message.get("agv_id", "")
        status = message.get("status", "")
        current_point = message.get("current_point", "")
        cargo = message.get("cargo", [])
        
        # If AGV is at raw materials and idle, load a product
        if status == "IDLE" and current_point == "P0" and not cargo:
            return {
                "command_id": command_id,
                "action": "load",
                "target": agv_id,
                "params": {}
            }
        
        # If AGV has cargo and is at raw materials, move to Station A
        if cargo and current_point == "P0":
            return {
                "command_id": command_id,
                "action": "move",
                "target": agv_id,
                "params": {"target_point": "P1"}
            }
        
        # If AGV has cargo and is at Station A, unload
        if cargo and current_point == "P1" and status == "IDLE":
            return {
                "command_id": command_id,
                "action": "unload",
                "target": agv_id,
                "params": {}
            }
    
    return None


def no_action_strategy(topic: str, message: dict) -> dict:
    """
    A strategy that takes no actions - useful as a baseline.
    """
    return None


def main():
    """
    Demonstrate different ways to evaluate strategies.
    """
    print("🧪 Strategy Evaluation Demo")
    print("=" * 50)
    
    # Test different strategies
    strategies = [
        ("No Action (Baseline)", no_action_strategy),
        ("Simple Strategy", simple_strategy),
        ("Reactive Strategy", reactive_strategy),
        ("Advanced Strategy", advanced_strategy),
    ]
    
    simulation_time = 60  # Run for 1 minute for demo purposes
    
    results = {}
    
    for name, strategy_func in strategies:
        print(f"\n🔄 Evaluating: {name}")
        print("-" * 30)
        
        try:
            # Use quick_eval for simple score comparison
            score = quick_eval(strategy_func, simulation_time)
            results[name] = score
            print(f"✅ Score: {score:.2f}")
            
        except Exception as e:
            print(f"❌ Error evaluating {name}: {e}")
            results[name] = 0.0
    
    # Print comparison
    print(f"\n📊 Strategy Comparison (Simulation Time: {simulation_time}s)")
    print("=" * 50)
    
    sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)
    for i, (name, score) in enumerate(sorted_results, 1):
        print(f"{i}. {name}: {score:.2f}")
    
    # Demonstrate detailed evaluation
    print(f"\n🔍 Detailed Evaluation Example")
    print("-" * 30)
    
    try:
        detailed_results = eval_strategy(
            reactive_strategy, 
            simulation_time,
            no_mqtt=True,  # Offline testing
            no_faults=True  # No random faults
        )
        
        print(f"Total Score: {detailed_results.get('total_score', 'N/A')}")
        print(f"Efficiency Score: {detailed_results.get('efficiency_score', 'N/A')}")
        print(f"Quality Cost Score: {detailed_results.get('quality_cost_score', 'N/A')}")
        print(f"AGV Score: {detailed_results.get('agv_score', 'N/A')}")
        
        metadata = detailed_results.get('evaluation_metadata', {})
        print(f"Messages Processed: {metadata.get('messages_processed', 'N/A')}")
        
    except Exception as e:
        print(f"❌ Error in detailed evaluation: {e}")


if __name__ == "__main__":
    main()