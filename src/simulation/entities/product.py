# src/simulation/entities/product.py
import uuid
import random
from typing import List, Tuple, Dict, Optional
from enum import Enum


class QualityStatus(Enum):
    """产品质量状态"""

    UNKNOWN = "unknown"  # 未检测
    MAJOR_DEFECT = "major_defect"  # 严重缺陷，需返工
    SCRAP = "scrap"  # 报废


class Product:
    """
    Represents a single product unit being manufactured in the factory.

    Attributes:
        id (str): A unique identifier for the product instance.
        product_type (str): The type of the product (e.g., 'P1', 'P2').
        order_id (str): The ID of the order this product belongs to.
        history (List[Tuple[float, str]]): A log of events for this product.
        quality_status (QualityStatus): Current quality status
        quality_score (float): Quality score
        processing_stations (List[str]): Records of stations processed
        rework_count (int): 返工次数
        inspection_count (int): 检测次数
        current_location (str): 当前所在位置
        process_step (int): 当前工艺步骤索引
        visit_count (Dict[str, int]): 跟踪访问每个工站的次数

    """

    # 产品工艺路线定义 - 定义每种产品类型的标准加工顺序
    PROCESS_ROUTES = {
        "P1": [
            "RawMaterial",
            "StationA",
            "StationB",
            "StationC",
            "QualityCheck",
            "Warehouse",
        ],
        "P2": [
            "RawMaterial",
            "StationA",
            "StationB",
            "StationC",
            "QualityCheck",
            "Warehouse",
        ],
        "P3": [
            "RawMaterial",
            "StationA",
            "StationB",
            "StationC",
            "StationB",
            "StationC",
            "QualityCheck",
            "Warehouse",
        ],
    }

    def __init__(self, product_type: str, order_id: str):
        self.id: str = f"prod_{product_type[1]}_{uuid.uuid4().hex[:8]}"
        self.product_type: str = product_type
        self.order_id: str = order_id
        self.history: List[Tuple[float, str]] = []

        # 质量相关属性
        self.quality_status: QualityStatus = QualityStatus.UNKNOWN
        self.processing_stations: List[str] = []
        self.rework_count: int = 0
        self.inspection_count: int = 0

        # 移动控制相关属性
        self.current_location: str = "RawMaterial"  # 初始位置在原料仓库
        self.process_step: int = 0  # 当前在工艺路线中的步骤索引
        self.visit_count: Dict[str, int] = {}  # 跟踪访问每个工站的次数

        # 质量评分系统
        self.quality_score: float = random.uniform(0.85, 0.95)  # 当前质量分数
        self.quality_factors: Dict[str, float] = {  # 质量影响因素
            "processing_defects": 0.0,  # 加工缺陷累积
            "rework_improvement": 0.0,  # 返工改善
            "handling_damage": 0.0,  # 搬运损伤
        }

    def __repr__(self) -> str:
        return f"Product(id='{self.id}', type='{self.product_type}', location='{self.current_location}', quality='{self.quality_status.value}')"

    def add_history(self, timestamp: float, event: str):
        """Adds a new event to the product's history log."""
        self.history.append((timestamp, event))

    def next_move_checker(
        self, timestamp: float, target_location: str
    ) -> Tuple[bool, str]:
        """
        检查下一个move是否符合当前产品的station orderpolicy

        Args:
            timestamp: 当前时间戳
            target_location: 目标位置

        Returns:
            Tuple[bool, str]: (是否允许移动, 说明信息)
        """
        # 获取当前产品的工艺路线
        route = self.PROCESS_ROUTES.get(self.product_type)
        if not route:
            return False, f"未知产品类型: {self.product_type}"

        # 检查当前位置是否在路线中
        if self.current_location not in route:
            return False, f"当前位置 {self.current_location} 不在工艺路线中"

        current_index = route.index(self.current_location)

        # 处理特殊情况：P3产品的返工逻辑
        if self._is_p3_rework_move(target_location, current_index):
            return True, f"P3产品从 {self.current_location} 返工到 {target_location}"

        # 标准顺序检查：只能前进到下一个工站
        if current_index >= len(route) - 1:
            return False, "产品已到达最终位置"

        expected_next = route[current_index + 1]

        if target_location == expected_next:
            return True, f"允许从 {self.current_location} 移动到 {target_location}"

        # 检查是否为质检返工移动
        if self.rework_count > 0:
            # 返工时允许从QualityCheck回到StationC
            if self.current_location == "QualityCheck" and target_location.startswith(
                "StationC"
            ):
                return (
                    True,
                    f"质检返工移动：从 {self.current_location} 返回到 {target_location}",
                )
            # 返工完成后可以再次去质检
            elif target_location == "QualityCheck" and self.current_location in route:
                return (
                    True,
                    f"返工后再次质检：从 {self.current_location} 到 {target_location}",
                )

        # 其他情况均不允许
        return (
            False,
            f"不允许的移动：从 {self.current_location} 到 {target_location}，期望下一站: {expected_next}",
        )

    def _is_p3_rework_move(self, target_location: str, current_index: int) -> bool:
        """检查是否为P3产品的标准工艺流程移动（非质检返工）"""
        if self.product_type != "P3" or self.current_location != "StationC":
            return False

        stationc_visits = self.visit_count.get("StationC", 0)

        # P3标准工艺：第一次在StationC后需要去StationB
        if (
            stationc_visits == 1
            and target_location == "StationB"
            and self.rework_count == 0
        ):
            return True

        # P3标准工艺：第二次在StationC后可以去质检
        if stationc_visits == 2 and target_location == "QualityCheck":
            return True

        return False

    def update_location(self, new_location: str, timestamp: float) -> bool:
        """
        更新产品位置（应在移动检查通过后调用）

        Args:
            new_location: 新位置
            timestamp: 时间戳

        Returns:
            bool: 更新是否成功
        """
        # 更新位置
        old_location = self.current_location
        self.current_location = new_location

        # 注意：访问次数已在 process_at_station 中更新，这里不再更新
        # 避免重复计数

        # 更新工艺步骤索引
        route = self.PROCESS_ROUTES[self.product_type]
        if new_location in route:
            self.process_step = route.index(new_location)

        # 搬运过程可能造成损伤
        if old_location != "RawMaterial" and new_location != "Warehouse":
            damage_probability = 0.05  # 5%概率
            if random.random() < damage_probability:
                damage_impact = random.uniform(0.01, 0.03)  # 1-3%的质量损失
                self.quality_factors["handling_damage"] += damage_impact
                self._update_quality_score()
                self.add_history(
                    timestamp, f"Handling damage during transport: -{damage_impact:.2%}"
                )

        # 记录历史
        self.add_history(timestamp, f"Moved from {old_location} to {new_location}")

        print(
            f"[{timestamp:.2f}] 📦 {self.id}: 成功移动 {old_location} → {new_location}"
        )
        return True

    def get_next_expected_location(self) -> Optional[str]:
        """获取下一个期望的位置"""
        route = self.PROCESS_ROUTES.get(self.product_type)
        if not route or self.current_location not in route:
            return None

        current_index = route.index(self.current_location)

        # 处理P3标准工艺流程（非质检返工）
        if (
            self.product_type == "P3"
            and self.current_location == "StationC"
            and self.rework_count == 0
        ):
            stationc_visits = self.visit_count.get("StationC", 0)
            if stationc_visits == 1:  # 第一次在StationC
                return "StationB"  # 需要返回StationB
            elif stationc_visits == 2:  # 第二次在StationC
                return "QualityCheck"  # 可以去质检站

        # 标准情况：返回下一个位置
        if current_index < len(route) - 1:
            return route[current_index + 1]

        return None  # 已经到达最终位置

    def get_process_completion_percentage(self) -> float:
        """获取工艺完成百分比"""
        route = self.PROCESS_ROUTES.get(self.product_type)
        if not route or self.current_location not in route:
            return 0.0

        total_steps = len(route) - 1  # 减去起始位置
        current_index = route.index(self.current_location)
        return (current_index / total_steps) * 100.0

    def process_at_station(self, station_id: str, timestamp: float):
        """记录在工站的处理（不进行移动检查，假设产品已经在该工站）"""
        # 记录调试信息
        old_count = self.visit_count.get(station_id, 0)

        self.processing_stations.append(station_id)
        self.add_history(timestamp, f"Processed at {station_id}")

        # 加工过程可能引入缺陷
        if station_id.startswith("Station"):
            # 每次加工有概率引入小缺陷
            defect_probability = 0.1  # 10%概率
            if random.random() < defect_probability:
                defect_impact = random.uniform(0.02, 0.05)  # 2-5%的质量损失
                self.quality_factors["processing_defects"] += defect_impact
                self._update_quality_score()
                self.add_history(
                    timestamp,
                    f"Processing defect at {station_id}: -{defect_impact:.2%}",
                )

        # 更新访问计数（重要：用于P3产品的流程控制）
        self.visit_count[station_id] = self.visit_count.get(station_id, 0) + 1

        print(
            f"[{timestamp:.2f}] 📊 {self.id}: {station_id} 访问次数: {old_count} → {self.visit_count[station_id]}"
        )

    def start_inspection(self, timestamp: float):
        """开始质量检测"""
        self.inspection_count += 1
        self.add_history(
            timestamp, f"Quality inspection started (#{self.inspection_count})"
        )

    def complete_inspection(self, timestamp: float, result: QualityStatus):
        """完成质量检测"""
        self.quality_status = result
        self.add_history(timestamp, f"Quality inspection completed: {result.value}")

    def start_rework(self, timestamp: float, target_station: str):
        """开始返工（质检不合格导致）"""
        self.rework_count += 1
        self.quality_status = QualityStatus.UNKNOWN  # 返工后重新检测

        # 返工改善质量：只允许一次返工，修复70%的加工缺陷
        if self.rework_count == 1:
            actual_improvement = self.quality_factors["processing_defects"] * 0.7
        else:
            actual_improvement = 0  # 不允许第二次返工

        if actual_improvement > 0:
            self.quality_factors["rework_improvement"] += actual_improvement
            self.quality_factors["processing_defects"] = max(
                0, self.quality_factors["processing_defects"] - actual_improvement
            )
            self._update_quality_score()
            self.add_history(
                timestamp,
                f"Rework #{self.rework_count} -> {target_station}, quality improved by {actual_improvement:.2%}",
            )
        else:
            self.add_history(
                timestamp,
                f"Rework #{self.rework_count} -> {target_station}, no improvement possible",
            )

        self.add_history(timestamp, f"Marked for rework to {target_station}")

    def get_quality_summary(self) -> Dict:
        """获取质量摘要信息"""
        return {
            "id": self.id,
            "product_type": self.product_type,
            "quality_status": self.quality_status.value,
            "quality_score": round(self.quality_score, 2),
            "rework_count": self.rework_count,
            "inspection_count": self.inspection_count,
            "processing_stations": self.processing_stations.copy(),
            "can_rework": self.rework_count == 0,
            "quality_factors": self.quality_factors.copy(),
        }

    def _update_quality_score(self):
        """根据各种因素更新质量分数"""
        # 计算总质量分数
        total_impact = (
            self.quality_factors["processing_defects"]
            + self.quality_factors["handling_damage"]
            - self.quality_factors["rework_improvement"]
        )

        # 更新当前质量分数，确保在0-1范围内
        self.quality_score = max(0.0, min(1.0, self.quality_score - total_impact))

    def simulate_aging(self, timestamp: float, aging_factor: float = 0.01):
        """模拟产品老化（如在仓库等待时）"""
        self.quality_factors["handling_damage"] += aging_factor
        self._update_quality_score()
        self.add_history(timestamp, f"Product aging: -{aging_factor:.2%}")
