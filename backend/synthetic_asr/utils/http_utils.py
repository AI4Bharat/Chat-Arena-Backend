"""
HTTP utilities for external service communication.
Ported from synthetic-benchmarks for Django integration.
"""

import json
import http.client
from typing import Dict, Tuple, Any


def make_post_request(
    host: str,
    url: str,
    headers: Dict[str, str],
    body: Dict,
    port: int = 443,
    timeout: int = 30
) -> Tuple[Any, str]:
    """
    Make HTTPS POST request
    
    Args:
        host: Host name
        url: URL path
        headers: Request headers
        body: Request body (dict, will be JSONified)
        port: Port number (default 443)
        timeout: Timeout in seconds
        
    Returns:
        Tuple of (response data, error message)
    """
    try:
        conn = http.client.HTTPSConnection(host, port=port, timeout=timeout)
        headers['Content-Type'] = 'application/json'
        
        conn.request('POST', url, body=json.dumps(body), headers=headers)
        response = conn.getresponse()
        data = response.read()
        conn.close()
        
        if response.status >= 400:
            return None, f"HTTP {response.status}: {response.reason}"
        
        try:
            return json.loads(data.decode('utf-8')), ""
        except json.JSONDecodeError:
            return data.decode('utf-8'), ""
            
    except Exception as e:
        return None, f"Request error: {str(e)}"


def make_local_post_request(
    host: str,
    url: str,
    headers: Dict[str, str],
    body: Dict,
    port: int = 8000,
    timeout: int = 30
) -> Tuple[Any, str]:
    """
    Make local HTTP POST request (not HTTPS)
    
    Args:
        host: Host name/IP
        url: URL path
        headers: Request headers
        body: Request body (dict, will be JSONified)
        port: Port number
        timeout: Timeout in seconds
        
    Returns:
        Tuple of (response data, error message)
    """
    try:
        conn = http.client.HTTPConnection(host, port=port, timeout=timeout)
        headers['Content-Type'] = 'application/json'
        
        conn.request('POST', url, body=json.dumps(body), headers=headers)
        response = conn.getresponse()
        data = response.read()
        conn.close()
        
        if response.status >= 400:
            return None, f"HTTP {response.status}: {response.reason}"
        
        try:
            return json.loads(data.decode('utf-8')), ""
        except json.JSONDecodeError:
            return data.decode('utf-8'), ""
            
    except Exception as e:
        return None, f"Request error: {str(e)}"


def make_get_request(
    host: str,
    url: str,
    headers: Dict[str, str] = None,
    port: int = 443,
    timeout: int = 30,
    is_https: bool = True
) -> Tuple[Any, str]:
    """
    Make GET request
    
    Args:
        host: Host name
        url: URL path
        headers: Request headers (optional)
        port: Port number
        timeout: Timeout in seconds
        is_https: Use HTTPS if True, HTTP if False
        
    Returns:
        Tuple of (response data, error message)
    """
    try:
        if headers is None:
            headers = {}
        
        ConnClass = http.client.HTTPSConnection if is_https else http.client.HTTPConnection
        conn = ConnClass(host, port=port, timeout=timeout)
        
        conn.request('GET', url, headers=headers)
        response = conn.getresponse()
        data = response.read()
        conn.close()
        
        if response.status >= 400:
            return None, f"HTTP {response.status}: {response.reason}"
        
        try:
            return json.loads(data.decode('utf-8')), ""
        except json.JSONDecodeError:
            return data.decode('utf-8'), ""
            
    except Exception as e:
        return None, f"Request error: {str(e)}"
