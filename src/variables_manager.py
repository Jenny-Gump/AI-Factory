"""
Variables Manager for Content Factory
Manages dynamic variables that can be injected into prompts at different pipeline stages
"""

import json
import os
from typing import Dict, Any, Optional, List
from src.logger_config import logger

class VariablesManager:
    """Manages dynamic variables for prompt customization"""

    def __init__(self, config_path: str = "variables_config.json"):
        """
        Initialize the variables manager

        Args:
            config_path: Path to the variables configuration file
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.active_variables = {}

    def _load_config(self) -> Dict[str, Any]:
        """Load variables configuration from JSON file"""
        if not os.path.exists(self.config_path):
            logger.warning(f"Variables config not found at {self.config_path}, using empty config")
            return {"variables": {}}

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.debug(f"Loaded {len(config.get('variables', {}))} variable definitions")
                return config
        except Exception as e:
            logger.error(f"Failed to load variables config: {e}")
            return {"variables": {}}

    def set_variables(self, **kwargs) -> None:
        """
        Set active variables from keyword arguments

        Args:
            **kwargs: Variable names and values
        """
        for var_name, value in kwargs.items():
            if value is not None:  # Only set non-None values
                if var_name in self.config.get("variables", {}):
                    # Validate type
                    expected_type = self.config["variables"][var_name].get("type", "string")
                    if not self._validate_type(value, expected_type):
                        logger.warning(f"Variable {var_name} has wrong type, expected {expected_type}")
                        continue

                    self.active_variables[var_name] = value
                    logger.info(f"Set variable {var_name} = {value}")
                else:
                    logger.debug(f"Unknown variable {var_name}, skipping")

    def _validate_type(self, value: Any, expected_type: str) -> bool:
        """Validate variable type"""
        type_map = {
            "string": str,
            "number": (int, float),
            "boolean": bool
        }

        expected_python_type = type_map.get(expected_type, str)
        return isinstance(value, expected_python_type)

    def get_variables_for_replacement(self) -> Dict[str, str]:
        """
        Get all active variables formatted for prompt replacement.
        Returns dict with variable names and formatted strings using templates.
        If variable is not set or empty, returns empty string.

        Returns:
            Dictionary of variable_name: formatted_string pairs
        """
        result = {}

        for var_name, var_config in self.config.get("variables", {}).items():
            # Get value from active variables or use default
            value = self.active_variables.get(var_name)

            if value is None:
                value = var_config.get("default")

            # If still None or empty, return empty string for this variable
            if value is None or value == "":
                result[var_name] = ""
                continue

            # Get template and format it with value
            template = var_config.get("template", "")

            if template:
                # Special handling for boolean values
                if var_config.get("type") == "boolean" and value:
                    # For boolean, include template only if True (no {value} replacement)
                    result[var_name] = template
                elif "{value}" in template:
                    # Replace {value} placeholder with actual value
                    result[var_name] = template.replace("{value}", str(value))
                else:
                    # No placeholder, just use template as-is
                    result[var_name] = template
            else:
                # No template, just return the value
                result[var_name] = str(value)

        return result

    def get_active_variables_summary(self) -> Dict[str, Any]:
        """Get summary of all active variables"""
        return {
            "active_count": len(self.active_variables),
            "variables": self.active_variables.copy()
        }

    def clear_variables(self) -> None:
        """Clear all active variables"""
        self.active_variables.clear()
        logger.debug("Cleared all active variables")

    @classmethod
    def create_from_args(cls, args_dict: Dict[str, Any]) -> 'VariablesManager':
        """
        Create a VariablesManager instance from CLI arguments

        Args:
            args_dict: Dictionary of CLI arguments

        Returns:
            Configured VariablesManager instance
        """
        manager = cls()

        # Extract known variable arguments
        variable_args = {
            'article_length': args_dict.get('article_length'),
            'author_style': args_dict.get('author_style'),
            'theme_focus': args_dict.get('theme_focus'),
            'custom_requirements': args_dict.get('custom_requirements'),
            'target_audience': args_dict.get('target_audience'),
            'tone_of_voice': args_dict.get('tone_of_voice'),
            'include_examples': args_dict.get('include_examples'),
            'seo_keywords': args_dict.get('seo_keywords'),
            'language': args_dict.get('language'),
            'translation_mode': args_dict.get('translation_mode', 'on'),
            'fact_check_mode': args_dict.get('fact_check_mode', 'on'),
            'link_placement_mode': args_dict.get('link_placement_mode', 'on'),
            'llm_model': args_dict.get('llm_model')
        }

        # Filter out None values
        active_vars = {k: v for k, v in variable_args.items() if v is not None}

        if active_vars:
            logger.info(f"Initializing {len(active_vars)} variable(s) from CLI arguments")
            manager.set_variables(**active_vars)

        return manager


# Global instance for easy access (optional, can be created per pipeline run)
_global_manager = None

def get_global_manager() -> VariablesManager:
    """Get or create global variables manager instance"""
    global _global_manager
    if _global_manager is None:
        _global_manager = VariablesManager()
    return _global_manager

def set_global_variables(**kwargs) -> None:
    """Set variables on the global manager"""
    manager = get_global_manager()
    manager.set_variables(**kwargs)

def clear_global_variables() -> None:
    """Clear all variables from global manager"""
    manager = get_global_manager()
    manager.clear_variables()