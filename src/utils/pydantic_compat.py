"""
Pydantic compatibility utilities for handling different versions.
"""
from typing import Type, Dict, Any
from pydantic import BaseModel


def model_to_json(model: BaseModel) -> str:
    """
    Convert a Pydantic model to JSON string, handling different Pydantic versions.
    
    Args:
        model: Pydantic BaseModel instance
        
    Returns:
        JSON string representation of the model
    """
    try:
        # Try Pydantic v1 method (primary for this codebase)
        return model.json()
    except AttributeError:
        # Fallback to v2 method if v1 method doesn't exist
        return model.model_dump_json()


def model_validate(model_class: Type[BaseModel], data: Dict[str, Any]) -> BaseModel:
    """
    Validate data using a Pydantic model, handling different Pydantic versions.
    
    Args:
        model_class: Pydantic BaseModel class
        data: Dictionary data to validate
        
    Returns:
        Validated model instance
    """
    try:
        # Try Pydantic v1 method (primary for this codebase)
        return model_class.parse_obj(data)
    except AttributeError:
        # Fallback to v2 method if v1 method doesn't exist
        return model_class.model_validate(data)