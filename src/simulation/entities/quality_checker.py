# src/simulation/entities/quality_checker.py
import simpy
import random
from typing import Dict, Tuple, Optional
from enum import Enum

from config.schemas import DeviceStatus, StationStatus
from src.simulation.entities.station import Station
from src.simulation.entities.product import Product, QualityStatus
from src.utils.topic_manager import TopicManager


class SimpleDecision(Enum):
    """简化的质量检测决策"""

    PASS = "pass"  # 通过
    SCRAP = "scrap"  # 报废
    REWORK = "rework"  # 返工 (回到上一个工站)


class QualityChecker(Station):
    """
    简化版质量检测站 - 只保留核心功能

    核心逻辑：
    1. 基于产品质量分数做出简单决策
    2. 通过/报废/返工三种结果
    3. 最小化配置参数
    4. 增加output_buffer，满时阻塞并告警
    """

    def __init__(
        self,
        env: simpy.Environment,
        id: str,
        position: Tuple[int, int],
        buffer_size: int = 1,
        processing_times: Dict[str, Tuple[int, int]] = {},
        pass_threshold: float = 80.0,  # 合格阈值
        scrap_threshold: float = 60.0,  # 报废阈值
        output_buffer_capacity: int = 5,  # 新增，output buffer容量
        mqtt_client=None,
        interacting_points: list = [],
        topic_manager: Optional[TopicManager] = None,
        line_id: Optional[str] = None,
    ):
        # 默认检测时间
        if processing_times is None:
            processing_times = {"P1": (10, 15), "P2": (12, 18), "P3": (10, 15)}

        # Initialize output buffer before calling super().__init__()
        # since publish_status() is called in parent's __init__
        self.pass_threshold = pass_threshold
        self.scrap_threshold = scrap_threshold
        self.output_buffer_capacity = output_buffer_capacity
        self.output_buffer = simpy.Store(env, capacity=output_buffer_capacity)

        super().__init__(
            env,
            id,
            position,
            topic_manager=topic_manager,
            line_id=line_id,
            buffer_size=buffer_size,
            processing_times=processing_times,
            downstream_conveyor=None,
            mqtt_client=mqtt_client,
            interacting_points=interacting_points,
        )

        # 简单统计
        self.stats = {
            "inspected_count": 0,
            "total_processing_time": 0.0,
            "average_processing_time": 0.0,
            "passed_count": 0,
            "reworked_count": 0,
            "scrapped_count": 0,
            "working_time": 0.0,  # Total time spent in PROCESSING status
            "start_time": env.now,  # Track when station started
        }

        print(
            f"[{self.env.now:.2f}] 🔍 {self.id}: Simple quality checker ready (pass≥{self.pass_threshold}%, scrap≤{self.scrap_threshold}%)"
        )
        # The run process is already started by the parent Station class

    def publish_status(self, message: Optional[str] = None):
        """Publishes the current status of the station to MQTT."""
        if not self.mqtt_client or not self.mqtt_client.is_connected():
            return

        status_data = StationStatus(
            timestamp=self.env.now,
            source_id=self.id,
            status=self.status,
            buffer=[p.id for p in self.buffer.items],
            stats=self.stats,
            output_buffer=[p.id for p in self.output_buffer.items],
            message=message,
        )
        if self.topic_manager and self.line_id:
            topic = self.topic_manager.get_station_status_topic(self.line_id, self.id)
        else:
            from config.topics import get_station_status_topic

            topic = get_station_status_topic(self.id)
        self.mqtt_client.publish(topic, status_data.model_dump_json(), retain=False)

    def process_product(self, product: Product):
        """
        Quality check process following Station's timeout-get-put pattern.
        """
        try:
            print(
                f"[{self.env.now:.2f}] [DEBUG] {self.id}: process_product called for {product.id}, buffer={len(self.buffer.items)}, output_buffer={len(self.output_buffer.items)}"
            )
            # Check if the device can operate
            if not self.can_operate():
                msg = f"[{self.env.now:.2f}] ⚠️  {self.id}: can not process product, device is not available"
                print(msg)
                self.publish_status(msg)
                return

            self.set_status(DeviceStatus.PROCESSING)
            print(
                f"[{self.env.now:.2f}] [DEBUG] {self.id}: set_status(PROCESSING), buffer={len(self.buffer.items)}, output_buffer={len(self.output_buffer.items)}"
            )
            self.publish_status()

            # Record processing start and get processing time
            min_time, max_time = self.processing_times.get(
                product.product_type, (10, 15)
            )
            processing_time = random.uniform(min_time, max_time)

            # Apply efficiency and fault impacts
            efficiency_factor = (
                getattr(self.performance_metrics, "efficiency_rate", 100.0) / 100.0
            )
            actual_processing_time = processing_time / efficiency_factor

            msg = f"[{self.env.now:.2f}] 🔍 {self.id}: 检测产品中... (预计{actual_processing_time:.1f}s)"
            print(msg)
            self.publish_status(msg)

            # The actual processing work (timeout-get pattern like Station)
            yield self.env.timeout(actual_processing_time)
            print(
                f"[{self.env.now:.2f}] [DEBUG] {self.id}: timeout finished for {product.id}, buffer={len(self.buffer.items)}, output_buffer={len(self.output_buffer.items)}"
            )
            product = yield self.buffer.get()
            print(
                f"[{self.env.now:.2f}] [DEBUG] {self.id}: got product {product.id} from buffer, buffer={len(self.buffer.items)}, output_buffer={len(self.output_buffer.items)}"
            )
            product.process_at_station(self.id, self.env.now)

            # Update statistics upon successful completion
            self.stats["inspected_count"] += 1
            self.stats["total_processing_time"] += actual_processing_time
            self.stats["average_processing_time"] = (
                self.stats["total_processing_time"] / self.stats["inspected_count"]
            )

            # Perform quality inspection
            decision = self._make_simple_decision(product)
            print(
                f"[{self.env.now:.2f}] [DEBUG] {self.id}: decision for {product.id} is {decision}, buffer={len(self.buffer.items)}, output_buffer={len(self.output_buffer.items)}"
            )

            # Processing finished successfully
            msg = f"[{self.env.now:.2f}] {self.id}: {product.id} finished inspecting, actual processing time: {actual_processing_time:.1f}s"
            print(msg)
            self.publish_status(msg)

            # Execute decision (equivalent to transfer_product_to_next_stage)
            yield self.env.process(self._execute_quality_decision(product, decision))

        except simpy.Interrupt as e:
            print(
                f"[{self.env.now:.2f}] ⚠️ {self.id}: Inspection of product {product.id} was interrupted: {e.cause}"
            )
            print(
                f"[{self.env.now:.2f}] [DEBUG] {self.id}: INTERRUPT, buffer={len(self.buffer.items)}, output_buffer={len(self.output_buffer.items)}"
            )
            if product not in self.buffer.items:
                # 产品已取出，说明检测时间已经完成，应该继续流转
                print(
                    f"[{self.env.now:.2f}] 🚚 {self.id}: 产品 {product.id} 已检测完成，继续流转"
                )
                decision = self._make_simple_decision(product)
                yield self.env.process(
                    self._execute_quality_decision(product, decision)
                )
            else:
                # 产品还在buffer中，说明在timeout期间被中断，等待下次处理
                print(
                    f"[{self.env.now:.2f}] ⏸️  {self.id}: 产品 {product.id} 检测被中断，留在buffer中"
                )
        finally:
            print(
                f"[{self.env.now:.2f}] [DEBUG] {self.id}: process_product finally for {product.id}, buffer={len(self.buffer.items)}, output_buffer={len(self.output_buffer.items)}"
            )
            # Clear the action handle once the process is complete or interrupted
            self.action = None

    def _execute_quality_decision(self, product: Product, decision: SimpleDecision):
        """Execute quality decision (equivalent to _transfer_product_to_next_stage)"""
        print(
            f"[{self.env.now:.2f}] [DEBUG] {self.id}: _execute_quality_decision for {product.id}, decision={decision}, buffer={len(self.buffer.items)}, output_buffer={len(self.output_buffer.items)}"
        )

        if decision == SimpleDecision.PASS:
            self.stats["passed_count"] += 1
            msg = f"[{self.env.now:.2f}] ✅ {self.id}: {product.id} passed quality inspection"
            print(msg)
            self.publish_status(msg)

            # Report to KPI calculator
            if hasattr(self, "kpi_calculator") and self.kpi_calculator:
                self.kpi_calculator.complete_order_item(
                    product.order_id, product.product_type, passed_quality=True
                )

            # Check if output buffer is full and report if needed
            if len(self.output_buffer.items) >= self.output_buffer_capacity:
                self.set_status(DeviceStatus.BLOCKED)
                msg = f"[{self.env.now:.2f}] ⚠️ {self.id}: output buffer is full, station is blocked"
                print(msg)
                self.publish_status(msg)
                self.report_buffer_full("output_buffer")
            # TODO: Quality Checker do not have downstream device, dont care about whether downstream can_operate, just cares about buffer full
            # Put product into output buffer (may block if full)
            yield self.output_buffer.put(product)
            msg = f"[{self.env.now:.2f}] 📦 {self.id}: 产品 {product.id} 放入output buffer，等待AGV/人工搬运"

        elif decision == SimpleDecision.SCRAP:
            # Report to KPI calculator
            if hasattr(self, "kpi_calculator") and self.kpi_calculator:
                self.kpi_calculator.complete_order_item(
                    product.order_id, product.product_type, passed_quality=False
                )

            yield self.env.process(
                self._handle_product_scrap(product, "quality_inspection_failed")
            )
            self.stats["scrapped_count"] += 1
            self.set_status(DeviceStatus.SCRAP)
            msg = f"[{self.env.now:.2f}] ❌ {self.id}: {product.id} scrapping"
            self.publish_status(msg)
            msg = f"[{self.env.now:.2f}] ⚠️ {self.id}: {product.id} scrapped"

        elif decision == SimpleDecision.REWORK:
            self.stats["reworked_count"] += 1
            # 返工：回到最后一个加工工站
            last_station = self._get_last_processing_station(product)
            if last_station:
                # 检查output buffer是否满
                if len(self.output_buffer.items) >= self.output_buffer_capacity:
                    self.set_status(DeviceStatus.BLOCKED)
                    self.publish_status("output buffer is full, station is blocked")
                    self.report_buffer_full("output_buffer")

                # 将返工产品放入output buffer，等待AGV运送
                yield self.output_buffer.put(product)
                msg = f"[{self.env.now:.2f}] 📦 {self.id}: {product.id} reworked to {last_station}, put into output buffer, waiting for AGV to deliver"

            else:
                msg = f"[{self.env.now:.2f}] ⚠️  {self.id}: can not determine rework station, product scrapped"
                yield self.env.process(
                    self._handle_product_scrap(product, "rework_failed")
                )

        # Set status back to IDLE after the operation is complete
        self.set_status(DeviceStatus.IDLE)
        print(msg)
        self.publish_status(msg if msg else None)

    def _handle_product_scrap(self, product, reason: str):
        """Handle product scrapping due to quality issues"""

        # Set product status to scrapped
        product.quality_score = 0.0
        product.quality_status = QualityStatus.SCRAP

        # Simulate scrap handling time
        yield self.env.timeout(2.0)

    def _make_simple_decision(self, product: Product) -> SimpleDecision:
        """简化的决策逻辑：最多一次返工"""
        quality_percentage = product.quality_score * 100

        # 如果已经返工过一次
        if product.rework_count >= 1:
            # 返工后仍然不合格，直接报废
            if quality_percentage < self.pass_threshold:
                return SimpleDecision.SCRAP
            else:
                return SimpleDecision.PASS

        # 首次检测决策
        if quality_percentage >= self.pass_threshold:
            return SimpleDecision.PASS
        elif quality_percentage <= self.scrap_threshold:
            return SimpleDecision.SCRAP
        else:
            # 中间质量，可以返工
            return SimpleDecision.REWORK

    def _get_last_processing_station(self, product: Product) -> str:
        """获取产品最后处理的工站 (排除QualityCheck)"""
        processing_stations = [s for s in product.processing_stations if s != self.id]
        return processing_stations[-1] if processing_stations else ""

    def get_simple_stats(self) -> Dict:
        """获取简化的统计信息"""
        total = self.stats["inspected_count"]
        if total == 0:
            return {"inspected": 0, "pass_rate": 0, "scrap_rate": 0, "rework_rate": 0}

        return {
            "inspected": total,
            "passed": self.stats["passed_count"],
            "scrapped": self.stats["scrapped_count"],
            "reworked": self.stats["reworked_count"],
            "pass_rate": round(self.stats["passed_count"] / total * 100, 1),
            "scrap_rate": round(self.stats["scrapped_count"] / total * 100, 1),
            "rework_rate": round(self.stats["reworked_count"] / total * 100, 1),
            "buffer_level": self.get_buffer_level(),
        }

    def reset_stats(self):
        """重置统计数据"""
        self.stats = {
            "inspected_count": 0,
            "total_processing_time": 0.0,
            "average_processing_time": 0.0,
            "passed_count": 0,
            "reworked_count": 0,
            "scrapped_count": 0,
            "working_time": 0.0,  # Total time spent in PROCESSING status
            "start_time": self.env.now,  # Track when station started
        }

    def pop(self, buffer_type=None):
        """Remove and return a product from the specified buffer.

        Args:
            buffer_type: "buffer" for input buffer, "output_buffer" for output buffer

        Returns:
            The removed product
        """
        if buffer_type == "output_buffer" or buffer_type is None:
            # 从 output_buffer 取货（默认）
            product = yield self.output_buffer.get()
            msg = f"Product {product.id} taken from {self.id} output_buffer by AGV"
        else:
            # 从输入 buffer 取货，需要检查是否正在处理
            if (
                len(self.buffer.items) > 0
                and self.current_product_id == self.buffer.items[0].id
            ):
                raise ValueError(
                    f"Product {self.current_product_id} is currently being processed and cannot be taken"
                )

            product = yield self.buffer.get()
            msg = f"Product {product.id} taken from {self.id} input buffer by AGV"

        print(f"[{self.env.now:.2f}] 📤 {self.id}: {msg}")
        self.publish_status(msg)
        return product

    def add_product_to_outputbuffer(self, product: Product):
        """Add a product to its output buffer (used by AGV for delivery)"""
        yield self.output_buffer.put(product)
        print(
            f"[{self.env.now:.2f}] 📦 {self.id}: 运出产品 {product.id} 到output buffer"
        )
        return True
