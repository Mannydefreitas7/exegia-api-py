import json
import logging
from typing import Any

from supabase import Client, create_client

from src.config import settings

logger = logging.getLogger(__name__)

_client: Client | None = None


def _get_client() -> Client:
	global _client
	if _client is None:
		_client = create_client(settings.supabase_url, settings.supabase_service_role_key)
	return _client


def get_object(key: str) -> Any | None:
	"""Download an object from Supabase Storage and return parsed JSON, or None if not found."""
	try:
		data = _get_client().storage.from_(settings.supabase_storage_bucket).download(key)
		return json.loads(data)
	except Exception as e:
		logger.debug("Storage object not found or unavailable: %s — %s", key, e)
		return None


def put_object(key: str, data: Any) -> None:
	"""Serialize data to JSON and upload to Supabase Storage (upsert)."""
	body = json.dumps(data, ensure_ascii=False).encode("utf-8")
	_get_client().storage.from_(settings.supabase_storage_bucket).upload(
		path=key,
		file=body,
		file_options={"content-type": "application/json", "upsert": "true"},
	)
	logger.debug("Uploaded storage object: %s", key)


def list_objects(prefix: str) -> list[str]:
	"""List all object paths under a given prefix in Supabase Storage."""
	response = _get_client().storage.from_(settings.supabase_storage_bucket).list(prefix)
	return [f"{prefix}/{obj['name']}" for obj in response if obj.get("name")]
