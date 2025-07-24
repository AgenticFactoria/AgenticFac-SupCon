# src/utils/topic_manager.py
from typing import Dict, Optional


class TopicManager:
    """
    Manages the generation of all MQTT topics for the simulation.
    It ensures a consistent topic structure based on a root name.
    """

    def __init__(self, player_name: str):
        """
        Initializes the TopicManager with a root topic name.
        Args:
            player_name: The root name for all topics, typically the player's or team's name.
        """
        if not player_name or not isinstance(player_name, str) or "/" in player_name:
            raise ValueError("Player name cannot be empty or contain '/'")
        self.root = player_name
        print(f"✅ TopicManager initialized with root topic: '{self.root}'")

    def get_station_status_topic(self, line_id: str, device_id: str) -> str:
        """Generates topic for device status updates."""
        # device_id from Line class is already line_x_device_y, so we can just use it
        return f"{self.root}/{line_id}/station/{device_id}/status"

    def get_conveyor_status_topic(self, line_id: str, device_id: str) -> str:
        """Generates topic for device status updates."""
        # device_id from Line class is already line_x_device_y, so we can just use it
        return f"{self.root}/{line_id}/conveyor/{device_id}/status"

    def get_warehouse_status_topic(self, device_id: str) -> str:
        """Generates topic for device status updates."""
        # device_id from Line class is already line_x_device_y, so we can just use it
        return f"{self.root}/warehouse/{device_id}/status"

    def get_agv_status_topic(self, line_id: str, agv_id: str) -> str:
        """Generates topic for AGV status updates."""
        return f"{self.root}/{line_id}/agv/{agv_id}/status"

    def get_order_topic(self) -> str:
        """Generates topic for new order announcements."""
        return f"{self.root}/orders/status"

    def get_fault_alert_topic(self, line_id: str) -> str:
        """Generates topic for fault alerts."""
        return f"{self.root}/{line_id}/alerts"

    def get_kpi_topic(self) -> str:
        """Generates topic for factory-wide KPI updates."""
        return f"{self.root}/kpi/status"

    def get_result_topic(self) -> str:
        """Generates topic for factory-wide result updates."""
        return f"{self.root}/result/status"

    def get_agent_command_topic_wildcard(self) -> str:
        """Generates a wildcard topic for agent commands for all lines."""
        return f"{self.root}/command/+"

    def get_agent_command_topic(self, line_id: str) -> str:
        """Generates the specific command topic for a given line."""
        return f"{self.root}/command/{line_id}"

    def parse_agent_command_topic(self, topic: str) -> Optional[Dict[str, str]]:
        """
        Parses an agent command topic to extract line_id.
        Expected format: {root}/command/{line_id}
        """
        parts = topic.split("/")
        if len(parts) == 3 and parts[0] == self.root and parts[1] == "command":
            return {"line_id": parts[2]}
        return None

    def get_agent_response_topic(self, line_id: Optional[str]) -> str:
        """Generates the response topic for agent commands."""
        if line_id:
            return f"{self.root}/response/{line_id}"
        else:
            return f"{self.root}/response/general"
