# Strategy Evaluation Framework

This document explains how to use the strategy evaluation framework to test and compare different LLM Agent strategies for the NLDF Factory Simulation.

## Overview

The evaluation framework provides a function `eval_strategy(func, time)` that abstracts the testing process for LLM Agent strategies. It allows you to:

1. Test strategy functions in isolation
2. Compare different strategies objectively
3. Get detailed KPI results
4. Run offline tests without MQTT dependencies

## Core Function

```python
def eval_strategy(
    strategy_func: Callable[[str, Dict[str, Any]], Optional[Dict[str, Any]]], 
    simulation_time: int,
    root_topic: Optional[str] = None,
    no_mqtt: bool = False,
    no_faults: bool = True
) -> Dict[str, Any]:
```

### Parameters

- **strategy_func**: A function that takes `(topic, message)` and returns a command dict
- **simulation_time**: Duration to run the evaluation in real seconds (synchronized with simulation time)
- **root_topic**: MQTT topic root (optional, uses environment variables if not provided)
- **no_mqtt**: If True, disables MQTT communication for offline testing
- **no_faults**: If True, disables random fault injection for cleaner testing

### Returns

A dictionary containing:
- KPI scores (total_score, efficiency_score, quality_cost_score, agv_score)
- Component breakdowns for each score category
- Evaluation metadata (simulation time, messages processed, etc.)

## Strategy Function Format

Your strategy function must follow this signature:

```python
def my_strategy(topic: str, message: dict) -> Optional[dict]:
    """
    Process an MQTT message and return a command.
    
    Args:
        topic: MQTT topic where the message was received
        message: The message content as a dictionary
    
    Returns:
        Command dictionary in the format specified in README.md, or None for no action
    """
    # Your logic here
    if "orders" in topic:
        return {
            "command_id": "optional_id",
            "action": "move",
            "target": "AGV_1",
            "params": {"target_point": "P0"}
        }
    return None
```

### Input Messages

Your strategy function will receive messages from these MQTT topics:

- `{root}/line{1,2,3}/station/{id}/status` - Station status updates
- `{root}/line{1,2,3}/agv/{id}/status` - AGV status updates  
- `{root}/line{1,2,3}/conveyor/{id}/status` - Conveyor status updates
- `{root}/line{1,2,3}/alerts` - Fault alerts
- `{root}/warehouse/{id}/status` - Warehouse status
- `{root}/orders/status` - New order notifications
- `{root}/kpi/status` - KPI updates
- `{root}/result/status` - Result updates
- `{root}/response/{line_id}` - Command responses

### Output Commands

Your strategy function should return commands in this format:

```python
{
    "command_id": "str (optional)",
    "action": "str (required: move|load|unload|charge|get_result)",
    "target": "str (required: AGV_ID or device_id)",
    "params": {
        # Action-specific parameters
    }
}
```

Supported actions:
- **move**: `{"target_point": "P0-P9"}`
- **load**: `{"product_id": "prod_id"}` (only for RawMaterial)
- **unload**: `{}` (no parameters)
- **charge**: `{"target_level": 80.0}` (optional, default 80.0)
- **get_result**: `{}` (no parameters)

## Usage Examples

### Basic Usage

```python
from src.evaluation.strategy_evaluator import eval_strategy

def simple_strategy(topic: str, message: dict) -> dict:
    if "orders" in topic:
        return {
            "action": "move",
            "target": "AGV_1",
            "params": {"target_point": "P0"}
        }
    return None

# Evaluate for 3 minutes
results = eval_strategy(simple_strategy, 180)
print(f"Total score: {results['total_score']}")
```

### Quick Evaluation

```python
from src.evaluation.strategy_evaluator import quick_eval

# Get just the total score
score = quick_eval(simple_strategy, 300)
print(f"Score: {score}")
```

### Comparing Strategies

```python
strategies = [
    ("Simple", simple_strategy),
    ("Advanced", advanced_strategy),
]

for name, strategy in strategies:
    score = quick_eval(strategy, 180)  # 3 minutes
    print(f"{name}: {score:.2f}")
```

### Offline Testing

```python
# Test without MQTT broker
results = eval_strategy(
    my_strategy, 
    300,
    no_mqtt=True,  # Offline mode
    no_faults=True  # No random failures
)
```

## Strategy Development Tips

### 1. Handle Different Message Types

```python
def comprehensive_strategy(topic: str, message: dict) -> dict:
    if "orders" in topic:
        # Handle new orders
        return handle_new_order(message)
    elif "agv" in topic:
        # Handle AGV status updates
        return handle_agv_status(message)
    elif "station" in topic:
        # Handle station status updates
        return handle_station_status(message)
    return None
```

### 2. Maintain State (Advanced)

For complex strategies, consider using a class-based approach:

```python
class StatefulStrategy:
    def __init__(self):
        self.agv_states = {}
        self.pending_orders = []
    
    def __call__(self, topic: str, message: dict) -> dict:
        # Update internal state
        self.update_state(topic, message)
        
        # Make decisions based on state
        return self.decide_action(topic, message)

strategy = StatefulStrategy()
results = eval_strategy(strategy, 180)
```

### 3. Error Handling

```python
def robust_strategy(topic: str, message: dict) -> dict:
    try:
        # Your strategy logic
        if "orders" in topic:
            return create_command(message)
    except Exception as e:
        # Log error but don't crash
        print(f"Strategy error: {e}")
    return None
```

## Running Examples

### Command Line Examples

```bash
# Run the basic evaluation example
python run_simple_agent.py --eval

# Run the comprehensive demo
python examples/strategy_evaluation_demo.py

# Use the command line evaluation tool
python eval_strategy.py --builtin simple --time 180 --verbose
python eval_strategy.py example_strategy.py --time 300 --debug
python eval_strategy.py my_strategy.py::my_function --log-strategy
```

### Command Line Evaluation Tool

The `eval_strategy.py` tool provides a convenient way to evaluate strategies from the command line:

#### Basic Usage
```bash
# Evaluate a strategy file
python eval_strategy.py my_strategy.py

# Evaluate with specific function name
python eval_strategy.py my_strategy.py::my_function

# Evaluate built-in strategy
python eval_strategy.py --builtin simple

# Compare multiple strategies
python eval_strategy.py --builtin simple reactive --compare
```

#### Advanced Options
```bash
# Set simulation time (default: 300 seconds)
python eval_strategy.py my_strategy.py --time 600

# Enable verbose logging
python eval_strategy.py my_strategy.py --verbose

# Enable debug logging with strategy I/O
python eval_strategy.py my_strategy.py --debug --log-strategy

# Offline mode (no MQTT)
python eval_strategy.py my_strategy.py --no-mqtt

# Save results to JSON file
python eval_strategy.py my_strategy.py --output results.json

# Quick evaluation (score only)
python eval_strategy.py my_strategy.py --quick
```

#### Built-in Strategies
- `none`: No action baseline
- `simple`: Basic order response
- `reactive`: Multi-message response strategy

### Integration with Existing Agent

To convert your existing SimpleAgent to use the evaluation framework:

```python
# Original SimpleAgent approach
class SimpleAgent:
    def on_message(self, topic: str, payload: bytes):
        message = json.loads(payload.decode())
        # Process and publish command
        
# Converted to strategy function
def agent_strategy(topic: str, message: dict) -> dict:
    # Same logic, but return command instead of publishing
    if "orders" in topic:
        return {
            "action": "move",
            "target": "AGV_1", 
            "params": {"target_point": "P0"}
        }
    return None

# Evaluate the strategy
results = eval_strategy(agent_strategy, 180)
```

## Performance Metrics

The evaluation framework returns detailed KPI metrics:

### Efficiency Score (40% of total)
- Order completion rate (16%)
- Production cycle efficiency (16%) 
- Device utilization rate (8%)

### Quality & Cost Score (30% of total)
- First pass rate (12%)
- Cost efficiency (18%)

### AGV Efficiency Score (30% of total)
- Charging strategy efficiency (9%)
- Energy efficiency (12%)
- AGV utilization rate (9%)

## Best Practices

1. **Start Simple**: Begin with basic strategies and gradually add complexity
2. **Test Offline**: Use `no_mqtt=True` for faster iteration during development
3. **Handle All Message Types**: Don't ignore important status updates
4. **Monitor Battery Levels**: Implement charging strategies to avoid downtime
5. **Optimize for KPIs**: Focus on the metrics that matter most for scoring
6. **Error Recovery**: Handle unexpected situations gracefully
7. **State Management**: For complex strategies, maintain awareness of factory state

## Troubleshooting

### Common Issues

1. **Strategy function not called**: Check that you're returning valid command dictionaries
2. **Commands ignored**: Ensure command format matches the schema exactly
3. **Low scores**: Monitor AGV battery levels and implement charging strategies
4. **Evaluation hangs**: Check for infinite loops in your strategy function

### Debug Tips

```python
def debug_strategy(topic: str, message: dict) -> dict:
    print(f"Received: {topic} -> {message}")
    
    command = your_strategy_logic(topic, message)
    
    if command:
        print(f"Sending: {command}")
    
    return command
```

## Next Steps

1. Study the example strategies in `examples/strategy_evaluation_demo.py`
2. Implement your own strategy function
3. Use `eval_strategy` to test and refine your approach
4. Compare against baseline strategies
5. Optimize for specific KPI components
6. Deploy your best strategy in the full simulation environment