# simulation/entities/conveyor.py
import simpy
from typing import Optional
from src.simulation.entities.base import BaseConveyor
from typing import Tuple
from src.utils.topic_manager import TopicManager
from config.schemas import DeviceStatus, ConveyorStatus
from config.topics import get_conveyor_status_topic


class Conveyor(BaseConveyor):
    """
    Conveyor with limited capacity, simulating a production line conveyor belt.
    Now uses simpy.Store for event-driven simulation and supports auto-transfer.
    """

    def __init__(
        self,
        env,
        id,
        capacity,
        position: Tuple[int, int],
        interacting_points: list,
        transfer_time: float = 5.0,
        mqtt_client=None,
        kpi_calculator=None,
        topic_manager: Optional[TopicManager] = None,
        line_id: Optional[str] = None,
    ):
        super().__init__(
            env,
            id,
            position,
            transfer_time,
            line_id,
            interacting_points,
            topic_manager,
            mqtt_client,
        )
        self.capacity = capacity
        self.buffer = simpy.Store(env, capacity=capacity)
        self.downstream_station = None  # 下游工站引用
        self.action = None  # 保留但不使用，兼容 fault system 接口
        self.transfer_time = transfer_time  # 模拟搬运时间
        self.topic_manager = topic_manager
        self.line_id = line_id
        self.main_process = None  # 主运行进程
        self.active_processes = {}  # Track active transfer processes per product
        self.product_start_times = {}  # Track when each product started transfer
        self.product_elapsed_times = {}  # Track elapsed time before interruption

        # 阻塞管理
        self.blocked_leader_process = None  # 正在等待下游的领头产品进程
        self.kpi_calculator = kpi_calculator  # KPI calculator dependency

        # 传送带默认状态为工作中
        self.status = DeviceStatus.WORKING
        self.publish_status("Conveyor initialized")
        # Initialize device utilization tracking
        if self.kpi_calculator:
            self.kpi_calculator.update_device_utilization(self.id, self.line_id, 0.0)

        # Start background process to update total time for utilization calculation
        self.env.process(self._update_total_time())

    def publish_status(self, message: Optional[str] = None):
        """直接发布传送带状态，不通过set_status"""
        if not self.mqtt_client or not self.mqtt_client.is_connected():
            return

        status_data = ConveyorStatus(
            timestamp=self.env.now,
            source_id=self.id,
            status=self.status,
            buffer=[p.id for p in self.buffer.items],
            message=message,
            upper_buffer=None,
            lower_buffer=None,
        )
        if self.topic_manager and self.line_id:
            topic = self.topic_manager.get_conveyor_status_topic(self.line_id, self.id)
        else:
            topic = get_conveyor_status_topic(self.id)
        self.mqtt_client.publish(topic, status_data.json(), retain=False)

    def set_downstream_station(self, station):
        """Set the downstream station for auto-transfer."""
        self.downstream_station = station
        if self.main_process is None:
            self.main_process = self.env.process(self.run())

    def push(self, product):
        """Put a product on the conveyor (may block if full)."""
        result = self.buffer.put(product)
        print(
            f"[{self.env.now:.2f}] [DEBUG] Conveyor {self.id}: push {product.id}, buffer={len(self.buffer.items)}/{self.capacity}"
        )
        # 产品添加后发布状态
        self.publish_status()
        return result

    def pop(self):
        """Remove and return a product from the conveyor (may block if empty)."""
        product = yield self.buffer.get()
        print(
            f"[{self.env.now:.2f}] [DEBUG] Conveyor {self.id}: pop {product.id}, buffer={len(self.buffer.items)}/{self.capacity}"
        )

        # 如果该产品有对应的处理进程，中断并删除它
        if product.id in self.active_processes:
            process = self.active_processes[product.id]
            if process.is_alive:
                process.interrupt("Product removed by AGV")
                print(
                    f"[{self.env.now:.2f}] 🚫 Conveyor {self.id}: Interrupted process for product {product.id} (taken by AGV)"
                )
            del self.active_processes[product.id]

            # 清理该产品的时间记录
            if product.id in self.product_start_times:
                del self.product_start_times[product.id]
            if product.id in self.product_elapsed_times:
                del self.product_elapsed_times[product.id]

        # 产品移除后发布状态
        self.publish_status()
        return product

    def get_buffer(self):
        return self.buffer

    def is_full(self):
        return len(self.buffer.items) >= self.capacity

    def is_empty(self):
        return len(self.buffer.items) == 0

    def peek(self):
        if self.buffer.items:
            return self.buffer.items[0]
        return None

    def _update_total_time(self):
        """Background process to update total time for KPI utilization calculation"""
        while True:
            yield self.env.timeout(10.0)  # Update every 10 seconds
            if self.kpi_calculator:
                self.kpi_calculator.update_device_utilization(
                    self.id, self.line_id, self.env.now
                )

    def run(self):
        """Main operational loop for the conveyor. This should NOT be interrupted by faults."""
        while True:
            # 等待设备可操作且buffer有产品
            yield self.env.process(self._wait_for_ready_state())

            # 检查是否应该解除阻塞状态
            if self.status == DeviceStatus.BLOCKED:
                # 如果下游工站恢复正常或者没有正在等待的领头进程，解除阻塞
                if self.downstream_station and self.downstream_station.can_operate():
                    if (
                        self.blocked_leader_process is None
                        or not self.blocked_leader_process.is_alive
                    ):
                        print(
                            f"[{self.env.now:.2f}] 🔓 Conveyor {self.id}: Downstream recovered or no leader waiting, unblocking"
                        )
                        self._unblock_all_products()

            # 检查buffer中的每个产品，如果还没有处理进程就启动一个
            for item in list(self.buffer.items):  # 使用list避免迭代时修改
                if item.id not in self.active_processes:
                    # 只有在非阻塞状态下才为新产品启动处理进程
                    if self.status != DeviceStatus.BLOCKED:
                        # 为这个产品启动一个处理进程
                        process = self.env.process(self.process_single_item(item))
                        self.active_processes[item.id] = process
                    else:
                        # 如果是阻塞状态，检查这个产品是否是第一个（领头产品）
                        if (
                            len(self.buffer.items) > 0
                            and self.buffer.items[0].id == item.id
                        ):
                            # 这是领头产品，允许启动进程
                            process = self.env.process(self.process_single_item(item))
                            self.active_processes[item.id] = process
                            print(
                                f"[{self.env.now:.2f}] 👑 Conveyor {self.id}: Starting process for leader product {item.id} despite blocked status"
                            )

            # 清理已完成的进程
            completed_ids = []
            for product_id, process in self.active_processes.items():
                if not process.is_alive:
                    completed_ids.append(product_id)
            for product_id in completed_ids:
                del self.active_processes[product_id]

            yield self.env.timeout(0.1)

    def _wait_for_ready_state(self):
        """等待设备处于可操作状态且buffer有产品"""
        while True:
            # 如果没有下游站点，等待
            if self.downstream_station is None:
                yield self.env.timeout(1)
                continue

            # 如果buffer为空，等待
            if len(self.buffer.items) == 0 or not self.can_operate():
                yield self.env.timeout(0.1)
                continue

            # 设备可操作且有产品，返回
            return

    def process_single_item(self, product):
        """Process a single item with timeout-get-put pattern. This CAN be interrupted by faults."""
        actual_product = None
        try:
            # 检查下游站点是否存在
            if self.downstream_station is None:
                return

            # 如果当前是blocked状态且不是领头产品，不应该继续
            if self.status == DeviceStatus.BLOCKED:
                is_leader = (
                    len(self.buffer.items) > 0 and self.buffer.items[0].id == product.id
                )
                if not is_leader:
                    print(
                        f"[{self.env.now:.2f}] 🚫 Conveyor {self.id}: Product {product.id} blocked at start, not leader"
                    )
                    return

            self.set_status(DeviceStatus.WORKING)
            self.publish_status()

            print(
                f"[{self.env.now:.2f}] 📋 Conveyor {self.id}: Added {product.id} to processing order, current order: {[p.id for p in self.buffer.items]}"
            )

            # 计算剩余传输时间（处理中断后恢复的情况）
            if product.id in self.product_elapsed_times:
                # 恢复传输：使用之前记录的已传输时间
                elapsed_time = self.product_elapsed_times[product.id]
                remaining_time = max(0, self.transfer_time - elapsed_time)
                msg = f"[{self.env.now:.2f}] Conveyor {self.id}: {product.id} resume transferring, elapsed {elapsed_time:.1f}s, remaining {remaining_time:.1f}s"
            else:
                # 第一次开始传输
                remaining_time = self.transfer_time
                msg = f"[{self.env.now:.2f}] Conveyor {self.id}: {product.id} start transferring, need {remaining_time:.1f}s"

            self.product_start_times[product.id] = self.env.now
            print(msg)
            self.publish_status(msg)

            # Track start of working time for KPI
            yield self.env.timeout(remaining_time)
            is_first_product = self.buffer.items[0].id == product.id
            # Report energy cost and working time for this transfer
            if self.kpi_calculator:
                self.kpi_calculator.add_energy_cost(
                    self.id, self.line_id, remaining_time, is_peak_hour=False
                )
                # Working time is already tracked in add_energy_cost

            # 传输完成，从buffer获取产品（get）
            actual_product = yield self.buffer.get()

            # 确保获取的是正确的产品
            if actual_product.id != product.id:
                # 如果不是预期的产品，放回去
                yield self.buffer.put(actual_product)
                msg = f"[{self.env.now:.2f}] Conveyor {self.id}: unexpected product order, retrying"
                print(msg)
                self.publish_status(msg)
                return

            self.publish_status()

            # 使用处理顺序信息
            if is_first_product:
                # 这是最前面的产品，设为领头进程
                self.blocked_leader_process = self.env.active_process
                print(
                    f"[{self.env.now:.2f}] 🎯 Conveyor {self.id}: {actual_product.id} is the leader product (first in order)"
                )

                downstream_full = self.downstream_station.is_full()
                print(
                    f"[{self.env.now:.2f}] 🔍 Conveyor {self.id}: Downstream buffer {len(self.downstream_station.buffer.items)}/{self.downstream_station.buffer.capacity}, full={downstream_full}, can opeatate:{self.downstream_station.can_operate()}"
                )

                if (
                    downstream_full or not self.downstream_station.can_operate()
                ) and self.status != DeviceStatus.BLOCKED:
                    # 下游已满或下游工站不可操作，阻塞其他产品
                    self._block_all_products()

                while not self.downstream_station.can_operate():
                    yield self.env.timeout(0.1)
                # 尝试放入下游（可能会阻塞）
                print(
                    f"[{self.env.now:.2f}] ⏳ Conveyor {self.id}: Leader {actual_product.id} trying to put to downstream..."
                )
                yield self.downstream_station.buffer.put(actual_product)

                # 成功放入，如果之前是阻塞状态，现在解除
                if (
                    self.status == DeviceStatus.BLOCKED
                    and self.downstream_station.can_operate()
                ):
                    self._unblock_all_products()

            else:
                # 不是第一个产品
                print(
                    f"[{self.env.now:.2f}] 📦 Conveyor {self.id}: {actual_product.id} is NOT the leader product (order: {[p.id for p in self.buffer.items]})"
                )

                # 非领头产品需要等待，直到轮到它或者传送带解除阻塞
                while self.status == DeviceStatus.BLOCKED:
                    print(
                        f"[{self.env.now:.2f}] ⏳ Conveyor {self.id}: {actual_product.id} waiting for its turn or unblock..."
                    )
                    yield self.env.timeout(0.1)

                # 现在可以尝试放入下游
                yield self.downstream_station.buffer.put(actual_product)

            actual_product.update_location(self.downstream_station.id, self.env.now)
            msg = f"[{self.env.now:.2f}] Conveyor {self.id}: moved product {actual_product.id} to {self.downstream_station.id}"
            print(msg)
            self.publish_status(msg)

            # 清理传输时间记录
            if actual_product.id in self.product_start_times:
                del self.product_start_times[actual_product.id]
            if actual_product.id in self.product_elapsed_times:
                del self.product_elapsed_times[actual_product.id]

        except simpy.Interrupt as e:
            print(
                f"[{self.env.now:.2f}] 🚫 Conveyor {self.id}: Interrupted by{e}: {e.cause}"
            )
            interrupt_reason = str(e.cause) if hasattr(e, "cause") else "Unknown"

            # 如果是AGV取走产品的中断，直接返回
            if "Product removed by AGV" in interrupt_reason:
                print(
                    f"[{self.env.now:.2f}] 🚚 Conveyor {self.id}: Product {product.id} was taken by AGV, stopping process"
                )
                # 时间记录已经在pop()中清理了，这里不需要再清理
                return

            # 记录中断时已经传输的时间（阻塞和故障都需要）
            if product.id in self.product_start_times:
                start_time = self.product_start_times[product.id]
                elapsed_before_interrupt = self.env.now - start_time
                self.product_elapsed_times[product.id] = (
                    self.product_elapsed_times.get(product.id, 0)
                    + elapsed_before_interrupt
                )
                del self.product_start_times[product.id]
                print(
                    f"[{self.env.now:.2f}] 💾 Conveyor {self.id}: 产品 {product.id} 中断前已传输 {elapsed_before_interrupt:.1f}s，剩余 {self.transfer_time - self.product_elapsed_times.get(product.id, 0):.1f}s"
                )

            # 根据中断原因处理
            if "Downstream blocked" in interrupt_reason:
                # 这是阻塞中断
                print(
                    f"[{self.env.now:.2f}] ⏸️ Conveyor {self.id}: Product {product.id} paused due to downstream blockage"
                )
                # 阻塞状态已经由_block_all_products设置，这里不需要重复设置

            else:
                # 这是故障中断
                print(
                    f"[{self.env.now:.2f}] ⚠️ Conveyor {self.id}: Processing of product {product.id} was interrupted by fault"
                )

                # 如果产品已经取出，说明已完成传输，应该放入下游
                if (
                    actual_product
                    and actual_product not in self.buffer.items
                    and self.downstream_station
                ):
                    # 产品已完成传输，直接放入下游
                    print(
                        f"[{self.env.now:.2f}] 📦 Conveyor {self.id}: Product {actual_product.id} already transferred, putting to downstream"
                    )
                    yield self.downstream_station.buffer.put(actual_product)

                    # 更新产品位置
                    actual_product.update_location(
                        self.downstream_station.id, self.env.now
                    )
                    msg = f"[{self.env.now:.2f}] Conveyor {self.id}: moved product {actual_product.id} to {self.downstream_station.id} (during fault interrupt)"
                    print(msg)

                    # 清理时间记录
                    if actual_product.id in self.product_start_times:
                        del self.product_start_times[actual_product.id]
                    if actual_product.id in self.product_elapsed_times:
                        del self.product_elapsed_times[actual_product.id]
                else:
                    # 产品还在传输中，中断是合理的
                    print(
                        f"[{self.env.now:.2f}] 🔄 Conveyor {self.id}: Product {product.id} interrupted during transfer"
                    )

                # 设置故障状态
                self.set_status(DeviceStatus.FAULT)
                self.publish_status()

        finally:
            self.publish_status()

    def recover(self):
        """Custom recovery logic for the conveyor."""
        # 清理不在buffer中的产品的时间记录
        products_in_buffer = {p.id for p in self.buffer.items}

        # 清理start_times
        expired_products = [
            pid for pid in self.product_start_times if pid not in products_in_buffer
        ]
        for pid in expired_products:
            del self.product_start_times[pid]
            print(
                f"[{self.env.now:.2f}] 🗑️ Conveyor {self.id}: 清理过期产品 {pid} 的开始时间记录"
            )

        # 清理elapsed_times
        expired_elapsed = [
            pid for pid in self.product_elapsed_times if pid not in products_in_buffer
        ]
        for pid in expired_elapsed:
            del self.product_elapsed_times[pid]
            print(
                f"[{self.env.now:.2f}] 🗑️ Conveyor {self.id}: 清理过期产品 {pid} 的已传输时间记录"
            )

        # 恢复后，它应该继续工作，而不是空闲
        self.set_status(DeviceStatus.WORKING)
        msg = f"[{self.env.now:.2f}] ✅ Conveyor {self.id} is recovered."
        print(msg)
        self.publish_status(msg)

    def interrupt_all_processing(self):
        """Interrupt all active product processing. Called by fault system."""
        interrupted_count = 0
        for product_id, process in list(self.active_processes.items()):
            if process.is_alive:
                process.interrupt("Fault injected")
                interrupted_count += 1
        print(
            f"[{self.env.now:.2f}] 🚫 Conveyor {self.id}: Interrupted {interrupted_count} product processes"
        )
        return interrupted_count

    def _block_all_products(self, reason="Downstream blocked"):
        """阻塞所有产品处理（除了正在等待的领头产品）"""
        if self.status == DeviceStatus.BLOCKED:
            print(
                f"[{self.env.now:.2f}] [DEBUG] Conveyor {self.id}: already blocked, skip"
            )
            return  # 已经处于阻塞状态

        # 设置阻塞状态
        self.set_status(DeviceStatus.BLOCKED)
        self.publish_status("Conveyor blocked - downstream full")

        # 中断所有非领头的活跃进程（与interrupt_all_processing类似）
        blocked_count = 0
        for product_id, process in list(self.active_processes.items()):
            if process != self.blocked_leader_process and process.is_alive:
                process.interrupt(reason)
                blocked_count += 1

        print(
            f"[{self.env.now:.2f}] 🚧 Conveyor {self.id}: Blocked {blocked_count} products due to downstream blockage"
        )

    def _unblock_all_products(self):
        """解除阻塞，允许产品继续处理"""
        if self.status != DeviceStatus.BLOCKED:
            print(
                f"[{self.env.now:.2f}] [DEBUG] Conveyor {self.id}: not blocked, skip unblock"
            )
            return  # 不在阻塞状态

        self.set_status(DeviceStatus.WORKING)
        self.publish_status("Conveyor unblocked - resuming operation")
        self.blocked_leader_process = None

        print(
            f"[{self.env.now:.2f}] ✅ Conveyor {self.id}: Unblocked, products can resume"
        )


class TripleBufferConveyor(BaseConveyor):
    """
    Conveyor with three buffers:
    - main_buffer: for direct transfer to QualityCheck (auto-transfer)
    - upper_buffer: for P3 products, AGV pickup
    - lower_buffer: for P3 products, AGV pickup
    All buffers use simpy.Store for event-driven simulation.
    """

    def __init__(
        self,
        env,
        id,
        main_capacity,
        upper_capacity,
        lower_capacity,
        position: Tuple[int, int],
        transfer_time: float = 5.0,
        mqtt_client=None,
        interacting_points: list = [],
        kpi_calculator=None,
        topic_manager: Optional[TopicManager] = None,
        line_id: Optional[str] = None,
    ):
        super().__init__(
            env,
            id,
            position,
            transfer_time,
            line_id,
            interacting_points,
            topic_manager,
            mqtt_client,
        )
        self.topic_manager = topic_manager
        self.line_id = line_id
        self.main_buffer = simpy.Store(env, capacity=main_capacity)
        self.upper_buffer = simpy.Store(env, capacity=upper_capacity)
        self.lower_buffer = simpy.Store(env, capacity=lower_capacity)
        self.kpi_calculator = kpi_calculator  # KPI calculator dependency
        self.downstream_station = None  # QualityCheck
        self.action = None  # 保留但不使用，兼容 fault system 接口
        self.transfer_time = transfer_time  # 模拟搬运时间
        self.main_process = None  # 主运行进程
        self.active_processes = {}  # Track active transfer processes per product
        self.product_start_times = {}  # Track when each product started transfer
        self.product_elapsed_times = {}  # Track elapsed time before interruption

        # 阻塞管理
        self.blocked_leader_process = None  # 正在等待下游的领头产品进程

        # 传送带默认状态为工作中
        self.status = DeviceStatus.WORKING
        self.publish_status("Conveyor initialized")

        # Initialize device utilization tracking
        if self.kpi_calculator:
            self.kpi_calculator.update_device_utilization(self.id, self.line_id, 0.0)

        # Start background process to update total time for utilization calculation
        self.env.process(self._update_total_time())

    def _should_be_blocked(self):
        """检查三缓冲传送带是否应该处于阻塞状态"""
        # 所有缓冲区都满才算真正阻塞
        return (
            self.is_full("main")
            and self.is_full("upper")
            and self.is_full("lower")
            and self.downstream_station
            and not self.downstream_station.can_operate()
        )

    def publish_status(self, message: Optional[str] = None):
        """发布当前传送带状态到MQTT"""
        if not self.mqtt_client or not self.mqtt_client.is_connected():
            return

        # 只发布，不修改状态
        status_data = ConveyorStatus(
            timestamp=self.env.now,
            source_id=self.id,
            status=self.status,
            buffer=[p.id for p in self.main_buffer.items],
            upper_buffer=[p.id for p in self.upper_buffer.items],
            lower_buffer=[p.id for p in self.lower_buffer.items],
            message=message,
        )
        if self.topic_manager and self.line_id:
            topic = self.topic_manager.get_conveyor_status_topic(self.line_id, self.id)
        else:
            topic = get_conveyor_status_topic(self.id)
        self.mqtt_client.publish(topic, status_data.json(), retain=False)

    def set_downstream_station(self, station):
        """Set the downstream station for auto-transfer from main_buffer."""
        self.downstream_station = station
        if self.main_process is None:
            self.main_process = self.env.process(self.run())

    def push(self, product, buffer_type="main"):
        """Put product into specified buffer. buffer_type: 'main', 'upper', 'lower'."""
        result = self.get_buffer(buffer_type).put(product)
        print(
            f"[{self.env.now:.2f}] [DEBUG] TripleBufferConveyor {self.id}: push {product.id} to {buffer_type} buffer, buffer={len(self.get_buffer(buffer_type).items)}/{self.get_buffer(buffer_type).capacity}"
        )
        # 产品添加后发布状态
        self.publish_status()
        return result

    def get_buffer(self, buffer_type="main"):
        if buffer_type == "main":
            return self.main_buffer
        elif buffer_type == "upper":
            return self.upper_buffer
        elif buffer_type == "lower":
            return self.lower_buffer
        else:
            raise ValueError("buffer_type must be 'main', 'upper', or 'lower'")

    def pop(self, buffer_type="main"):
        """Get product from specified buffer."""
        product = yield self.get_buffer(buffer_type).get()
        print(
            f"[{self.env.now:.2f}] [DEBUG] TripleBufferConveyor {self.id}: pop {product.id} from {buffer_type} buffer, buffer={len(self.get_buffer(buffer_type).items)}/{self.get_buffer(buffer_type).capacity}"
        )

        # 如果是从main_buffer取出且该产品有对应的处理进程，中断并删除它
        if buffer_type == "main" and product.id in self.active_processes:
            process = self.active_processes[product.id]
            if process.is_alive:
                process.interrupt("Product removed by AGV")
                print(
                    f"[{self.env.now:.2f}] 🚫 TripleBufferConveyor {self.id}: Interrupted process for product {product.id} (taken by AGV from {buffer_type})"
                )
            del self.active_processes[product.id]

            # 清理该产品的时间记录
            if product.id in self.product_start_times:
                del self.product_start_times[product.id]
            if product.id in self.product_elapsed_times:
                del self.product_elapsed_times[product.id]

        # 产品移除后发布状态
        self.publish_status()
        return product

    def is_full(self, buffer_type="main"):
        if buffer_type == "main":
            return len(self.main_buffer.items) >= self.main_buffer.capacity
        elif buffer_type == "upper":
            return len(self.upper_buffer.items) >= self.upper_buffer.capacity
        elif buffer_type == "lower":
            return len(self.lower_buffer.items) >= self.lower_buffer.capacity
        else:
            raise ValueError("buffer_type must be 'main', 'upper', or 'lower'")

    def is_empty(self, buffer_type="main"):
        if buffer_type == "main":
            return len(self.main_buffer.items) == 0
        elif buffer_type == "upper":
            return len(self.upper_buffer.items) == 0
        elif buffer_type == "lower":
            return len(self.lower_buffer.items) == 0
        else:
            raise ValueError("buffer_type must be 'main', 'upper', or 'lower'")

    def run(self):
        """Main operational loop for the triple buffer conveyor. This should NOT be interrupted by faults."""

        while True:
            # 等待设备可操作且buffer有产品
            yield self.env.process(self._wait_for_ready_state())

            # 检查是否应该解除阻塞状态
            if self.status == DeviceStatus.BLOCKED:
                # 如果下游工站恢复正常或者没有正在等待的领头进程，解除阻塞
                if (
                    self.downstream_station
                    and self.downstream_station.can_operate()
                    and not self.downstream_station.is_full()
                ):
                    if (
                        self.blocked_leader_process is None
                        or not self.blocked_leader_process.is_alive
                    ):
                        print(
                            f"[{self.env.now:.2f}] 🔓 TripleBufferConveyor {self.id}: Downstream recovered or no leader waiting, unblocking"
                        )
                        self._unblock_all_products()

            # 检查main_buffer中的每个产品，如果还没有处理进程就启动一个
            for item in list(self.main_buffer.items):  # 使用list避免迭代时修改
                if item.id not in self.active_processes:
                    # 只有在非阻塞状态下才为新产品启动处理进程
                    if self.status != DeviceStatus.BLOCKED:
                        # 为这个产品启动一个处理进程
                        process = self.env.process(self.process_single_item(item))
                        self.active_processes[item.id] = process
                    else:
                        # 如果是阻塞状态，检查这个产品是否是第一个（领头产品）
                        if (
                            len(self.main_buffer.items) > 0
                            and self.main_buffer.items[0].id == item.id
                        ):
                            # 这是领头产品，允许启动进程
                            process = self.env.process(self.process_single_item(item))
                            self.active_processes[item.id] = process
                            print(
                                f"[{self.env.now:.2f}] 👑 TripleBufferConveyor {self.id}: Starting process for leader product {item.id} despite blocked status"
                            )

            # 清理已完成的进程
            completed_ids = []
            for product_id, process in self.active_processes.items():
                if not process.is_alive:
                    completed_ids.append(product_id)
            for product_id in completed_ids:
                del self.active_processes[product_id]

            yield self.env.timeout(0.1)  # 短暂等待后再检查

    def _wait_for_ready_state(self):
        """等待设备处于可操作状态且buffer有产品"""
        while True:
            # 如果没有下游站点，等待
            if self.downstream_station is None:
                yield self.env.timeout(1)
                continue
            # 如果main_buffer为空，等待
            if len(self.main_buffer.items) == 0 or not self.can_operate():
                yield self.env.timeout(0.1)
                continue
            return

    def process_single_item(self, product):
        """Process a single item from main_buffer with timeout-get-put pattern. This CAN be interrupted by faults."""
        actual_product = None
        try:
            # 检查下游站点是否存在
            if self.downstream_station is None:
                return

            # 如果当前是blocked状态且不是领头产品，不应该继续
            if self.status == DeviceStatus.BLOCKED:
                is_leader = (
                    len(self.main_buffer.items) > 0
                    and self.main_buffer.items[0].id == product.id
                )
                if not is_leader:
                    print(
                        f"[{self.env.now:.2f}] 🚫 TripleBufferConveyor {self.id}: Product {product.id} blocked at start, not leader"
                    )
                    return

            self.set_status(DeviceStatus.WORKING)
            self.publish_status()

            # 计算剩余传输时间（处理中断后恢复的情况）
            if product.id in self.product_elapsed_times:
                # 恢复传输：使用之前记录的已传输时间
                elapsed_time = self.product_elapsed_times[product.id]
                remaining_time = max(0, self.transfer_time - elapsed_time)
                msg = f"[{self.env.now:.2f}] Conveyor {self.id}: {product.id} resume transferring, elapsed {elapsed_time:.1f}s, remaining {remaining_time:.1f}s"
            else:
                # 第一次开始传输
                remaining_time = self.transfer_time
                msg = f"[{self.env.now:.2f}] Conveyor {self.id}: {product.id} start transferring, need {remaining_time:.1f}s"
            print(msg)
            self.publish_status(msg)
            self.product_start_times[product.id] = self.env.now

            # 进行timeout（模拟搬运时间）
            # Track start of working time for KPI
            yield self.env.timeout(remaining_time)

            is_first_product = self.main_buffer.items[0].id == product.id

            # Report energy cost and working time for this transfer
            if self.kpi_calculator:
                self.kpi_calculator.add_energy_cost(
                    self.id, self.line_id, self.transfer_time, is_peak_hour=False
                )
                # Working time is already tracked in add_energy_cost

            # 获取产品
            actual_product = yield self.main_buffer.get()

            # 确保获取的是正确的产品
            if actual_product.id != product.id:
                # 如果不是预期的产品，放回去
                yield self.main_buffer.put(actual_product)
                msg = f"[{self.env.now:.2f}] TripleBufferConveyor {self.id}: unexpected product order, retrying"
                print(msg)
                self.publish_status(msg)
                return

            self.publish_status()

            target_buffer = self._determine_target_buffer_for_product(product)
            # 根据目标buffer类型决定处理
            if target_buffer in ["upper", "lower"]:
                # P3产品返工路径：选择最优的side buffer
                chosen_buffer = self._choose_optimal_side_buffer()
                buffer_name = (
                    "upper_buffer"
                    if chosen_buffer == self.upper_buffer
                    else "lower_buffer"
                )
                actual_product.add_history(
                    self.env.now, f"Moved to {buffer_name} of {self.id} for rework"
                )
                msg = f"[{self.env.now:.2f}] TripleBufferConveyor {self.id}: moved product {actual_product.id} to {buffer_name}"
            else:
                chosen_buffer = self.downstream_station.buffer
                buffer_name = self.downstream_station.id + "_buffer"
                msg = f"[{self.env.now:.2f}] TripleBufferConveyor {self.id}: moved product {actual_product.id} to {self.downstream_station.id}"
            print(msg)
            self.publish_status(msg)

            if is_first_product:
                # 这是最前面的产品，设为领头进程
                self.blocked_leader_process = self.env.active_process
                print(
                    f"[{self.env.now:.2f}] 🎯 Conveyor {self.id}: {actual_product.id} is the leader product (first in order)"
                )

                print(
                    f"[{self.env.now:.2f}] 🔍 Conveyor {self.id}: {buffer_name} buffer {len(chosen_buffer.items)}/{chosen_buffer.capacity}, can opeatate:{self.downstream_station.can_operate()}"
                )

                if buffer_name == "upper_buffer" or buffer_name == "lower_buffer":
                    if (
                        len(chosen_buffer.items) >= chosen_buffer.capacity
                        and self.status != DeviceStatus.BLOCKED
                    ):
                        # 下游已满或下游工站不可操作，阻塞其他产品
                        self._block_all_products()
                    while len(chosen_buffer.items) >= chosen_buffer.capacity:
                        yield self.env.timeout(0.1)
                else:
                    if (
                        len(chosen_buffer.items) >= chosen_buffer.capacity
                        or not self.downstream_station.can_operate()
                    ) and self.status != DeviceStatus.BLOCKED:
                        # 下游已满，阻塞其他产品
                        self._block_all_products()
                    while (
                        len(chosen_buffer.items) >= chosen_buffer.capacity
                        or not self.downstream_station.can_operate()
                    ):
                        yield self.env.timeout(1)

                yield chosen_buffer.put(actual_product)

                # 成功放入，如果之前是阻塞状态，现在解除
                if self.status == DeviceStatus.BLOCKED:
                    self._unblock_all_products()

            else:
                # 不是第一个产品
                print(
                    f"[{self.env.now:.2f}] 📦 Conveyor {self.id}: {actual_product.id} is NOT the leader product (order: {[p.id for p in self.main_buffer.items]})"
                )

                # 非领头产品需要等待，直到轮到它或者传送带解除阻塞
                while self.status == DeviceStatus.BLOCKED:
                    print(
                        f"[{self.env.now:.2f}] ⏳ Conveyor {self.id}: {actual_product.id} waiting for its turn or unblock..."
                    )
                    yield self.env.timeout(0.1)

                # 现在可以尝试放入下游
                yield chosen_buffer.put(actual_product)

            if target_buffer not in ["upper", "lower"]:
                actual_product.update_location(self.downstream_station.id, self.env.now)

            # 清理时间记录
            if actual_product and actual_product.id in self.product_start_times:
                del self.product_start_times[actual_product.id]
            if actual_product and actual_product.id in self.product_elapsed_times:
                del self.product_elapsed_times[actual_product.id]

        except simpy.Interrupt as e:
            interrupt_reason = str(e.cause) if hasattr(e, "cause") else "Unknown"

            # 如果是AGV取走产品的中断，直接返回
            if "Product removed by AGV" in interrupt_reason:
                print(
                    f"[{self.env.now:.2f}] 🚚 TripleBufferConveyor {self.id}: Product {product.id} was taken by AGV, stopping process"
                )
                # 时间记录已经在pop()中清理了，这里不需要再清理
                return

            print(
                f"[{self.env.now:.2f}] ⚠️ TripleBufferConveyor {self.id}: Processing of product {product.id} was interrupted:{interrupt_reason}"
            )

            # 记录中断时已经传输的时间（阻塞和故障都需要）
            if product.id in self.product_start_times:
                start_time = self.product_start_times[product.id]
                elapsed_before_interrupt = self.env.now - start_time
                self.product_elapsed_times[product.id] = (
                    self.product_elapsed_times.get(product.id, 0)
                    + elapsed_before_interrupt
                )
                del self.product_start_times[product.id]
                print(
                    f"[{self.env.now:.2f}] 💾 Conveyor {self.id}: 产品 {product.id} 中断前已传输 {elapsed_before_interrupt:.1f}s，剩余 {self.transfer_time - self.product_elapsed_times.get(product.id, 0):.1f}s"
                )

        finally:
            self.publish_status()

    def _determine_target_buffer_for_product(self, product):
        """根据产品类型和工艺状态确定目标buffer"""
        if product.product_type != "P3":
            print(
                f"[{self.env.now:.2f}] 🔍 TripleBufferConveyor {self.id}: P1/P2产品 {product.id} 直接进入下游工站buffer"
            )
            return "main"

        # P3产品的特殊逻辑：基于访问次数判断
        stationc_visits = product.visit_count.get("StationC", 0)

        print(
            f"[{self.env.now:.2f}] 🔍 TripleBufferConveyor {self.id}: P3产品 {product.id} StationC处理次数={stationc_visits}"
        )

        if stationc_visits == 1:  # 第一次完成StationC处理
            print(
                f"[{self.env.now:.2f}] 🔄 TripleBufferConveyor {self.id}: P3产品 {product.id} 第一次在StationC处理完成，需要返工到StationB"
            )
            return "upper"  # 返工到side buffer
        elif stationc_visits >= 2:  # 第二次及以后完成StationC处理
            print(
                f"[{self.env.now:.2f}] ✅ TripleBufferConveyor {self.id}: P3产品 {product.id} 第二次处理完成，继续主流程"
            )
            return "main"  # 进入主流程
        else:
            print(
                f"[{self.env.now:.2f}] ⚠️ TripleBufferConveyor {self.id}: P3产品 {product.id} 未处理过，继续主流程"
            )
            return "main"  # 默认主流程

    def _choose_optimal_side_buffer(self):
        """选择最优的side buffer（upper或lower）"""
        if self.downstream_station is None:
            return self.upper_buffer  # 默认返回upper

        if self.upper_buffer.capacity - len(
            self.upper_buffer.items
        ) >= self.lower_buffer.capacity - len(self.lower_buffer.items):
            if self.is_full("upper") and self.is_full("lower"):
                self.report_buffer_full("upper_buffer and lower_buffer are full")
            return self.upper_buffer
        else:
            return self.lower_buffer

    def recover(self):
        """Custom recovery logic for the TripleBufferConveyor."""
        print(f"[{self.env.now:.2f}] ✅ TripleBufferConveyor {self.id} is recovering.")
        # 恢复后，它应该继续工作，而不是空闲

    def _update_total_time(self):
        """Background process to update total time for KPI utilization calculation"""
        while True:
            yield self.env.timeout(10.0)  # Update every 10 seconds
            if self.kpi_calculator:
                self.kpi_calculator.update_device_utilization(
                    self.id, self.line_id, self.env.now
                )
        self.set_status(DeviceStatus.WORKING)
        self.publish_status()

    def interrupt_all_processing(self):
        """Interrupt all active product processing. Called by fault system."""
        interrupted_count = 0
        for product_id, process in list(self.active_processes.items()):
            if process.is_alive:
                process.interrupt("Fault injected")
                interrupted_count += 1
        print(
            f"[{self.env.now:.2f}] 🚫 TripleBufferConveyor {self.id}: Interrupted {interrupted_count} product processes"
        )
        return interrupted_count

    def _block_all_products(self, reason="Downstream or side buffer blocked"):
        """阻塞所有产品处理（除了正在等待的领头产品）"""
        if self.status == DeviceStatus.BLOCKED:
            print(
                f"[{self.env.now:.2f}] [DEBUG] TripleBufferConveyor {self.id}: already blocked, skip"
            )
            return  # 已经处于阻塞状态

        # 设置阻塞状态
        self.set_status(DeviceStatus.BLOCKED)
        self.publish_status("Conveyor blocked - downstream or side buffer full")

        # 中断所有非领头的活跃进程（与interrupt_all_processing类似）
        blocked_count = 0
        for product_id, process in list(self.active_processes.items()):
            if process != self.blocked_leader_process and process.is_alive:
                process.interrupt(reason)
                blocked_count += 1

        print(
            f"[{self.env.now:.2f}] 🚧 Conveyor {self.id}: Blocked {blocked_count} products due to downstream blockage"
        )

    def _unblock_all_products(self):
        """解除阻塞，允许产品继续处理"""
        if self.status != DeviceStatus.BLOCKED:
            print(
                f"[{self.env.now:.2f}] [DEBUG] TripleBufferConveyor {self.id}: not blocked, skip unblock"
            )
            return  # 不在阻塞状态

        self.set_status(DeviceStatus.WORKING)
        self.publish_status("Conveyor unblocked - resuming operation")
        self.blocked_leader_process = None

        print(
            f"[{self.env.now:.2f}] ✅ Conveyor {self.id}: Unblocked, products can resume"
        )
