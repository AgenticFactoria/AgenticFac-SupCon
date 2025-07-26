#!/usr/bin/env python3
"""
Debug script to test AGV_1 movement to P0 on line3
"""

import simpy
import yaml
from src.simulation.entities.agv import AGV
from src.simulation.entities.warehouse import RawMaterial
from config.path_timing import get_travel_time

def test_agv_line3_to_p0():
    """Test AGV_1 movement from P10 to P0 on line3"""
    
    # Create simulation environment
    env = simpy.Environment()
    
    # Load factory layout
    with open('config/factory_layout_multi.yml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # Find line3 configuration
    line3_config = None
    for line in config['factory']['production_lines']:
        if line['name'] == 'line3':
            line3_config = line
            break
    
    if not line3_config:
        print("❌ Line3 configuration not found")
        return
    
    # Find AGV_1 configuration for line3
    agv1_config = None
    for agv in line3_config['agvs']:
        if agv['id'] == 'AGV_1':
            agv1_config = agv
            break
    
    if not agv1_config:
        print("❌ AGV_1 configuration not found for line3")
        return
    
    print("🔍 Debug: Line3 AGV_1 Configuration")
    print(f"   Position: {agv1_config['position']}")
    print(f"   Current Point: P10 (from position)")
    print(f"   Target Point: P0 {agv1_config['path_points']['P0']}")
    print(f"   Battery Level: {agv1_config['battery_level']}%")
    print(f"   Speed: {agv1_config['speed_mps']} m/s")
    
    # Check path timing
    travel_time = get_travel_time("P10", "P0")
    print(f"\n🛣️  Path Analysis:")
    print(f"   Travel time P10→P0: {travel_time} seconds")
    
    # Create AGV instance
    path_points = agv1_config['path_points']
    
    # Determine current point from position
    current_point = None
    for point_name, pos in path_points.items():
        if pos == agv1_config['position']:
            current_point = point_name
            break
    
    if not current_point:
        # Map position to nearest point
        from math import dist
        min_dist = float('inf')
        for point_name, pos in path_points.items():
            d = dist(agv1_config['position'], pos)
            if d < min_dist:
                min_dist = d
                current_point = point_name
        print(f"   ⚠️  Position mapped to {current_point} (distance: {min_dist})")
    
    print(f"   Current Point: {current_point}")
    print(f"   P0 Position: {path_points['P0']}")
    
    # Create AGV
    agv = AGV(
        env=env,
        id="line3_AGV_1",
        position=tuple(agv1_config['position']),
        path_points=path_points,
        speed_mps=agv1_config['speed_mps'],
        battery_level=agv1_config['battery_level'],
        charging_point=agv1_config['charging_point'],
        low_battery_threshold=agv1_config['low_battery_threshold'],
        battery_consumption_per_meter=agv1_config['battery_consumption_per_meter'],
        battery_consumption_per_action=agv1_config['battery_consumption_per_action']
    )
    
    print(f"\n🔋 Battery Analysis:")
    print(f"   Initial battery: {agv.battery_level:.1f}%")
    
    # Check if battery is sufficient
    distance = travel_time * agv1_config['speed_mps']
    required_battery = distance * agv1_config['battery_consumption_per_meter'] + agv1_config['battery_consumption_per_action']
    print(f"   Distance: {distance:.1f}m")
    print(f"   Required battery: {required_battery:.1f}%")
    print(f"   Sufficient battery: {agv.battery_level >= required_battery}")
    
    # Test can_complete_task
    can_complete = agv.can_complete_task(travel_time, 1, "P0")
    print(f"   can_complete_task(): {can_complete}")
    
    # Test move_to function
    def test_move():
        print(f"\n🚀 Starting movement test...")
        try:
            success, message = yield env.process(agv.move_to("P0"))
            print(f"   Movement result: {success}")
            print(f"   Message: {message}")
            print(f"   Final position: {agv.position}")
            print(f"   Final battery: {agv.battery_level:.1f}%")
        except Exception as e:
            print(f"   ❌ Movement failed: {e}")
    
    # Run the test
    env.process(test_move())
    env.run(until=100)

if __name__ == "__main__":
    test_agv_line3_to_p0()