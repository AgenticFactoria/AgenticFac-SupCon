# 命令行策略评测工具使用指南

## 概述

`eval_strategy.py` 是一个命令行工具，让你可以方便地评测和比较不同的 LLM Agent 策略。它提供了详细的日志输出，就像原来的 `run_simple_agent.py` 一样。

## 快速开始

### 1. 评测内置策略

```bash
# 评测简单策略（5分钟）
python eval_strategy.py --builtin simple --time 300

# 快速评测（仅显示得分）
python eval_strategy.py --builtin simple --time 60 --quick

# 详细评测（显示组件得分）
python eval_strategy.py --builtin simple --time 300 --verbose
```

### 2. 评测自定义策略

```bash
# 评测策略文件
python eval_strategy.py my_strategy.py --time 300

# 指定函数名
python eval_strategy.py my_strategy.py::my_function --time 300

# 使用示例策略文件
python eval_strategy.py example_strategy.py --time 300
```

### 3. 比较多个策略

```bash
# 比较内置策略
python eval_strategy.py --builtin simple reactive --compare --time 180

# 比较文件策略和内置策略
python eval_strategy.py example_strategy.py --builtin simple --compare --time 180
```

## 详细功能

### 日志级别

```bash
# 基本输出（仅结果）
python eval_strategy.py --builtin simple --time 60

# 详细日志（显示仿真过程）
python eval_strategy.py --builtin simple --time 60 --verbose

# 调试日志（显示所有细节）
python eval_strategy.py --builtin simple --time 60 --debug

# 记录策略输入输出
python eval_strategy.py --builtin simple --time 60 --debug --log-strategy
```

### 仿真选项

```bash
# 设置评测时间（真实秒数）
python eval_strategy.py --builtin simple --time 600

# 离线模式（不使用 MQTT）
python eval_strategy.py --builtin simple --time 300 --no-mqtt

# 禁用随机故障
python eval_strategy.py --builtin simple --time 300 --no-faults

# 自定义 MQTT 主题根
python eval_strategy.py --builtin simple --time 300 --topic-root MY_TOPIC
```

### 输出选项

```bash
# 保存结果到 JSON 文件
python eval_strategy.py --builtin simple --time 300 --output results.json

# 快速模式（仅显示总得分）
python eval_strategy.py --builtin simple --time 300 --quick
```

## 策略文件格式

### 基本格式

创建一个 Python 文件，包含策略函数：

```python
def my_strategy(topic: str, message: dict) -> dict:
    """
    策略函数
    
    Args:
        topic: MQTT 主题
        message: 消息内容字典
    
    Returns:
        命令字典或 None
    """
    if "orders" in topic:
        return {
            "action": "move",
            "target": "AGV_1",
            "params": {"target_point": "P0"}
        }
    return None
```

### 多函数文件

```python
def strategy_a(topic: str, message: dict) -> dict:
    # 策略 A 的逻辑
    pass

def strategy_b(topic: str, message: dict) -> dict:
    # 策略 B 的逻辑
    pass

# 默认策略（如果不指定函数名会使用这个）
def strategy(topic: str, message: dict) -> dict:
    return strategy_a(topic, message)
```

使用时：
```bash
# 使用默认策略函数
python eval_strategy.py my_strategies.py

# 指定具体函数
python eval_strategy.py my_strategies.py::strategy_a
python eval_strategy.py my_strategies.py::strategy_b
```

## 内置策略

工具提供了三个内置策略用于测试和比较：

- **`none`**: 不执行任何操作的基准策略
- **`simple`**: 简单策略，响应订单移动 AGV 到原料仓库
- **`reactive`**: 响应式策略，根据不同消息类型做出反应

```bash
# 使用内置策略
python eval_strategy.py --builtin none --time 300
python eval_strategy.py --builtin simple --time 300
python eval_strategy.py --builtin reactive --time 300
```

## 日志输出说明

### 基本模式
```
🧪 评测策略: example_strategy
==================================================
📊 评测结果
==================================================
总得分: 45.67
生产效率得分: 18.23
质量成本得分: 13.45
AGV效率得分: 13.99
```

### 详细模式 (`--verbose`)
```
🧪 评测策略: example_strategy
==================================================
2024-01-20 10:30:15 - __main__ - INFO - 🚀 启动 NLDF 策略评测工具
2024-01-20 10:30:15 - __main__ - INFO - ✅ 加载内置策略: simple
2024-01-20 10:30:15 - src.evaluation.strategy_evaluator - INFO - 🏭 正在初始化工厂仿真环境...
2024-01-20 10:30:16 - src.evaluation.strategy_evaluator - INFO - ✅ 工厂创建成功，包含 3 条生产线
...
```

### 调试模式 (`--debug --log-strategy`)
```
2024-01-20 10:30:20 - strategy.simple - INFO - 📥 收到消息 - 主题: NLDF_TEST/orders/status
2024-01-20 10:30:20 - strategy.simple - DEBUG - 📥 消息内容: {
  "order_id": "order_001",
  "products": ["prod_1_abc123"]
}
2024-01-20 10:30:20 - strategy.simple - INFO - 📤 执行动作: move -> AGV_1
```

## 实用示例

### 开发新策略的工作流

1. **创建策略文件**
```python
# my_new_strategy.py
def my_strategy(topic: str, message: dict) -> dict:
    # 你的策略逻辑
    pass
```

2. **快速测试**
```bash
python eval_strategy.py my_new_strategy.py --time 60 --quick
```

3. **详细调试**
```bash
python eval_strategy.py my_new_strategy.py --time 120 --debug --log-strategy
```

4. **与基准比较**
```bash
python eval_strategy.py my_new_strategy.py --builtin simple --compare --time 300
```

5. **保存结果**
```bash
python eval_strategy.py my_new_strategy.py --time 600 --output my_results.json
```

### 批量测试多个策略

```bash
# 创建测试脚本
#!/bin/bash
strategies=("strategy_v1.py" "strategy_v2.py" "strategy_v3.py")

for strategy in "${strategies[@]}"; do
    echo "Testing $strategy"
    python eval_strategy.py "$strategy" --time 300 --output "${strategy%.py}_results.json"
done
```

## 故障排除

### 常见问题

1. **策略文件加载失败**
```bash
❌ 加载策略失败 'my_strategy.py': 函数 'strategy' 在文件 my_strategy.py 中不存在
```
解决：确保文件中有可调用的函数，或使用 `::function_name` 指定函数名

2. **MQTT 连接失败**
```bash
❌ MQTT 连接失败
```
解决：使用 `--no-mqtt` 进行离线测试

3. **策略执行错误**
```bash
❌ 策略函数执行错误: 'dict' object has no attribute 'get'
```
解决：检查策略函数中的消息处理逻辑

### 调试技巧

1. **使用调试模式查看详细信息**
```bash
python eval_strategy.py my_strategy.py --debug --log-strategy --time 60
```

2. **先用内置策略测试环境**
```bash
python eval_strategy.py --builtin simple --time 30 --verbose
```

3. **使用短时间测试快速迭代**
```bash
python eval_strategy.py my_strategy.py --time 30 --quick
```

## 测试工具

运行测试脚本验证工具是否正常工作：

```bash
python test_cli_tool.py
```

这会运行一系列测试来验证命令行工具的各项功能。

## 评测时间说明

评测工具中的 `--time` 参数指的是**真实时间**，与仿真时间同步。

- **真实时间**: 评测实际花费的墙钟时间
- **仿真时间**: 工厂仿真内部的虚拟时间，与真实时间 1:1 同步

例如：
- `--time 300` 表示评测运行 5 分钟真实时间
- 仿真时间也会相应地推进 300 秒

这样设计是为了让评测结果更接近真实的工厂运行情况。

## 性能建议

- **开发阶段**: 使用 `--time 60-300` 进行快速测试（1-5分钟）
- **调试阶段**: 使用 `--debug --log-strategy` 查看详细执行过程
- **最终评测**: 使用 `--time 600-1800` 进行完整评测（10-30分钟）
- **批量比较**: 使用 `--compare` 模式同时测试多个策略
- **离线开发**: 使用 `--no-mqtt` 避免网络依赖