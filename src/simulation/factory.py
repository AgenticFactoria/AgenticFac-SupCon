# src/simulation/factory.py
import simpy
from typing import Dict, List, Optional

from src.simulation.entities.conveyor import Conveyor, TripleBufferConveyor
from src.simulation.entities.base import BaseConveyor
from src.simulation.entities.warehouse import Warehouse, RawMaterial
from src.simulation.entities.station import Station
from src.simulation.entities.agv import AGV
from src.simulation.entities.quality_checker import QualityChecker
from src.game_logic.order_generator import OrderGenerator
from src.game_logic.fault_system import FaultSystem
from src.game_logic.kpi_calculator import KPICalculator
from src.utils.mqtt_client import MQTTClient

# Import configuration loader
from src.utils.config_loader import load_factory_config


class Factory:
    """
    The main class that orchestrates the entire factory simulation.
    """

    def __init__(
        self,
        layout_config: Dict,
        mqtt_client: Optional[MQTTClient] = None,
        no_faults: bool = False,
    ):
        self.env = simpy.Environment()
        self.layout = layout_config
        self.mqtt_client = mqtt_client
        self.no_faults_mode = no_faults  # Store the flag

        self.stations: Dict[str, Station] = {}
        self.agvs: Dict[str, AGV] = {}
        self.conveyors: Dict[str, BaseConveyor] = {}

        # Warehouse attributes - will be set during device creation
        self.warehouse: Optional[Warehouse] = None
        self.raw_material: Optional[RawMaterial] = None

        # AGV task queue for product transportation
        self.agv_task_queue = simpy.Store(self.env)

        # Statistics for scrapped products
        self.scrap_stats = {
            "total_scrapped": 0,
            "scrap_by_station": {},
            "scrap_reasons": {},
        }

        # Initialize all_devices dictionary first
        self.all_devices = {}

        # Game logic components will be initialized dynamically
        self.order_generator: Optional[OrderGenerator] = None
        self.fault_system: Optional[FaultSystem] = None

        # Initialize KPI calculator early so it can be passed to devices
        self.kpi_calculator = KPICalculator(
            self.env, self.mqtt_client, None, self.layout
        )

        # Create devices first
        self._create_devices()

        # Update all_devices with created devices
        self.all_devices.update(self.stations)
        self.all_devices.update(self.agvs)
        self.all_devices.update(self.conveyors)

        if self.warehouse is not None:
            self.all_devices[self.warehouse.id] = self.warehouse

        if self.raw_material is not None:
            self.all_devices[self.raw_material.id] = self.raw_material

        # Create game logic systems from config
        self._create_game_logic_systems()

        # If order generator is not created, some features might not work.
        if not self.order_generator:
            print(
                "⚠️ Order Generator not configured in layout. Order-related features will be disabled."
            )

        # If fault system is not created, fault features will be disabled.
        if not self.fault_system:
            print(
                "⚠️ Fault System not configured in layout or is disabled. No faults will be generated."
            )

        # Recreate order generator with KPI calculator
        if self.order_generator:
            self._update_order_generator_with_kpi()

        # Update all devices with KPI calculator
        self._update_agvs_with_kpi()
        self._update_stations_with_kpi()

        # Setup event handlers
        self._setup_event_handlers()

        # Start process to update active faults count
        self.env.process(self._update_active_faults_count())

        # Start device status publishing
        self._start_status_publishing()

        self._bind_conveyors_to_stations()
        self._setup_conveyor_downstreams()

    def _create_devices(self):
        """Instantiates all devices based on the layout configuration."""

        for station_cfg in self.layout["stations"]:
            # Quality checker station
            if station_cfg["id"] == "QualityCheck":
                station = QualityChecker(
                    env=self.env, mqtt_client=self.mqtt_client, **station_cfg
                )
                print(
                    f"[{self.env.now:.2f}] 🔍 Created QualityChecker: {station_cfg['id']}"
                )
            else:
                # create normal station
                station = Station(
                    env=self.env, mqtt_client=self.mqtt_client, **station_cfg
                )
                print(f"[{self.env.now:.2f}] 🏭 Created Station: {station_cfg['id']}")

            self.stations[station.id] = station

        # create AGV
        for agv_cfg in self.layout["agvs"]:
            agv = AGV(
                env=self.env,
                mqtt_client=self.mqtt_client,
                fault_system=self.fault_system,
                kpi_calculator=self.kpi_calculator,
                **agv_cfg,
            )
            self.agvs[agv.id] = agv
            print(f"[{self.env.now:.2f}] 🚛 Created AGV: {agv_cfg['id']}")

        # create conveyor
        for conveyor_cfg in self.layout["conveyors"]:
            conveyor_id = conveyor_cfg["id"]
            # Common arguments for all conveyors
            common_args = {
                "env": self.env,
                "id": conveyor_id,
                "position": conveyor_cfg["position"],
                "interacting_points": conveyor_cfg["interacting_points"],
                "transfer_time": conveyor_cfg["transfer_time"],
                "mqtt_client": self.mqtt_client,
                "kpi_calculator": self.kpi_calculator,
            }
            if conveyor_id == "Conveyor_CQ":
                conveyor = TripleBufferConveyor(
                    main_capacity=conveyor_cfg["main_capacity"],
                    upper_capacity=conveyor_cfg["upper_capacity"],
                    lower_capacity=conveyor_cfg["lower_capacity"],
                    **common_args,
                )
            elif conveyor_id in ["Conveyor_AB", "Conveyor_BC"]:
                conveyor = Conveyor(capacity=conveyor_cfg["capacity"], **common_args)
            else:
                raise ValueError(f"Unknown conveyor type: {conveyor_id}")

            self.conveyors[conveyor.id] = conveyor
            print(f"[{self.env.now:.2f}] 🚛 Created Conveyor: {conveyor_id}")

        # create warehouse
        for warehouse_cfg in self.layout["warehouses"]:
            # Common arguments for all warehouses
            common_args = {
                "env": self.env,
                "mqtt_client": self.mqtt_client,
                **warehouse_cfg,
            }
            if warehouse_cfg["id"] == "RawMaterial":
                warehouse = RawMaterial(
                    **common_args, kpi_calculator=self.kpi_calculator
                )
                self.raw_material = warehouse  # Store dedicated reference
            elif warehouse_cfg["id"] == "Warehouse":
                warehouse = Warehouse(**common_args)
                self.warehouse = warehouse  # Store dedicated reference
            else:
                raise ValueError(f"Unknown warehouse type: {warehouse_cfg['id']}")

            print(f"[{self.env.now:.2f}] 🏪 Created Warehouse: {warehouse_cfg['id']}")

    def _create_game_logic_systems(self):
        """Dynamically create game logic systems like OrderGenerator and FaultSystem from config."""
        if "order_generator" in self.layout:
            if self.raw_material:
                og_config = self.layout["order_generator"]
                self.order_generator = OrderGenerator(
                    env=self.env,
                    raw_material=self.raw_material,
                    mqtt_client=self.mqtt_client,
                    kpi_calculator=None,  # Will be set later
                    **og_config,
                )
                print(
                    f"[{self.env.now:.2f}] 📝 Created OrderGenerator with config: {og_config}"
                )
            else:
                print("⚠️ Cannot create OrderGenerator: RawMaterial device not found.")

        if "fault_system" in self.layout and not self.no_faults_mode:
            fs_config = self.layout["fault_system"]
            self.fault_system = FaultSystem(
                env=self.env,
                devices=self.all_devices,
                mqtt_client=self.mqtt_client,
                kpi_calculator=self.kpi_calculator,
                **fs_config,
            )
            print(
                f"[{self.env.now:.2f}] 🔧 Created FaultSystem with config: {fs_config}"
            )
        elif self.no_faults_mode:
            print("🚫 Fault System Disabled (no-faults mode).")

    def _update_order_generator_with_kpi(self):
        """Update order generator with KPI calculator reference."""
        if self.order_generator and self.kpi_calculator:
            self.order_generator.kpi_calculator = self.kpi_calculator

    def _update_agvs_with_kpi(self):
        """Update AGVs with KPI calculator reference."""
        if self.kpi_calculator:
            for agv in self.agvs.values():
                agv.kpi_calculator = self.kpi_calculator

    def _update_stations_with_kpi(self):
        """Update stations with KPI calculator reference."""
        if self.kpi_calculator:
            for station in self.stations.values():
                station.kpi_calculator = self.kpi_calculator

    def _setup_event_handlers(self):
        """Setup event handlers for order processing and fault handling."""
        # Force initial KPI update
        if self.kpi_calculator:
            self.kpi_calculator.force_kpi_update()

    def get_available_devices(self) -> List[str]:
        """
        Get list of devices that can currently be operated (not frozen).
        """
        if self.fault_system is None:
            print(
                f"[{self.env.now:.2f}] 🚫 Fault System is disabled. No available devices from fault system."
            )
            return []
        return self.fault_system.get_available_devices()

    def get_device_status(self, device_id: str) -> Dict:
        """Get comprehensive device status including faults."""
        if device_id in self.all_devices:
            device = self.all_devices[device_id]
            detailed_status = device.get_detailed_status()

            # Convert to simplified status format for compatibility
            status_dict = {
                "device_id": device_id,
                "device_type": detailed_status.device_type,
                "status": detailed_status.current_status.value,
                "symptom": detailed_status.fault_symptom,
                "temperature": detailed_status.temperature,
                "efficiency_rate": detailed_status.efficiency_rate,
                "can_operate": device.can_operate(),
                "frozen_until": detailed_status.frozen_until,
            }

            # Add device-specific information
            if device_id in self.stations:
                status_dict.update(
                    {
                        "buffer_level": self.stations[device_id].get_buffer_level(),
                        "precision_level": detailed_status.precision_level,
                        "tool_wear_level": detailed_status.tool_wear_level,
                    }
                )
            elif device_id in self.agvs:
                agv = self.agvs[device_id]
                status_dict.update(
                    {
                        "position": {"x": agv.position[0], "y": agv.position[1]},
                        "battery_level": detailed_status.battery_level,
                        "position_accuracy": detailed_status.position_accuracy,
                        "payload": [p.id for p in agv.payload.items]
                        if hasattr(agv, "payload")
                        else [],
                    }
                )

            return status_dict
        return {}

    def _start_status_publishing(self):
        """Start processes to publish device status to MQTT."""
        # Start factory overall status publishing
        self.env.process(self._publish_factory_status())

    def _publish_factory_status(self):
        """Publish factory overall status every 30 seconds."""
        while True:
            yield self.env.timeout(30.0)  # Publish every 30 seconds

            # Create factory status summary
            from config.topics import FACTORY_STATUS_TOPIC
            from config.schemas import FactoryStatus

            factory_status = FactoryStatus(
                timestamp=self.env.now,
                total_stations=len(self.stations),
                total_agvs=len(self.agvs),
                active_orders=len(self.kpi_calculator.active_orders),
                total_orders=self.kpi_calculator.stats.total_orders,
                completed_orders=self.kpi_calculator.stats.completed_orders,
                active_faults=len(self.fault_system.active_faults)
                if self.fault_system
                else 0,
                simulation_time=self.env.now,
            )

            try:
                if self.mqtt_client:
                    self.mqtt_client.publish(FACTORY_STATUS_TOPIC, factory_status)
                print(
                    f"[{self.env.now:.2f}] 📊 Published factory status: {factory_status.active_orders} active orders, {factory_status.active_faults} faults"
                )
            except Exception as e:
                print(f"[{self.env.now:.2f}] ❌ Failed to publish factory status: {e}")

    def _publish_fault_events(self):
        """Publish enhanced fault events to make them more visible."""
        while True:
            yield self.env.timeout(1.0)  # Check for faults every 1 seconds

            # If there are active faults, publish them more frequently
            if self.fault_system and self.fault_system.active_faults:
                for device_id, fault in self.fault_system.active_faults.items():
                    # Create a detailed fault alert message
                    device_status = self.get_device_status(device_id)

                    fault_alert = {
                        "device_id": device_id,
                        "fault_type": fault.fault_type.value,
                        "symptom": fault.symptom,
                        "duration_seconds": self.env.now - fault.start_time,
                        "device_status": device_status.get("status"),
                        "can_operate": device_status.get("can_operate", False),
                        "frozen_until": device_status.get("frozen_until"),
                        "timestamp": self.env.now,
                    }

                    try:
                        import json

                        if self.mqtt_client:
                            self.mqtt_client.publish(
                                f"factory/alerts/{device_id}", json.dumps(fault_alert)
                            )
                        print(
                            f"[{self.env.now:.2f}] 🚨 Enhanced fault alert published for {device_id}: {fault.symptom}"
                        )
                    except Exception as e:
                        print(
                            f"[{self.env.now:.2f}] ❌ Failed to publish fault alert: {e}"
                        )

    def run(self, until: int):
        """Runs the simulation for a given duration."""
        # print(f"--- Factory simulation starting for {until} seconds ---")
        # print(f"--- Available devices: {', '.join(self.all_devices.keys())} ---")
        # print(f"--- Use 'inspect_device', 'skip_repair_time', 'request_maintenance' commands ---")
        """
        # Core simulation processes are already started in __init__:
        # - Order generation: self.order_generator.run() (auto-started)
        # - Fault injection: self.fault_system.run_fault_injection() (auto-started) 
        # - KPI updates: self.kpi_calculator.run_kpi_updates() (auto-started)
        # - MQTT publishing: self._start_status_publishing() (started in __init__)
        """
        # print(f"--- Active processes: Order Gen, Fault Injection, KPI Updates, MQTT Publishing ---")
        self.env.run(until=until)
        # print("--- Factory simulation finished ---")

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

    def get_final_scores(self) -> Optional[Dict]:
        """Get final competition scores from KPI calculator."""
        if self.kpi_calculator:
            return self.kpi_calculator.get_final_score()
        return None

    def get_factory_stats(self) -> Dict:
        """Get comprehensive factory statistics"""
        station_stats = {}
        for station_id, station in self.stations.items():
            if hasattr(station, "get_processing_stats"):
                station_stats[station_id] = station.get_processing_stats()

        agv_stats = {}
        for agv_id, agv in self.agvs.items():
            agv_stats[agv_id] = {
                "status": agv.status.value,
                "position": agv.position,
                "battery_level": getattr(agv, "battery_level", 100.0),
                "payload_count": len(agv.payload.items),  # Use .items for SimPy Store
            }

        return {
            "timestamp": self.env.now,
            "stations": station_stats,
            "agvs": agv_stats,
            "scrap_stats": self.scrap_stats,
            "total_devices": len(self.all_devices),
            "active_transport_tasks": len(self.agv_task_queue.items),
        }

    def _bind_conveyors_to_stations(self):
        """Bind conveyors to stations according to the process flow."""
        # StationA → conveyor_ab
        if "StationA" in self.stations and "Conveyor_AB" in self.conveyors:
            self.stations["StationA"].downstream_conveyor = self.conveyors[
                "Conveyor_AB"
            ]
        # StationB → conveyor_bc
        if "StationB" in self.stations and "Conveyor_BC" in self.conveyors:
            self.stations["StationB"].downstream_conveyor = self.conveyors[
                "Conveyor_BC"
            ]
        # StationC → conveyor_cq (TripleBufferConveyor)
        if "StationC" in self.stations and "Conveyor_CQ" in self.conveyors:
            self.stations["StationC"].downstream_conveyor = self.conveyors[
                "Conveyor_CQ"
            ]

    def _setup_conveyor_downstreams(self):
        """Set downstream stations for conveyors to enable auto-transfer."""
        # conveyor_ab → StationB
        if "StationB" in self.stations and "Conveyor_AB" in self.conveyors:
            self.conveyors["Conveyor_AB"].set_downstream_station(
                self.stations["StationB"]
            )
        # conveyor_bc → StationC
        if "StationC" in self.stations and "Conveyor_BC" in self.conveyors:
            self.conveyors["Conveyor_BC"].set_downstream_station(
                self.stations["StationC"]
            )
        # conveyor_cq → QualityCheck
        if "QualityCheck" in self.stations and "Conveyor_CQ" in self.conveyors:
            self.conveyors["Conveyor_CQ"].set_downstream_station(
                self.stations["QualityCheck"]
            )

    def _update_active_faults_count(self):
        """Periodically update the active faults count in KPI calculator."""
        while True:
            # For single-line factory, just count faults from the single FaultSystem
            active_faults_count = 0
            if self.fault_system:
                active_faults_count = len(self.fault_system.active_faults)

            # Update KPI calculator with the count
            if self.kpi_calculator:
                self.kpi_calculator.update_active_faults_count(active_faults_count)

            # Wait for 1 second before next update
            yield self.env.timeout(1.0)


# Example of how to run the factory simulation
if __name__ == "__main__":
    from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT

    mqtt_client = MQTTClient(
        host=MQTT_BROKER_HOST, port=MQTT_BROKER_PORT, client_id="factory_test"
    )
    # 连接MQTT broker
    mqtt_client.connect()
    print(f"✅ Connected to MQTT broker at {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}")

    # 加载配置
    try:
        from src.utils.config_loader import load_factory_config

        layout_config = load_factory_config()
    except Exception as e:
        print(f"❌ Failed to load factory configuration: {e}")
        raise e

    factory = Factory(layout_config, mqtt_client)

    # Simple test - just create the factory and run briefly
    print(f"[{factory.env.now:.2f}] 🎉 Factory created successfully!")
    print(f"[{factory.env.now:.2f}] 📊 Stations: {list(factory.stations.keys())}")
    print(f"[{factory.env.now:.2f}] 🚛 AGVs: {list(factory.agvs.keys())}")
    agv1 = factory.agvs["AGV_1"]
    factory.env.process(agv1.move_to("LP1"))

    print(f"[{factory.env.now:.2f}] 🛤️  Conveyors: {list(factory.conveyors.keys())}")
    print(
        f"[{factory.env.now:.2f}] 🏪 Warehouses: RawMaterial={factory.raw_material.id if factory.raw_material else None}, Warehouse={factory.warehouse.id if factory.warehouse else None}"
    )

    # Test simple simulation for 30 seconds
    factory.run(until=20)
