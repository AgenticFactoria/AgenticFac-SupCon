# src/simulation/line.py
import simpy
from typing import Dict, Optional

from src.simulation.entities.conveyor import (
    Conveyor,
    TripleBufferConveyor,
    BaseConveyor,
)
from src.simulation.entities.warehouse import Warehouse, RawMaterial
from src.simulation.entities.station import Station
from src.simulation.entities.agv import AGV
from src.simulation.entities.quality_checker import QualityChecker
from src.game_logic.order_generator import OrderGenerator
from src.game_logic.fault_system import FaultSystem
from src.game_logic.kpi_calculator import KPICalculator
from src.utils.mqtt_client import MQTTClient
from src.utils.topic_manager import TopicManager


class Line:
    """
    Represents a single production line within the factory.
    """

    def __init__(
        self,
        env: simpy.Environment,
        line_name: str,
        line_config: Dict,
        mqtt_client: MQTTClient,
        topic_manager: TopicManager,
        warehouse: Warehouse,
        raw_material: RawMaterial,
        order_generator: OrderGenerator,
        kpi_calculator: KPICalculator,
        no_faults: bool = False,
    ):
        self.env = env
        self.name = line_name
        self.config = line_config
        self.mqtt_client = mqtt_client
        self.topic_manager = topic_manager
        self.no_faults_mode = no_faults
        self.fault_system: Optional[FaultSystem] = None

        # Shared resources injected from Factory
        self.warehouse = warehouse
        self.raw_material = raw_material
        self.order_generator = order_generator
        self.kpi_calculator = kpi_calculator
        self.stations: Dict[str, Station] = {}
        self.agvs: Dict[str, AGV] = {}
        self.conveyors: Dict[str, BaseConveyor] = {}

        self.agv_task_queue = simpy.Store(self.env)
        self.all_devices = {}

        self._create_devices()

        self.all_devices.update(self.stations)
        self.all_devices.update(self.agvs)
        self.all_devices.update(self.conveyors)

        # Update all devices with KPI calculator
        self._update_agvs_with_kpi()
        self._update_stations_with_kpi()
        self._setup_event_handlers()

        self._create_game_logic_systems()
        self._bind_conveyors_to_stations()
        self._setup_conveyor_downstreams()

    def _create_devices(self):
        """Instantiates all devices for this line based on its configuration."""
        for station_cfg in self.config.get("stations", []):
            if station_cfg["id"] == "QualityCheck":
                station = QualityChecker(
                    env=self.env,
                    mqtt_client=self.mqtt_client,
                    topic_manager=self.topic_manager,
                    line_id=self.name,
                    **station_cfg,
                )
            else:
                station = Station(
                    env=self.env,
                    mqtt_client=self.mqtt_client,
                    topic_manager=self.topic_manager,
                    line_id=self.name,
                    **station_cfg,
                )
            self.stations[station.id] = station

        for agv_cfg in self.config.get("agvs", []):
            # Get agv_operations for this specific AGV
            agv_operations = self.config.get("agv_operations", {}).get(
                agv_cfg["id"], {}
            )
            agv = AGV(
                env=self.env,
                mqtt_client=self.mqtt_client,
                topic_manager=self.topic_manager,
                fault_system=self.fault_system,
                kpi_calculator=self.kpi_calculator,
                line_id=self.name,
                agv_operations=agv_operations,
                **agv_cfg,
            )
            self.agvs[agv.id] = agv

        for conveyor_cfg in self.config.get("conveyors", []):
            conveyor_id = conveyor_cfg["id"]
            common_args = {
                "env": self.env,
                "id": conveyor_id,
                "position": conveyor_cfg["position"],
                "interacting_points": conveyor_cfg["interacting_points"],
                "transfer_time": conveyor_cfg["transfer_time"],
                "mqtt_client": self.mqtt_client,
                "topic_manager": self.topic_manager,
                "line_id": self.name,
                "kpi_calculator": self.kpi_calculator,
            }
            if conveyor_cfg["id"] == "Conveyor_CQ":
                conveyor = TripleBufferConveyor(
                    **common_args,
                    main_capacity=conveyor_cfg["main_capacity"],
                    upper_capacity=conveyor_cfg["upper_capacity"],
                    lower_capacity=conveyor_cfg["lower_capacity"],
                )
            else:  # Assuming 'Conveyor_AB', 'Conveyor_BC' or similar
                conveyor = Conveyor(**common_args, capacity=conveyor_cfg["capacity"])
            self.conveyors[conveyor_id] = conveyor

    def _create_game_logic_systems(self):
        """Creates game logic systems like FaultSystem for this line."""
        if "fault_system" in self.config and not self.no_faults_mode:
            fs_config = self.config["fault_system"]
            self.fault_system = FaultSystem(
                self.env,
                self.all_devices,
                self.mqtt_client,
                self.topic_manager,
                self.name,
                kpi_calculator=self.kpi_calculator,
                **fs_config,
            )

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

    def _bind_conveyors_to_stations(self):
        """Bind conveyors to stations according to the process flow."""
        if "StationA" in self.stations and "Conveyor_AB" in self.conveyors:
            self.stations["StationA"].downstream_conveyor = self.conveyors[
                "Conveyor_AB"
            ]
        if "StationB" in self.stations and "Conveyor_BC" in self.conveyors:
            self.stations["StationB"].downstream_conveyor = self.conveyors[
                "Conveyor_BC"
            ]
        if "StationC" in self.stations and "Conveyor_CQ" in self.conveyors:
            self.stations["StationC"].downstream_conveyor = self.conveyors[
                "Conveyor_CQ"
            ]

    def _setup_conveyor_downstreams(self):
        """Set downstream stations for conveyors to enable auto-transfer."""
        if "StationB" in self.stations and "Conveyor_AB" in self.conveyors:
            self.conveyors["Conveyor_AB"].set_downstream_station(
                self.stations["StationB"]
            )
        if "StationC" in self.stations and "Conveyor_BC" in self.conveyors:
            self.conveyors["Conveyor_BC"].set_downstream_station(
                self.stations["StationC"]
            )
        if "QualityCheck" in self.stations and "Conveyor_CQ" in self.conveyors:
            self.conveyors["Conveyor_CQ"].set_downstream_station(
                self.stations["QualityCheck"]
            )
