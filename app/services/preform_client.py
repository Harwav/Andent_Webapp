"""PreFormClient - Client for PreFormServer API.

This module provides a Python client for interacting with the PreFormServer
which manages dental scene creation, STL model imports, and print job submission.

PreFormServer API Reference:
- Base URL: http://localhost:44388
- POST /scene/ - Create scene
- POST /scene/{id}/import-model - Import STL
- POST /print/ - Send to printer
- GET /devices/ - List printers
"""
import time
from functools import wraps
from typing import Any, Dict, List

import requests


DEFAULT_SCENE_SETTINGS = {
    "layer_thickness_mm": 0.1,
    "machine_type": "FRML-4-0",
    "material_code": "FLPMBE01",
    "print_setting": "DEFAULT",
}


def retry_on_failure(max_retries: int = 3, backoff_factor: float = 2.0):
    """Decorator to retry API calls on failure with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        backoff_factor: Exponential backoff multiplier
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (requests.RequestException, requests.ConnectionError, requests.Timeout) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        sleep_time = backoff_factor ** attempt
                        time.sleep(sleep_time)
            raise last_exception
        return wrapper
    return decorator


class PreFormClient:
    """Client for PreFormServer API interactions.
    
    This client handles communication with the PreFormServer to:
    - Create dental scenes for patients
    - Import STL models into scenes
    - Submit print jobs to available printers
    - List available printing devices
    """
    
    def __init__(self, base_url: str = "http://localhost:44388"):
        """Initialize the PreFormClient.
        
        Args:
            base_url: Base URL of the PreFormServer API.
                     Defaults to http://localhost:44388
        """
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
    
    @retry_on_failure(max_retries=3, backoff_factor=2.0)
    def create_scene(self, patient_id: str, case_name: str) -> Dict[str, Any]:
        """Create a new dental scene using the current Local API contract.
        
        Args:
            patient_id: Retained for compatibility with older callers.
            case_name: Retained for compatibility with older callers.
            
        Returns:
            Dict containing scene_id and status from the server
            
        Raises:
            Exception: If the API request fails
        """
        url = f"{self.base_url}/scene/"
        payload = dict(DEFAULT_SCENE_SETTINGS)
        
        try:
            response = self.session.post(url, json=payload, timeout=30)
        except requests.RequestException as e:
            raise Exception(f"Failed to connect to PreFormServer: {str(e)}. Please ensure PreFormServer is running.")
        
        if response.status_code == 404:
            raise Exception("PreFormServer not found. Please check the server URL.")
        elif response.status_code == 503:
            raise Exception("PreFormServer is unavailable. Please try again later.")
        elif response.status_code != 200:
            raise Exception(f"Failed to create scene: {response.status_code} - {response.text}")
        
        payload = response.json()
        if isinstance(payload, dict) and "scene_id" not in payload and "id" in payload:
            payload = {
                **payload,
                "scene_id": payload["id"],
            }

        return payload
    
    @retry_on_failure(max_retries=3, backoff_factor=2.0)
    def import_model(self, scene_id: str, stl_path: str, preset: str | None = None) -> Dict[str, Any]:
        """Import an STL model file into an existing scene.
        
        Args:
            scene_id: ID of the scene to import the model into
            stl_path: File path to the STL model file
            preset: Optional preset hint for PreFormServer material/orientation settings
            
        Returns:
            Dict containing import status and model_id
            
        Raises:
            Exception: If the API request fails
        """
        url = f"{self.base_url}/scene/{scene_id}/import-model"
        
        try:
            payload = {'file': stl_path}
            if preset:
                payload['preset'] = preset
            response = self.session.post(url, json=payload, timeout=60)
        except requests.RequestException as e:
            raise Exception(f"Failed to connect to PreFormServer: {str(e)}. Please ensure PreFormServer is running.")
        except FileNotFoundError:
            raise Exception(f"STL file not found: {stl_path}")
        
        if response.status_code == 404:
            raise Exception(f"Scene {scene_id} not found. Please check the scene ID.")
        elif response.status_code == 413:
            raise Exception(f"STL file too large: {stl_path}. Please reduce file size.")
        elif response.status_code == 422:
            raise Exception(f"Invalid STL file format: {stl_path}. Please check the file.")
        elif response.status_code != 200:
            raise Exception(f"Failed to import model: {response.status_code} - {response.text}")
        
        return response.json()

    @retry_on_failure(max_retries=3, backoff_factor=2.0)
    def auto_layout(self, scene_id: str) -> Dict[str, Any]:
        """Trigger automatic layout generation for a scene."""
        url = f"{self.base_url}/scene/{scene_id}/auto-layout/"
        payload = {"allow_overlapping_supports": False}

        response = self.session.post(url, json=payload, timeout=30)

        if response.status_code != 200:
            raise Exception(f"Failed to auto-layout scene: {response.status_code} - {response.text}")

        return response.json()

    @retry_on_failure(max_retries=3, backoff_factor=2.0)
    def validate_scene(self, scene_id: str) -> Dict[str, Any]:
        """Validate a scene and return validity state and reported issues."""
        url = f"{self.base_url}/scene/{scene_id}/print-validation"

        response = self.session.get(url, timeout=30)

        if response.status_code != 200:
            raise Exception(f"Failed to validate scene: {response.status_code} - {response.text}")

        payload = response.json()
        if isinstance(payload, dict) and "valid" in payload and "errors" in payload:
            return payload

        per_model_results = (
            payload.get("per_model_results", {})
            if isinstance(payload, dict)
            else {}
        )
        errors: list[str] = []
        for model_id, result in per_model_results.items():
            if not isinstance(result, dict):
                continue
            if result.get("undersupported"):
                errors.append(f"{model_id}: undersupported")
            unsupported_minima = result.get("unsupported_minima", 0)
            if isinstance(unsupported_minima, (int, float)) and unsupported_minima:
                errors.append(f"{model_id}: unsupported minima {unsupported_minima}")
            cups = result.get("cups", 0)
            if isinstance(cups, (int, float)) and cups:
                errors.append(f"{model_id}: cups {cups}")
            if result.get("has_seamline"):
                errors.append(f"{model_id}: seamline detected")

        return {"valid": len(errors) == 0, "errors": errors}
    
    @retry_on_failure(max_retries=3, backoff_factor=2.0)
    def send_to_printer(
        self,
        scene_id: str,
        device_id: str,
        job_name: str | None = None,
    ) -> Dict[str, Any]:
        """Send a scene to a printer for production.
        
        Args:
            scene_id: ID of the scene to print
            device_id: ID of the target printer device
            
        Returns:
            Dict containing print_id and queue status
            
        Raises:
            Exception: If the API request fails
        """
        url = f"{self.base_url}/scene/{scene_id}/print/"
        payload = {
            "job_name": job_name or scene_id,
            "printer": device_id,
        }
        
        try:
            response = self.session.post(url, json=payload, timeout=30)
        except requests.RequestException as e:
            raise Exception(f"Failed to connect to PreFormServer: {str(e)}. Please ensure PreFormServer is running.")
        
        if response.status_code == 404:
            raise Exception(f"Scene {scene_id} or printer {device_id} not found.")
        elif response.status_code == 409:
            raise Exception(f"Printer {device_id} is busy. Please try again later.")
        elif response.status_code == 422:
            raise Exception("Scene validation failed. Please check scene configuration.")
        elif response.status_code != 200:
            raise Exception(f"Failed to send to printer: {response.status_code} - {response.text}")
        
        payload = response.json()
        if isinstance(payload, dict) and "print_id" not in payload and "job_id" in payload:
            payload = {
                **payload,
                "print_id": payload["job_id"],
            }
        return payload
    
    def list_devices(self) -> List[Dict[str, Any]]:
        """List all available printer devices.
        
        Returns:
            List of device dictionaries containing device_id, name, and status
            
        Raises:
            Exception: If the API request fails
        """
        url = f"{self.base_url}/devices/"
        
        response = self.session.get(url)
        
        if response.status_code != 200:
            raise Exception(f"Failed to list devices: {response.status_code} - {response.text}")
        
        return response.json()
    
    def get_scene_status(self, scene_id: str) -> Dict[str, Any]:
        """Get the current status of a scene.
        
        Args:
            scene_id: ID of the scene to check
            
        Returns:
            Dict containing scene status information
            
        Raises:
            Exception: If the API request fails
        """
        url = f"{self.base_url}/scene/{scene_id}"
        
        response = self.session.get(url)
        
        if response.status_code != 200:
            raise Exception(f"Failed to get scene status: {response.status_code} - {response.text}")
        
        return response.json()
    
    def close(self):
        """Close the client session."""
        self.session.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
