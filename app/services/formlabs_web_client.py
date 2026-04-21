"""FormlabsWebClient - Client for Formlabs Web API.

This module provides a Python client for interacting with the Formlabs Web API
for print job management and status tracking.

Formlabs Web API Reference:
- Base URL: https://api.formlabs.com/v1
- Authentication: Token <api_token>
- Endpoints:
  - GET /print-jobs/ - List print jobs
  - GET /print-jobs/{id}/ - Get job status
  - GET /print-jobs/{id}/screenshot/ - Get job screenshot
"""

from __future__ import annotations

import os

import requests
from typing import Any, List, Dict


class FormlabsWebClient:
    """Client for Formlabs Web API interactions.
    
    This client handles communication with the Formlabs Web API to:
    - Authenticate with API token
    - List print jobs
    - Get job status and details
    - Fetch job screenshots
    
    Usage:
        client = FormlabsWebClient(api_token="your-token")
        if client.authenticate():
            jobs = client.list_print_jobs()
            for job in jobs:
                print(f"Job {job['id']}: {job['status']}")
        client.close()
    """
    
    def __init__(self, api_token: str, base_url: str = "https://api.formlabs.com/v1"):
        """Initialize the FormlabsWebClient.
        
        Args:
            api_token: API token for authentication
            base_url: Base URL for the Formlabs Web API.
                     Defaults to https://api.formlabs.com/v1
        """
        self.api_token = api_token or os.getenv("ANDENT_WEB_FORMLABS_API_TOKEN") or os.getenv("FORMLABS_API_TOKEN") or ""
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Token {self.api_token}",
            "Content-Type": "application/json",
        })
    
    def authenticate(self) -> bool:
        """Authenticate with the Formlabs Web API.
        
        Returns:
            True if authentication successful, False otherwise
        """
        try:
            response = self.session.get(f"{self.base_url}/print-jobs/", timeout=10)
            return response.status_code == 200
        except requests.RequestException:
            return False
    
    def list_print_jobs(self) -> List[Dict[str, Any]]:
        """List all print jobs.
        
        Returns:
            List of job dictionaries containing:
            - id: Job ID
            - status: Job status (Queued, Printing, Failed, Paused, Completed)
            - printer: Printer type
            - resin: Resin type
            - layer_height_microns: Layer height
            - created_at: Creation timestamp
            - estimated_completion: Estimated completion timestamp
            
        Raises:
            Exception: If the API request fails
        """
        url = f"{self.base_url}/print-jobs/"
        
        try:
            response = self.session.get(url, timeout=10)
        except requests.RequestException as exc:
            raise Exception(f"Failed to list print jobs: {exc}")
        
        if response.status_code == 401:
            raise Exception("Authentication failed: Invalid API token")
        elif response.status_code != 200:
            raise Exception(f"Failed to list print jobs: {response.status_code} - {response.text}")
        
        return response.json()
    
    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get status and details for a specific print job.
        
        Args:
            job_id: ID of the print job
            
        Returns:
            Dict containing job details:
            - id: Job ID
            - status: Current status
            - printer: Printer type
            - resin: Resin type
            - layer_height_microns: Layer height
            - progress_percent: Print progress (0-100)
            - created_at: Creation timestamp
            - estimated_completion: Estimated completion timestamp
            
        Raises:
            Exception: If the API request fails
        """
        url = f"{self.base_url}/print-jobs/{job_id}/"
        
        try:
            response = self.session.get(url, timeout=10)
        except requests.RequestException as exc:
            raise Exception(f"Failed to get job status for {job_id}: {exc}")
        
        if response.status_code == 404:
            raise Exception(f"Job not found: {job_id}")
        elif response.status_code == 401:
            raise Exception("Authentication failed: Invalid API token")
        elif response.status_code != 200:
            raise Exception(f"Failed to get job status: {response.status_code} - {response.text}")
        
        return response.json()
    
    def get_job_screenshot(self, job_id: str) -> bytes:
        """Get screenshot image for a specific print job.
        
        Args:
            job_id: ID of the print job
            
        Returns:
            Screenshot image as bytes
            
        Raises:
            Exception: If the API request fails
        """
        url = f"{self.base_url}/print-jobs/{job_id}/screenshot/"
        
        try:
            response = self.session.get(url, timeout=30)
        except requests.RequestException as exc:
            raise Exception(f"Failed to get screenshot for job {job_id}: {exc}")
        
        if response.status_code == 404:
            raise Exception(f"Screenshot not found for job: {job_id}")
        elif response.status_code == 401:
            raise Exception("Authentication failed: Invalid API token")
        elif response.status_code != 200:
            raise Exception(f"Failed to get screenshot: {response.status_code} - {response.text}")
        
        return response.content
    
    def close(self) -> None:
        """Close the client session."""
        self.session.close()
    
    def __enter__(self) -> "FormlabsWebClient":
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()
