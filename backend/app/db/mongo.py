"""Local MongoDB layer.

GOV SIM keeps four kinds of state in Mongo, all of it local by default
(``mongodb://127.0.0.1:27017``):

    ml_models       one document per trained model — metrics, features, the
                    dataset it was fitted on, when it was trained
    sensor_readings the loop-detector network: per-sensor location and
                    an aggregated speed profile, so the map can draw real
                    observed traffic rather than a synthetic stand-in
    runs            every simulation the user executes, with its policy, its
                    outputs and a content hash — this is what makes a result
                    reproducible and citable after the fact
    policies        compiled policy documents, keyed by hash

The engine must keep working with Mongo down — a hackathon demo cannot hard-fail
because a database is not running — so every accessor here returns ``None`` or an
empty list instead of raising, and ``available()`` reports the truth to the
health endpoint.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, MongoClient
from pymongo.errors import PyMongoError

from app.config import settings

log = logging.getLogger(__name__)

_client: MongoClient | None = None
_failed = False


def client() -> MongoClient | None:
    """Return a shared client, or None if Mongo cannot be reached.

    The first failure latches ``_failed`` so a down database costs one timeout
    per process rather than one per request.
    """
    global _client, _failed
    if _client is not None:
        return _client
    if _failed:
        return None
    try:
        c = MongoClient(
            settings.mongo_uri,
            serverSelectionTimeoutMS=int(settings.mongo_timeout_ms),
            appname="govsim",
        )
        c.admin.command("ping")
        _client = c
        log.info("MongoDB connected: %s", settings.mongo_uri)
        return c
    except PyMongoError as exc:
        _failed = True
        log.warning("MongoDB unavailable (%s) — running without persistence", exc)
        return None


def db():
    c = client()
    return c[settings.mongo_db] if c is not None else None


def available() -> bool:
    return db() is not None


def status() -> dict[str, Any]:
    """Health-endpoint view of the persistence layer."""
    d = db()
    if d is None:
        return {"connected": False, "uri": settings.mongo_uri, "database": settings.mongo_db}
    try:
        return {
            "connected": True,
            "uri": settings.mongo_uri,
            "database": settings.mongo_db,
            "collections": {
                name: d[name].estimated_document_count()
                for name in ("ml_models", "sensor_readings", "runs", "policies")
            },
        }
    except PyMongoError as exc:
        return {"connected": False, "error": str(exc)}


def ensure_indexes() -> None:
    d = db()
    if d is None:
        return
    try:
        d.ml_models.create_index([("name", ASCENDING)], unique=True)
        d.sensor_readings.create_index([("sensor_id", ASCENDING)], unique=True)
        d.runs.create_index([("run_hash", ASCENDING)])
        d.runs.create_index([("created_at", ASCENDING)])
        d.policies.create_index([("policy_hash", ASCENDING)], unique=True)
    except PyMongoError as exc:
        log.warning("index creation skipped: %s", exc)


# ---------------------------------------------------------------------------
# Accessors — each one degrades to a no-op / empty result when Mongo is absent
# ---------------------------------------------------------------------------


def upsert_model(name: str, doc: dict[str, Any]) -> bool:
    d = db()
    if d is None:
        return False
    try:
        d.ml_models.update_one(
            {"name": name},
            {"$set": {**doc, "name": name, "updated_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
        return True
    except PyMongoError as exc:
        log.warning("upsert_model(%s) failed: %s", name, exc)
        return False


def list_models() -> list[dict[str, Any]]:
    d = db()
    if d is None:
        return []
    try:
        return list(d.ml_models.find({}, {"_id": 0}).sort("name", ASCENDING))
    except PyMongoError:
        return []


def get_model(name: str) -> dict[str, Any] | None:
    d = db()
    if d is None:
        return None
    try:
        return d.ml_models.find_one({"name": name}, {"_id": 0})
    except PyMongoError:
        return None


def replace_sensors(docs: list[dict[str, Any]]) -> int:
    d = db()
    if d is None:
        return 0
    try:
        d.sensor_readings.delete_many({})
        if docs:
            d.sensor_readings.insert_many(docs)
        return len(docs)
    except PyMongoError as exc:
        log.warning("replace_sensors failed: %s", exc)
        return 0


def list_sensors(limit: int = 500) -> list[dict[str, Any]]:
    d = db()
    if d is None:
        return []
    try:
        return list(d.sensor_readings.find({}, {"_id": 0}).limit(limit))
    except PyMongoError:
        return []


def record_run(doc: dict[str, Any]) -> str | None:
    """Append a simulation run to the history. Returns its id, or None."""
    d = db()
    if d is None:
        return None
    try:
        payload = {**doc, "created_at": datetime.now(timezone.utc)}
        return str(d.runs.insert_one(payload).inserted_id)
    except PyMongoError as exc:
        log.warning("record_run failed: %s", exc)
        return None


def recent_runs(limit: int = 25) -> list[dict[str, Any]]:
    d = db()
    if d is None:
        return []
    try:
        rows = list(
            d.runs.find({}, {"_id": 0}).sort("created_at", -1).limit(limit)
        )
        for r in rows:
            if isinstance(r.get("created_at"), datetime):
                r["created_at"] = r["created_at"].isoformat()
        return rows
    except PyMongoError:
        return []


def save_policy(policy_hash: str, doc: dict[str, Any]) -> bool:
    d = db()
    if d is None:
        return False
    try:
        d.policies.update_one(
            {"policy_hash": policy_hash},
            {
                "$set": {**doc, "policy_hash": policy_hash},
                "$setOnInsert": {"first_seen": datetime.now(timezone.utc)},
            },
            upsert=True,
        )
        return True
    except PyMongoError:
        return False
