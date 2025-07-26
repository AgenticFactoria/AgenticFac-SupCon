# src/simulation/factory_multi.py
import os
import simpy
from typing import Dict

from src.simulation.line import Line
from src.game_logic.kpi_calculator import KPICalculator
from src.utils.mqtt_client import MQTTClient
from src.simulation.entities.warehouse import Warehouse, RawMaterial
from src.game_logic.order_generator import OrderGenerator
from src.utils.topic_manager import TopicManager


class Factory:
    """
    The main class that orchestrates the entire factory simulation with multiple production lines.
    """

    def __init__(
        self, layout_config: Dict, mqtt_client: MQTTClient, no_faults: bool = False
    ):
        self.env = simpy.Environment()
        self.layout = layout_config
        self.mqtt_client = mqtt_client
        self.no_faults_mode = no_faults

        # Read player name from environment variable
        topic_root = (
            os.getenv("TOPIC_ROOT")
            or os.getenv("USERNAME")
            or os.getenv("USER")
            or "NLDF_TEST"
        )
        self.topic_manager = TopicManager(topic_root)

        self.lines: Dict[str, Line] = {}
        self.raw_material: RawMaterial
        self.warehouse: Warehouse
        self.order_generator: OrderGenerator
        self.kpi_calculator = KPICalculator(
            self.env, self.mqtt_client, self.topic_manager
        )

        self.all_devices = {}
        self._create_warehouse_order_generator()
        self._create_production_lines()

        # Start process to update active faults count
        self.env.process(self._update_active_faults_count())

    def _create_production_lines(self):
        """Creates all production lines based on the layout configuration."""
        for line_config in self.layout.get("production_lines", []):
            line_name = line_config["name"]
            line = Line(
                env=self.env,
                line_name=line_name,
                line_config=line_config,
                mqtt_client=self.mqtt_client,
                topic_manager=self.topic_manager,
                warehouse=self.warehouse,
                raw_material=self.raw_material,
                order_generator=self.order_generator,
                no_faults=self.no_faults_mode,
                kpi_calculator=self.kpi_calculator,
            )
            self.lines[line_name] = line
            print(f"[{self.env.now:.2f}] 🏭 Created Production Line: {line_name}")

    def _create_warehouse_order_generator(self):
        """Creates the warehouse for the factory."""
        for warehouse_cfg in self.layout.get("warehouses", []):
            common_args = {
                "env": self.env,
                "mqtt_client": self.mqtt_client,
                "topic_manager": self.topic_manager,
                **warehouse_cfg,
            }
            if warehouse_cfg["id"] == "RawMaterial":
                self.raw_material = RawMaterial(
                    **common_args, kpi_calculator=self.kpi_calculator
                )
            elif warehouse_cfg["id"] == "Warehouse":
                self.warehouse = Warehouse(**common_args)

            if self.raw_material:
                og_config = self.layout.get("order_generator", {})
                self.order_generator = OrderGenerator(
                    env=self.env,
                    raw_material=self.raw_material,
                    mqtt_client=self.mqtt_client,
                    topic_manager=self.topic_manager,
                    kpi_calculator=self.kpi_calculator,
                    **og_config,
                )

        # Add global devices to all_devices
        if hasattr(self, "warehouse") and self.warehouse is not None:
            self.all_devices[self.warehouse.id] = self.warehouse
        if hasattr(self, "raw_material") and self.raw_material is not None:
            self.all_devices[self.raw_material.id] = self.raw_material

    def get_device_status(self, device_id: str) -> Dict:
        """Get comprehensive device status including faults."""
        for line in self.lines.values():
            if device_id in line.all_devices:
                # This part can be enhanced to call a method on the line object
                # which in turn calls the device. For now, direct access for simplicity.
                device = line.all_devices[device_id]
                return device.get_detailed_status()  # Simplified for now
        return {}

    def _update_active_faults_count(self):
        """Periodically update the active faults count in KPI calculator."""
        while True:
            # Count total active faults across all lines
            total_active_faults = 0
            for line in self.lines.values():
                if line.fault_system:
                    total_active_faults += len(line.fault_system.active_faults)

            # Update KPI calculator with the total count
            if self.kpi_calculator:
                self.kpi_calculator.update_active_faults_count(total_active_faults)

            # Wait for 1 second before next update
            yield self.env.timeout(1.0)

    def print_final_scores(self, force_update: bool = False):
        """Print final competition scores. 
        
        Args:
            force_update: Whether to force a KPI update after printing (default: False)
        """
        if self.kpi_calculator:
            final_scores = self.kpi_calculator.get_final_score()
            print(f"\n{'=' * 60}")
            print("🏆 最终竞赛得分")
            print(f"{'=' * 60}")
            print(f"生产效率得分 (40%): {final_scores['efficiency_score']:.2f}")
            print(
                f"  - 订单完成率: {final_scores['efficiency_components']['order_completion']:.1f}%"
            )
            print(
                f"  - 生产周期效率: {final_scores['efficiency_components']['production_cycle']:.1f}%"
            )
            print(
                f"  - 设备利用率: {final_scores['efficiency_components']['device_utilization']:.1f}%"
            )
            print(f"\n质量与成本得分 (30%): {final_scores['quality_cost_score']:.2f}")
            print(
                f"  - 一次通过率: {final_scores['quality_cost_components']['first_pass_rate']:.1f}%"
            )
            print(
                f"  - 成本效率: {final_scores['quality_cost_components']['cost_efficiency']:.1f}%"
            )
            print(f"\nAGV效率得分 (30%): {final_scores['agv_score']:.2f}")
            print(
                f"  - 充电策略效率: {final_scores['agv_components']['charge_strategy']:.1f}%"
            )
            print(
                f"  - 能效比: {final_scores['agv_components']['energy_efficiency']:.1f}%"
            )
            print(
                f"  - AGV利用率: {final_scores['agv_components']['utilization']:.1f}%"
            )
            print(f"\n总得分: {final_scores['total_score']:.2f}")
            print(f"{'=' * 60}\n")

            # Only force KPI update if explicitly requested
            if force_update:
                self.kpi_calculator.force_kpi_update()

    def get_final_scores(self) -> Dict:
        """Get final competition scores from KPI calculator."""
        if self.kpi_calculator:
            return self.kpi_calculator.get_final_score()
        return {}

    def run(self, until: int):
        """Runs the simulation for a given duration."""
        self.env.run(until=until)
