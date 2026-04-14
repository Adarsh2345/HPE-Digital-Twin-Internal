import redis
import json
import logging

logger = logging.getLogger(__name__)

class HotStateEngine:
    def __init__(self, host='localhost', port=6379, db=0):
        try:
            self.client = redis.Redis(host=host, port=port, db=db, decode_responses=True)
            self.client.ping()
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}. Hot state will be disabled.")
            self.client = None

    def set_node_state(self, node_id: str, state: dict):
        if self.client:
            self.client.set(f"node:{node_id}", json.dumps(state))
            logger.info(f"Updated hot state for node: {node_id}")
        
    def get_node_state(self, node_id: str) -> dict:
        if self.client:
            data = self.client.get(f"node:{node_id}")
            return json.loads(data) if data else None
        return None

hot_state = HotStateEngine()
