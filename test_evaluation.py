#!/usr/bin/env python3
"""
Simple test script to verify the evaluation framework works correctly.
"""

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

def test_strategy(topic: str, message: dict) -> dict:
    """
    Simple test strategy that responds to orders.
    """
    if "orders" in topic:
        return {
            "command_id": "test_001",
            "action": "move",
            "target": "AGV_1",
            "params": {"target_point": "P0"}
        }
    return None

def main():
    """Test the evaluation framework."""
    try:
        from src.evaluation.strategy_evaluator import quick_eval
        
        print("🧪 Testing evaluation framework...")
        print("Running 30-second test simulation...")
        
        # Quick test with short duration
        score = quick_eval(test_strategy, 30)
        
        print(f"✅ Test completed successfully!")
        print(f"Test score: {score:.2f}")
        
        if score >= 0:
            print("✅ Evaluation framework is working correctly")
            return True
        else:
            print("❌ Unexpected negative score")
            return False
            
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure all dependencies are installed")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)