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
    # FACTORY STATE MANAGEMENT (Persistent across calls)
    # =============================================================================
    
    if not hasattr(predict, 'factory_state'):
        predict.factory_state = {
            'agvs': {},
            'stations': {},
            'conveyors': {},
            'warehouse': {},
            'orders': {},
            'alerts': []
        }
    
    if not hasattr(predict, 'command_history'):
        predict.command_history = []
    
    def update_factory_state(topic: str, message: dict):
        """Update persistent factory state based on incoming messages"""
        try:
            if "agv" in topic.lower():
                agv_id = message.get("agv_id") or topic.split("/")[-2]
                predict.factory_state['agvs'][agv_id] = message
                
            elif "station" in topic.lower():
                station_id = topic.split("/")[-2] if "/" in topic else "unknown"
                predict.factory_state['stations'][station_id] = message
                
            elif "conveyor" in topic.lower():
                conveyor_id = topic.split("/")[-2] if "/" in topic else "unknown"
                predict.factory_state['conveyors'][conveyor_id] = message
                
            elif "warehouse" in topic.lower():
                predict.factory_state['warehouse'] = message
                
            elif "order" in topic.lower():
                order_id = message.get("order_id", f"order_{int(time.time())}")
                predict.factory_state['orders'][order_id] = message
                
            elif "alert" in topic.lower():
                predict.factory_state['alerts'].append({
                    'timestamp': time.time(),
                    'data': message
                })
                # Keep only recent alerts
                predict.factory_state['alerts'] = predict.factory_state['alerts'][-10:]
                
        except Exception as e:
            logger.error(f"Error updating factory state: {e}")
    
    def get_factory_context() -> dict:
        """Get current factory context for decision making"""
        return {
            'current_state': predict.factory_state,
            'recent_commands': predict.command_history[-5:],
            'timestamp': time.time()
        }
    
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
    
    | Action       | Description                  | Target Format | Example                                                                                             |
    |:-------------|:-----------------------------|:--------------|:----------------------------------------------------------------------------------------------------|
    | `move`       | Move AGV to a point          | AGV_1 or AGV_2 | `{"action": "move", "target": "AGV_1", "params": {"target_point": "P1"}}`                            |
    | `charge`     | Command AGV to charge        | AGV_1 or AGV_2 | `{"action": "charge", "target": "AGV_1", "params": {"target_level": 80.0}}`                          |
    | `unload`     | Unload product at a station  | AGV_1 or AGV_2 | `{"action": "unload", "target": "AGV_2", "params": {}}`                                             |
    | `load`       | Load product from a station  | AGV_1 or AGV_2 | `{"action": "load", "target": "AGV_1", "params": {"product_id": "prod_1_abc123"}}`                 |
    | `get_result` | Get current factory KPI      | factory        | `{"action": "get_result", "target": "factory", "params": {}}`                                       |
    
    **IMPORTANT**: 
    - Always use simple AGV target format: "AGV_1" or "AGV_2" (NOT "line1_AGV_1" or "line3/AGV_1")
    - The system will automatically add the correct line prefix based on the topic
    - For factory-wide commands, use "factory" as target
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

    def create_intelligent_response(topic: str, message: dict) -> Dict[str, Any]:
        """Generate intelligent response based on NLDF factory logic with full context"""
        
        print(f"🔧 [DEBUG] create_intelligent_response called with topic: {topic}")
        
        # Get current factory context
        factory_context = get_factory_context()
        current_state = factory_context['current_state']
        
        print(f"🔧 [DEBUG] Current state: {current_state}")
        
        # Extract line info from topic - handle both NLDF1 and NLDF formats
        line_match = "line1"  # Default
        for line in ["line1", "line2", "line3"]:
            if line in topic:
                line_match = line
                break
        
        # AGV targets (simple format as used by the factory)
        agv_targets = ["AGV_1", "AGV_2"]
        
        def find_available_agv() -> str:
            """Find the best available AGV for a task"""
            agv_scores = {}
            for agv_id in agv_targets:
                agv_data = current_state['agvs'].get(agv_id, {})
                status = agv_data.get('status', 'idle')
                battery = agv_data.get('battery_level', 100)
                payload = agv_data.get('payload', [])
                
                # Score AGV based on availability and battery
                score = 0
                if status == 'idle' and len(payload) == 0:
                    score += 100
                elif status == 'idle':
                    score += 50
                
                score += battery  # Higher battery = better
                agv_scores[agv_id] = score
            
            # Return AGV with highest score
            return max(agv_scores.items(), key=lambda x: x[1])[0] if agv_scores else agv_targets[0]
        
        def get_agv_status(agv_id: str) -> dict:
            """Get current status of specific AGV"""
            return current_state['agvs'].get(agv_id, {
                'status': 'idle',
                'battery_level': 100,
                'current_point': 'P0',
                'payload': []
            })
        
        def check_urgent_situations() -> Dict[str, Any]:
            """Check for urgent situations that need immediate attention"""
            # Check for critical battery levels
            for agv_id, agv_data in current_state['agvs'].items():
                battery = agv_data.get('battery_level', 100)
                status = agv_data.get('status', 'idle')
                if battery < 15 and status != 'charging':
                    return {
                        "command_id": f"nldf_emergency_charge_{agv_id}_{int(time.time())}",
                        "action": "charge",
                        "target": agv_id,
                        "params": {"target_level": 80.0}
                    }
            
            # Check for blocked stations
            for station_id, station_data in current_state['stations'].items():
                if station_data.get('status') == 'blocked':
                    # Send AGV to investigate/help
                    best_agv = find_available_agv()
                    station_points = {
                        'StationA': 'P1',
                        'StationB': 'P3', 
                        'StationC': 'P5',
                        'QualityCheck': 'P7'
                    }
                    target_point = station_points.get(station_id, 'P1')
                    return {
                        "command_id": f"nldf_blocked_station_{station_id}_{int(time.time())}",
                        "action": "move",
                        "target": best_agv,
                        "params": {"target_point": target_point}
                    }
            
            # Check for recent critical alerts
            recent_alerts = [a for a in current_state['alerts'] if time.time() - a['timestamp'] < 60]
            for alert in recent_alerts:
                alert_data = alert['data']
                alert_type = alert_data.get('alert_type', '')
                if alert_type in ['device_fault', 'emergency_stop']:
                    # Emergency response - move AGVs to safe positions
                    best_agv = find_available_agv()
                    return {
                        "command_id": f"nldf_emergency_alert_{alert_type}_{int(time.time())}",
                        "action": "move",
                        "target": best_agv,
                        "params": {"target_point": "P0"}  # Safe position
                    }
            
            return None
        
        # First check for urgent situations that override normal processing
        urgent_response = check_urgent_situations()
        if urgent_response:
            return urgent_response
        
        # Process different message types with NLDF-like logic
        if "order" in topic.lower():
            print(f"🔧 [DEBUG] Processing order: {message}")
            # New order received - initiate production workflow
            order_id = message.get("order_id", "unknown")
            items = message.get("items", [])
            
            # Find best available AGV for this order
            best_agv = find_available_agv()
            print(f"🔧 [DEBUG] Best AGV: {best_agv}")
            agv_status = get_agv_status(best_agv)
            print(f"🔧 [DEBUG] AGV status: {agv_status}")
            
            # If AGV is already at raw materials and idle, load directly
            if agv_status.get('current_point') == 'P0' and agv_status.get('status') == 'idle':
                return {
                    "command_id": f"nldf_order_load_{order_id}_{int(time.time())}",
                    "action": "load",
                    "target": best_agv,
                    "params": {"product_id": f"prod_{order_id}_{random.randint(1000, 9999)}"}
                }
            else:
                # Move AGV to raw materials for pickup
                return {
                    "command_id": f"nldf_order_move_{order_id}_{int(time.time())}",
                    "action": "move",
                    "target": best_agv,
                    "params": {"target_point": "P0"}  # Raw Material warehouse
                }
            
        elif "agv" in topic.lower():
            # AGV status update - reactive decision making
            agv_id = message.get("agv_id", agv_targets[0])
            status = message.get("status", "idle")
            battery = message.get("battery_level", 100)
            current_point = message.get("current_point", "P0")
            payload = message.get("payload", [])
            
            # Critical battery - immediate charging
            if battery < 20 and status != "charging":
                return {
                    "command_id": f"nldf_critical_battery_{agv_id}_{int(time.time())}",
                    "action": "charge",
                    "target": agv_id,
                    "params": {"target_level": 80.0}
                }
            
            # Low battery but not critical - charge when convenient
            elif battery < 30 and status == "idle":
                return {
                    "command_id": f"nldf_low_battery_{agv_id}_{int(time.time())}",
                    "action": "charge", 
                    "target": agv_id,
                    "params": {"target_level": 80.0}
                }
            
            # AGV is idle and loaded - needs to follow product workflow
            elif status == "idle" and len(payload) > 0:
                # Get product info to determine workflow
                product_info = payload[0] if payload else {}
                product_type = product_info.get('product_type', 'P1')
                
                # Determine next step based on current location and product type
                if current_point == "P0":  # At raw materials with product
                    return {
                        "command_id": f"nldf_to_station_a_{agv_id}_{int(time.time())}",
                        "action": "move",
                        "target": agv_id,
                        "params": {"target_point": "P1"}  # Move to StationA
                    }
                elif current_point == "P1":  # At StationA - unload for processing
                    return {
                        "command_id": f"nldf_unload_station_a_{agv_id}_{int(time.time())}",
                        "action": "unload",
                        "target": agv_id,
                        "params": {}
                    }
                elif current_point in ["P6", "P7"]:  # At quality check area
                    if product_type == "P3" and not product_info.get('double_processed', False):
                        # P3 needs double processing - back to StationB
                        return {
                            "command_id": f"nldf_p3_double_process_{agv_id}_{int(time.time())}",
                            "action": "move",
                            "target": agv_id,
                            "params": {"target_point": "P3"}  # Back to StationB
                        }
                    else:
                        # Normal flow or P3 already double processed - to warehouse
                        return {
                            "command_id": f"nldf_to_warehouse_{agv_id}_{int(time.time())}",
                            "action": "move",
                            "target": agv_id,
                            "params": {"target_point": "P9"}  # Move to warehouse
                        }
                elif current_point == "P9":  # At warehouse - unload finished product
                    return {
                        "command_id": f"nldf_unload_warehouse_{agv_id}_{int(time.time())}",
                        "action": "unload",
                        "target": agv_id,
                        "params": {}
                    }
                else:
                    # Default - move towards warehouse
                    return {
                        "command_id": f"nldf_default_warehouse_{agv_id}_{int(time.time())}",
                        "action": "move",
                        "target": agv_id,
                        "params": {"target_point": "P9"}
                    }
            
            # AGV is idle and empty - look for work
            elif status == "idle" and len(payload) == 0:
                if current_point == "P0":  # At raw materials - load
                    return {
                        "command_id": f"nldf_load_raw_{agv_id}_{int(time.time())}",
                        "action": "load",
                        "target": agv_id,
                        "params": {"product_id": f"prod_{random.randint(1000, 9999)}"}
                    }
                else:
                    # Move to raw materials to pick up work
                    return {
                        "command_id": f"nldf_move_raw_{agv_id}_{int(time.time())}",
                        "action": "move",
                        "target": agv_id,
                        "params": {"target_point": "P0"}
                    }
            
            # AGV moving or working - no immediate action needed
            else:
                return None
                
        elif "station" in topic.lower():
            # Station status update - check for bottlenecks
            station_id = topic.split("/")[-2] if "/" in topic else "unknown"
            status = message.get("status", "idle")
            buffer = message.get("buffer", [])
            
            # Station is blocked - critical issue
            if status == "blocked":
                return {
                    "command_id": f"nldf_station_blocked_{station_id}_{int(time.time())}",
                    "action": "move",
                    "target": agv_targets[0],
                    "params": {"target_point": "P1"}  # Send AGV to investigate
                }
            
            # Station idle with backup - needs pickup
            elif status == "idle" and len(buffer) > 2:
                # Determine pickup point based on station
                pickup_points = {
                    "StationA": "P1",
                    "StationB": "P3", 
                    "StationC": "P5",
                    "QualityCheck": "P7"
                }
                target_point = pickup_points.get(station_id, "P1")
                
                return {
                    "command_id": f"nldf_pickup_{station_id}_{int(time.time())}",
                    "action": "move",
                    "target": agv_targets[1],  # Use second AGV
                    "params": {"target_point": target_point}
                }
            
            # Normal station operation - no action needed
            else:
                return None
                
        elif "conveyor" in topic.lower():
            # Conveyor status - check for blockages
            conveyor_id = topic.split("/")[-2] if "/" in topic else "unknown"
            status = message.get("status", "idle")
            buffer = message.get("buffer", [])
            
            # Conveyor blocked or buffer full
            if status == "blocked" or len(buffer) > 5:
                return {
                    "command_id": f"nldf_conveyor_issue_{conveyor_id}_{int(time.time())}",
                    "action": "move",
                    "target": agv_targets[0],
                    "params": {"target_point": "P2"}  # Send AGV to help
                }
            else:
                return None
                
        elif "alert" in topic.lower():
            # Factory alert - emergency response
            alert_type = message.get("alert_type", "unknown")
            device_id = message.get("device_id", "unknown")
            
            if alert_type in ["device_fault", "emergency_stop"]:
                # Critical alert - stop all AGVs
                return {
                    "command_id": f"nldf_emergency_{alert_type}_{int(time.time())}",
                    "action": "move",
                    "target": agv_targets[0],
                    "params": {"target_point": "P0"}  # Return to safe position
                }
            else:
                return None
        
        # Default - no action needed
        return None

    def post_process_llm_command(command_dict: dict, topic: str) -> dict:
        """Post-process LLM generated command to fix target format and other issues"""
        
        # Extract line info from topic
        line_match = "line1"  # Default
        for line in ["line1", "line2", "line3"]:
            if line in topic:
                line_match = line
                break
        
        # Fix target format - remove line prefix and keep only AGV part
        target = command_dict.get("target", "")
        
        # If target contains line info like "line3/AGV_1", extract just the AGV part
        if "/" in target:
            target_parts = target.split("/")
            if len(target_parts) == 2:
                line_part, agv_part = target_parts
                target = agv_part  # Keep only AGV_1 or AGV_2
        
        # If target has line prefix like "line3_AGV_1", remove the line prefix
        elif "_AGV_" in target:
            agv_part = target.split("_AGV_")
            if len(agv_part) == 2:
                target = f"AGV_{agv_part[1]}"  # Keep only AGV_1 or AGV_2
        
        # If target already in correct format (AGV_1, AGV_2), keep it
        elif target in ["AGV_1", "AGV_2"]:
            target = target  # Already correct
        
        # If target doesn't match expected AGV format, use default
        elif command_dict.get("action") in ["move", "charge", "load", "unload"]:
            if target != "factory":  # Don't change factory target
                target = "AGV_1"  # Default AGV
                print(f"🔧 [DEBUG] Fixed invalid target to: {target}")
        
        # Update the command
        command_dict["target"] = target
        
        # Ensure command_id is properly formatted
        if "command_id" not in command_dict or not command_dict["command_id"]:
            command_dict["command_id"] = f"nldf_{line_match}_{int(time.time())}_{random.randint(1000, 9999)}"
        
        # Validate params
        if "params" not in command_dict:
            command_dict["params"] = {}
        
        print(f"🔧 [DEBUG] Post-processed command: line={line_match} (from topic), target={command_dict['target']}, action={command_dict.get('action')}")
        
        return command_dict

    def create_user_prompt(topic: str, message: dict) -> str:
        """Create user prompt for LLM processing with full factory context"""
        factory_context = get_factory_context()
        
        return f"""
        You are an AI agent controlling the Next-Level Digital Factory (NLDF).
        
        CURRENT EVENT:
        Topic: {topic}
        Message: {json.dumps(message, indent=2, ensure_ascii=False)}
        
        FULL FACTORY STATE:
        {json.dumps(factory_context['current_state'], indent=2, ensure_ascii=False)}
        
        RECENT COMMANDS:
        {json.dumps(factory_context['recent_commands'], indent=2, ensure_ascii=False)}
        
        TASK:
        Based on the current factory state and this new event, decide what action to take next.
        
        Consider:
        1. AGV battery levels and locations
        2. Station statuses and buffer levels  
        3. Product workflows (P1/P2 vs P3)
        4. Order priorities and deadlines
        5. Recent command history to avoid conflicts
        
        Focus on maximizing KPI scores through:
        - Efficient AGV utilization
        - Production optimization
        - Minimizing idle time
        - Preventing bottlenecks
        
        IMPORTANT TARGET FORMAT:
        - For AGV commands: Use "AGV_1" or "AGV_2" (simple format)
        - For factory commands: Use "factory"
        - DO NOT include line prefixes like "line1_" or "line3/"
        
        Respond with a single JSON command or null if no action needed:
        {{
            "command_id": "unique_id",
            "action": "move|charge|load|unload|get_result",
            "target": "AGV_1|AGV_2|factory", 
            "params": {{...}}
        }}
        """

    # =============================================================================
    # MAIN PROCESSING LOGIC
    # =============================================================================

    try:
        # Update factory state with new message
        update_factory_state(topic, message)
        
        # Debug: Print all received topics and messages
        print(f"🔍 [DEBUG] Received topic: {topic}")
        print(f"🔍 [DEBUG] Message: {json.dumps(message, indent=2)}")
        
        # Create user prompt with full context
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
                        
                        # Post-process the LLM response to fix target format
                        command_dict = post_process_llm_command(command_dict, topic)
                        
                        # Validate required fields
                        if "action" in command_dict and "target" in command_dict:
                            # Add to command history
                            predict.command_history.append({
                                'timestamp': time.time(),
                                'command': command_dict,
                                'topic': topic,
                                'source': 'llm'
                            })
                            print(f"🤖 [DEBUG] Generated command by LLM: {json.dumps(command_dict, indent=2)}")
                            return command_dict
                            
            except Exception as e:
                logger.error(f"LLM processing error: {e}")
        
        # Use intelligent response as fallback
        result = create_intelligent_response(topic, message)
        if result:
            # Add to command history
            predict.command_history.append({
                'timestamp': time.time(),
                'command': result,
                'topic': topic,
                'source': 'intelligent_logic'
            })
            print(f"🤖 [DEBUG] Generated command by intelligent logic: {json.dumps(result, indent=2)}")
            return result
        else:
            print(f"🤖 [DEBUG] No action needed for topic: {topic}")
            return None
        
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
        print(json.dumps(result, indent=2, ensure_ascii=False))