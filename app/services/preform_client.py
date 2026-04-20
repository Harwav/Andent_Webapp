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
import requests
from typing import List, Dict, Any, Optional


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
    
    def create_scene(self, patient_id: str, case_name: str) -> Dict[str, Any]:
        """Create a new dental scene for a patient case.
        
        Args:
            patient_id: Unique identifier for the patient
            case_name: Name/description of the dental case
            
        Returns:
            Dict containing scene_id and status from the server
            
        Raises:
            Exception: If the API request fails
        """
        url = f"{self.base_url}/scene/"
        payload = {
            "patient_id": patient_id,
            "case_name": case_name
        }
        
        response = self.session.post(url, json=payload)
        
        if response.status_code != 200:
            raise Exception(f"Failed to create scene: {response.status_code} - {response.text}")
        
        return response.json()
    
    def import_model(self, scene_id: str, stl_path: str) -> Dict[str, Any]:
        """Import an STL model file into an existing scene.
        
        Args:
            scene_id: ID of the scene to import the model into
            stl_path: File path to the STL model file
            
        Returns:
            Dict containing import status and model_id
            
        Raises:
            Exception: If the API request fails
        """
        url = f"{self.base_url}/scene/{scene_id}/import-model"
        
        with open(stl_path, 'rb') as f:
            files = {'model': f}
            response = self.session.post(url, files=files)
        
        if response.status_code != 200:
            raise Exception(f"Failed to import model: {response.status_code} - {response.text}")
        
        return response.json()
    
    def send_to_printer(self, scene_id: str, device_id: str) -> Dict[str, Any]:
        """Send a scene to a printer for production.
        
        Args:
            scene_id: ID of the scene to print
            device_id: ID of the target printer device
            
        Returns:
            Dict containing print_id and queue status
            
        Raises:
            Exception: If the API request fails
        """
        url = f"{self.base_url}/print/"
        payload = {
            "scene_id": scene_id,
            "device_id": device_id
        }
        
        response = self.session.post(url, json=payload)
        
        if response.status_code != 200:
            raise Exception(f"Failed to send to printer: {response.status_code} - {response.text}")
        
        return response.json()
    
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
