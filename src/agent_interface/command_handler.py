# src/agent_interface/command_handler.py
import json
import logging
from typing import Any, Dict, Optional

from config.schemas import AgentCommand, SystemResponse
from config.topics import AGENT_COMMANDS_TOPIC, AGENT_RESPONSES_TOPIC
from src.utils.mqtt_client import MQTTClient

logger = logging.getLogger(__name__)


class CommandHandler:
    """
    Handles MQTT commands received from agents and translates them
    into method calls on the factory simulation.

    This is the bridge between the external MQTT interface and the internal simulation.
    """

    def __init__(self, factory, mqtt_client: MQTTClient):
        """
        Args:
            factory: The Factory instance to send commands to.
            mqtt_client: The MQTT client to subscribe to agent commands.
        """
        self.factory = factory
        self.mqtt_client = mqtt_client

        # Subscribe to agent commands
        self.mqtt_client.subscribe(AGENT_COMMANDS_TOPIC, self._handle_command_message)
        logger.info(
            f"CommandHandler initialized and subscribed to {AGENT_COMMANDS_TOPIC}"
        )

    def _handle_command_message(self, topic: str, payload: bytes):
        """
        Callback for incoming MQTT command messages.
        Parses the JSON and validates it against the AgentCommand schema.
        """
        try:
            # Parse JSON payload
            command_data = json.loads(payload.decode("utf-8"))

            try:
                # Validate using Pydantic schema
                command = AgentCommand.model_validate(command_data)
            except Exception as e:
                msg = f"Failed to validate command: {e}"
                logger.error(msg)
                response_payload = SystemResponse(
                    timestamp=self.factory.env.now,
                    response=msg,
                    command_id=command_data.get("command_id"),
                ).model_dump_json()
                self.mqtt_client.publish(AGENT_RESPONSES_TOPIC, response_payload)
                return

            logger.debug(
                f"Received valid command: {command.action} for {command.target}"
            )

            # Route the command to the appropriate handler
            self._execute_command(command)

        except Exception as e:
            msg = f"Failed to process command: {e}"
            logger.error(msg)
            response_payload = SystemResponse(
                timestamp=self.factory.env.now,
                command_id=command_data.get("command_id"),
                response=msg,
            ).model_dump_json()
            self.mqtt_client.publish(AGENT_RESPONSES_TOPIC, response_payload)

    def _execute_command(self, command: AgentCommand):
        """
        Executes a validated command by calling the appropriate factory method.
        """
        action = command.action
        params = command.params
        target = command.target
        command_id = command.command_id
        try:
            if action == "test":
                self._handle_test_command(target, params, command_id)
            elif action == "move":
                self._handle_move_agv(target, params, command_id)
            elif action == "load":
                self._handle_load_agv(target, params, command_id)
            elif action == "unload":
                self._handle_unload_agv(target, params, command_id)
            elif action == "charge":
                self._handle_charge_agv(target, params, command_id)
            elif action == "agv_action_sequence":
                self._handle_agv_action_sequence(target, params)
            elif action == "request_maintenance":
                self._handle_request_maintenance(target, params)
            elif action == "inspect_device":
                self._handle_inspect_device(target, params)
            elif action == "skip_repair_time":
                self._handle_skip_repair_time(target, params)
            elif action == "get_available_devices":
                self._handle_get_available_devices(target, params)
            elif action == "emergency_stop":
                self._handle_emergency_stop(target, params)
            elif action == "adjust_priority":
                self._handle_adjust_priority(target, params)
            elif action == "reroute_order":
                self._handle_reroute_order(target, params)
            else:
                logger.warning(f"Unknown action: {action}")

        except Exception as e:
            logger.error(f"Failed to execute command {action}: {e}")

    def _handle_test_command(
        self, target: str, params: Dict[str, Any], command_id: Optional[str] = None
    ):
        """Handle test MQTT commands."""
        msg = (
            f"Received MQTT test command to {target} with params: {json.dumps(params)}"
        )
        logger.debug(msg)
        payload = SystemResponse(
            timestamp=self.factory.env.now, command_id=command_id, response=msg
        ).model_dump_json()
        self.mqtt_client.publish(AGENT_RESPONSES_TOPIC, payload)
        return True

    def _handle_move_agv(
        self, agv_id: str, params: Dict[str, Any], command_id: Optional[str] = None
    ):
        """Handle AGV movement commands.
        params: {target_point: str}
        """
        target_point = params.get("target_point")
        if not target_point:
            msg = "move_agv command missing 'target_point' parameter"
            logger.error(msg)
            self.mqtt_client.publish(
                AGENT_RESPONSES_TOPIC,
                SystemResponse(
                    timestamp=self.factory.env.now, command_id=command_id, response=msg
                ).model_dump_json(),
            )
            return

        if agv_id not in self.factory.agvs:
            msg = f"AGV {agv_id} not found in factory"
            logger.error(msg)
            self.mqtt_client.publish(
                AGENT_RESPONSES_TOPIC,
                SystemResponse(
                    timestamp=self.factory.env.now, command_id=command_id, response=msg
                ).model_dump_json(),
            )
            return

        agv = self.factory.agvs[agv_id]

        logger.info(f"Moving {agv_id} from {agv.current_point} to {target_point}")

        def move_process():
            success, message = yield from agv.move_to(target_point)
            self.mqtt_client.publish(
                AGENT_RESPONSES_TOPIC,
                SystemResponse(
                    timestamp=self.factory.env.now,
                    command_id=command_id,
                    response=message,
                ).model_dump_json(),
            )
            return success, message

        self.factory.env.process(move_process())

    def _handle_load_agv(
        self, agv_id: str, params: Dict[str, Any], command_id: Optional[str] = None
    ):
        """Handle AGV load commands.
        params: {device_id: str, buffer_type: str}
        """
        device_id = params.get("device_id")
        buffer_type = params.get("buffer_type")
        product_id = params.get("product_id", None)

        if not device_id:
            msg = "load_agv command missing 'device_id' parameter"
            logger.error(msg)
            self.mqtt_client.publish(
                AGENT_RESPONSES_TOPIC,
                SystemResponse(
                    timestamp=self.factory.env.now, command_id=command_id, response=msg
                ).model_dump_json(),
            )
            return
        if agv_id not in self.factory.agvs:
            msg = f"AGV {agv_id} not found in factory"
            logger.error(msg)
            self.mqtt_client.publish(
                AGENT_RESPONSES_TOPIC,
                SystemResponse(
                    timestamp=self.factory.env.now,
                    command_id=command_id,
                    response=f"AGV {agv_id} not found in factory",
                ).model_dump_json(),
            )
            return
        agv = self.factory.agvs[agv_id]
        device = self.factory.all_devices.get(device_id)
        if not device:
            msg = f"Device {device_id} not found in factory"
            logger.error(msg)
            self.mqtt_client.publish(
                AGENT_RESPONSES_TOPIC,
                SystemResponse(
                    timestamp=self.factory.env.now,
                    command_id=command_id,
                    response=f"Device {device_id} not found in factory",
                ).model_dump_json(),
            )
            return
        logger.info(
            f"AGV {agv_id} loading from {device_id} with buffer_type {buffer_type}"
        )

        def load_process():
            success, message, _ = yield from agv.load_from(
                device, buffer_type, product_id
            )
            self.mqtt_client.publish(
                AGENT_RESPONSES_TOPIC,
                SystemResponse(
                    timestamp=self.factory.env.now,
                    command_id=command_id,
                    response=message,
                ).model_dump_json(),
            )
            return success, message

        self.factory.env.process(load_process())

    def _handle_unload_agv(
        self, agv_id: str, params: Dict[str, Any], command_id: Optional[str] = None
    ):
        """Handle AGV unload commands.
        params: {device_id: str, buffer_type: str}
        """
        device_id = params.get("device_id")
        buffer_type = params.get("buffer_type")
        if not device_id:
            msg = "unload_agv command missing 'device_id' parameter"
            logger.error(msg)
            self.mqtt_client.publish(
                AGENT_RESPONSES_TOPIC,
                SystemResponse(
                    timestamp=self.factory.env.now, command_id=command_id, response=msg
                ).model_dump_json(),
            )
            return
        if agv_id not in self.factory.agvs:
            msg = f"AGV {agv_id} not found in factory"
            logger.error(msg)
            self.mqtt_client.publish(
                AGENT_RESPONSES_TOPIC,
                SystemResponse(
                    timestamp=self.factory.env.now, command_id=command_id, response=msg
                ).model_dump_json(),
            )
            return
        agv = self.factory.agvs[agv_id]
        device = self.factory.all_devices.get(device_id)
        if not device:
            msg = f"Device {device_id} not found in factory"
            logger.error(msg)
            self.mqtt_client.publish(
                AGENT_RESPONSES_TOPIC,
                SystemResponse(
                    timestamp=self.factory.env.now, command_id=command_id, response=msg
                ).model_dump_json(),
            )
            return
        logger.info(
            f"AGV {agv_id} unloading {device_id} with buffer_type {buffer_type}"
        )

        def unload_process():
            success, message, _ = yield from agv.unload_to(device, buffer_type)
            self.mqtt_client.publish(
                AGENT_RESPONSES_TOPIC,
                SystemResponse(
                    timestamp=self.factory.env.now,
                    command_id=command_id,
                    response=message,
                ).model_dump_json(),
            )
            return success, message

        self.factory.env.process(unload_process())

    def _handle_charge_agv(
        self, agv_id: str, params: Dict[str, Any], command_id: Optional[str] = None
    ):
        """Handle AGV charge commands.
        params: {target_level: float, action_time_factor: float}
        """
        target_level = params.get("target_level")
        if not target_level:
            msg = "charge_agv command missing 'target_level' parameter"
            logger.error(msg)
            self.mqtt_client.publish(
                AGENT_RESPONSES_TOPIC,
                SystemResponse(
                    timestamp=self.factory.env.now, command_id=command_id, response=msg
                ).model_dump_json(),
            )
            return
        if agv_id not in self.factory.agvs:
            msg = f"AGV {agv_id} not found in factory"
            logger.error(msg)
            self.mqtt_client.publish(
                AGENT_RESPONSES_TOPIC,
                SystemResponse(
                    timestamp=self.factory.env.now, command_id=command_id, response=msg
                ).model_dump_json(),
            )
            return
        agv = self.factory.agvs[agv_id]

        def charge_process():
            success, message = yield from agv.voluntary_charge(target_level)
            self.mqtt_client.publish(
                AGENT_RESPONSES_TOPIC,
                SystemResponse(
                    timestamp=self.factory.env.now,
                    command_id=command_id,
                    response=message,
                ).model_dump_json(),
            )
            return success, message

        self.factory.env.process(charge_process())

    def _handle_agv_action_sequence(
        self, agv_id: str, params: Dict[str, Any], command_id: Optional[str] = None
    ):
        """支持agent一次下发一串AGV动作，仿真端按序执行并反馈。params: {actions: [{type, args}]}
        type: move/load/unload; args: dict
        """
        if agv_id not in self.factory.agvs:
            logger.error(f"AGV {agv_id} not found in factory")
            return
        agv = self.factory.agvs[agv_id]
        actions = params.get("actions", [])
        env = self.factory.env
        devices = {**self.factory.stations, **self.factory.agvs}
        # 加入conveyor/qualitychecker
        if hasattr(self.factory, "conveyor_ab"):
            devices["conveyor_ab"] = self.factory.conveyor_ab
        if hasattr(self.factory, "conveyor_bc"):
            devices["conveyor_bc"] = self.factory.conveyor_bc
        if hasattr(self.factory, "conveyor_cq"):
            devices["conveyor_cq"] = self.factory.conveyor_cq
        if (
            hasattr(self.factory, "stations")
            and "QualityCheck" in self.factory.stations
        ):
            devices["QualityCheck"] = self.factory.stations["QualityCheck"]

        def agv_action_sequence_proc():
            for idx, act in enumerate(actions):
                act_type = act.get("type")
                args = act.get("args", {})
                feedback = ""
                success = False
                # move: args: {target_point: str}
                if act_type == "move":
                    # 支持两种格式：坐标位置或路径点名称
                    if "target_point" in args:
                        # 使用路径点名称（推荐方式）
                        target_point = args["target_point"]
                        success, feedback = yield from agv.move_to(target_point)
                    else:
                        feedback = "move命令缺少target_point参数"
                        success = False
                # load: args: {device_id, buffer_type}
                elif act_type == "load":
                    device_id = args.get("device_id")
                    buffer_type = args.get("buffer_type")
                    device = devices.get(device_id)
                    if device is None:
                        feedback = f"未找到设备{device_id}"
                    else:
                        s, f, _ = yield from agv.load_from(device, buffer_type)
                        feedback = f
                        success = s
                # unload: args: {device_id, buffer_type}
                elif act_type == "unload":
                    device_id = args.get("device_id")
                    buffer_type = args.get("buffer_type")
                    device = devices.get(device_id)
                    if device is None:
                        feedback = f"未找到设备{device_id}"
                    else:
                        s, f, _ = yield from agv.unload_to(device, buffer_type)
                        feedback = f
                        success = s
                else:
                    feedback = f"未知动作类型: {act_type}"
                # 反馈
                resp = SystemResponse(
                    timestamp=env.now,
                    command_id=command_id,
                    response=f"[{idx + 1}/{len(actions)}] {act_type}: {feedback}",
                ).model_dump_json()
                self.mqtt_client.publish(AGENT_RESPONSES_TOPIC, resp)
                # 若失败则中断后续
                if not success:
                    break

        # 启动仿真进程
        env.process(agv_action_sequence_proc())

    def _handle_request_maintenance(self, device_id: str, params: Dict[str, Any]):
        """Handle maintenance request commands."""
        maintenance_type = params.get("maintenance_type")
        if not maintenance_type:
            logger.error(
                "request_maintenance command missing 'maintenance_type' parameter"
            )
            return

        logger.info(f"Requesting {maintenance_type} maintenance for {device_id}")

        # Use the factory's maintenance handling system
        diagnosis_result = self.factory.handle_maintenance_request(
            device_id, maintenance_type
        )

        if diagnosis_result.is_correct:
            logger.info(
                f"✅ Correct diagnosis for {device_id}, repair time: {diagnosis_result.repair_time:.1f}s"
            )
        else:
            logger.warning(
                f"❌ Incorrect diagnosis for {device_id}, penalty time: {diagnosis_result.repair_time:.1f}s"
            )
            if diagnosis_result.affected_devices:
                logger.warning(
                    f"   Affected devices: {', '.join(diagnosis_result.affected_devices)}"
                )

        return diagnosis_result

    def _handle_inspect_device(self, device_id: str, params: Dict[str, Any]):
        """Handle device inspection commands."""
        logger.info(f"Inspecting device {device_id}")

        if not hasattr(self.factory, "fault_system"):
            logger.error("Factory does not have fault system available")
            return None

        # Use the fault system's inspect function
        detailed_status = self.factory.fault_system.inspect_device(device_id)

        if detailed_status:
            logger.info(f"✅ Device {device_id} inspection completed")
            # 发布检查结果供agent使用
            self._publish_inspection_result(device_id, detailed_status)
        else:
            logger.warning(f"❌ Device {device_id} inspection failed")

        return detailed_status

    def _handle_skip_repair_time(self, device_id: str, params: Dict[str, Any]):
        """Handle skip repair time commands."""
        logger.info(f"Attempting to skip repair time for {device_id}")

        if not hasattr(self.factory, "fault_system"):
            logger.error("Factory does not have fault system available")
            return False

        # Use the fault system's skip function
        success = self.factory.fault_system.skip_repair_time(device_id)

        if success:
            logger.info(f"✅ Successfully skipped repair time for {device_id}")
        else:
            logger.warning(f"❌ Failed to skip repair time for {device_id}")

        return success

    def _handle_get_available_devices(self, target: str, params: Dict[str, Any]):
        """Handle get available devices commands."""
        logger.info("Retrieving available devices list")

        if not hasattr(self.factory, "fault_system"):
            logger.error("Factory does not have fault system available")
            return []

        # Get available devices from fault system
        available_devices = self.factory.fault_system.get_available_devices()

        logger.info(f"✅ Available devices: {', '.join(available_devices)}")

        # Publish available devices via MQTT
        self._publish_available_devices(available_devices)

        return available_devices

    def _handle_emergency_stop(self, device_id: str, params: Dict[str, Any]):
        """Handle emergency stop commands."""
        logger.info(f"Emergency stop requested for {device_id}")

        success = False

        # Handle station emergency stop
        if device_id in self.factory.stations:
            station = self.factory.stations[device_id]
            if hasattr(station, "emergency_stop"):
                station.emergency_stop()
                success = True
            else:
                # Fallback: force station to idle state
                from src.simulation.entities.base import DeviceStatus

                station.status = DeviceStatus.MAINTENANCE
                logger.info(
                    f"✅ Station {device_id} emergency stopped (forced to maintenance mode)"
                )
                success = True

        # Handle AGV emergency stop
        elif device_id in self.factory.agvs:
            agv = self.factory.agvs[device_id]
            if hasattr(agv, "emergency_stop"):
                agv.emergency_stop()
                success = True
            else:
                # Fallback: force AGV to stop
                agv.is_moving = False
                logger.info(f"✅ AGV {device_id} emergency stopped")
                success = True

        # Handle factory-wide emergency stop
        elif device_id == "factory":
            logger.info("🚨 Factory-wide emergency stop initiated")
            # Stop all stations
            for station_id, station in self.factory.stations.items():
                if hasattr(station, "emergency_stop"):
                    station.emergency_stop()
                else:
                    from src.simulation.entities.base import DeviceStatus

                    station.status = DeviceStatus.MAINTENANCE

            # Stop all AGVs
            for agv_id, agv in self.factory.agvs.items():
                if hasattr(agv, "emergency_stop"):
                    agv.emergency_stop()
                else:
                    agv.is_moving = False

            success = True

        else:
            logger.error(f"❌ Unknown device for emergency stop: {device_id}")

        if success:
            logger.info(f"✅ Emergency stop completed for {device_id}")
        else:
            logger.error(f"❌ Emergency stop failed for {device_id}")

        return success

    def _handle_adjust_priority(self, order_id: str, params: Dict[str, Any]):
        """Handle order priority adjustment commands."""
        new_priority = params.get("priority")
        if not new_priority:
            logger.error("adjust_priority command missing 'priority' parameter")
            return False

        logger.info(f"Adjusting priority of order {order_id} to {new_priority}")

        # Validate priority value
        valid_priorities = ["low", "medium", "high"]
        if new_priority not in valid_priorities:
            logger.error(
                f"Invalid priority '{new_priority}'. Valid priorities: {valid_priorities}"
            )
            return False

        success = False

        # Try to find and update the order in the order generator
        if hasattr(self.factory, "order_generator"):
            order_generator = self.factory.order_generator

            # Look for the order in active orders
            if hasattr(order_generator, "active_orders"):
                for order in order_generator.active_orders:
                    if order.order_id == order_id:
                        old_priority = order.priority
                        order.priority = new_priority

                        # Recalculate deadline based on new priority
                        if hasattr(order_generator, "_calculate_deadline"):
                            order.deadline = order_generator._calculate_deadline(
                                new_priority, order.quantity
                            )

                        logger.info(
                            f"✅ Order {order_id} priority changed from {old_priority} to {new_priority}"
                        )
                        success = True
                        break

            # If not found in active orders, check pending orders
            if not success and hasattr(order_generator, "pending_orders"):
                for order in order_generator.pending_orders:
                    if order.order_id == order_id:
                        old_priority = order.priority
                        order.priority = new_priority

                        # Recalculate deadline
                        if hasattr(order_generator, "_calculate_deadline"):
                            order.deadline = order_generator._calculate_deadline(
                                new_priority, order.quantity
                            )

                        logger.info(
                            f"✅ Order {order_id} priority changed from {old_priority} to {new_priority}"
                        )
                        success = True
                        break

        # Also try to update in KPI calculator if it tracks orders
        if hasattr(self.factory, "kpi_calculator"):
            kpi_calculator = self.factory.kpi_calculator
            if hasattr(kpi_calculator, "update_order_priority"):
                kpi_calculator.update_order_priority(order_id, new_priority)

        if not success:
            logger.error(f"❌ Order {order_id} not found or could not be updated")

        return success

    def _handle_reroute_order(self, order_id: str, params: Dict[str, Any]):
        """Handle order rerouting commands."""
        target_station_id = params.get("target_station_id")
        if not target_station_id:
            logger.error("reroute_order command missing 'target_station_id' parameter")
            return False

        logger.info(f"Rerouting order {order_id} to {target_station_id}")

        # Validate target station exists
        if target_station_id not in self.factory.stations:
            logger.error(f"Target station '{target_station_id}' does not exist")
            return False

        success = False

        # Try to find the order and reroute it
        if hasattr(self.factory, "order_generator"):
            order_generator = self.factory.order_generator

            # Look for the order in active orders
            if hasattr(order_generator, "active_orders"):
                for order in order_generator.active_orders:
                    if order.order_id == order_id:
                        # Check if the order has a route or current station
                        if hasattr(order, "current_station"):
                            old_station = order.current_station
                            order.current_station = target_station_id
                            logger.info(
                                f"✅ Order {order_id} rerouted from {old_station} to {target_station_id}"
                            )
                            success = True
                        elif hasattr(order, "route"):
                            # Modify the route to include the target station
                            if isinstance(order.route, list):
                                # Insert target station at the beginning of remaining route
                                order.route.insert(0, target_station_id)
                            else:
                                # Simple case: set route to target station
                                order.route = [target_station_id]
                            logger.info(
                                f"✅ Order {order_id} route updated to include {target_station_id}"
                            )
                            success = True
                        else:
                            # Create a new route attribute if it doesn't exist
                            order.next_station = target_station_id
                            logger.info(
                                f"✅ Order {order_id} next station set to {target_station_id}"
                            )
                            success = True
                        break

        # If the order is currently being processed at a station, we might need to stop it
        if success:
            target_station = self.factory.stations[target_station_id]

            # Notify the target station about incoming order (if supported)
            if hasattr(target_station, "notify_incoming_order"):
                target_station.notify_incoming_order(order_id)

            # Update KPI calculator if it tracks order routing
            if hasattr(self.factory, "kpi_calculator"):
                kpi_calculator = self.factory.kpi_calculator
                if hasattr(kpi_calculator, "update_order_route"):
                    kpi_calculator.update_order_route(order_id, target_station_id)

        if not success:
            logger.error(f"❌ Order {order_id} not found or could not be rerouted")

        return success

    def _publish_inspection_result(self, device_id: str, detailed_status):
        """Publish device inspection result via MQTT."""
        topic = f"factory/inspection/{device_id}/result"
        message = {
            "device_id": device_id,
            "timestamp": self.factory.env.now,
            "status": detailed_status.dict(),
        }

        try:
            self.mqtt_client.publish(topic, json.dumps(message))
            logger.debug(f"Published inspection result for {device_id}")
        except Exception as e:
            logger.error(f"Failed to publish inspection result: {e}")

    def _publish_available_devices(self, available_devices):
        """Publish available devices list via MQTT."""
        topic = "factory/devices/available"
        message = {
            "timestamp": self.factory.env.now,
            "available_devices": available_devices,
        }

        try:
            self.mqtt_client.publish(topic, json.dumps(message))
            logger.debug("Published available devices list")
        except Exception as e:
            logger.error(f"Failed to publish available devices: {e}")
