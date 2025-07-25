#!/usr/bin/env python3
"""
测试命令行评测工具的脚本
"""

import subprocess
import sys
import os
from pathlib import Path

def run_command(cmd, description):
    """运行命令并显示结果"""
    print(f"\n{'='*60}")
    print(f"测试: {description}")
    print(f"命令: {' '.join(cmd)}")
    print('='*60)
    
    try:
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=120  # 2分钟超时
        )
        
        if result.returncode == 0:
            print("✅ 命令执行成功")
            print("输出:")
            print(result.stdout)
        else:
            print("❌ 命令执行失败")
            print("错误输出:")
            print(result.stderr)
            
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        print("⏰ 命令执行超时")
        return False
    except Exception as e:
        print(f"❌ 执行异常: {e}")
        return False

def main():
    """运行测试"""
    print("🧪 测试命令行评测工具")
    
    # 确保在正确的目录
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    tests = [
        # 基本功能测试
        (
            ["python", "eval_strategy.py", "--builtin", "simple", "--time", "30", "--quick"],
            "内置简单策略快速评测"
        ),
        
        # 详细日志测试
        (
            ["python", "eval_strategy.py", "--builtin", "simple", "--time", "30", "--verbose"],
            "内置简单策略详细评测"
        ),
        
        # 文件策略测试
        (
            ["python", "eval_strategy.py", "example_strategy.py", "--time", "30", "--quick"],
            "文件策略评测"
        ),
        
        # 指定函数名测试
        (
            ["python", "eval_strategy.py", "example_strategy.py::advanced_strategy", "--time", "30", "--quick"],
            "指定函数名评测"
        ),
        
        # 比较模式测试
        (
            ["python", "eval_strategy.py", "--builtin", "simple", "reactive", "--compare", "--time", "30"],
            "策略比较模式"
        ),
        
        # 调试模式测试
        (
            ["python", "eval_strategy.py", "--builtin", "simple", "--time", "20", "--debug", "--log-strategy"],
            "调试模式测试"
        ),
    ]
    
    success_count = 0
    total_count = len(tests)
    
    for cmd, description in tests:
        if run_command(cmd, description):
            success_count += 1
    
    print(f"\n{'='*60}")
    print(f"测试总结: {success_count}/{total_count} 个测试通过")
    print('='*60)
    
    if success_count == total_count:
        print("🎉 所有测试通过！命令行工具工作正常。")
        return 0
    else:
        print("⚠️  部分测试失败，请检查错误信息。")
        return 1

if __name__ == "__main__":
    sys.exit(main())