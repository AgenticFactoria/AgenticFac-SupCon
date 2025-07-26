#!/usr/bin/env python3
"""
Test script to verify LLM command post-processing works correctly.
"""

import json
from src.utils.command_processor import CommandProcessor

def test_llm_command_processing():
    """Test the command processor with the provided AGV movement command."""
    
    # Test case 1: Original LLM command with line prefix
    llm_command = {
        "command_id": "cmd_line3_agv1_move_to_stationA",
        "action": "move",
        "target": "line3/AGV_1",
        "params": {
            "target_point": "P1"
        }
    }
    
    print("🔍 Testing LLM command processing...")
    print(f"Original command: {json.dumps(llm_command, indent=2)}")
    
    # Process the command
    processed = CommandProcessor.process_llm_command(llm_command)
    
    print(f"Processed command: {json.dumps(processed, indent=2)}")
    
    # Verify the results
    expected_line_id = "3"
    expected_target = "AGV_1"
    
    assert processed["line_id"] == expected_line_id, f"Expected line_id {expected_line_id}, got {processed.get('line_id')}"
    assert processed["target"] == expected_target, f"Expected target {expected_target}, got {processed.get('target')}"
    
    print("✅ LLM command processing test PASSED!")
    
    # Test case 2: Command without line prefix (should remain unchanged)
    normal_command = {
        "command_id": "cmd_agv1_move_to_stationA",
        "action": "move",
        "target": "AGV_1",
        "params": {
            "target_point": "P1"
        }
    }
    
    print("\n🔍 Testing normal command (no line prefix)...")
    print(f"Original command: {json.dumps(normal_command, indent=2)}")
    
    processed_normal = CommandProcessor.process_llm_command(normal_command)
    
    print(f"Processed command: {json.dumps(processed_normal, indent=2)}")
    
    # Verify no changes for normal command
    assert "line_id" not in processed_normal, "Normal command should not have line_id added"
    assert processed_normal["target"] == "AGV_1", "Normal command target should remain unchanged"
    
    print("✅ Normal command test PASSED!")
    
    # Test case 3: Edge cases
    test_cases = [
        {"target": "line0/AGV_1", "expected_line": "0", "expected_device": "AGV_1"},
        {"target": "line10/Station_A", "expected_line": "10", "expected_device": "Station_A"},
        {"target": "invalid/AGV_1", "expected_line": None, "expected_device": "invalid/AGV_1"},
        {"target": "AGV_1", "expected_line": None, "expected_device": "AGV_1"},
        {"target": "lineABC/AGV_1", "expected_line": None, "expected_device": "lineABC/AGV_1"},
    ]
    
    print("\n🔍 Testing edge cases...")
    for i, test_case in enumerate(test_cases, 1):
        target = test_case["target"]
        expected_line = test_case["expected_line"]
        expected_device = test_case["expected_device"]
        
        line_id, device_id = CommandProcessor.extract_line_and_device(target)
        
        print(f"Test {i}: '{target}' -> line_id={line_id}, device_id={device_id}")
        
        assert line_id == expected_line, f"Expected line_id {expected_line}, got {line_id}"
        assert device_id == expected_device, f"Expected device_id {expected_device}, got {device_id}"
    
    print("✅ All edge cases PASSED!")
    
    return True

if __name__ == "__main__":
    try:
        test_llm_command_processing()
        print("\n🎉 All tests passed successfully!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()