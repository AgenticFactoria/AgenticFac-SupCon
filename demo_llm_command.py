#!/usr/bin/env python3
"""
Demonstration of LLM command post-processing for AGV movement.
"""

import json
from src.utils.command_processor import CommandProcessor

def demonstrate_llm_command():
    """Demonstrate the LLM command processing workflow."""
    
    print("🤖 LLM Command Processing Demo")
    print("=" * 50)
    
    # Original LLM-generated command
    original_command = {
        "command_id": "cmd_line3_agv1_move_to_stationA",
        "action": "move",
        "target": "line3/AGV_1",
        "params": {
            "target_point": "P1"
        }
    }
    
    print("📥 Original LLM Command:")
    print(json.dumps(original_command, indent=2))
    print()
    
    # Post-process the command
    processed_command = CommandProcessor.process_llm_command(original_command)
    
    print("🔧 Post-processed Command:")
    print(json.dumps(processed_command, indent=2))
    print()
    
    # Extract components
    line_id = processed_command.get("line_id", "3")  # Default to 3 if not extracted
    device_id = processed_command["target"]
    action = processed_command["action"]
    params = processed_command["params"]
    
    print("📊 Command Components:")
    print(f"  Line ID: {line_id}")
    print(f"  Device ID: {device_id}")
    print(f"  Action: {action}")
    print(f"  Parameters: {params}")
    print()
    
    # Simulate the command execution
    print("🚀 Command Execution Simulation:")
    print(f"  → Moving {device_id} on line {line_id} to point {params['target_point']}")
    print(f"  → Command ID: {processed_command['command_id']}")
    print()
    
    print("✅ Post-processing complete! The command is now ready for the simulation.")

if __name__ == "__main__":
    demonstrate_llm_command()