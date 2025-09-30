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

    def get_stage_addon(self, stage_name: str) -> str:
        """
        Get combined prompt addon for a specific pipeline stage

        Args:
            stage_name: Name of the pipeline stage (e.g., 'generate_article', 'editorial_review')

        Returns:
            Combined prompt addon string for all active variables applicable to this stage
        """
        addons = []

        for var_name, value in self.active_variables.items():
            if var_name not in self.config.get("variables", {}):
                continue

            var_config = self.config["variables"][var_name]

            # Check if this variable applies to current stage
            if stage_name in var_config.get("stages", []):
                prompt_addon = var_config.get("prompt_addon", "")

                # Replace {value} placeholder with actual value
                if prompt_addon:
                    # Special handling for boolean values
                    if var_config.get("type") == "boolean" and value:
                        # For boolean, include addon only if True
                        addons.append(prompt_addon)
                    elif "{value}" in prompt_addon:
                        # Replace placeholder with value
                        addon = prompt_addon.replace("{value}", str(value))
                        addons.append(addon)
                    else:
                        # No placeholder, just append
                        addons.append(prompt_addon)

                    logger.debug(f"Added {var_name} addon for stage {stage_name}")

        # Combine all addons with newlines
        combined_addon = "\n".join(addons)

        if combined_addon:
            logger.info(f"Stage {stage_name} has {len(addons)} variable addon(s)")

        return combined_addon

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

    def get_stage_mapping(self, stage_name: str) -> Dict[str, str]:
        """
        Map common function names to stage names used in config

        Args:
            stage_name: Function or stage name

        Returns:
            Mapped stage name for config lookup
        """
        # Map function names to config stage names
        stage_map = {
            "generate_article_by_sections": "generate_article",
            "_generate_single_section_async": "generate_article",
            "fact_check_sections": "fact_check",
            "editorial_review": "editorial_review",
            "create_structure": "create_structure"
        }

        # Return mapped name or original if not in map
        return stage_map.get(stage_name, stage_name)

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
            'fact_check_mode': args_dict.get('fact_check_mode', 'on')
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