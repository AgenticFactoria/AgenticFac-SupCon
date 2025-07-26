"""
Simple Agent Strategy - Unified Single Function

This file contains a single comprehensive function that includes all necessary
dependencies and classes for the simple agent strategy. It can be used
directly with evaluate(func) without any external dependencies.

Usage:
    from simple_strategy_function import agent_strategy_function
    results = eval_strategy(agent_strategy_function, simulation_time=300)
"""

import json
import asyncio
import logging
import os
import random
import time
from typing import Dict, Any, Optional, List
from enum import Enum

# Configure logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def predict(topic: str, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Simple agent strategy function with all dependencies included.
    
    This function contains all necessary classes, prompts, and processing logic
    for the simple agent strategy. It can be used directly with eval_strategy().
    
    Args:
        topic: MQTT topic string
        message: Received message dictionary
        
    Returns:
        dict: Agent-generated command, or None if no action needed
    """
    
    # =============================================================================
    # EMBEDDED CLASSES AND ENUMS
    # =============================================================================
    
    class DeviceStatus(str, Enum):
        IDLE = "idle"
        PROCESSING = "processing"
        MAINTENANCE = "maintenance"
        SCRAP = "scrap"
        WORKING = "working"
        BLOCKED = "blocked"
        FAULT = "fault"
        MOVING = "moving"
        INTERACTING = "interacting"
        CHARGING = "charging"

    class OrderPriority(str, Enum):
        LOW = "low"
        MEDIUM = "medium"
        HIGH = "high"

    # =============================================================================
    # EMBEDDED PROMPTS
    # =============================================================================

    SIMPLE_AGENT_PROMPT = """
    You are an AI agent controlling a factory with the goal of maximizing KPI scores. You will receive JSON messages with real-time data from the factory and must respond with JSON commands to control the AGVs.

    ## Factory Layout

    The factory has 3 identical production lines, a raw material warehouse, and a finished product warehouse. Each production line has:
    - Stations: A, B, C
    - Quality Check Station
    - Conveyors: AB, BC, CQ
    - 2 AGVs (AGV_1, AGV_2)

    ### AGV Path Points

    AGVs move between the following points:

    | point_id | device_id    | Description       |
    |:---------|:-------------|:------------------|
    | P0       | RawMaterial  | Raw Material      |
    | P1       | StationA     | Station A         |
    | P2       | Conveyor_AB  | Conveyor AB       |
    | P3       | StationB     | Station B         |
    | P4       | Conveyor_BC  | Conveyor BC       |
    | P5       | StationC     | Station C         |
    | P6       | Conveyor_CQ  | Conveyor CQ       |
    | P7       | QualityCheck | Quality Check     |
    | P8       | QualityCheck | Quality Check     |
    | P9       | Warehouse    | Finished Goods    |

    ## Game Rules

    1.  **Order Generation**: New orders for products (P1, P2, P3) appear in the raw material warehouse.
    2.  **Product Workflows**:
        *   **P1/P2**: `RawMaterial -> [AGV] -> StationA -> Conveyor_AB -> StationB -> Conveyor_BC -> StationC -> Conveyor_CQ -> QualityCheck -> [AGV] -> Warehouse`
        *   **P3**: `RawMaterial -> [AGV] -> StationA -> Conveyor_AB -> StationB -> Conveyor_BC -> StationC -> Conveyor_CQ -> [AGV] -> StationB -> Conveyor_BC -> StationC -> Conveyor_CQ -> QualityCheck -> [AGV] -> Warehouse`
    3.  **AGV Battery**: AGVs have a limited battery and will automatically recharge if they lack the power for a task. You can also command them to charge.

    ## KPI Metrics

    Your performance is measured by the following KPIs:

    - **Production Efficiency (40%)**: Order completion rate, production cycle efficiency, equipment utilization.
    - **Quality Costs (30%)**: First-pass yield, production costs (materials, energy, maintenance, scrap).
    - **AGV Efficiency (30%)**: Charging strategy, energy efficiency, AGV utilization.

    ## Commands

    You MUST respond with a JSON command in the following format:

    ```json
    {
      "command_id": "str (optional)",
      "action": "str (see table below)",
      "target": "str (target device ID)",
      "params": {
        "key": "value"
      }
    }
    ```

    ### Supported Actions

    | Action       | Description                  | Target | Example                                                                                             |
    |:-------------|:-----------------------------|:-------|:----------------------------------------------------------------------------------------------------|
    | `move`       | Move AGV to a point          | AGV ID | `{"action": "move", "target": "AGV_1", "params": {"target_point": "P1"}}`                            |
    | `charge`     | Command AGV to charge        | AGV ID | `{"action": "charge", "target": "AGV_1", "params": {"target_level": 80.0}}`                          |
    | `unload`     | Unload product at a station  | AGV ID | `{"action": "unload", "target": "AGV_2", "params": {}}`                                             |
    | `load`       | Load product from a station  | AGV ID | `{"action": "load", "target": "AGV_1", "params": {"product_id": "prod_1_1ee7ce46"}}`                 |
    | `get_result` | Get current factory KPI      | any    | `{"action": "get_result", "target": "factory", "params": {}}`                                       |
    """

    # =============================================================================
    # UTILITY FUNCTIONS
    # =============================================================================

    def safe_async_run(coro, timeout: float = 30.0):
        """Safely run an async coroutine with proper cleanup"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            return loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))
        finally:
            try:
                if not loop.is_closed():
                    loop.close()
            except Exception:
                pass

    def create_mock_llm_response(prompt: str) -> Dict[str, Any]:
        """Generate mock LLM response for testing"""
        actions = ["move", "charge", "load", "unload", "get_result"]
        action = random.choice(actions)
        
        if action == "move":
            targets = ["AGV_1", "AGV_2"]
            points = [f"P{i}" for i in range(10)]
            return {
                "command_id": f"simple_mock_{int(time.time())}_{random.randint(1000, 9999)}",
                "action": "move",
                "target": random.choice(targets),
                "params": {"target_point": random.choice(points)}
            }
        elif action == "charge":
            return {
                "command_id": f"simple_mock_{int(time.time())}_{random.randint(1000, 9999)}",
                "action": "charge",
                "target": random.choice(["AGV_1", "AGV_2"]),
                "params": {"target_level": random.uniform(70, 90)}
            }
        elif action == "load":
            return {
                "command_id": f"simple_mock_{int(time.time())}_{random.randint(1000, 9999)}",
                "action": "load",
                "target": random.choice(["AGV_1", "AGV_2"]),
                "params": {"product_id": f"prod_{random.randint(1000, 9999)}"}
            }
        elif action == "unload":
            return {
                "command_id": f"simple_mock_{int(time.time())}_{random.randint(1000, 9999)}",
                "action": "unload",
                "target": random.choice(["AGV_1", "AGV_2"]),
                "params": {}
            }
        else:
            return {
                "command_id": f"simple_mock_{int(time.time())}_{random.randint(1000, 9999)}",
                "action": "get_result",
                "target": "factory",
                "params": {}
            }

    def create_user_prompt(topic: str, message: dict) -> str:
        """Create user prompt for LLM processing"""
        return f"""
        You are an AI agent controlling a factory production line.
        
        Current factory state:
        {json.dumps(message, indent=2, ensure_ascii=False)}
        
        Based on the current state, decide what action to take next.
        Focus on maximizing KPI scores through efficient AGV utilization.
        
        Respond with a JSON command in the format:
        {{
            "action": "move|charge|load|unload|get_result",
            "target": "device_id", 
            "params": {{...}}
        }}
        """

    # =============================================================================
    # MAIN PROCESSING LOGIC
    # =============================================================================

    try:
        # Only process order-related messages
        if "orders" not in topic:
            return None
        
        # Create user prompt
        prompt = create_user_prompt(topic, message)
        
        # Try to use real LLM if available, otherwise use mock
        api_key = os.getenv("MOONSHOT_API_KEY")
        if api_key:
            try:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(base_url="https://api.moonshot.cn/v1", api_key=api_key)
                
                completion = safe_async_run(
                    client.chat.completions.create(
                        model="kimi-k2-0711-preview",
                        messages=[
                            {"role": "system", "content": SIMPLE_AGENT_PROMPT},
                            {"role": "user", "content": prompt}
                        ],
                        response_format={"type": "json_object"},
                        max_tokens=500,
                        temperature=0.1
                    ),
                    timeout=30.0
                )
                
                if completion and completion.choices:
                    response_content = completion.choices[0].message.content
                    if response_content:
                        command_dict = json.loads(response_content)
                        
                        # Ensure command_id exists
                        if "command_id" not in command_dict:
                            command_dict["command_id"] = f"simple_{int(time.time())}_{random.randint(1000, 9999)}"
                        
                        # Validate required fields
                        if "action" in command_dict and "target" in command_dict:
                            return command_dict
                            
            except Exception as e:
                logger.error(f"LLM processing error: {e}")
        
        # Use mock response as fallback
        return create_mock_llm_response(prompt)
        
    except Exception as e:
        logger.error(f"Error in simple_strategy_function: {e}")
        return None


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    # Test the function
    test_topic = "NLDF_AGENT_TEST/line1/orders"
    test_message = {
        "order_id": "TEST001",
        "product_type": "A", 
        "quantity": 10,
        "priority": "high",
        "timestamp": "2024-01-01T12:00:00Z"
    }
    
    result = agent_strategy_function(test_topic, test_message)
    print("Agent Strategy Function Test Result:")
    print(json.dumps(result, indent=2, ensure_ascii=False))