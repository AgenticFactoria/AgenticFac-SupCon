"""
Multi-Agent Strategy - Unified Single Function

This file contains a single comprehensive function that includes all necessary
dependencies and classes for the multi-agent strategy. It can be used
directly with evaluate(func) without any external dependencies.

Usage:
    from multi_strategy_function import agent_strategy_function
    results = eval_strategy(agent_strategy_function, simulation_time=300)
"""

import json
import asyncio
import logging
import os
import random
import threading
import time
from typing import Dict, Any, Optional, List
from enum import Enum

# Configure logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def predict(topic: str, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Multi-agent strategy function with all dependencies included.
    
    This function contains all necessary classes, prompts, and processing logic
    for the multi-agent strategy. It can be used directly with eval_strategy().
    
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

    SUPERVISOR_PROMPT = """
    You are a Supervisor Agent controlling a smart factory with multiple production lines.

    Your primary responsibility is to optimize overall factory performance by making strategic decisions about order allocation and resource management.

    FACTORY CONFIGURATION:
    - 3 production lines (currently MVP focuses on line1)
    - Each line can produce products P1 and P2 (full system will support P3)
    - Each line has 2 AGVs and stations: A, B, C, Quality Check
    - Product workflows:
      * P1/P2: RawMaterial → [AGV] → StationA → Conveyor_AB → StationB → Conveyor_BC → StationC → Conveyor_CQ → QualityCheck → [AGV] → Warehouse

    KEY PERFORMANCE INDICATORS (TARGET OPTIMIZATION):
    - Production Efficiency (40%): Order completion rate, cycle efficiency, equipment utilization
    - Quality Costs (30%): First-pass yield, production costs
    - AGV Efficiency (30%): Charging strategy, energy efficiency, utilization

    DECISION MAKING PRINCIPLES:
    1. Prioritize orders based on deadlines and customer importance
    2. Balance workload across available production lines
    3. Consider current line capacities and AGV availability
    4. Minimize transportation distances and energy consumption
    5. Ensure quality standards are maintained

    When assigning orders:
    - Choose the line with lowest current load for load balancing
    - Consider product type compatibility
    - Factor in AGV battery levels and charging needs
    - Set appropriate priority levels (1=urgent, 2=normal, 3=low)
    """

    LINE_COMMANDER_PROMPT = """
    You are a Line Commander Agent controlling production line {line_id} in a smart factory.

    Your responsibilities:
    1. Control 2 AGVs (AGV_1, AGV_2) on your production line
    2. Execute orders assigned by the Supervisor Agent
    3. Optimize local production efficiency and AGV utilization
    4. Monitor equipment status and handle alerts

    PRODUCTION LINE LAYOUT:
    Path Points:
    - P0: RawMaterial (pickup point)
    - P1: StationA (first processing station)
    - P2: Conveyor_AB (between A and B)
    - P3: StationB (second processing station)
    - P4: Conveyor_BC (between B and C)
    - P5: StationC (final processing station)
    - P6: Conveyor_CQ (to quality check)
    - P7: QualityCheck (quality inspection)
    - P8: QualityCheck (alternate quality point)
    - P9: Warehouse (final delivery)

    PRODUCT WORKFLOW (P1, P2):
    RawMaterial → [AGV transport] → StationA → Conveyor_AB → StationB → Conveyor_BC → StationC → Conveyor_CQ → QualityCheck → [AGV transport] → Warehouse

    AGV OPERATIONS:
    - Move between path points (P0-P9)
    - Load products from stations/warehouse
    - Unload products to stations/warehouse  
    - Charge when battery gets low
    - Monitor battery levels and plan charging strategically

    DECISION MAKING PRIORITIES:
    1. Execute assigned orders efficiently
    2. Maintain adequate battery levels (>20% minimum)
    3. Minimize idle time and maximize utilization
    4. Coordinate between AGVs to avoid conflicts
    5. Respond to equipment alerts and adapt plans
    """

    # =============================================================================
    # MULTI-AGENT STRATEGY IMPLEMENTATION
    # =============================================================================

    class MultiAgentDecisionEngine:
        """Core multi-agent decision engine"""
        
        def __init__(self):
            self.decision_count = 0
            self.last_decision_time = 0
            self.agv_states = {
                "AGV_1": {"status": "idle", "location": "P0", "battery": 100},
                "AGV_2": {"status": "idle", "location": "P0", "battery": 100}
            }
            self.station_states = {
                "StationA": {"status": "idle", "queue": []},
                "StationB": {"status": "idle", "queue": []},
                "StationC": {"status": "idle", "queue": []},
                "QualityCheck": {"status": "idle", "queue": []}
            }

        def analyze_factory_state(self, message: dict) -> Dict[str, Any]:
            """Analyze current factory state"""
            state = {
                "agv_status": {},
                "station_status": {},
                "orders": [],
                "alerts": []
            }
            
            # Extract AGV status
            if "agv" in str(message).lower():
                for agv_id in ["AGV_1", "AGV_2"]:
                    state["agv_status"][agv_id] = {
                        "status": message.get("status", "idle"),
                        "battery": message.get("battery_level", 100),
                        "location": message.get("current_point", "P0")
                    }
            
            # Extract station status
            for station in ["StationA", "StationB", "StationC", "QualityCheck"]:
                if station.lower() in str(message).lower():
                    state["station_status"][station] = {
                        "status": message.get("status", "idle"),
                        "queue_length": len(message.get("buffer", [])),
                        "current_product": message.get("product_id")
                    }
            
            # Extract orders
            if "order" in str(message).lower():
                state["orders"].append({
                    "id": message.get("order_id", "unknown"),
                    "type": message.get("product_type", "P1"),
                    "priority": message.get("priority", "medium")
                })
            
            return state

        def make_supervisor_decision(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            """Make supervisor-level decision for order allocation"""
            if state["orders"]:
                # Simple order allocation logic
                order = state["orders"][0]
                return {
                    "command_id": f"supervisor_assign_{int(time.time())}_{random.randint(1000, 9999)}",
                    "action": "assign_order",
                    "target": "line1",
                    "params": {
                        "order_id": order["id"],
                        "priority": 2 if order["priority"] == "medium" else (1 if order["priority"] == "high" else 3)
                    }
                }
            return None

        def make_line_commander_decision(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            """Make line commander decision for AGV coordination"""
            
            # Check for idle AGVs
            idle_agvs = [agv_id for agv_id, info in state["agv_status"].items() 
                        if info["status"] == "idle"]
            
            if idle_agvs:
                agv_id = random.choice(idle_agvs)
                
                # Find stations that need products
                for station, info in state["station_status"].items():
                    if info["status"] == "idle" and info["queue_length"] == 0:
                        return {
                            "command_id": f"line_cmd_{station}_{int(time.time())}_{random.randint(1000, 9999)}",
                            "action": "move",
                            "target": agv_id,
                            "params": {"target_point": "P0"}
                        }
            
            return None

        def make_coordination_decision(self, topic: str, message: dict) -> Optional[Dict[str, Any]]:
            """Make coordination decision based on topic and message"""
            
            # Station-related decisions
            if "station" in topic and message.get("status") == "idle":
                station_id = message.get("station_id", "")
                if message.get("product_id"):
                    return {
                        "command_id": f"multi_process_{station_id}_{int(time.time())}_{random.randint(1000, 9999)}",
                        "action": "process",
                        "target": station_id,
                        "params": {"product_id": message["product_id"]}
                    }
                else:
                    return {
                        "command_id": f"multi_request_{station_id}_{int(time.time())}_{random.randint(1000, 9999)}",
                        "action": "load",
                        "target": station_id,
                        "params": {}
                    }
            
            # AGV-related decisions
            elif "agv" in topic and message.get("status") == "idle":
                agv_id = message.get("agv_id", "")
                battery = message.get("battery_level", 100)
                
                if battery < 20:
                    return {
                        "command_id": f"multi_charge_{agv_id}_{int(time.time())}_{random.randint(1000, 9999)}",
                        "action": "charge",
                        "target": agv_id,
                        "params": {"target_level": 80.0}
                    }
                else:
                    return {
                        "command_id": f"multi_move_{agv_id}_{int(time.time())}_{random.randint(1000, 9999)}",
                        "action": "move",
                        "target": agv_id,
                        "params": {"target_point": "P0"}
                    }
            
            # Order-related decisions
            elif "orders" in topic:
                return {
                    "command_id": f"multi_order_{int(time.time())}_{random.randint(1000, 9999)}",
                    "action": "get_result",
                    "target": "factory",
                    "params": {}
                }
            
            return None

    # =============================================================================
    # MAIN PROCESSING LOGIC
    # =============================================================================

    try:
        # Initialize decision engine
        engine = MultiAgentDecisionEngine()
        engine.decision_count += 1
        
        # Analyze factory state
        state = engine.analyze_factory_state(message)
        
        # Make decision based on topic and message
        if "orders" in topic:
            # Supervisor-level decision for new orders
            return engine.make_supervisor_decision(state)
        elif "station" in topic:
            # Line commander decision for station events
            return engine.make_line_commander_decision(state)
        elif "agv" in topic:
            # AGV coordination decision
            return engine.make_coordination_decision(topic, message)
        else:
            # General coordination decision
            return engine.make_coordination_decision(topic, message)
        
    except Exception as e:
        logger.error(f"Error in multi_strategy_function: {e}")
        
        # Fallback rule-based decision
        return {
            "command_id": f"multi_fallback_{int(time.time())}_{random.randint(1000, 9999)}",
            "action": "get_result",
            "target": "factory",
            "params": {}
        }


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    # Test the function
    test_cases = [
        {
            "topic": "NLDF_MULTI_EVAL/line1/orders",
            "message": {
                "order_id": "TEST001",
                "product_type": "A",
                "quantity": 10,
                "priority": "high"
            }
        },
        {
            "topic": "NLDF_MULTI_EVAL/line1/station/StationA/status",
            "message": {
                "station_id": "StationA",
                "status": "idle",
                "product_id": None,
                "buffer": []
            }
        },
        {
            "topic": "NLDF_MULTI_EVAL/line1/agv/AGV_1/status",
            "message": {
                "agv_id": "AGV_1",
                "status": "idle",
                "battery_level": 85,
                "current_point": "P0"
            }
        }
    ]
    
    print("🤖 Testing Multi-Agent Strategy Function...")
    for i, test in enumerate(test_cases):
        print(f"\nTest {i+1}: {test['topic']}")
        result = agent_strategy_function(test["topic"], test["message"])
        print(json.dumps(result, indent=2, ensure_ascii=False))