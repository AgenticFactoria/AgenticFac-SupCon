#!/usr/bin/env python3
"""
测试真实时间同步是否正确工作
"""

import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

def test_strategy(topic: str, message: dict) -> dict:
    """简单的测试策略"""
    if "orders" in topic:
        print(f"[{time.strftime('%H:%M:%S')}] 策略响应订单")
        return {
            "action": "move",
            "target": "AGV_1",
            "params": {"target_point": "P0"}
        }
    return None

def main():
    """测试真实时间同步"""
    try:
        from src.evaluation.strategy_evaluator import eval_strategy
        
        print("🧪 测试真实时间同步...")
        print("=" * 50)
        
        # 测试 10 秒的真实时间同步
        test_duration = 10
        print(f"开始评测，持续时间: {test_duration}秒（真实时间）")
        print(f"开始时间: {time.strftime('%H:%M:%S')}")
        
        start_time = time.time()
        
        results = eval_strategy(
            test_strategy, 
            test_duration,
            no_mqtt=True,  # 离线测试
            no_faults=True
        )
        
        end_time = time.time()
        actual_duration = end_time - start_time
        
        print(f"结束时间: {time.strftime('%H:%M:%S')}")
        print(f"\n📊 时间同步测试结果:")
        print(f"设定时间: {test_duration}秒")
        print(f"实际耗时: {actual_duration:.2f}秒")
        print(f"时间误差: {abs(actual_duration - test_duration):.2f}秒")
        
        # 允许 ±2 秒的误差
        if abs(actual_duration - test_duration) <= 2:
            print("✅ 真实时间同步正常")
            return True
        else:
            print("❌ 真实时间同步可能有问题")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)