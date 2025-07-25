import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.simple_agent import main
from src.evaluation.strategy_evaluator import eval_strategy

def simple_llm_strategy(topic: str, message: dict) -> dict:
    """
    Example strategy function that can be used with eval_strategy.
    This demonstrates how to convert the SimpleAgent logic into a strategy function.
    """
    import json
    import random
    
    # Only respond to new orders (similar to SimpleAgent)
    if "orders" not in topic:
        return None
    
    # Create a simple command to move AGV_1 to raw materials
    return {
        "command_id": f"simple_{random.randint(1000, 9999)}",
        "action": "move",
        "target": "AGV_1",
        "params": {"target_point": "P0"}
    }

def run_evaluation_example():
    """
    Example of how to use the eval_strategy function to test strategies.
    """
    print("🧪 Running Strategy Evaluation Example")
    print("=" * 50)
    
    # Evaluate the simple strategy for 2 minutes
    try:
        results = eval_strategy(
            simple_llm_strategy, 
            simulation_time=120,  # 2 minutes
            no_mqtt=True,  # Offline testing
            no_faults=True  # No random faults for cleaner testing
        )
        
        print(f"✅ Evaluation completed!")
        print(f"Total Score: {results.get('total_score', 'N/A'):.2f}")
        print(f"Efficiency Score: {results.get('efficiency_score', 'N/A'):.2f}")
        print(f"Quality Cost Score: {results.get('quality_cost_score', 'N/A'):.2f}")
        print(f"AGV Score: {results.get('agv_score', 'N/A'):.2f}")
        
        metadata = results.get('evaluation_metadata', {})
        print(f"Messages Processed: {metadata.get('messages_processed', 'N/A')}")
        
    except Exception as e:
        print(f"❌ Evaluation failed: {e}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run simple agent or evaluation")
    parser.add_argument("--eval", action="store_true", help="Run evaluation example instead of agent")
    args = parser.parse_args()
    
    if args.eval:
        run_evaluation_example()
    else:
        main()
