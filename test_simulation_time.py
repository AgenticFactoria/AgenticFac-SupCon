#!/usr/bin/env python3
"""
测试仿真时间处理是否正确
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
        return {
            "action": "move",
            "target": "AGV_1",
            "params": {"target_point": "P0"}
        }
    return None

def main():
    """测试仿真时间处理"""
    try:
        from src.evaluation.strategy_evaluator import eval_strategy
        
        print("🧪 测试仿真时间处理...")
        print("=" * 50)
        
        # 记录真实开始时间
        real_start_time = time.time()
        
        # 运行 30 秒的真实时间
        simulation_time = 30
        print(f"开始评测，评测时间: {simulation_time}秒")
        print("注意：这是真实时间，与仿真时间同步")
        
        results = eval_strategy(
            test_strategy, 
            simulation_time,
            no_mqtt=True,  # 离线测试
            no_faults=True
        )
        
        # 计算真实耗时
        real_elapsed = time.time() - real_start_time
        
        print(f"\n📊 测试结果:")
        print(f"设定评测时间: {simulation_time}秒")
        print(f"实际耗时: {real_elapsed:.2f}秒")
        print(f"时间差异: {abs(real_elapsed - simulation_time):.2f}秒")
        print(f"总得分: {results.get('total_score', 0):.2f}")
        
        metadata = results.get('evaluation_metadata', {})
        print(f"处理消息数: {metadata.get('messages_processed', 0)}")
        
        # 允许一定的时间误差（比如 ±2 秒）
        time_diff = abs(real_elapsed - simulation_time)
        if time_diff <= 2:
            print("✅ 时间同步正确：真实时间与设定时间基本一致")
        else:
            print(f"❌ 时间同步可能有问题：时间差异 {time_diff:.2f}秒")
            
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)