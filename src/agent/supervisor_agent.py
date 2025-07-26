"""
Supervisor Agent for Factory Control System

Responsibilities:
- Monitor global orders and assign them to production lines
- Track overall factory KPI metrics
- Coordinate between different production lines
- Make high-level strategic decisions
"""

import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

# Using openai-agents library from the project
from agents import Agent, Runner
from pydantic import BaseModel, Field

from .prompts import AgentPrompts


@dataclass
class OrderAssignment:
    """Represents an order assignment to a production line"""

    order_id: str
    line_id: str
    products: List[Dict]
    priority: int
    estimated_completion_time: float


class SupervisorDecision(BaseModel):
    """Model for supervisor agent decisions"""

    action: str = Field(
        description="Action to take: assign_order, analyze_kpi, optimize_factory"
    )
    order_id: Optional[str] = Field(description="Order ID for assignment actions")
    line_id: Optional[str] = Field(description="Target line ID for assignments")
    priority: Optional[int] = Field(
        description="Priority level (1=high, 2=medium, 3=low)"
    )
    reasoning: str = Field(description="Explanation for the decision")


class SupervisorAgent:
    """
    Supervisor Agent manages global factory operations and order allocation
    """

    def __init__(self, llm, factory_state, topic_manager, mqtt_client):
        self.factory_state = factory_state
        self.topic_manager = topic_manager
        self.mqtt_client = mqtt_client
        self.logger = logging.getLogger(f"{self.__class__.__name__}")

        # Agent state
        self.active_assignments: List[OrderAssignment] = []
        self.line_capabilities: Dict[str, Dict] = {}
        self.current_kpi: Dict = {}

        # Initialize openai-agents Agent
        self.agent = Agent(
            name="SupervisorAgent",
            instructions=AgentPrompts.SUPERVISOR,
            model="kimi-k2-0711-preview",  # Using same model as simple_agent
            output_type=SupervisorDecision,
        )

    async def handle_message(self, topic: str, message: Dict):
        """Handle incoming MQTT messages"""
        try:
            if "orders" in topic:
                await self._handle_new_order(message)
            elif "kpi" in topic:
                await self._handle_kpi_update(message)
            elif "result" in topic:
                await self._handle_result_update(message)
            else:
                self.logger.debug(f"Unhandled topic: {topic}")

        except Exception as e:
            self.logger.error(f"Error handling message from {topic}: {e}")

    async def _handle_new_order(self, order: Dict):
        """Process new orders and make assignment decisions"""
        self.logger.info(f"Processing new order: {order}")

        # Create context for the agent
        context = {
            "new_order": order,
            "active_assignments": len(self.active_assignments),
            "line_capabilities": self.line_capabilities,
            "current_kpi": self.current_kpi,
        }

        prompt = f"""
        New order received: {json.dumps(order, indent=2)}
        
        Current factory context:
        - Active assignments: {len(self.active_assignments)}
        - Available lines: {list(self.line_capabilities.keys())}
        - Current KPI metrics: {self.current_kpi}
        
        Please analyze this order and decide:
        1. Which production line should handle this order?
        2. What priority should it have?
        3. Provide reasoning for your decision.
        
        Focus on optimizing overall factory KPIs and load balancing.
        """

        try:
            result = await Runner.run(self.agent, input=prompt)
            if result and result.final_output:
                decision = result.final_output
                await self._execute_supervisor_decision(decision, order)
            else:
                self.logger.error("Agent returned no decision")
                await self._fallback_order_assignment(order)

        except Exception as e:
            self.logger.error(f"Supervisor agent processing failed: {e}")
            await self._fallback_order_assignment(order)

    async def _execute_supervisor_decision(
        self, decision: SupervisorDecision, order: Dict
    ):
        """Execute the decision made by the supervisor agent"""
        if decision.action == "assign_order" and decision.line_id:
            await self._assign_order_to_line(
                order_id=decision.order_id or order.get("order_id", "unknown"),
                line_id=decision.line_id,
                priority=decision.priority or 2,
                order_data=order,
            )
            self.logger.info(f"Supervisor decision: {decision.reasoning}")
        else:
            self.logger.warning(f"Invalid decision action: {decision.action}")
            await self._fallback_order_assignment(order)

    async def _assign_order_to_line(
        self, order_id: str, line_id: str, priority: int, order_data: Dict
    ):
        """Assign an order to a specific production line"""
        try:
            # Create assignment record
            assignment = OrderAssignment(
                order_id=order_id,
                line_id=line_id,
                products=order_data.get("products", []),
                priority=priority,
                estimated_completion_time=0.0,  # TODO: Calculate based on line capacity
            )

            self.active_assignments.append(assignment)

            # Send assignment message to line commander
            assignment_message = {
                "type": "order_assignment",
                "order_id": order_id,
                "products": assignment.products,
                "priority": priority,
                "assigned_by": "supervisor",
                "timestamp": order_data.get("timestamp"),
            }

            # Publish to line's command topic
            command_topic = self.topic_manager.get_agent_command_topic(line_id)
            self.mqtt_client.publish(command_topic, json.dumps(assignment_message))

            self.logger.info(
                f"Assigned order {order_id} to {line_id} with priority {priority}"
            )

        except Exception as e:
            self.logger.error(f"Failed to assign order {order_id}: {e}")

    async def _fallback_order_assignment(self, order: Dict):
        """Fallback order assignment when agent fails"""
        # Simple assignment to line1 (for MVP)
        line_id = "line1"
        order_id = order.get("order_id", f"fallback_{len(self.active_assignments)}")

        await self._assign_order_to_line(
            order_id=order_id,
            line_id=line_id,
            priority=2,  # Medium priority
            order_data=order,
        )

        self.logger.info(f"Fallback: Assigned order {order_id} to {line_id}")

    async def _handle_kpi_update(self, kpi_data: Dict):
        """Process KPI updates"""
        self.current_kpi.update(kpi_data)
        self.logger.info(f"KPI updated: {kpi_data}")

        # Check for critical KPI thresholds
        critical_issues = self._analyze_kpi_thresholds(kpi_data)
        if critical_issues:
            self.logger.warning(f"Critical KPI issues detected: {critical_issues}")
            # TODO: Trigger optimization actions

    def _analyze_kpi_thresholds(self, kpi_data: Dict) -> List[str]:
        """Analyze KPI data for critical thresholds"""
        issues = []

        if kpi_data.get("production_efficiency", 1.0) < 0.6:
            issues.append("Production efficiency critically low")

        if kpi_data.get("first_pass_yield", 1.0) < 0.7:
            issues.append("Quality issues detected")

        if kpi_data.get("agv_utilization", 1.0) < 0.5:
            issues.append("AGV underutilization")

        return issues

    async def _handle_result_update(self, result_data: Dict):
        """Process final result updates"""
        self.logger.info(f"Factory result update: {result_data}")
        # TODO: Store final results for analysis

    def start(self):
        """Start the supervisor agent"""
        self.logger.info(
            "Supervisor Agent started - monitoring global factory operations"
        )

        # Initialize line capabilities for MVP (line1 only)
        self.line_capabilities["line1"] = {
            "supported_products": ["P1", "P2"],  # MVP: P1 and P2 only
            "agv_count": 2,
            "max_concurrent_orders": 3,
            "current_load": 0,
        }

        # TODO: Add line2 and line3 capabilities for full implementation
        # self.line_capabilities["line2"] = {...}
        # self.line_capabilities["line3"] = {...}

    def stop(self):
        """Stop the supervisor agent"""
        self.logger.info("Supervisor Agent stopped")
        # TODO: Cleanup resources, save state, etc.


# Supervisor Agent System Prompt is now managed in prompts.py
