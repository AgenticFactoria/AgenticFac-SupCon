import json
from src.simulation.factory import Factory
from src.utils.mqtt_client import MQTTClient
from config.topics import AGENT_COMMANDS_TOPIC, RESULT_TOPIC
from src.game_logic.fault_system import FaultType


def get_device_map(factory: Factory) -> dict:
    """Creates a mapping from simple codes to full device IDs."""
    device_map = {
        "R": "RawMaterial",
        "W": "Warehouse",
        "A": "StationA",
        "B": "StationB",
        "C": "StationC",
        "Q": "QualityCheck",
        "C1": "Conveyor_AB",
        "C2": "Conveyor_BC",
        "C3": "Conveyor_CQ",
    }
    # Dynamically add AGVs to the map
    for agv in factory.agvs.values():
        agv_num = agv.id.split("_")[-1]
        device_map[agv_num] = agv.id
    return device_map


def menu_input_thread(mqtt_client: MQTTClient, factory: Factory):
    """Thread for handling user menu input for manual control."""
    device_map = get_device_map(factory)

    load_unload_devices = {k: v for k, v in device_map.items() if not k.isdigit()}
    fault_devices = device_map

    load_prompt = f"请输入装载设备编号 ({', '.join(load_unload_devices.keys())}): "
    unload_prompt = f"请输入卸载设备编号 ({', '.join(load_unload_devices.keys())}): "
    fault_prompt = f"请输入设备编号 ({', '.join(fault_devices.keys())}): "

    while True:
        print("\n请选择操作类型：")
        print("1. 移动AGV")
        print("2. 装载")
        print("3. 卸载")
        print("4. 充电")
        print("5. 注入故障")
        print("6. 查看结果 (result)")
        print("7. 退出")
        op = input("> ").strip().lower()

        if op == "1":
            agv_id_short = input("请输入AGV编号 (e.g., 1, 2): ").strip()
            agv_id = f"AGV_{agv_id_short}"
            target_point = "P" + input("请输入目标点 (e.g., 1): ").strip()
            cmd = {
                "action": "move",
                "target": agv_id,
                "params": {"target_point": target_point},
            }

        elif op in ["2", "3"]:  # Load/Unload
            action = "load" if op == "2" else "unload"
            agv_id_short = input("请输入AGV编号 (e.g., 1, 2): ").strip()
            agv_id = f"AGV_{agv_id_short}"

            prompt = load_prompt if action == "load" else unload_prompt
            device_id_short = input(prompt).strip().upper()
            device_id = load_unload_devices.get(device_id_short)

            if not device_id:
                print("无效设备编号，请重试。")
                continue

            buffer_type = input(
                "请输入buffer类型 (N.A./output_buffer/upper/lower): "
            ).strip()
            params = {"device_id": device_id, "buffer_type": buffer_type}

            if action == "load":
                product_id = input("请输入产品编号（可选）: ").strip()
                if product_id:
                    params["product_id"] = product_id

            cmd = {"action": action, "target": agv_id, "params": params}

        elif op == "4":
            agv_id_short = input("请输入AGV编号 (e.g., 1, 2): ").strip()
            agv_id = f"AGV_{agv_id_short}"
            try:
                target_level = float(input("请输入目标电量 (e.g., 80): ").strip())
            except ValueError:
                print("目标电量需为数字！")
                continue
            cmd = {
                "action": "charge",
                "target": agv_id,
                "params": {"target_level": target_level},
            }

        elif op == "5":
            if factory.fault_system is None:
                print("故障系统未初始化，请先初始化故障系统。")
                continue

            # 1:StationB, 2:Conveyor_BC, 3:StationC
            fast_fault = input(
                "请输入故障类型 (1:StationA for 50s, 2:Conveyor_AB for 50s, 3.StationB for 50s,4, Conveyor_BC for 50s, 5:StationC for 50s) else manual: "
            ).strip()
            if fast_fault == "1":
                fault_type = FaultType.STATION_FAULT
                device_id = "StationA"
                fault_duration = 50.0
            elif fast_fault == "2":
                fault_type = FaultType.CONVEYOR_FAULT
                device_id = "Conveyor_AB"
                fault_duration = 50.0
            elif fast_fault == "3":
                fault_type = FaultType.STATION_FAULT
                device_id = "StationB"
                fault_duration = 50.0
            elif fast_fault == "4":
                fault_type = FaultType.STATION_FAULT
                device_id = "Conveyor_BC"
                fault_duration = 50.0
            elif fast_fault == "5":
                fault_type = FaultType.STATION_FAULT
                device_id = "StationC"
                fault_duration = 50.0
            else:
                print("手动设置故障，请输入设备编号: ")
                fault_type_in = input(
                    "请输入故障类型 (1:AGV, 2:工站, 3:传送带): "
                ).strip()
                fault_map = {
                    "1": FaultType.AGV_FAULT,
                    "2": FaultType.STATION_FAULT,
                    "3": FaultType.CONVEYOR_FAULT,
                }
                fault_type = fault_map.get(fault_type_in)
                device_id_short = input(fault_prompt).strip().upper()
                device_id = fault_devices.get(device_id_short)
                if not device_id:
                    print("无效设备编号，请重试。")
                    continue
                fault_duration = float(input("请输入故障持续时间 (秒): ").strip())
                try:
                    if not fault_type:
                        raise ValueError("无效的故障类型")
                except (ValueError, KeyError) as e:
                    print(f"输入无效: {e}！")
                    continue
                try:
                    if not fault_type:
                        raise ValueError("无效的故障类型")
                except (ValueError, KeyError) as e:
                    print(f"输入无效: {e}！")
                    continue

            factory.fault_system._inject_fault_now(
                device_id, fault_type, fault_duration
            )
            print(f"已注入故障: {device_id} {fault_type.name} {fault_duration}s")
            continue

        elif op == "6" or op == "result":
            # 获取并显示最终结果
            if factory.kpi_calculator:
                final_scores = factory.kpi_calculator.get_final_score()

                # 打印到终端（与factory.print_final_scores()相同格式）
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
                print(
                    f"\n质量与成本得分 (30%): {final_scores['quality_cost_score']:.2f}"
                )
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

                # 发布得分到MQTT（不包含原始指标）
                result_topic = RESULT_TOPIC

                scores_only = {
                    "total_score": round(final_scores["total_score"], 2),
                    "efficiency_score": round(final_scores["efficiency_score"], 2),
                    "efficiency_components": {
                        k: round(v, 2)
                        for k, v in final_scores["efficiency_components"].items()
                    },
                    "quality_cost_score": round(final_scores["quality_cost_score"], 2),
                    "quality_cost_components": {
                        k: round(v, 2)
                        for k, v in final_scores["quality_cost_components"].items()
                    },
                    "agv_score": round(final_scores["agv_score"], 2),
                    "agv_components": {
                        k: round(v, 2)
                        for k, v in final_scores["agv_components"].items()
                    },
                }
                result_json = json.dumps(scores_only)

                mqtt_client.publish(result_topic, result_json)
                print(f"✅ 结果已发布到 {result_topic}")
            else:
                print("❌ KPI计算器未初始化")
            continue

        elif op == "7":
            print("退出菜单输入线程。")
            break
        else:
            print("无效选择，请重试。")
            continue

        mqtt_client.publish(AGENT_COMMANDS_TOPIC, json.dumps(cmd))
        print(f"已发送命令: {cmd}")
