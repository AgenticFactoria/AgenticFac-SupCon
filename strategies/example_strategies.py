"""
Example Strategies for Factory Simulation

This module contains various strategy implementations that can be used
with the evaluation framework, including the multi-agent strategy.
"""

from typing import Dict, Any, Optional
import time

from .multi_agent_strategy import create_multi_agent_strategy, eval_multi_agent_system


def simple_reactive_strategy(topic: str, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Simple reactive strategy that responds to station idle states.
    
    When a station becomes idle, it requests the next product from warehouse.
    """
    
    # Check if this is a station status message
    if 'station' in topic and 'status' in message:
        station_status = message.get('status', '').lower()
        station_id = message.get('station_id', '')
        
        # If station is idle, request next product
        if station_status == 'idle':
            return {
                "action": "request_product",
                "target": "warehouse",
                "params": {"station_id": station_id}
            }
    
    return None


def proactive_scheduling_strategy(topic: str, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Proactive scheduling strategy that optimizes AGV routes.
    
    Uses predictive scheduling based on order patterns and station states.
    """
    
    # Check for order messages
    if 'orders' in topic:
        order_data = message
        
        # Simple heuristic: if urgent order, prioritize AGV movement
        if order_data.get('priority', 0) > 5:
            return {
                "action": "prioritize_agv",
                "target": "AGV_1",
                "params": {"priority_order": order_data}
            }
    
    # Check for station completion
    elif 'station' in topic and message.get('status') == 'completed':
        station_id = message.get('station_id', '')
        
        # Move completed product to next station
        return {
            "action": "move_product",
            "target": "AGV_1",
            "params": {
                "from_station": station_id,
                "target_point": "next_station"
            }
        }
    
    return None


def warehouse_optimization_strategy(topic: str, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Warehouse-focused optimization strategy.
    
    Optimizes warehouse operations and inventory management.
    """
    
    # Monitor warehouse inventory levels
    if 'warehouse' in topic:
        inventory = message.get('inventory', {})
        
        # Reorder products if inventory is low
        for product_id, count in inventory.items():
            if count < 2:  # Low stock threshold
                return {
                    "action": "reorder",
                    "target": "warehouse",
                    "params": {
                        "product_id": product_id,
                        "quantity": 10
                    }
                }
    
    return None


def load_balancing_strategy(topic: str, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Load balancing strategy across multiple stations.
    
    Distributes workload evenly across available stations.
    """
    
    # Check station status for load balancing
    if 'station' in topic and 'status' in message:
        station_id = message.get('station_id', '')
        queue_length = message.get('queue_length', 0)
        
        # If queue is long, redirect to another station
        if queue_length > 3:
            return {
                "action": "redirect_product",
                "target": "AGV_1",
                "params": {
                    "from_station": station_id,
                    "reason": "queue_overflow"
                }
            }
    
    return None


# Multi-agent strategy (wrapper)
multi_agent_strategy = create_multi_agent_strategy()


# Strategy registry for easy testing
AVAILABLE_STRATEGIES = {
    'simple_reactive': simple_reactive_strategy,
    'proactive_scheduling': proactive_scheduling_strategy,
    'warehouse_optimization': warehouse_optimization_strategy,
    'load_balancing': load_balancing_strategy,
    'multi_agent': multi_agent_strategy
}


def get_strategy(name: str):
    """Get a strategy by name from the registry."""
    return AVAILABLE_STRATEGIES.get(name)


def list_strategies():
    """List all available strategies."""
    return list(AVAILABLE_STRATEGIES.keys())


if __name__ == "__main__":
    """Test the strategies"""
    
    print("Available strategies:")
    for strategy_name in list_strategies():
        print(f"  - {strategy_name}")
    
    print("\nTesting multi-agent strategy...")
    
    # Quick test of multi-agent evaluation
    results = eval_multi_agent_system(
        simulation_time=120,  # 2 minutes
        root_topic="EVAL_TEST_MULTI"
    )
    
    if 'error' not in results:
        print(f"Multi-agent evaluation complete!")
        print(f"Total Score: {results['kpi_results'].get('total_score', 'N/A')}")
        print(f"Messages: {results['evaluation_metadata']['messages_processed']}")
    else:
        print(f"Error: {results['error']}")