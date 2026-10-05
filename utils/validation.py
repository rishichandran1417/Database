import os
from typing import Optional
from fastapi import Header, HTTPException, status

API_KEY = os.getenv("API_KEY")

def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Verifies X-API-Key header if API_KEY environment variable is configured."""
    api_key_env = os.getenv("API_KEY") or API_KEY
    if api_key_env and api_key_env.strip():
        if not x_api_key or x_api_key.strip() != api_key_env.strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing X-API-Key authentication header.",
            )
