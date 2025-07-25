"""
Line Commander Agent for Factory Control System

Responsibilities:
- Control AGVs on a specific production line
- Monitor line-specific equipment status
- Execute orders assigned by Supervisor Agent
- Optimize local production efficiency
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

# Using openai-agents library from the project
from agents import Agent, AgentOutputSchema, Runner
from pydantic import BaseModel, Field

from .prompts import AgentPrompts


class AGVTask(Enum):
    IDLE = "idle"
    MOVING = "moving"
    LOADING = "loading"
    UNLOADING = "unloading"
    CHARGING = "charging"


@dataclass
class AGVStatus:
    """Represents the status of an AGV"""

    agv_id: str
    current_position: str
    battery_level: float
    current_task: AGVTask
    cargo: Optional[str] = None


@dataclass
class LineOrder:
    """Represents an order assigned to this production line"""

    order_id: str
    products: List[Dict]
    priority: int
    status: str = "pending"  # pending, in_progress, completed
    assigned_agvs: Optional[List[str]] = None

    def __post_init__(self):
        if self.assigned_agvs is None:
            self.assigned_agvs = []


class LineCommandDecision(BaseModel):
    """Model for line commander agent decisions"""

    action: str = Field(description="AGV action: move, load, unload, charge")
    target_agv: str = Field(description="Target AGV ID")
    target_point: Optional[str] = Field(description="Target point for move action")
    product_id: Optional[str] = Field(description="Product ID for load action")
    target_level: Optional[float] = Field(
        description="Target battery level for charge action"
    )
    reasoning: str = Field(description="Explanation for the decision")


class LineCommanderAgent:
    """
    Line Commander Agent manages a specific production line
    """

    def __init__(self, line_id, llm, factory_state, topic_manager, mqtt_client):
        self.line_id = line_id
        self.factory_state = factory_state
        self.topic_manager = topic_manager
        self.mqtt_client = mqtt_client
        self.logger = logging.getLogger(f"{self.__class__.__name__}_{line_id}")

        # Line state
        self.agv_status: Dict[str, AGVStatus] = {}
        self.current_orders: List[LineOrder] = []
        self.station_status: Dict[str, Dict] = {}
        self.conveyor_status: Dict[str, Dict] = {}
        self.line_kpi: Dict = {}

        # Initialize openai-agents Agent
        self.agent = Agent(
            name=f"LineCommander_{line_id}",
            instructions=AgentPrompts.get_line_commander_prompt(line_id),
            model="kimi-k2-0711-preview",
            output_type=AgentOutputSchema(
                LineCommandDecision, strict_json_schema=False
            ),
        )

        # AGV task queue
        self.task_queue: List[Dict] = []

    def start(self):
        """Start the line commander agent"""
        self.logger.info(f"Line Commander Agent for {self.line_id} started")
        self._setup_line_subscriptions()
        self._initialize_agv_status()

    def stop(self):
        """Stop the line commander agent"""
        self.logger.info(f"Line Commander Agent for {self.line_id} stopped")

    def _setup_line_subscriptions(self):
        """Setup MQTT subscriptions for this production line"""
        root_topic = self.topic_manager.root
        line_id = self.line_id

        # Subscribe to line-specific topics
        topics = [
            f"{root_topic}/{line_id}/station/+/status",
            f"{root_topic}/{line_id}/agv/+/status",
            f"{root_topic}/{line_id}/conveyor/+/status",
            f"{root_topic}/{line_id}/alerts",
            f"{root_topic}/response/{line_id}",
        ]

        for topic in topics:
            self.mqtt_client.subscribe(topic, self._on_line_message)

    def _initialize_agv_status(self):
        """Initialize AGV status tracking for this line"""
        # For MVP, each line has 2 AGVs
        for i in range(1, 3):  # AGV_1, AGV_2
            agv_id = f"AGV_{i}"
            self.agv_status[agv_id] = AGVStatus(
                agv_id=agv_id,
                current_position="P0",  # Start at raw material
                battery_level=100.0,
                current_task=AGVTask.IDLE,
            )

    def _on_line_message(self, topic: str, payload: bytes):
        """Handle line-specific messages"""
        try:
            message = json.loads(payload.decode())
            self.logger.info(f"Line {self.line_id} received: {topic}")

            # Route messages to appropriate handlers
            if "/agv/" in topic:
                asyncio.create_task(self._handle_agv_status(message, topic))
            elif "/station/" in topic:
                asyncio.create_task(self._handle_station_status(message, topic))
            elif "/conveyor/" in topic:
                asyncio.create_task(self._handle_conveyor_status(message, topic))
            elif "/alerts" in topic:
                asyncio.create_task(self._handle_alert(message))
            elif "/response/" in topic:
                asyncio.create_task(self._handle_command_response(message))
            elif message.get("type") == "order_assignment":
                asyncio.create_task(self._handle_order_assignment(message))

        except Exception as e:
            self.logger.error(f"Error handling line message: {e}")

    async def _handle_agv_status(self, status: Dict, topic: str):
        """Handle AGV status updates"""
        agv_id = self._extract_device_id(topic)
        if agv_id and agv_id in self.agv_status:
            # Update AGV status
            agv = self.agv_status[agv_id]
            agv.current_position = status.get("current_position", agv.current_position)
            agv.battery_level = status.get("battery_level", agv.battery_level)
            agv.cargo = status.get("cargo")

            # Update task status
            task_mapping = {
                "IDLE": AGVTask.IDLE,
                "MOVING": AGVTask.MOVING,
                "LOADING": AGVTask.LOADING,
                "UNLOADING": AGVTask.UNLOADING,
                "CHARGING": AGVTask.CHARGING,
            }
            agv.current_task = task_mapping.get(
                status.get("status", "IDLE"), AGVTask.IDLE
            )

            self.logger.debug(
                f"Updated {agv_id}: pos={agv.current_position}, battery={agv.battery_level}%, task={agv.current_task}"
            )

            # Trigger decision making if AGV becomes idle
            if agv.current_task == AGVTask.IDLE:
                await self._make_agv_decision(agv_id)

    async def _handle_station_status(self, status: Dict, topic: str):
        """Handle station status updates"""
        station_id = self._extract_device_id(topic)
        if station_id:
            self.station_status[station_id] = status
            self.logger.debug(f"Station {station_id} status updated")

    async def _handle_conveyor_status(self, status: Dict, topic: str):
        """Handle conveyor status updates"""
        conveyor_id = self._extract_device_id(topic)
        if conveyor_id:
            self.conveyor_status[conveyor_id] = status
            self.logger.debug(f"Conveyor {conveyor_id} status updated")

    async def _handle_alert(self, alert: Dict):
        """Handle equipment alerts"""
        self.logger.warning(f"Line {self.line_id} alert: {alert}")
        # TODO: Implement alert response logic

    async def _handle_command_response(self, response: Dict):
        """Handle responses to commands sent"""
        self.logger.info(f"Command response: {response}")
        # TODO: Update task status based on response

    async def _handle_order_assignment(self, assignment: Dict):
        """Handle new order assignment from supervisor"""
        self.logger.info(f"Received order assignment: {assignment}")

        order = LineOrder(
            order_id=assignment["order_id"],
            products=assignment["products"],
            priority=assignment["priority"],
        )

        self.current_orders.append(order)

        # Start processing the order
        await self._process_new_order(order)

    async def _process_new_order(self, order: LineOrder):
        """Process a new order assignment"""
        self.logger.info(
            f"Processing order {order.order_id} with {len(order.products)} products"
        )

        # For each product in the order, plan AGV tasks
        for product in order.products:
            await self._plan_product_workflow(product, order)

    async def _plan_product_workflow(self, product: Dict, order: LineOrder):
        """Plan the workflow for a specific product"""
        product_id = product.get("id", "unknown")
        product_type = product.get("type", "P1")

        self.logger.info(
            f"Planning workflow for product {product_id} (type: {product_type})"
        )

        # For P1/P2: RawMaterial → [AGV] → StationA → Conveyor → StationB → Conveyor → StationC → Conveyor → QualityCheck → [AGV] → Warehouse
        # AGV tasks: 1) Load from RawMaterial, 2) Transport to StationA, 3) Pick up from QualityCheck, 4) Transport to Warehouse

        # Task 1: Send AGV to pick up product from raw material
        await self._assign_agv_task(
            {
                "type": "pickup_raw_material",
                "product_id": product_id,
                "order_id": order.order_id,
                "priority": order.priority,
            }
        )

    async def _assign_agv_task(self, task: Dict):
        """Assign a task to the best available AGV"""
        # Find best AGV for the task
        best_agv = self._select_best_agv(task)
        if best_agv:
            task["assigned_agv"] = best_agv
            self.task_queue.append(task)
            await self._execute_agv_task(task)
        else:
            self.logger.warning(f"No available AGV for task: {task}")
            # Queue the task for later
            self.task_queue.append(task)

    def _select_best_agv(self, task: Dict) -> Optional[str]:
        """Select the best AGV for a given task"""
        available_agvs = [
            agv_id
            for agv_id, agv in self.agv_status.items()
            if agv.current_task == AGVTask.IDLE and agv.battery_level > 20.0
        ]

        if not available_agvs:
            return None

        # For now, simple selection - choose first available
        # TODO: Implement more sophisticated selection based on position, battery, etc.
        return available_agvs[0]

    async def _execute_agv_task(self, task: Dict):
        """Execute a specific AGV task"""
        agv_id = task["assigned_agv"]
        task_type = task["type"]

        if task_type == "pickup_raw_material":
            # Move AGV to raw material, then load product
            await self._send_agv_command(agv_id, "move", {"target_point": "P0"})
            # Note: Loading command will be sent after AGV reaches P0
        elif task_type == "deliver_to_warehouse":
            # Move AGV to warehouse, then unload
            await self._send_agv_command(agv_id, "move", {"target_point": "P9"})

    async def _make_agv_decision(self, agv_id: str):
        """Make intelligent decisions about what an idle AGV should do"""
        agv = self.agv_status[agv_id]

        # Check if there are pending tasks
        pending_tasks = [
            task for task in self.task_queue if task.get("assigned_agv") == agv_id
        ]
        if pending_tasks:
            await self._continue_task_sequence(agv_id, pending_tasks[0])
            return

        # Check if battery is low
        if agv.battery_level < 30.0:
            await self._send_agv_command(agv_id, "charge", {"target_level": 80.0})
            return

        # Use AI agent to make decision
        await self._ai_assisted_decision(agv_id)

    async def _ai_assisted_decision(self, agv_id: str):
        """Use AI agent to make decisions about AGV actions"""
        agv = self.agv_status[agv_id]

        context = {
            "agv_status": {
                "id": agv.agv_id,
                "position": agv.current_position,
                "battery": agv.battery_level,
                "cargo": agv.cargo,
            },
            "pending_orders": [
                {"order_id": o.order_id, "priority": o.priority, "status": o.status}
                for o in self.current_orders
                if o.status != "completed"
            ],
            "station_status": self.station_status,
            "other_agvs": {
                aid: {"position": a.current_position, "task": a.current_task.value}
                for aid, a in self.agv_status.items()
                if aid != agv_id
            },
        }

        prompt = f"""
        AGV {agv_id} is now idle and needs a task assignment.
        
        Current situation:
        {json.dumps(context, indent=2)}
        
        Please decide the next best action for this AGV to optimize production efficiency.
        Consider:
        1. Pending orders that need attention
        2. Station readiness for pickup/delivery
        3. Battery level and charging needs
        4. Coordination with other AGVs
        5. Product workflow requirements (P1/P2: RawMaterial → StationA → ... → QualityCheck → Warehouse)
        
        Choose the most appropriate action and provide reasoning.
        """

        try:
            result = await Runner.run(self.agent, input=prompt)
            if result and result.final_output:
                decision = result.final_output
                await self._execute_ai_decision(decision, agv_id)
            else:
                self.logger.error(f"Agent returned no decision for {agv_id}")

        except Exception as e:
            self.logger.error(f"AI decision failed for {agv_id}: {e}")

    async def _execute_ai_decision(self, decision: LineCommandDecision, agv_id: str):
        """Execute the AI agent's decision"""
        if decision.target_agv != agv_id:
            self.logger.warning(
                f"Decision target mismatch: expected {agv_id}, got {decision.target_agv}"
            )
            return

        self.logger.info(
            f"AI Decision for {agv_id}: {decision.action} - {decision.reasoning}"
        )

        if decision.action == "move":
            await self._send_agv_command(
                agv_id, "move", {"target_point": decision.target_point}
            )
        elif decision.action == "load":
            params = {}
            if decision.product_id:
                params["product_id"] = decision.product_id
            await self._send_agv_command(agv_id, "load", params)
        elif decision.action == "unload":
            await self._send_agv_command(agv_id, "unload", {})
        elif decision.action == "charge":
            params = {"target_level": decision.target_level or 80.0}
            await self._send_agv_command(agv_id, "charge", params)

    async def _send_agv_command(self, agv_id: str, action: str, params: Dict):
        """Send a command to an AGV"""
        command = {
            "command_id": f"{self.line_id}_{agv_id}_{action}_{len(self.task_queue)}",
            "action": action,
            "target": agv_id,
            "params": params,
        }

        command_topic = self.topic_manager.get_agent_command_topic(self.line_id)
        self.mqtt_client.publish(command_topic, json.dumps(command))

        self.logger.info(f"Sent command to {agv_id}: {action} with params {params}")

    async def _continue_task_sequence(self, agv_id: str, task: Dict):
        """Continue a multi-step task sequence"""
        # TODO: Implement task sequence logic based on current AGV position and task state
        pass

    def _extract_device_id(self, topic: str) -> Optional[str]:
        """Extract device ID from MQTT topic"""
        parts = topic.split("/")
        if len(parts) >= 4:
            return parts[-2]  # Device ID is typically the second-to-last part
        return None


# Line Commander Agent System Prompt is now managed in prompts.py
