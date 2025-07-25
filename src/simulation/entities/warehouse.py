# simulation/entities/warehouse.py
import simpy
from typing import Tuple, Optional

from src.simulation.entities.base import Device
from src.simulation.entities.product import Product
from config.schemas import WarehouseStatus
from config.topics import get_warehouse_status_topic
from src.utils.topic_manager import TopicManager


class BaseWarehouse(Device):
    """Base class for all warehouse types, inheriting from Device."""

    def __init__(
        self,
        env: simpy.Environment,
        id: str,
        position: Tuple[int, int],
        mqtt_client=None,
        interacting_points: list = [],
        topic_manager: Optional[TopicManager] = None,
        line_id: Optional[str] = None,
        **kwargs,  # Absorb other config values
    ):
        super().__init__(
            env, id, position, device_type="warehouse", mqtt_client=mqtt_client
        )
        self.buffer = simpy.Store(env)
        self.interacting_points = interacting_points
        self.stats = {}  # To be overridden by subclasses
        self.topic_manager = topic_manager
        self.line_id = line_id

    def publish_status(self, message: str = "Warehouse is ready"):
        """Publishes the current status of the warehouse to MQTT."""
        if not self.mqtt_client or not self.mqtt_client.is_connected():
            return
        status_data = WarehouseStatus(
            timestamp=self.env.now,
            source_id=self.id,
            message=message,
            buffer=[p.id for p in self.buffer.items],
            stats=self.stats,
        )
        if self.topic_manager:
            topic = self.topic_manager.get_warehouse_status_topic(self.id)
        else:
            topic = get_warehouse_status_topic(self.id)
        self.mqtt_client.publish(topic, status_data.model_dump_json(), retain=False)

    def get_buffer_level(self) -> int:
        """Return the current number of items in the buffer."""
        return len(self.buffer.items)

    def pop(self, product_id: Optional[str] = None):
        """
        Remove and return a product from the warehouse buffer.
        If product_id is specified, remove the product with that id.
        Otherwise, remove the first product in the buffer.
        """
        if product_id:
            # Try to find and remove the product with the specified id
            for idx, p in enumerate(self.buffer.items):
                if p.id == product_id:
                    product = self.buffer.items.pop(idx)
                    print(
                        f"[{self.env.now:.2f}] 📤 {self.id}: Product {product.id} taken from warehouse buffer."
                    )
                    break
            else:
                # If not found, raise an error
                raise ValueError(
                    f"Product with id {product_id} not found in warehouse buffer."
                )
        else:
            product = yield self.buffer.get()
            print(
                f"[{self.env.now:.2f}] 📤 {self.id}: Default Product taken from warehouse buffer."
            )

        # 发布状态更新
        msg = f"Product {product.id} taken from {self.id} by AGV"
        print(f"[{self.env.now:.2f}] 📤 {self.id}: {msg}")
        self.publish_status(msg)
        return product

    def run(self):
        """Warehouses don't process products, just idle loop."""
        while True:
            yield self.env.timeout(60)  # Check every minute


class RawMaterial(BaseWarehouse):
    """Raw material warehouse - the starting point of the production line"""

    def __init__(
        self, env: simpy.Environment, mqtt_client=None, kpi_calculator=None, **config
    ):
        super().__init__(env=env, mqtt_client=mqtt_client, **config)
        self.device_type = "raw_material"  # Override device type
        self.kpi_calculator = kpi_calculator
        self.stats = {
            "total_materials_supplied": 0,
            "product_type_summary": {"P1": 0, "P2": 0, "P3": 0},
        }
        print(f"[{self.env.now:.2f}] 🏭 {self.id}: Raw material warehouse is ready")
        self.publish_status("Raw material warehouse is ready")

    def create_raw_material(self, product_type: str, order_id: str) -> Product:
        """Create raw material product"""
        product = Product(product_type, order_id)
        self.stats["total_materials_supplied"] += 1
        self.stats["product_type_summary"][product_type] += 1
        product.add_history(self.env.now, f"Raw material created at {self.id}")
        # Only log raw material creation in debug mode
        import logging
        logger = logging.getLogger(f"{self.__class__.__name__}.{self.id}")
        logger.debug(
            f"[{self.env.now:.2f}] 🔧 {self.id}: Create raw material {product.id} (type: {product_type})"
        )
        self.buffer.put(product)
        self.publish_status(
            f"Supply raw material {product.id} (type: {product_type}) since order {order_id} is created"
        )
        return product

    def pop(self, product_id: Optional[str] = None):
        """
        Override parent's pop method to add material cost calculation.
        Material cost is added when product is taken from raw material warehouse.
        """
        # First get the product using parent's pop method
        product = yield from super().pop(product_id)

        # Add material cost to KPI when product is taken
        if self.kpi_calculator and hasattr(product, "product_type"):
            material_cost = self.kpi_calculator.cost_parameters[
                "material_cost_per_product"
            ].get(
                product.product_type,
                10.0,  # Default to P1 cost if not found
            )
            self.kpi_calculator.stats.material_costs += material_cost

            # Also update the order tracking if it exists
            if (
                hasattr(product, "order_id")
                and product.order_id in self.kpi_calculator.active_orders
            ):
                order_tracking = self.kpi_calculator.active_orders[product.order_id]
                order_tracking.total_cost += material_cost

            print(
                f"[{self.env.now:.2f}] 💰 {self.id}: Added material cost ${material_cost:.2f} for {product.product_type}"
            )

            # Trigger KPI update
            self.kpi_calculator._check_and_publish_kpi_update()

        return product

    def is_full(self) -> bool:
        # return self.get_buffer_level() >= self.buffer_size
        return False


class Warehouse(BaseWarehouse):
    """Finished product warehouse - the ending point of the production line"""

    def __init__(self, env: simpy.Environment, mqtt_client=None, **config):
        super().__init__(env=env, mqtt_client=mqtt_client, **config)
        self.stats = {
            "total_products_received": 0,
            "product_type_summary": {"P1": 0, "P2": 0, "P3": 0},
        }
        print(f"[{self.env.now:.2f}] 🏪 {self.id}: Finished product warehouse is ready")
        self.publish_status("Warehouse is ready")

    def add_product_to_buffer(self, product: Product):
        """AGV put product to warehouse"""
        yield self.buffer.put(product)
        self.publish_status(
            f"Store finished product {product.id} (type: {product.product_type})"
        )
        self.stats["total_products_received"] += 1
        self.stats["product_type_summary"][product.product_type] += 1
        product.add_history(self.env.now, f"Stored in warehouse {self.id}")
        print(
            f"[{self.env.now:.2f}] 📦 {self.id}: Store finished product {product.id} (type: {product.product_type})"
        )
        return True

    def is_full(self) -> bool:
        # return self.get_buffer_level() >= self.buffer_size
        return False
