#!/usr/bin/env python3
"""
Simple eval(func) function for NLDF Factory Simulation
"""

import sys
import threading
import time as time_module
import logging
from pathlib import Path
from typing import Callable, Dict, Any, Optional

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.strategy_evaluator import eval_strategy
from run_multi_line_simulation import MultiLineFactorySimulation

logger = logging.getLogger(__name__)


def evaluate(func: Callable, duration: int = 180, detailed: bool = True, auto_start_simulation: bool = True) -> Dict[str, float]:
    """
    Evaluate a strategy function and return detailed scores.
    
    Args:
        func: Strategy function that takes (topic, message) and returns command dict
        duration: Evaluation time in seconds (default: 3 minutes)
        detailed: If True, prints detailed breakdown; if False, only returns scores
        auto_start_simulation: If True, automatically starts the simulation system
    
    Returns:
        Dict containing all KPI scores
    
    Example:
        def my_strategy(topic, message):
            if "orders" in topic:
                return {"action": "move", "target": "AGV_1", "params": {"target_point": "P1"}}
            return None
        
        scores = evaluate(my_strategy)
        print(f"总得分: {scores['total_score']}")
        print(f"生产效率得分: {scores['efficiency_score']}")
        print(f"质量成本得分: {scores['quality_cost_score']}")
        print(f"AGV效率得分: {scores['agv_score']}")
    """
    simulation = None
    
    if auto_start_simulation:
        print("🚀 Starting factory simulation system...")
        simulation = MultiLineFactorySimulation()
        simulation.initialize(no_faults=True, no_mqtt=False)
        
        # Start simulation in a separate thread
        def run_simulation():
            try:
                simulation.run(duration=duration + 10)  # Run a bit longer than evaluation
            except Exception as e:
                logger.error(f"Simulation error: {e}")
        
        sim_thread = threading.Thread(target=run_simulation, daemon=True)
        sim_thread.start()
        
        # Give simulation time to start up
        print("⏳ Waiting for simulation to initialize...")
        time_module.sleep(5)
        print("✅ Simulation system ready!")
    
    try:
        results = eval_strategy(
            strategy_func=func,
            simulation_time=duration,
            no_mqtt=False,  # Enable MQTT connection
            no_faults=True  # No random faults for consistent testing
        )
    finally:
        if simulation:
            print("🛑 Stopping simulation system...")
            simulation.shutdown()
    
    # Extract and format the key scores
    scores = {
        'total_score': results.get('total_score', 0.0),
        'efficiency_score': results.get('efficiency_score', 0.0),
        'quality_cost_score': results.get('quality_cost_score', 0.0),
        'agv_score': results.get('agv_score', 0.0)
    }
    
    # Print detailed breakdown if requested
    if detailed:
        print(f"\n{'=' * 60}")
        print("🏆 策略评估结果")
        print(f"{'=' * 60}")
        print(f"总得分: {scores['total_score']:.2f}")
        print(f"生产效率得分 (40%): {scores['efficiency_score']:.2f}")
        
        # Print efficiency components if available
        if 'efficiency_components' in results:
            components = results['efficiency_components']
            print(f"  - 订单完成率: {components.get('order_completion', 0):.1f}%")
            print(f"  - 生产周期效率: {components.get('production_cycle', 0):.1f}%")
            print(f"  - 设备利用率: {components.get('device_utilization', 0):.1f}%")
        
        print(f"质量与成本得分 (30%): {scores['quality_cost_score']:.2f}")
        
        # Print quality/cost components if available
        if 'quality_cost_components' in results:
            components = results['quality_cost_components']
            print(f"  - 一次通过率: {components.get('first_pass_rate', 0):.1f}%")
            print(f"  - 成本效率: {components.get('cost_efficiency', 0):.1f}%")
        
        print(f"AGV效率得分 (30%): {scores['agv_score']:.2f}")
        
        # Print AGV components if available
        if 'agv_components' in results:
            components = results['agv_components']
            print(f"  - 充电策略效率: {components.get('charge_strategy', 0):.1f}%")
            print(f"  - 能效比: {components.get('energy_efficiency', 0):.1f}%")
            print(f"  - AGV利用率: {components.get('utilization', 0):.1f}%")
        
        print(f"{'=' * 60}\n")
    
    return scores


def eval_score(func: Callable, duration: int = 180) -> float:
    """
    Evaluate a strategy function and return only the total score.
    
    Args:
        func: Strategy function that takes (topic, message) and returns command dict
        duration: Evaluation time in seconds (default: 3 minutes)
    
    Returns:
        Total KPI score as float
    
    Example:
        def my_strategy(topic, message):
            if "orders" in topic:
                return {"action": "move", "target": "AGV_1", "params": {"target_point": "P1"}}
            return None
        
        score = eval_score(my_strategy)
        print(f"Score: {score}")
    """
    scores = evaluate(func, duration, detailed=False)
    return scores['total_score']


# Aliases for convenience
eval = evaluate  # Alias for the main function


# For testing
if __name__ == "__main__":
    def test_strategy(topic: str, message: dict) -> dict:
        if "orders" in topic:
            return {
                "action": "move",
                "target": "AGV_1", 
                "params": {"target_point": "P1"}
            }
        return None
    
    print("🧪 Testing strategy...")
    scores = evaluate(test_strategy, 60)
    print(f"✅ Evaluation completed!")

def quick_eval(func: Callable, duration: int = 60) -> float:
    """
    Quick evaluation function that returns only the total score.
    
    Args:
        func: Strategy function
        duration: Evaluation time in seconds (default: 1 minute for quick test)
    
    Returns:
        Total score as float
    """
    scores = evaluate(func, duration=duration, detailed=False, auto_start_simulation=True)
    return scores['total_score']


def main():
    """
    Main function for command line usage.
    """
    import importlib.util
    import argparse
    
    parser = argparse.ArgumentParser(description='Evaluate a strategy function')
    parser.add_argument('strategy_file', help='Python file containing the strategy function')
    parser.add_argument('--function', '-f', default='strategy', help='Function name to evaluate (default: strategy)')
    parser.add_argument('--time', '-t', type=int, default=180, help='Evaluation time in seconds (default: 180)')
    parser.add_argument('--quick', '-q', action='store_true', help='Quick evaluation (60 seconds, score only)')
    
    args = parser.parse_args()
    
    # Load the strategy function
    spec = importlib.util.spec_from_file_location("strategy_module", args.strategy_file)
    strategy_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(strategy_module)
    
    strategy_func = getattr(strategy_module, args.function)
    
    if args.quick:
        score = quick_eval(strategy_func)
        print(f"Quick evaluation score: {score:.2f}")
    else:
        evaluate(strategy_func, duration=args.time)


if __name__ == "__main__":
    main()