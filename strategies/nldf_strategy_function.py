"""
NLDF Strategy Function - Unified Single Function

This file contains a single comprehensive function that includes all necessary
dependencies and classes for the NLDF (Next-Level Digital Factory) agent strategy.
It follows the same pattern as AgenticFac-SupCon strategies.

Usage:
    from nldf_strategy_function import predict
    results = eval_strategy(predict, simulation_time=300)
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
    NLDF agent strategy function with all dependencies included.
    
    This function contains all necessary classes, prompts, and processing logic
    for the NLDF factory agent strategy. It can be used directly with eval_strategy().
    
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

    NLDF_AGENT_PROMPT = """
    You are an AI agent controlling the Next-Level Digital Factory (NLDF) with the goal of maximizing KPI scores.
    
    ## Factory Configuration
    
    The NLDF consists of multiple production lines with the following structure:
    - Production Lines: line1, line2, line3
    - Each line has stations: StationA, StationB, StationC, QualityCheck
    - Each line has 2 AGVs: AGV_1, AGV_2
    - Raw Material Warehouse and Finished Goods Warehouse
    
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
    
    ## Product Workflows
    
    - **P1/P2**: RawMaterial → [AGV] → StationA → Conveyor_AB → StationB → Conveyor_BC → StationC → Conveyor_CQ → QualityCheck → [AGV] → Warehouse
    - **P3**: RawMaterial → [AGV] → StationA → Conveyor_AB → StationB → Conveyor_BC → StationC → Conveyor_CQ → [AGV] → StationB → Conveyor_BC → StationC → Conveyor_CQ → QualityCheck → [AGV] → Warehouse
    
    ## KPI Metrics
    
    Your performance is measured by:
    - **Production Efficiency (40%)**: Order completion rate, cycle time, equipment utilization
    - **Quality Costs (30%)**: First-pass yield, defect rates, production costs
    - **AGV Efficiency (30%)**: Energy usage, charging strategy, utilization rate
    
    ## MQTT Topics
    
    - Orders: NLDF/line{1-3}/orders
    - Status updates: NLDF/line{1-3}/status
    - AGV updates: NLDF/line{1-3}/agv/{AGV_1,AGV_2}/status
    - Station updates: NLDF/line{1-3}/station/{StationA,StationB,StationC,QualityCheck}/status
    
    ## Available Commands
    
    Respond with JSON commands in the following format:
    ```json
    {
      "command_id": "unique_id",
      "action": "action_type",
      "target": "device_id",
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
    | `load`       | Load product from a station  | AGV ID | `{"action": "load", "target": "AGV_1", "params": {"product_id": "prod_1_abc123"}}`                 |
    | `get_result` | Get current factory KPI      | any    | `{"action": "get_result", "target": "factory", "params": {}}`                                       |
    """

    # =============================================================================
    # UTILITY FUNCTIONS
    # =============================================================================

    async def make_llm_request(prompt):
        """Make LLM request with proper client management"""
        from openai import AsyncOpenAI
        
        api_key = os.getenv("MOONSHOT_API_KEY")
        async with AsyncOpenAI(base_url="https://api.moonshot.cn/v1", api_key=api_key) as client:
            completion = await client.chat.completions.create(
                model="kimi-k2-0711-preview",
                messages=[
                    {"role": "system", "content": NLDF_AGENT_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_tokens=500,
                temperature=0.1
            )
            return completion

    def safe_async_run(coro, timeout: float = 30.0):
        """Safely run an async coroutine with proper cleanup"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            return loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))
        finally:
            try:
                # Cancel all remaining tasks
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                
                # Wait for tasks to complete cancellation
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                
                if not loop.is_closed():
                    loop.close()
            except Exception:
                pass

    def create_mock_llm_response(topic: str, message: dict) -> Dict[str, Any]:
        """Generate intelligent mock LLM response based on message content"""
        
        # Extract line info from topic if available
        line_match = None
        if "line1" in topic:
            line_match = "line1"
        elif "line2" in topic:
            line_match = "line2"
        elif "line3" in topic:
            line_match = "line3"
        
        # Determine AGV targets based on line
        if line_match:
            agv_targets = [f"{line_match}_AGV_1", f"{line_match}_AGV_2"]
        else:
            agv_targets = ["line1_AGV_1", "line1_AGV_2", "line2_AGV_1", "line2_AGV_2", "line3_AGV_1", "line3_AGV_2"]
        
        # Smart action selection based on message content
        if "order" in topic.lower() or "order" in str(message).lower():
            # New order - start production by moving AGV to raw materials
            return {
                "command_id": f"nldf_mock_{int(time.time())}_{random.randint(1000, 9999)}",
                "action": "move",
                "target": random.choice(agv_targets),
                "params": {"target_point": "P0"}  # Raw Material
            }
        elif "agv" in topic.lower():
            # AGV status update - decide next action based on AGV state
            agv_status = message.get("status", "idle")
            battery = message.get("battery_level", 100)
            current_point = message.get("current_point", "P0")
            
            if battery < 30:
                return {
                    "command_id": f"nldf_mock_{int(time.time())}_{random.randint(1000, 9999)}",
                    "action": "charge",
                    "target": message.get("agv_id", random.choice(agv_targets)),
                    "params": {"target_level": 80.0}
                }
            elif agv_status == "idle" and current_point == "P0":
                return {
                    "command_id": f"nldf_mock_{int(time.time())}_{random.randint(1000, 9999)}",
                    "action": "load",
                    "target": message.get("agv_id", random.choice(agv_targets)),
                    "params": {"product_id": f"prod_{random.randint(1000, 9999)}"}
                }
            else:
                # Move to next station in workflow
                next_points = ["P1", "P3", "P5", "P7", "P9"]
                return {
                    "command_id": f"nldf_mock_{int(time.time())}_{random.randint(1000, 9999)}",
                    "action": "move",
                    "target": message.get("agv_id", random.choice(agv_targets)),
                    "params": {"target_point": random.choice(next_points)}
                }
        elif "station" in topic.lower():
            # Station status - might need AGV interaction
            station_status = message.get("status", "idle")
            if station_status == "idle":
                return {
                    "command_id": f"nldf_mock_{int(time.time())}_{random.randint(1000, 9999)}",
                    "action": "move",
                    "target": random.choice(agv_targets),
                    "params": {"target_point": "P1"}  # Move to StationA
                }
        
        # Default fallback
        return {
            "command_id": f"nldf_mock_{int(time.time())}_{random.randint(1000, 9999)}",
            "action": "get_result",
            "target": "factory",
            "params": {}
        }

    def create_user_prompt(topic: str, message: dict) -> str:
        """Create user prompt for LLM processing"""
        return f"""
        You are an AI agent controlling the Next-Level Digital Factory (NLDF).
        
        Current factory state from topic: {topic}
        
        Message data:
        {json.dumps(message, indent=2, ensure_ascii=False)}
        
        Based on the current state, decide what action to take next.
        Focus on maximizing KPI scores through efficient AGV utilization and production optimization.
        
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
        # Debug: Print all received topics and messages
        print(f"🔍 [DEBUG] Received topic: {topic}")
        print(f"🔍 [DEBUG] Message: {json.dumps(message, indent=2)}")
        
        # Process all topics initially to see what we're getting
        # Later we can filter more specifically
        
        # Create user prompt
        prompt = create_user_prompt(topic, message)
        
        # Try to use real LLM if available, otherwise use mock
        api_key = os.getenv("MOONSHOT_API_KEY")
        if api_key:
            try:
                completion = safe_async_run(
                    make_llm_request(prompt),
                    timeout=30.0
                )
                
                if completion and completion.choices:
                    response_content = completion.choices[0].message.content
                    if response_content:
                        command_dict = json.loads(response_content)
                        
                        # Ensure command_id exists
                        if "command_id" not in command_dict:
                            command_dict["command_id"] = f"nldf_{int(time.time())}_{random.randint(1000, 9999)}"
                        
                        # Validate required fields
                        if "action" in command_dict and "target" in command_dict:
                            print(f"🤖 [DEBUG] Generated command by LLM: {json.dumps(command_dict, indent=2)}")
                            return command_dict
                            
            except Exception as e:
                logger.error(f"LLM processing error: {e}")
        
        # Use mock response as fallback
        result = create_mock_llm_response(topic, message)
        print(f"🤖 [DEBUG] Generated command by mock LLM: {json.dumps(result, indent=2)}")
        return result
        
    except Exception as e:
        logger.error(f"Error in NLDF strategy function: {e}")
        return None


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    # Test the function
    test_cases = [
        {
            "topic": "NLDF/line1/orders",
            "message": {
                "order_id": "NLD001",
                "product_type": "P1",
                "quantity": 5,
                "priority": "high",
                "timestamp": "2024-07-25T10:00:00Z"
            }
        },
        {
            "topic": "NLDF/line2/agv/AGV_1/status",
            "message": {
                "agv_id": "AGV_1",
                "status": "idle",
                "battery_level": 75,
                "current_point": "P0"
            }
        },
        {
            "topic": "NLDF/line3/station/StationA/status",
            "message": {
                "station_id": "StationA",
                "status": "idle",
                "buffer": [],
                "current_product": None
            }
        }
    ]
    
    print("🤖 Testing NLDF Strategy Function...")
    for i, test in enumerate(test_cases):
        print(f"\nTest {i+1}: {test['topic']}")
        result = predict(test["topic"], test["message"])
        print(json.dumps(result, indent=2, ensure_ascii=False))