from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader

API_KEY = "test-operator-key-123"
API_KEY_NAME = "X-Operator-Token"

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def verify_operator(api_key_header: str = Security(api_key_header)):
    if api_key_header == API_KEY:
        return True
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail="Could not validate Operator credentials"
    )
