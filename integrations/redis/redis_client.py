"""
integrations/redis/redis_client.py
Thin Redis wrapper with graceful fallback to in-memory dict.
"""
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class RedisClient:
    def __init__(self, host: str, port: int, db: int = 0, password: str = None):
        self._client = None
        self._fallback: dict = {}
        try:
            import redis
            self._client = redis.Redis(
                host=host, port=port, db=db, password=password,
                socket_connect_timeout=2, decode_responses=True,
            )
            self._client.ping()
            logger.info(f"RedisClient connected: {host}:{port}")
        except Exception as e:
            logger.warning(f"RedisClient fallback to in-memory ({e})")

    def set(self, key: str, value: Any, ex: int = None) -> bool:
        serialized = json.dumps(value, default=str)
        if self._client:
            try:
                self._client.set(key, serialized, ex=ex)
                return True
            except Exception as e:
                logger.warning(f"Redis SET failed: {e}")
        self._fallback[key] = serialized
        return True

    def get(self, key: str) -> Optional[Any]:
        if self._client:
            try:
                val = self._client.get(key)
                return json.loads(val) if val else None
            except Exception:
                pass
        raw = self._fallback.get(key)
        return json.loads(raw) if raw else None

    def delete(self, key: str) -> bool:
        if self._client:
            try:
                self._client.delete(key)
            except Exception:
                pass
        self._fallback.pop(key, None)
        return True

    def ping(self) -> bool:
        if self._client:
            try:
                return bool(self._client.ping())
            except Exception:
                pass
        return True  # In-memory always alive
