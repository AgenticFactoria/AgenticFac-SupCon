"""
示例策略文件 - 用于测试命令行评测工具

这个文件展示了如何编写一个策略函数供评测工具使用。
"""

import random
import json


def my_strategy(topic: str, message: dict) -> dict:
    """
    我的自定义策略函数
    
    这是一个示例策略，展示了如何响应不同类型的消息。
    
    Args:
        topic: MQTT 主题
        message: 消息内容
    
    Returns:
        命令字典或 None
    """
    command_id = f"my_strategy_{random.randint(1000, 9999)}"
    
    # 响应新订单
    if "orders" in topic:
        products = message.get("products", [])
        if products:
            # 有新订单时，让 AGV_1 去原料仓库
            return {
                "command_id": command_id,
                "action": "move",
                "target": "AGV_1",
                "params": {"target_point": "P0"}
            }
    
    # 响应 AGV 状态更新
    if "agv" in topic and "status" in topic:
        agv_id = message.get("agv_id", "")
        status = message.get("status", "")
        current_point = message.get("current_point", "")
        battery_level = message.get("battery_level", 100)
        cargo = message.get("cargo", [])
        
        # 电量低时充电
        if battery_level < 25:
            return {
                "command_id": command_id,
                "action": "charge",
                "target": agv_id,
                "params": {"target_level": 85.0}
            }
        
        # 在原料仓库且空载时装货
        if status == "IDLE" and current_point == "P0" and not cargo:
            return {
                "command_id": command_id,
                "action": "load",
                "target": agv_id,
                "params": {}
            }
        
        # 有货物且在原料仓库时，移动到工站A
        if cargo and current_point == "P0":
            return {
                "command_id": command_id,
                "action": "move",
                "target": agv_id,
                "params": {"target_point": "P1"}
            }
        
        # 有货物且在工站A时卸货
        if cargo and current_point == "P1" and status == "IDLE":
            return {
                "command_id": command_id,
                "action": "unload",
                "target": agv_id,
                "params": {}
            }
    
    # 响应工站状态
    if "station" in topic and "status" in topic:
        station_status = message.get("status", "")
        
        # 工站空闲时可以考虑调度 AGV
        if station_status == "IDLE":
            # 这里可以添加更复杂的调度逻辑
            pass
    
    return None


def advanced_strategy(topic: str, message: dict) -> dict:
    """
    更高级的策略函数示例
    
    这个函数展示了更复杂的决策逻辑。
    """
    command_id = f"advanced_{random.randint(1000, 9999)}"
    
    # 处理订单
    if "orders" in topic:
        return {
            "command_id": command_id,
            "action": "move",
            "target": "AGV_2",  # 使用不同的 AGV
            "params": {"target_point": "P0"}
        }
    
    # 处理 AGV 状态
    if "agv" in topic and "status" in topic:
        agv_id = message.get("agv_id", "")
        battery_level = message.get("battery_level", 100)
        
        # 更保守的充电策略
        if battery_level < 40:
            return {
                "command_id": command_id,
                "action": "charge",
                "target": agv_id,
                "params": {"target_level": 90.0}
            }
    
    return None


# 默认策略函数（如果没有指定函数名，会自动使用这个）
def strategy(topic: str, message: dict) -> dict:
    """默认策略函数"""
    return my_strategy(topic, message)


if __name__ == "__main__":
    # 这里可以添加一些测试代码
    print("这是一个示例策略文件")
    print("可用的策略函数:")
    print("- my_strategy: 基本策略")
    print("- advanced_strategy: 高级策略") 
    print("- strategy: 默认策略（等同于 my_strategy）")