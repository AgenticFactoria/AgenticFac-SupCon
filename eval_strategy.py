#!/usr/bin/env python3
"""
命令行策略评测工具

使用方法:
    python eval_strategy.py strategy_file.py [选项]
    python eval_strategy.py strategy_file.py::function_name [选项]
    python eval_strategy.py --builtin simple [选项]

示例:
    python eval_strategy.py my_strategy.py --time 300
    python eval_strategy.py strategies/advanced.py::my_advanced_strategy --time 600 --verbose
    python eval_strategy.py --builtin reactive --time 180 --compare
"""

import sys
import os
import argparse
import importlib.util
import json
import time
import logging
from pathlib import Path
from typing import Callable, Dict, Any, Optional, List

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.strategy_evaluator import eval_strategy, quick_eval


def create_logged_strategy(strategy_func: Callable, name: str, log_io: bool = False) -> Callable:
    """
    创建带日志记录的策略包装器，模拟 simple agent 的处理过程
    
    Args:
        strategy_func: 原始策略函数
        name: 策略名称
        log_io: 是否记录输入输出
    
    Returns:
        包装后的策略函数
    """
    logger = logging.getLogger(__name__)  # 使用主日志记录器
    
    def logged_strategy(topic: str, message: dict) -> dict:
        try:
            # 模拟 simple agent 的处理流程
            if "orders" in topic:
                logger.info("Running agent with new message...")
            
            # 调用原始策略函数
            result = strategy_func(topic, message)
            
            if result is not None:
                if log_io:
                    logger.info(f"Agent raw response: {result}")
                    logger.info(f"Extracted command: {result}")
                else:
                    logger.info("Agent is processing the message...")
                    logger.info(f"Agent raw response: {result}")
                    logger.info(f"Extracted command: {result}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to process message with agent: {e}")
            return None
    
    return logged_strategy


def load_strategy_from_file(file_path: str, function_name: Optional[str] = None) -> Callable:
    """
    从文件中加载策略函数
    
    Args:
        file_path: 策略文件路径
        function_name: 函数名（可选，默认查找常见名称）
    
    Returns:
        策略函数
    """
    logger = logging.getLogger(__name__)
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"策略文件不存在: {file_path}")
    
    logger.info(f"📂 加载策略文件: {file_path}")
    
    # 动态导入模块
    spec = importlib.util.spec_from_file_location("strategy_module", file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载策略文件: {file_path}")
    
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    # 查找策略函数
    if function_name:
        if not hasattr(module, function_name):
            raise AttributeError(f"函数 '{function_name}' 在文件 {file_path} 中不存在")
        logger.info(f"✅ 找到指定函数: {function_name}")
        return getattr(module, function_name)
    
    # 自动查找策略函数（按优先级）
    common_names = [
        'strategy', 'main_strategy', 'agent_strategy', 
        'my_strategy', 'run_strategy', 'execute_strategy'
    ]
    
    for name in common_names:
        if hasattr(module, name):
            func = getattr(module, name)
            if callable(func):
                logger.info(f"✅ 自动找到策略函数: {name}")
                return func
    
    # 查找所有可调用的函数
    functions = [name for name in dir(module) 
                if callable(getattr(module, name)) and not name.startswith('_')]
    
    if not functions:
        raise ValueError(f"在文件 {file_path} 中没有找到可调用的函数")
    
    if len(functions) == 1:
        logger.info(f"✅ 找到唯一函数: {functions[0]}")
        return getattr(module, functions[0])
    
    raise ValueError(f"在文件 {file_path} 中找到多个函数，请指定函数名: {functions}")


def get_builtin_strategy(name: str) -> Callable:
    """获取内置策略"""
    import random
    logger = logging.getLogger(__name__)
    
    def no_action_strategy(topic: str, message: dict) -> dict:
        """不执行任何操作的基准策略"""
        return None
    
    def simple_strategy(topic: str, message: dict) -> dict:
        """简单策略：响应订单，移动AGV到原料仓库"""
        if "orders" in topic:
            return {
                "command_id": f"simple_{random.randint(1000, 9999)}",
                "action": "move",
                "target": "AGV_1",
                "params": {"target_point": "P0"}
            }
        return None
    
    def reactive_strategy(topic: str, message: dict) -> dict:
        """响应式策略：根据不同消息类型做出反应"""
        command_id = f"reactive_{random.randint(1000, 9999)}"
        
        if "orders" in topic:
            return {
                "command_id": command_id,
                "action": "move",
                "target": "AGV_1",
                "params": {"target_point": "P0"}
            }
        
        if "agv" in topic and "status" in topic:
            agv_status = message.get("status", "")
            current_point = message.get("current_point", "")
            battery_level = message.get("battery_level", 100)
            agv_id = message.get("agv_id", "AGV_1")
            
            if agv_status == "IDLE" and current_point == "P0":
                return {
                    "command_id": command_id,
                    "action": "load",
                    "target": agv_id,
                    "params": {}
                }
            
            if battery_level < 30:
                return {
                    "command_id": command_id,
                    "action": "charge",
                    "target": agv_id,
                    "params": {"target_level": 80.0}
                }
        
        return None
    
    def multi_agent_strategy(topic: str, message: dict) -> dict:
        """多智能体策略：使用主管代理和生产线指挥官"""
        # 多智能体系统会在内部处理所有决策
        # 这里返回None，因为实际决策由多智能体系统内部完成
        return None
    
    strategies = {
        'none': no_action_strategy,
        'simple': simple_strategy,
        'reactive': reactive_strategy,
        'multi_agent': multi_agent_strategy,
    }
    
    if name not in strategies:
        available = ', '.join(strategies.keys())
        raise ValueError(f"未知的内置策略: {name}. 可用策略: {available}")
    
    logger.info(f"✅ 加载内置策略: {name}")
    return strategies[name]


def format_results(results: Dict[str, Any], verbose: bool = False) -> str:
    """格式化评测结果"""
    output = []
    
    # 基本得分信息
    output.append("📊 评测结果")
    output.append("=" * 50)
    output.append(f"总得分: {results.get('total_score', 0):.2f}")
    output.append(f"生产效率得分: {results.get('efficiency_score', 0):.2f}")
    output.append(f"质量成本得分: {results.get('quality_cost_score', 0):.2f}")
    output.append(f"AGV效率得分: {results.get('agv_score', 0):.2f}")
    
    if verbose:
        # 详细组件得分
        output.append("\n📈 详细得分组件")
        output.append("-" * 30)
        
        eff_comp = results.get('efficiency_components', {})
        output.append(f"生产效率组件:")
        output.append(f"  订单完成率: {eff_comp.get('order_completion', 0):.1f}%")
        output.append(f"  生产周期效率: {eff_comp.get('production_cycle', 0):.1f}%")
        output.append(f"  设备利用率: {eff_comp.get('device_utilization', 0):.1f}%")
        
        qc_comp = results.get('quality_cost_components', {})
        output.append(f"质量成本组件:")
        output.append(f"  一次通过率: {qc_comp.get('first_pass_rate', 0):.1f}%")
        output.append(f"  成本效率: {qc_comp.get('cost_efficiency', 0):.1f}%")
        
        agv_comp = results.get('agv_components', {})
        output.append(f"AGV效率组件:")
        output.append(f"  充电策略效率: {agv_comp.get('charge_strategy', 0):.1f}%")
        output.append(f"  能效比: {agv_comp.get('energy_efficiency', 0):.1f}%")
        output.append(f"  AGV利用率: {agv_comp.get('utilization', 0):.1f}%")
        
        # 元数据
        metadata = results.get('evaluation_metadata', {})
        output.append(f"\n🔍 评测元数据")
        output.append("-" * 30)
        output.append(f"仿真时间: {metadata.get('simulation_time', 0)}秒")
        output.append(f"处理消息数: {metadata.get('messages_processed', 0)}")
        output.append(f"离线模式: {'是' if metadata.get('no_mqtt', False) else '否'}")
        output.append(f"无故障模式: {'是' if metadata.get('no_faults', False) else '否'}")
    
    return "\n".join(output)


def compare_strategies(strategies: List[tuple], simulation_time: int, **kwargs) -> None:
    """比较多个策略"""
    logger = logging.getLogger(__name__)
    
    print("🏆 策略对比评测")
    print("=" * 60)
    logger.info(f"开始比较 {len(strategies)} 个策略，评测时间: {simulation_time}秒（真实时间）")
    
    results = []
    
    for i, (name, strategy_func) in enumerate(strategies, 1):
        print(f"\n🔄 评测策略 ({i}/{len(strategies)}): {name}")
        print("-" * 30)
        logger.info(f"开始评测策略: {name}")
        
        try:
            start_time = time.time()
            score = quick_eval(strategy_func, simulation_time, **kwargs)
            eval_time = time.time() - start_time
            
            results.append((name, score, eval_time))
            print(f"✅ 得分: {score:.2f} (用时: {eval_time:.1f}秒)")
            logger.info(f"策略 {name} 评测完成，得分: {score:.2f}")
            
        except Exception as e:
            print(f"❌ 评测失败: {e}")
            logger.error(f"策略 {name} 评测失败: {e}")
            results.append((name, 0.0, 0.0))
    
    # 排序并显示结果
    results.sort(key=lambda x: x[1], reverse=True)
    
    print(f"\n📊 策略排名 (仿真时间: {simulation_time}秒)")
    print("=" * 60)
    
    for i, (name, score, eval_time) in enumerate(results, 1):
        print(f"{i:2d}. {name:<20} 得分: {score:6.2f} 用时: {eval_time:5.1f}秒")
    
    logger.info("策略比较完成")


def save_results(results: Dict[str, Any], output_file: str) -> None:
    """保存结果到文件"""
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"✅ 结果已保存到: {output_file}")
    except Exception as e:
        print(f"❌ 保存结果失败: {e}")


def setup_logging(verbose: bool = False, debug: bool = False) -> None:
    """设置日志配置，模拟原来 simple agent 的日志格式"""
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    else:
        level = logging.WARNING
    
    # 配置根日志记录器，使用与 simple agent 相同的格式
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',  # 简化格式，与 simple agent 一致
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # 设置特定模块的日志级别
    if verbose or debug:
        # 只显示与策略执行相关的重要日志
        logging.getLogger('src.evaluation.strategy_evaluator').setLevel(logging.INFO)
        logging.getLogger('src.utils.mqtt_client').setLevel(logging.INFO)
        logging.getLogger('src.agent_interface').setLevel(logging.INFO)
        
        # 抑制仿真内部的详细日志，避免干扰
        logging.getLogger('src.simulation').setLevel(logging.WARNING)
        logging.getLogger('src.simulation.factory_multi').setLevel(logging.WARNING)
        logging.getLogger('src.simulation.production_line').setLevel(logging.WARNING)
        logging.getLogger('src.simulation.devices').setLevel(logging.WARNING)
        logging.getLogger('src.simulation.order_generator').setLevel(logging.WARNING)
        
        # 抑制设备创建等内部日志
        logging.getLogger('RawMaterial').setLevel(logging.WARNING)
        logging.getLogger('Station').setLevel(logging.WARNING)
        logging.getLogger('AGV').setLevel(logging.WARNING)
        logging.getLogger('Conveyor').setLevel(logging.WARNING)
        logging.getLogger('QualityCheck').setLevel(logging.WARNING)
        logging.getLogger('Warehouse').setLevel(logging.WARNING)
    
    if debug:
        # 调试模式下也要控制日志输出，避免过多干扰信息
        logging.getLogger().setLevel(logging.DEBUG)
        # 即使在调试模式下，也要抑制仿真内部的创建日志
        logging.getLogger('src.simulation.devices').setLevel(logging.INFO)
        logging.getLogger('RawMaterial').setLevel(logging.INFO)
        logging.getLogger('Station').setLevel(logging.INFO)
        logging.getLogger('AGV').setLevel(logging.INFO)
        logging.getLogger('Conveyor').setLevel(logging.INFO)


def main():
    parser = argparse.ArgumentParser(
        description="NLDF 策略评测工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python eval_strategy.py my_strategy.py --time 300
  python eval_strategy.py strategies/advanced.py::my_function --time 600 --verbose
  python eval_strategy.py --builtin simple --time 180
  python eval_strategy.py --builtin simple reactive --compare --time 300
  python eval_strategy.py my_strategy.py --debug  # 显示详细调试信息
        """
    )
    
    # 策略输入
    parser.add_argument(
        'strategy', 
        nargs='*',
        help='策略文件路径 (格式: file.py 或 file.py::function_name) 或内置策略名'
    )
    
    parser.add_argument(
        '--builtin', 
        nargs='+',
        choices=['none', 'simple', 'reactive', 'multi_agent'],
        help='使用内置策略 (可选: none, simple, reactive)'
    )
    
    # 评测参数
    parser.add_argument(
        '--time', '-t',
        type=int,
        default=180,
        help='评测时间（真实秒数，默认180）'
    )
    
    parser.add_argument(
        '--no-mqtt',
        action='store_true',
        help='离线模式（不使用MQTT）'
    )
    
    parser.add_argument(
        '--no-faults',
        action='store_true',
        default=True,
        help='禁用随机故障'
    )
    
    parser.add_argument(
        '--topic-root',
        type=str,
        help='MQTT主题根路径'
    )
    
    # 输出选项
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='显示详细结果和日志'
    )
    
    parser.add_argument(
        '--debug', '-d',
        action='store_true',
        help='显示调试级别的详细日志'
    )
    
    parser.add_argument(
        '--compare', '-c',
        action='store_true',
        help='比较多个策略（仅显示得分）'
    )
    
    parser.add_argument(
        '--output', '-o',
        type=str,
        help='保存结果到JSON文件'
    )
    
    parser.add_argument(
        '--quick',
        action='store_true',
        help='快速评测（仅返回总得分）'
    )
    
    parser.add_argument(
        '--log-strategy',
        action='store_true',
        help='记录策略函数的输入输出'
    )
    
    args = parser.parse_args()
    
    # 设置日志
    setup_logging(args.verbose, args.debug)
    logger = logging.getLogger(__name__)
    
    logger.info("🚀 启动 NLDF 策略评测工具")
    
    # 收集策略
    strategies = []
    
    # 处理内置策略
    if args.builtin:
        for builtin_name in args.builtin:
            try:
                strategy_func = get_builtin_strategy(builtin_name)
                # 包装策略函数以添加日志
                logged_strategy = create_logged_strategy(
                    strategy_func, 
                    f"内置-{builtin_name}", 
                    args.log_strategy
                )
                strategies.append((f"内置-{builtin_name}", logged_strategy))
            except ValueError as e:
                logger.error(f"加载内置策略失败: {e}")
                print(f"❌ {e}")
                return 1
    
    # 处理文件策略
    for strategy_input in args.strategy:
        try:
            if '::' in strategy_input:
                file_path, function_name = strategy_input.split('::', 1)
            else:
                file_path, function_name = strategy_input, None
            
            strategy_func = load_strategy_from_file(file_path, function_name)
            strategy_name = f"{Path(file_path).stem}"
            if function_name:
                strategy_name += f"::{function_name}"
            
            # 包装策略函数以添加日志
            logged_strategy = create_logged_strategy(
                strategy_func, 
                strategy_name, 
                args.log_strategy
            )
            strategies.append((strategy_name, logged_strategy))
            
        except (FileNotFoundError, ImportError, AttributeError, ValueError) as e:
            logger.error(f"加载策略失败 '{strategy_input}': {e}")
            print(f"❌ 加载策略失败 '{strategy_input}': {e}")
            return 1
    
    if not strategies:
        logger.error("未指定任何策略")
        print("❌ 请指定至少一个策略进行评测")
        parser.print_help()
        return 1
    
    logger.info(f"准备评测 {len(strategies)} 个策略")
    
    # 评测参数
    eval_kwargs = {
        'no_mqtt': args.no_mqtt,
        'no_faults': args.no_faults,
    }
    
    if args.topic_root:
        eval_kwargs['root_topic'] = args.topic_root
    
    logger.info(f"评测参数: 评测时间={args.time}秒（真实时间）, 离线模式={args.no_mqtt}, 无故障模式={args.no_faults}")
    
    try:
        if args.compare or len(strategies) > 1:
            # 比较模式
            logger.info("启动策略比较模式")
            compare_strategies(strategies, args.time, **eval_kwargs)
        else:
            # 单策略详细评测
            name, strategy_func = strategies[0]
            print(f"🧪 评测策略: {name}")
            print("=" * 50)
            logger.info(f"开始单策略详细评测: {name}")
            
            if args.quick:
                logger.info("使用快速评测模式")
                score = quick_eval(strategy_func, args.time, **eval_kwargs)
                print(f"总得分: {score:.2f}")
                logger.info(f"快速评测完成，得分: {score:.2f}")
            else:
                logger.info("使用详细评测模式")
                results = eval_strategy(strategy_func, args.time, **eval_kwargs)
                print(format_results(results, args.verbose))
                logger.info(f"详细评测完成，总得分: {results.get('total_score', 0):.2f}")
                
                if args.output:
                    save_results(results, args.output)
        
        logger.info("✅ 所有评测任务完成")
        return 0
        
    except Exception as e:
        logger.error(f"评测过程中发生错误: {e}", exc_info=True)
        print(f"❌ 评测过程中发生错误: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())