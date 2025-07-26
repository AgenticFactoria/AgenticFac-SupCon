# src/utils/command_processor.py
import json
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class CommandProcessor:
    """
    Handles post-processing of LLM-generated commands to extract line_id and device_id
    from target fields that use the format "lineX/device_id".
    """

    @staticmethod
    def process_llm_command(command_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Post-processes LLM-generated commands to extract line_id from target.
        
        Args:
            command_data: Raw command data from LLM
            
        Returns:
            Processed command data with line_id extracted
        """
        if not command_data.get("target"):
            return command_data
            
        target = command_data["target"]
        
        # Check if target contains line prefix (e.g., "line3/AGV_1", "line1/station_A")
        if "/" in target:
            parts = target.split("/", 1)
            if len(parts) == 2:
                line_prefix, device_id = parts
                
                # Validate line prefix format (lineX where X is a number)
                if line_prefix.lower().startswith("line") and line_prefix[4:].isdigit():
                    line_id = line_prefix[4:]  # Extract just the number
                    
                    # Update command data
                    processed_data = command_data.copy()
                    processed_data["target"] = device_id
                    processed_data["line_id"] = line_id
                    
                    logger.debug(
                        f"Processed LLM command: line_id={line_id}, device_id={device_id}, "
                        f"original_target={target}"
                    )
                    return processed_data
        
        # No processing needed, return original
        return command_data

    @staticmethod
    def validate_command_structure(command_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validates the basic structure of a command.
        
        Args:
            command_data: Command data to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        required_fields = ["action", "target"]
        
        for field in required_fields:
            if field not in command_data:
                return False, f"Missing required field: {field}"
                
        if not isinstance(command_data["action"], str):
            return False, "Action must be a string"
            
        if not isinstance(command_data["target"], str):
            return False, "Target must be a string"
            
        return True, ""

    @staticmethod
    def extract_line_and_device(target: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extracts line_id and device_id from target string.
        
        Args:
            target: Target string (e.g., "line3/AGV_1")
            
        Returns:
            Tuple of (line_id, device_id) or (None, None) if no line prefix
        """
        if not target or "/" not in target:
            return None, target
            
        parts = target.split("/", 1)
        if len(parts) != 2:
            return None, target
            
        line_prefix, device_id = parts
        
        # Check if line prefix matches format "lineX"
        if line_prefix.lower().startswith("line") and line_prefix[4:].isdigit():
            line_id = line_prefix[4:]
            return line_id, device_id
            
        return None, target