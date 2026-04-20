# fps_parser.py
"""
Handles parsing of .fps (Formlabs Print Settings) files with backward compatibility.
Supports both legacy format (schema v1/v2) and new format (schema v3+).
"""
import json
import logging
from typing import Dict, Optional, Tuple


class FPSParser:
    """Parser for .fps files that handles multiple schema versions."""

    @staticmethod
    def parse_fps_file(fps_path: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Parse an .fps file and extract scene settings in API-compatible format.

        Returns:
            Tuple of (scene_settings_dict, error_message)
            scene_settings_dict contains: machine_type, material_code, layer_thickness_mm, etc.
        """
        try:
            with open(fps_path, 'r', encoding='utf-8') as f:
                fps_data = json.load(f)
        except FileNotFoundError:
            return None, f"FPS file not found: {fps_path}"
        except json.JSONDecodeError as e:
            return None, f"Invalid JSON in FPS file: {e}"
        except Exception as e:
            return None, f"Error reading FPS file: {e}"

        # Detect schema version
        schema_version = FPSParser._detect_schema_version(fps_data)
        logging.info(f"Detected FPS schema version: {schema_version}")

        # Parse based on schema version
        if schema_version >= 3:
            return FPSParser._parse_schema_v3(fps_data)
        else:
            return FPSParser._parse_legacy_schema(fps_data)

    @staticmethod
    def _detect_schema_version(fps_data: Dict) -> int:
        """Detect the schema version of the FPS file."""
        # Schema v3+ has metadata with schema_version field
        if 'metadata' in fps_data:
            metadata = fps_data['metadata']
            if 'schema_version' in metadata:
                return metadata['schema_version']
            # If metadata exists but no schema_version, assume v3
            return 3

        # Legacy format has scene_settings at top level
        if 'scene_settings' in fps_data:
            return 1

        # Unknown format
        return 0

    @staticmethod
    def _parse_schema_v3(fps_data: Dict) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Parse new schema v3+ format.

        Schema v3 structure:
        {
            "metadata": {
                "base_material_identifier": {
                    "machine_type_id": "FORM-4-0",
                    "versioned_material_code": "FLFMGR01",
                    "layer_thickness_mm": 0.12
                },
                "schema_version": 3,
                "name": "120 Fast Arch"
            },
            "public_fields": {
                "categories": [
                    {
                        "key": "Core_Scene",
                        "values": {
                            "layer_thickness": {"layer_thickness_mm": 0.12},
                            "x_correction_factor": 1.00381,
                            ...
                        }
                    },
                    {
                        "key": "Material_Form_4_Family_Print",
                        "values": { ... print settings ... }
                    }
                ]
            }
        }
        """
        try:
            metadata = fps_data.get('metadata', {})
            base_material = metadata.get('base_material_identifier', {})

            # Extract core settings from base_material_identifier
            machine_type = base_material.get('machine_type_id')
            material_code = base_material.get('versioned_material_code')
            layer_thickness = base_material.get('layer_thickness_mm')

            if not machine_type or not material_code:
                return None, "Missing required fields: machine_type_id or versioned_material_code"

            # Build scene settings dict compatible with API
            # Note: Only include fields that the API accepts
            # Correction factors are filtered out (stored as metadata)
            # Use layer_thickness from metadata as it's the authoritative value
            scene_settings = {
                'machine_type': machine_type,
                'material_code': material_code,
                'layer_thickness_mm': layer_thickness or 0.1,
                'print_setting': 'F4_FAST_ARCHES' if layer_thickness == 0.16 else 'DEFAULT'
            }

            # Extract additional settings from public_fields if available
            public_fields = fps_data.get('public_fields', {})
            categories = public_fields.get('categories', [])

            # Look for Core_Scene category for correction factors (metadata only)
            for category in categories:
                if category.get('key') == 'Core_Scene':
                    values = category.get('values', {})

                    # DO NOT override layer thickness from Core_Scene - it may be incorrect
                    # The metadata.base_material_identifier.layer_thickness_mm is authoritative
                    # Store the Core_Scene value as metadata for reference only
                    layer_thickness_obj = values.get('layer_thickness', {})
                    if 'layer_thickness_mm' in layer_thickness_obj:
                        scene_settings['_core_scene_layer_thickness'] = layer_thickness_obj['layer_thickness_mm']

                    # Store correction factors as metadata (not for API)
                    # These are stored for informational purposes only
                    if 'x_correction_factor' in values:
                        scene_settings['_x_correction_factor'] = values['x_correction_factor']
                    if 'y_correction_factor' in values:
                        scene_settings['_y_correction_factor'] = values['y_correction_factor']
                    if 'z_correction_factor' in values:
                        scene_settings['_z_correction_factor'] = values['z_correction_factor']

                    break

            # Add metadata for informational purposes
            scene_settings['_fps_name'] = metadata.get('name', 'Custom FPS')
            scene_settings['_fps_schema_version'] = metadata.get('schema_version', 3)

            logging.info(f"Parsed FPS v3: {scene_settings.get('_fps_name')} - "
                        f"{machine_type} / {material_code} @ {scene_settings['layer_thickness_mm']}mm")

            return scene_settings, None

        except Exception as e:
            logging.error(f"Error parsing FPS schema v3: {e}", exc_info=True)
            return None, f"Failed to parse FPS schema v3: {e}"

    @staticmethod
    def _parse_legacy_schema(fps_data: Dict) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Parse legacy schema v1/v2 format.

        Legacy structure:
        {
            "scene_settings": {
                "machine_type": "FORM-4-0",
                "material_code": "FLFMGR01",
                "layer_thickness_mm": 0.1,
                ...
            }
        }
        """
        try:
            scene_settings = fps_data.get('scene_settings')

            if not scene_settings:
                return None, "Missing 'scene_settings' in legacy FPS file"

            # Validate required fields
            machine_type = scene_settings.get('machine_type')
            material_code = scene_settings.get('material_code')

            if not machine_type or not material_code:
                return None, "Missing required fields: machine_type or material_code"

            logging.info(f"Parsed FPS legacy: {machine_type} / {material_code}")

            return scene_settings, None

        except Exception as e:
            logging.error(f"Error parsing legacy FPS: {e}", exc_info=True)
            return None, f"Failed to parse legacy FPS: {e}"

    @staticmethod
    def extract_display_info(scene_settings: Dict) -> Tuple[str, str]:
        """
        Extract human-readable printer and material info from scene settings.

        Returns:
            Tuple of (machine_type, material_code) suitable for display
        """
        machine_type = scene_settings.get('machine_type', 'Unknown')
        material_code = scene_settings.get('material_code', 'Unknown')

        return machine_type, material_code
