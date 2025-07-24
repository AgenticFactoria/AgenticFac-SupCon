# config/schemas.py
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum

# --- Enums for Statuses and Priorities ---


class DeviceStatus(str, Enum):
    IDLE = "idle"
    PROCESSING = "processing"
    MAINTENANCE = "maintenance"
    SCRAP = "scrap"

    WORKING = "working"  # 正常工作中
    BLOCKED = "blocked"  # 被堵塞
    FAULT = "fault"  # 故障状态

    # AGV
    MOVING = "moving"
    INTERACTING = "interacting"  # New status for device-to-device interaction
    CHARGING = "charging"


class OrderPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# --- 新增：设备详细状态信息 ---


class DeviceDetailedStatus(BaseModel):
    """设备详细状态信息，用于inspect功能"""

    # 基础信息
    device_id: str = Field(..., description="设备ID")
    device_type: str = Field(..., description="设备类型（station/agv）")
    current_status: DeviceStatus = Field(..., description="当前设备状态")

    # 性能指标
    temperature: float = Field(..., description="设备温度（°C）")
    vibration_level: float = Field(..., description="振动水平（mm/s）")
    power_consumption: float = Field(..., description="功耗（W）")
    efficiency_rate: float = Field(..., description="效率率（%）")

    # 工作状态
    cycle_count: int = Field(..., description="工作循环次数")
    last_maintenance_time: float = Field(..., description="上次维护时间")
    operating_hours: float = Field(..., description="运行小时数")

    # 故障相关
    fault_symptom: Optional[str] = Field(None, description="故障症状")
    frozen_until: Optional[float] = Field(None, description="冻结到什么时候")

    # 特定于工站的属性
    precision_level: Optional[float] = Field(None, description="加工精度水平")
    tool_wear_level: Optional[float] = Field(None, description="刀具磨损程度")
    lubricant_level: Optional[float] = Field(None, description="润滑油水平")

    # 特定于AGV的属性
    battery_level: Optional[float] = Field(None, description="电池电量")
    position_accuracy: Optional[float] = Field(None, description="定位精度")
    load_weight: Optional[float] = Field(None, description="当前载重")


class DiagnosisResult(BaseModel):
    """诊断结果schema"""

    device_id: str = Field(..., description="设备ID")
    diagnosis_command: str = Field(..., description="诊断命令")
    is_correct: bool = Field(..., description="诊断是否正确")
    repair_time: float = Field(..., description="修复时间（秒）")
    penalty_applied: bool = Field(..., description="是否应用了惩罚")
    affected_devices: List[str] = Field([], description="受影响的其他设备")
    can_skip: bool = Field(..., description="是否可以跳过等待时间")


# --- Schemas for MQTT Messages ---


class AgentCommand(BaseModel):
    """
    Schema for commands sent by the agent to the factory.
    Published to: factory/agent/commands
    """

    command_id: Optional[str] = Field(None, description="The ID of the command.")
    action: str = Field(
        ..., description="The action to be performed, e.g., 'move_agv'."
    )
    target: str = Field(..., description="The ID of the device or entity to act upon.")
    params: Dict[str, Any] = Field(
        {}, description="A dictionary of parameters for the action."
    )


class SystemResponse(BaseModel):
    """
    Schema for responses sent by the system to the agent.
    Published to: factory/agent/responses
    """

    timestamp: float = Field(..., description="Simulation timestamp of the response.")
    command_id: Optional[str] = Field(None, description="The ID of the command.")
    response: str = Field(..., description="The response to the command.")


class ProductInfo(BaseModel):
    """简化的产品信息，用于MQTT传输"""

    id: str = Field(..., description="Product ID")
    product_type: str = Field(..., description="Product type (P1, P2, P3)")
    quality_score: float = Field(..., description="Current quality score")
    rework_count: int = Field(0, description="Number of reworks")


class StationStatus(BaseModel):
    """
    Schema for the status of a production station.
    Published to: NLDF/line1/station/{id}/status
    """

    timestamp: float = Field(
        ..., description="Simulation timestamp of the status update."
    )
    source_id: str = Field(..., description="ID of the station (e.g., 'Station_A').")
    status: DeviceStatus = Field(..., description="Current status of the station.")
    message: Optional[str] = Field(
        None,
        description="Current action message, e.g., 'emergency charging', 'voluntary charging', 'moving to P1'.",
    )
    buffer: List[str] = Field(..., description="List of product IDs in the buffer.")
    stats: Dict[str, Any] = Field(..., description="Statistics of the station.")
    # Optional fields, primarily for QualityChecker
    output_buffer: List[str] = Field(
        [], description="List of product IDs in the output buffer."
    )


class AGVStatus(BaseModel):
    """
    Schema for the status of an Automated Guided Vehicle (AGV).
    Published to: NLDF/line1/agv/{id}/status
    """

    timestamp: float = Field(
        ..., description="Simulation timestamp of the status update."
    )
    source_id: str = Field(..., description="ID of the AGV (e.g., 'AGV_1').")
    status: DeviceStatus = Field(..., description="Current status of the AGV.")
    speed_mps: float = Field(..., description="Current speed of the AGV (m/s).")
    current_point: str = Field(..., description="Current point of the AGV, e.g., 'P1'.")
    position: Dict[str, float] = Field(
        ..., description="Current coordinates of the AGV, e.g., {'x': 10.0, 'y': 15.0}."
    )
    target_point: Optional[str] = Field(
        None, description="Target point of the AGV if moving. eg. 'P1'"
    )
    estimated_time: float = Field(
        ...,
        description="Estimated time to complete the task or moving to the target point.",
    )
    payload: List[str] = Field(
        ..., description="List of product IDs currently being carried."
    )
    battery_level: float = Field(
        ..., ge=0, le=100, description="Current battery level (0-100%)."
    )
    message: Optional[str] = Field(
        None,
        description="Current action message, e.g., 'emergency charging', 'voluntary charging', 'moving to P1'.",
    )


class ConveyorStatus(BaseModel):
    """传送带状态的数据模型"""

    timestamp: float = Field(
        ..., description="Simulation timestamp of the status update."
    )
    source_id: str = Field(..., description="ID of the conveyor (e.g., 'Conveyor_1').")
    status: DeviceStatus = Field(..., description="Current status of the conveyor.")
    message: Optional[str] = Field(
        None,
        description="Current action message, e.g., 'emergency charging', 'voluntary charging', 'moving to P1'.",
    )
    # For TripleBufferConveyor, buffer is the main buffer
    buffer: List[str] = Field(..., description="List of product IDs in the buffer.")
    # Only for TripleBufferConveyor
    upper_buffer: Optional[List[str]] = Field(
        None, description="List of product IDs in the upper buffer."
    )
    lower_buffer: Optional[List[str]] = Field(
        None, description="List of product IDs in the lower buffer."
    )
    # 可选：包含详细产品信息
    # buffer_details: Optional[List[ProductInfo]] = Field(None, description="Detailed product information in buffers")


class WarehouseStatus(BaseModel):
    """
    Schema for the status of a warehouse.
    Published to: NLDF/line1/warehouse/{id}/status
    """

    timestamp: float = Field(
        ..., description="Simulation timestamp of the status update."
    )
    source_id: str = Field(
        ..., description="ID of the warehouse (e.g., 'Warehouse_1')."
    )
    message: str = Field(..., description="Message of the warehouse.")
    buffer: List[str] = Field(..., description="List of product IDs in the buffer.")
    stats: Dict[str, Any] = Field(..., description="Statistics of the warehouse.")


class OrderItem(BaseModel):
    """A single item within a new order."""

    product_type: str = Field(
        ..., description="Type of the product (e.g., 'P1', 'P2', 'P3')."
    )
    quantity: int = Field(
        ..., gt=0, description="Number of units for this product type."
    )


class NewOrder(BaseModel):
    """
    Schema for a new manufacturing order.
    Published to: factory/orders/new
    """

    order_id: str = Field(..., description="Unique ID for the new order.")
    created_at: float = Field(
        ..., description="Simulation timestamp when the order was created."
    )
    items: List[OrderItem] = Field(
        ..., description="List of products and quantities in the order."
    )
    priority: OrderPriority = Field(..., description="Priority level of the order.")
    deadline: float = Field(
        ..., description="Simulation timestamp by which the order should be completed."
    )


class FaultAlert(BaseModel):
    """
    Schema for fault alerts.
    Published to: NLDF/line1/alerts/{device_id}
    """

    timestamp: float = Field(..., description="Simulation timestamp of the alert.")
    device_id: str = Field(
        ..., description="ID of the device that triggered the alert."
    )
    alert_type: str = Field(..., description="Type of the alert.")
    symptom: str = Field(..., description="Symptom of the alert.")
    fault_type: str = Field(..., description="Type of the fault.")
    estimated_duration: float = Field(
        ..., description="Estimated duration of the fault (seconds)."
    )
    message: str = Field(..., description="Message of the alert.")


class KPIUpdate(BaseModel):
    """
    Schema for Key Performance Indicator (KPI) updates.
    Published to: factory/kpi/update
    """

    timestamp: float = Field(..., description="Simulation timestamp of the KPI update.")

    # Production Efficiency (40%)
    order_completion_rate: float = Field(
        ..., description="Percentage of orders completed."
    )
    average_production_cycle: float = Field(
        ..., description="Weighted average of actual/theoretical production time ratio."
    )
    on_time_delivery_rate: float = Field(
        ..., description="Percentage of orders completed on time."
    )
    device_utilization: float = Field(
        ..., description="Average device utilization rate (%)."
    )

    # Quality Metrics
    first_pass_rate: float = Field(
        ..., description="Percentage of products passing quality check on first try."
    )

    # Cost Control (30%)
    total_production_cost: float = Field(
        ..., description="Total accumulated production cost."
    )
    material_costs: float = Field(..., description="Total material costs.")
    energy_costs: float = Field(..., description="Total energy costs.")
    maintenance_costs: float = Field(..., description="Total maintenance costs.")
    scrap_costs: float = Field(..., description="Total costs from scrapped products.")

    # AGV Efficiency Metrics
    charge_strategy_efficiency: float = Field(
        0.0, description="Percentage of active charges vs total charges (%)."
    )
    agv_energy_efficiency: float = Field(
        0.0, description="AGV tasks completed per minute of charging."
    )
    agv_utilization: float = Field(
        0.0, description="Average AGV transport time utilization (%)."
    )

    # Raw Counts for Reference
    total_orders: int = Field(..., description="Total number of orders received.")
    completed_orders: int = Field(..., description="Number of completed orders.")
    active_orders: int = Field(..., description="Number of currently active orders.")
    total_products: int = Field(..., description="Total number of products produced.")
    active_faults: int = Field(..., description="Number of currently active faults.")


class FactoryStatus(BaseModel):
    """
    Schema for the overall factory status.
    Published to: factory/status
    """

    timestamp: float = Field(..., description="Simulation timestamp.")
    total_stations: int = Field(
        ..., description="Total number of stations in the factory."
    )
    total_agvs: int = Field(..., description="Total number of AGVs in the factory.")
    active_orders: int = Field(..., description="Number of currently active orders.")
    total_orders: int = Field(..., description="Total number of orders received.")
    completed_orders: int = Field(..., description="Number of completed orders.")
    active_faults: int = Field(..., description="Number of currently active faults.")
    simulation_time: float = Field(..., description="Current simulation time.")
