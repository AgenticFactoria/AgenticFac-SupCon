# simulation/entities/base.py
import simpy
import random
from abc import ABC, abstractmethod
from typing import Tuple, Optional

from config.schemas import DeviceStatus, DeviceDetailedStatus
from src.utils.topic_manager import TopicManager
from config.topics import DEVICE_ALERT_TOPIC


class Device:
    """
    Base class for all simulated devices in the factory.
    Simplified for a basic fault model.
    """

    def __init__(
        self,
        env: simpy.Environment,
        id: str,
        position: Tuple[int, int],
        device_type: str = "generic",
        mqtt_client=None,
        interacting_points: list = [],
        topic_manager: Optional[TopicManager] = None,
        line_id: Optional[str] = None,
    ):
        if not isinstance(env, simpy.Environment):
            raise ValueError("env must be a valid simpy.Environment object.")

        self.env = env
        self.id = id
        self.device_type = device_type
        self.position = position
        self.mqtt_client = mqtt_client
        self.interacting_points = (
            interacting_points if interacting_points is not None else []
        )
        self.topic_manager = topic_manager
        self.line_id = line_id

        # 设备状态和故障相关属性
        self.status = DeviceStatus.IDLE
        self.fault_symptom = None
        self.action: Optional[simpy.Process] = None  # Stores the current action process

        # 性能指标
        self.performance_metrics = type(
            "PerformanceMetrics",
            (),
            {"efficiency_rate": 100.0, "error_rate": 0.0, "uptime": 100.0},
        )()

        # 设备特定属性（可被子类扩展）
        self._specific_attributes = {
            "temperature": random.uniform(20.0, 25.0),
            "vibration_level": random.uniform(0.0, 5.0),
            "power_consumption": random.uniform(80.0, 120.0),
        }

    def set_status(self, new_status: DeviceStatus, message: Optional[str] = None):
        """设置设备状态"""
        if self.status != new_status:
            old_status = self.status
            self.status = new_status
            log_message = f"[{self.env.now:.2f}] 🔄 {self.id}: 状态变更 {old_status.value} → {new_status.value}"
            if message:
                log_message += f" ({message})"
            print(log_message)

    def can_operate(self) -> bool:
        """检查设备是否可以操作"""
        # 检查冻结状态
        return self.status not in [
            DeviceStatus.FAULT,
            DeviceStatus.MAINTENANCE,
            DeviceStatus.BLOCKED,
        ]

    def get_detailed_status(self) -> DeviceDetailedStatus:
        """获取设备详细状态"""
        return DeviceDetailedStatus(
            device_id=self.id,
            device_type=self.device_type,
            current_status=self.status,
            temperature=self._specific_attributes.get("temperature", 25.0),
            vibration_level=self._specific_attributes.get("vibration_level", 0.0),
            power_consumption=self._specific_attributes.get("power_consumption", 100.0),
            efficiency_rate=getattr(self.performance_metrics, "efficiency_rate", 100.0),
            cycle_count=0,  # 简化实现
            last_maintenance_time=0.0,  # 简化实现
            operating_hours=self.env.now / 3600.0,  # 转换为小时
            fault_symptom=self.fault_symptom,
            frozen_until=None,  # 简化故障系统不使用冻结机制
            precision_level=self._specific_attributes.get("precision_level", 100.0),
            tool_wear_level=self._specific_attributes.get("tool_wear_level", 0.0),
            lubricant_level=self._specific_attributes.get("lubricant_level", 100.0),
            battery_level=self._specific_attributes.get("battery_level", 100.0),
            position_accuracy=self._specific_attributes.get("position_accuracy", 100.0),
            load_weight=self._specific_attributes.get("load_weight", 0.0),
        )

    def _get_fault_topic(self) -> str:
        """Generates the correct fault topic based on context."""
        if self.topic_manager and self.line_id:
            return self.topic_manager.get_fault_alert_topic(self.line_id)
        else:
            return DEVICE_ALERT_TOPIC

    def report_buffer_full(self, buffer_name: str):
        """报告缓冲区满"""
        topic = self._get_fault_topic()
        payload = {
            "event_type": "buffer_full",
            "data": {
                "device_id": self.id,
                "buffer_name": buffer_name,
                "timestamp": self.env.now,
                "severity": "warning",
            },
        }
        self._publish_fault_event(topic, payload)
        print(f"[{self.env.now:.2f}] 📦 {self.id}: 缓冲区满告警 ({buffer_name})")

    def _publish_fault_event(self, topic: str, payload: dict):
        """发布故障事件到MQTT"""
        if self.mqtt_client:
            self.mqtt_client.publish(topic, payload)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(id='{self.id}', status='{self.status.value}')"
        )

    def recover(self):
        """Default recovery logic."""
        # 只有当设备处于FAULT状态时才恢复
        # 避免覆盖其他合法状态（如BLOCKED）
        if self.status == DeviceStatus.FAULT:
            self.set_status(DeviceStatus.IDLE)


class Vehicle(Device):
    """
    Base class for mobile entities like AGVs.
    """

    def __init__(
        self,
        env: simpy.Environment,
        id: str,
        position: Tuple[int, int],
        speed_mps: float,
        mqtt_client=None,
    ):
        super().__init__(env, id, position, "vehicle", mqtt_client)
        self.speed_mps = speed_mps


class BaseConveyor(Device, ABC):
    """
    Abstract base class for different types of conveyors.
    """

    def __init__(
        self,
        env: simpy.Environment,
        id: str,
        position: Tuple[int, int],
        transfer_time: float,
        line_id: Optional[str] = None,
        interacting_points: list = [],
        topic_manager: Optional[TopicManager] = None,
        mqtt_client=None,
    ):
        super().__init__(env, id, position, "conveyor", mqtt_client, interacting_points)

    @abstractmethod
    def push(self, product):
        """Add a product to the conveyor."""
        pass

    @abstractmethod
    def pop(self):
        """Remove a product from the conveyor."""
        pass

    @abstractmethod
    def is_full(self):
        """Check if the conveyor is full."""
        pass

    @abstractmethod
    def is_empty(self):
        """Check if the conveyor is empty."""
        pass

    @abstractmethod
    def get_buffer(self):
        """Get the internal buffer of the conveyor."""
        pass

    @abstractmethod
    def set_downstream_station(self, station):
        """Set the station that receives products from this conveyor."""
        pass
