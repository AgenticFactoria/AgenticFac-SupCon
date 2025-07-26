# SUPCON NLDF (Natual Language Driven Factory) Simulator

## Quick Start

### 1. Environment Setup

- Download [uv](https://docs.astral.sh/uv/getting-started/installation/)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

- Clone project

```bash
git clone https://github.com/supcon-international/25-AdventureX-SUPCON-Hackathon.git
cd 25-AdventureX-SUPCON-Hackathon
```

- Install dependencies

```bash
uv sync
```

### 2. Run Simulation

设置环境变量`TOPIC_ROOT`作为仿真系统 mqtt 的 client id 和 topic root 来分隔不同选手，默认值获取顺序为`TOPIC_ROOT`, `USERNAME`, `USER`的环境变量，否则默认"NLDF_TEST"

- add `--menu` arg to enable interactive input thread for test only
- add `--no-mqtt` arg to disable mqtt communication for debug offline

```bash
uv run run_multi_line_simulation.py (--menu) (--no-mqtt)
```

### 3. Unity Run

1. 设置 `StreamingAssets/MQTTBroker.json`中的 Root_Topic_Head 字段与上述的 topic root 一致，并修改 wss.client_id 字段防止 client 冲突。
2. 使用 VScode Live Server 插件，选中到 index.html 文件后 go live 初始化给予 WebGL 的 Unity 前端界面

   "wss":{
   "port": 8084,
   "host": "supos-ce-instance4.supos.app",
   "client*id": "**_NLDF2_mqtt_wss_test**",
   ......
   },

   "common*topic":{
   "Root_Topic_Head": "**_NLDF1**"},

## Background

Agent 成了每个领域绕不开的革命火种，在工业领域亦是如此。作为国内工业自动化的龙头企业，我们正在积极尝试将最前沿的 agent 技术引入真实产线，推动传统工厂向自适应、自组织、自优化系统演进。
我们进一步畅想：能否构建一个像人类一样通过语言决策的智能体系统？可以想象机器之间对话：“我这边快满了，暂停投料。”
“收到，我先缓一轮。”用语言做到理解彼此、协作应变、自主决策，实现工厂收益最大化的同时稳定运行。为此，我们搭建了一个可控的模拟工厂，等待你来赋予它思维与行动，探索 agent 与工业协作的新可能。

## 场景解释

工厂内部包含 3 条产线，一个原料仓库以及一个最终产品仓库，3 条产线配置有一样的 A，B，C 工站以及一个质检站，AB，BC，CQ 三条中间连接的自动传送带和 AGV_1，AGV_2 两个 AGV。选手需要对 3 条产线的一共 6 个 AGV 进行操作（包括移动，装货卸货等），选手需要在有限的时间内操作 agv 协调生产，同时应对随机故障，获得尽可能高的 KPI 得分。（KPI 定义见下文）

为了简单起见，每个 AGV 的可移动路径点都使用 P1-P10 来表示，他们表示当前 AGV 路径上的相对可停顿点，如果希望 AGV1 或 2 前往某点例如原料仓库，都需要移动到 P0 点。AGV 路径互不干扰，不考虑碰撞等因素，路径上的点 ID 如图。
![Factory Agent Logo](/docs/path_point.png)

| point_id | device_id    | 备注      |
| :------- | :----------- | :-------- |
| P0       | RawMaterial  | 原料仓库  |
| P1       | StationA     | 工站 A    |
| P2       | Conveyor_AB  | 传送带 AB |
| P3       | StationB     | 工站 B    |
| P4       | Conveyor_BC  | 传送带 BC |
| P5       | StationC     | 工站 C    |
| P6       | Conveyor_CQ  | 传送带 CQ |
| P7       | QualityCheck | 质检站    |
| P8       | QualityCheck | 质检站    |
| P9       | Warehouse    | 成品仓库  |

## 游戏机制

游戏使用 simpy 实现离散工厂的仿真

1. Order Generactor: 游戏有一个全局的订单生成器，每个订单中可能有一个或多个产品等待加工，一旦生成对应待加工的 product 会在原料仓库中出现
2. 产品说明： 游戏定义 P1，P2，P3 三种产品，产品 id:prod_1_XXXXXX 中包含 3 部分 prod,type 数字和 UUID，产品有自己对应的工艺流程：

- 产品 P1 / P2

```
RawMaterial → [AGV] → StationA → Conveyor_AB → StationB → Conveyor_BC → StationC → Conveyor_CQ → QualityCheck → [AGV] → Warehouse
```

- 产品 P3

```
RawMaterial → [AGV] → StationA → Conveyor_AB → StationB → Conveyor_BC → StationC → Conveyor_CQ[upper/lower buffer] → [AGV] → StationB → Conveyor_BC → StationC → Conveyor_CQ → QualityCheck → [AGV] → Warehousse
```

3. AGV 动作操控时会消耗电量，在移动前检查如果当前电量不足以完成动作，AGV 会自动返回充电站充电。
4. KPI 指标

| 类别         | 指标         | 计算公式                                      |
| :----------- | :----------- | :-------------------------------------------- |
| **生产效率** | 订单完成率   | `按时完成订单数 / 总订单数 × 100%`            |
|              | 生产周期效率 | `实际生产时间 / 理论生产时间`（含完成率权重） |
|              | 设备利用率   | `设备工作时间 / 总时间 × 100%`                |
| **质量成本** | 一次通过率   | `一次通过质检数 / 总产品数 × 100%`            |
|              | 生产成本     | `Σ(物料+能源+维修+报废成本)`                  |
| **AGV 效率** | 充电策略     | `主动充电次数 / 总充电次数 × 100%`            |
|              | 能源效率     | `完成任务数 / 总充电时间`                     |
|              | AGV 利用率   | `运输时间 / (总时间-故障-充电) × 100%`        |

5. 竞赛评分系统（100 分制）

- **生产效率**（40 分）：订单完成率 16 分 + 周期效率 16 分 + 设备利用率 8 分
- **质量成本**（30 分）：一次通过率 12 分 + 成本控制 18 分
- **AGV 效率**（30 分）：充电策略 9 分 + 能效比 12 分 + 利用率 9 分

## 3. 功能与架构

### 3.1 核心工作流：外部 JSON 接口，内部自然语言驱动

仿真环境与选手 Agent 之间通过结构化的 JSON 消息进行通信，我们要求选手在自己的 Agent 内部构建自然语言处理能力，形成 `JSON -> NL -> JSON` 的完整决策链路。

```mermaid
sequenceDiagram
    participant D as Device (SimPy)
    participant M as MQTT Broker
    participant A as AI Agent (选手代码)

    D->>M: PUBLISH (NLDF/station/StationA/status)<br>{"status":"IDLE", ...}
    M->>A: SUBSCRIBE
    A->>A: **内部实现: JSON -> 自然语言 -> 决策 -> JSON**
    A->>M: PUBLISH (agent/commands)<br>{"action": "unload_to_station", ...}
    M->>D: **执行仿真动作**
```

### 3.2 MQTT 通信层

#### Topic 架构 (`NLDF_DEFAULT` will be replaced by use environment variable `TOPIC_ROOT`)

| Topic                                         | Agent 权限    | 描述                            | 消息格式 (Payload) |
| :-------------------------------------------- | :------------ | :------------------------------ | :----------------- |
| `NLDF_DEFAULT/{line_id}/station/{id}/status`  | **Subscribe** | 订阅所有工站的状态              | JSON (结构化)      |
| `NLDF_DEFAULT/{line_id}/agv/{id}/status`      | **Subscribe** | 订阅所有 AGV 的状态             | JSON (结构化)      |
| `NLDF_DEFAULT/{line_id}/conveyor/{id}/status` | **Subscribe** | 订阅所有传送带的状态            | JSON (结构化)      |
| `NLDF_DEFAULT/warehouse/{id}/status`          | **Subscribe** | 订阅所有仓库的状态              | JSON (结构化)      |
| :---                                          | :---          | :---                            | :---               |
| `NLDF_DEFAULT/{line_id}/alerts`               | **Subscribe** | 订阅所有设备故障警报            | JSON (结构化)      |
| `NLDF_DEFAULT/orders/status`                  | **Subscribe** | 接收新订单信息                  | JSON (结构化)      |
| `NLDF_DEFAULT/kpi/status`                     | **Subscribe** | 订阅 KPI 更新                   | JSON (结构化)      |
| `NLDF_DEFAULT/result/status`                  | **Subscribe** | 订阅结果更新                    | JSON (结构化)      |
| :---                                          | :---          | :---                            | :---               |
| `NLDF_DEFAULT/command/{line_id}`              | **Publish**   | 发布选手 Agent 生成的结构化指令 | JSON (结构见下文)  |
| `NLDF_DEFAULT/response/{line_id}`             | **Subscribe** | 接收选手 Agent 的响应           | JSON（结构见下文） |

选手发往 `NLDF_DEFAULT/command/{line_id}` 的消息**必须**是以下格式的 JSON 字符串：

```json
{
  "command_id": "str (可选字段，用于记录决策过程)",
  "action": "str (必须是支持的动作之一)",
  "target": "str (动作的目标设备ID，可选)",
  "params": {
    "key1": "value1", ...
  }
}
```

系统反馈 `response/{line_id}` 的消息如下：

```json
{
  "timestamp": "float (仿真时间戳)",
  "command_id": "str (来自于选手的command_id)",
  "response": "str (反馈信息)"
}
```

支持的指令 `action` 和所需 `params`，command_id is optional, can be ignored.

| Action       | 描述                                                                               | Target | 示例                                                                                                                                                                                |
| :----------- | :--------------------------------------------------------------------------------- | :----- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `move`       | 命令 AGV 移动到指定路径点                                                          | AGV ID | `{'command_id': 'move_688777', 'action': 'move', 'target': 'AGV_1', 'params': {'target_point': 'P1'}}`                                                                              |
| `charge`     | 命令 AGV 主动充电                                                                  | AGV ID | `{'command_id': 'charge_688777', 'action': 'charge', 'target': 'AGV_1', 'params': {'target_level': 70.0}}`(default: 80.0)                                                           |
| `unload`     | 命令 AGV 卸载产品到指定工站                                                        | AGV ID | `{'command_id': 'unload_688777', 'action': 'unload', 'target': 'AGV_2', 'params': {}}`                                                                                              |
| `load`       | 命令 AGV 从指定工站装载产品                                                        | AGV ID | `{'command_id': 'load_688777', 'action': 'load', 'target': 'AGV_1', 'params': {'product_id': 'prod_1_1ee7ce46'}}`(Product ID only can be used in RawMaterial, else will be ignored) |
| 全局 action  | topic 中的 line_id 和 payload 中的 target 字段内容可以忽略，仅为过 schema 格式审核 | 全局   | :---                                                                                                                                                                                |
| `get_result` | 获取当前整个工厂的 KPI 结果                                                        | any    | `{'command_id': 'get_result_688777', 'action': 'get_result', 'target': my factoty', 'params': {}}`                                                                                  |

## 4.评价维度

除了 ADVX 的统一评价维度外，我们将从以下四个方面对你的项目进行等权重评价：

1. **KPI 得分**

   - 这是最直接且客观的评价标准。我们将根据你搭建的 Agent 在预定义 KPI 指标上的表现进行评分。
   - _注意：如果你对虚拟工厂进行了修改，我们会综合考虑这些改动对 KPI 得分的影响。_

2. **LLM Agent 工程能力**

   - 你需要设计或使用一个框架，使 LLM 能够通过 MQTT + JSON 与虚拟工厂高效交互。
   - 我们将重点考察你在上下文管理、状态管理、错误处理等关键机制上的实现。
   - 优雅、健壮的 Agent 工程设计将获得额外加分。

3. **虚拟工厂的改进**

   - 虚拟工厂基于 Simpy 实现，模拟了真实世界的高级排程（Advanced Scheduling）问题。
   - 如果你发现工厂存在不合理之处，可以直接修改或扩展其运行机制，使其更贴近真实工厂。
   - _如对虚拟工厂有任何修改，请务必在项目 README 中显著注明。_

4. **supOS-CE 开源框架的应用**

   - 成功部署 supOS-CE，并使用其自带的 MQTT Broker 作为虚拟工厂与 Agent 的通信接口，将获得加分。
   - 如果你进一步集成了 supOS-CE 的其他组件（如 NodeRED、Portainer 等），或发现并反馈了其问题/bug，也会获得额外加分。

   - > [supos 选手使用方法](https://ofra65wfwe.feishu.cn/wiki/SRgrwj9LWimsTikRFdzcVvlDnEU)

## Strategies Documentation

The project provides several strategy implementations for controlling the factory simulation. These strategies can be used with the evaluation framework to test different approaches to factory optimization.

### Strategy Functions Overview

All strategy functions follow the same interface pattern:

```python
def strategy_function(topic: str, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Process an MQTT message and return a command action.
    
    Args:
        topic: MQTT topic string (e.g., "NLDF/line1/orders")
        message: JSON message dictionary containing factory state
        
    Returns:
        dict: Command in format {"action": "...", "target": "...", "params": {...}}
        None: If no action should be taken
    """
```

### Available Strategy Files

#### 1. Simple Strategy (`strategies/simple_strategy_function.py`)

**Function Name:** `agent_strategy_function`

**Purpose:** Basic single-agent strategy with embedded dependencies

**Key Features:**
- Self-contained function with all dependencies embedded
- Uses LLM integration (Moonshot AI) when API key available
- Falls back to mock responses for testing
- Processes order-related messages only
- Simple decision-making logic

**Usage:**
```python
from simple_strategy_function import agent_strategy_function
results = eval_strategy(agent_strategy_function, simulation_time=300)
```

**Environment Variables:**
- `MOONSHOT_API_KEY`: API key for Moonshot AI integration (optional)

#### 2. Multi-Agent Strategy (`strategies/multi_strategy_function.py`)

**Function Name:** `agent_strategy_function`

**Purpose:** Multi-agent coordination strategy with supervisor and line commanders

**Key Features:**
- Multi-level decision making (supervisor + line commanders)
- Coordinated AGV management across multiple lines
- Order allocation and load balancing
- Battery-aware AGV scheduling
- Embedded multi-agent decision engine

**Decision Logic:**
- **Supervisor Level:** Order allocation and resource distribution
- **Line Commander Level:** AGV coordination within a line
- **AGV Level:** Individual AGV task assignment and charging

**Usage:**
```python
from multi_strategy_function import agent_strategy_function
results = eval_strategy(agent_strategy_function, simulation_time=300)
```

#### 3. NLDF Strategy (`strategies/nldf_strategy_function.py`)

**Function Name:** `predict`

**Purpose:** Next-Level Digital Factory (NLDF) optimized strategy

**Key Features:**
- NLDF-specific optimization logic
- Multi-line support (line1, line2, line3)
- Enhanced KPI-focused decision making
- Advanced LLM integration with proper async handling
- Comprehensive state analysis

**Usage:**
```python
from nldf_strategy_function import predict
results = eval_strategy(predict, simulation_time=300)
```

#### 4. Multi-Agent System Strategy (`strategies/multi_agent_strategy.py`)

**Function Name:** `multi_agent_factory_control`

**Purpose:** Full multi-agent system wrapper for production use

**Key Features:**
- Complete multi-agent system integration
- Supervisor agent for global coordination
- Line commander agents for local optimization
- Real MQTT communication
- Production-ready architecture

**Usage:**
```python
from multi_agent_strategy import multi_agent_factory_control, eval_multi_agent_system

# Quick evaluation
results = eval_multi_agent_system(simulation_time=300)

# Strategy function for eval_strategy
results = eval_strategy(multi_agent_factory_control, simulation_time=300)
```

#### 5. Example Strategies (`strategies/example_strategies.py`)

**Available Functions:**
- `simple_reactive_strategy`: Basic reactive responses to station idle states
- `proactive_scheduling_strategy`: Predictive scheduling based on order patterns
- `warehouse_optimization_strategy`: Focus on inventory and warehouse management
- `load_balancing_strategy`: Distribute workload across stations
- `multi_agent`: Wrapper for multi-agent system

**Usage:**
```python
from example_strategies import get_strategy, list_strategies

# Get specific strategy
strategy = get_strategy('simple_reactive')
results = eval_strategy(strategy, simulation_time=300)

# List all available strategies
print(list_strategies())
```

### Strategy Development Guidelines

#### Function Structure Template

When creating new strategies, follow this template:

```python
def my_strategy_function(topic: str, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Brief description of your strategy.
    
    Args:
        topic: MQTT topic string
        message: JSON message dictionary
        
    Returns:
        dict: Command dictionary or None
    """
    
    # 1. Message filtering - determine if this message is relevant
    if not should_process_message(topic, message):
        return None
    
    # 2. State analysis - extract relevant information from message
    state = analyze_factory_state(topic, message)
    
    # 3. Decision making - apply your strategy logic
    decision = make_strategic_decision(state)
    
    # 4. Command generation - format the response
    return format_command(decision)
```

#### Command Format Specification

All commands must follow this JSON structure:

```json
{
  "command_id": "unique_identifier_string",
  "action": "action_type",
  "target": "device_id",
  "params": {
    "key1": "value1",
    "key2": "value2"
  }
}
```

#### Supported Actions

| Action | Description | Target | Required Params |
|--------|-------------|---------|-----------------|
| `move` | Move AGV to specified point | AGV ID | `target_point`: "P0"-"P9" |
| `charge` | Command AGV to charge | AGV ID | `target_level`: 0-100 (default: 80) |
| `load` | Load product from station | AGV ID | `product_id`: specific product ID (optional) |
| `unload` | Unload product to station | AGV ID | {} (empty params) |
| `get_result` | Get current KPI results | any | {} (empty params) |

#### Testing Your Strategy

Each strategy file includes built-in testing:

```bash
# Test individual strategy
python strategies/simple_strategy_function.py
python strategies/multi_strategy_function.py
python strategies/nldf_strategy_function.py
python strategies/multi_agent_strategy.py

# Test example strategies
python strategies/example_strategies.py
```

#### Performance Evaluation

Use the evaluation framework to test strategies:

```python
from src.evaluation.strategy_evaluator import eval_strategy, quick_eval

# Full evaluation
results = eval_strategy(
    strategy_func=my_strategy,
    simulation_time=300,  # 5 minutes
    root_topic="MY_STRATEGY_TEST"
)

# Quick evaluation (1 minute)
score = quick_eval(my_strategy, 60)
```

### Strategy Comparison

| Strategy | Complexity | Multi-Agent | LLM Integration | Best For |
|----------|------------|-------------|-----------------|----------|
| Simple | Low | No | Optional | Quick testing, baseline |
| Multi | Medium | Yes | Optional | Coordinated AGV management |
| NLDF | High | No | Required | Advanced optimization |
| Multi-Agent System | High | Yes | Required | Production deployment |
| Example Strategies | Variable | Mixed | Optional | Learning and reference |

---