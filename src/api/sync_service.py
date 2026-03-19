"""Background sync service for Spotify recently-played tracks.

Spawns one asyncio Task per opted-in user. Each task fetches the user's
recently-played tracks every 60 minutes and ingests new events into BigQuery.

User settings (auto_sync flag, last_synced_cursor) are stored in Firestore
under the `users/{user_id}` document.

Designed for small deployments (≤15 users). No external dependencies needed.
"""

import asyncio
import logging
import os
import sys
from typing import Dict

logger = logging.getLogger(__name__)

_INGESTION_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../ingestion"))

SYNC_INTERVAL_SECONDS = 60 * 60  # 60 minutes


def _ensure_ingestion_path():
    if _INGESTION_DIR not in sys.path:
        sys.path.insert(0, _INGESTION_DIR)


def _get_firestore_client():
    from google.cloud import firestore
    project_id = os.environ.get("FIRESTORE_PROJECT_ID")
    database_id = os.environ.get("FIRESTORE_DATABASE_ID", "tolajs-timber")
    if project_id:
        return firestore.Client(project=project_id, database=database_id)
    return firestore.Client(database=database_id)


def _get_bigquery_db():
    _ensure_ingestion_path()
    from bigquery_db import BigQueryDatabase
    project_id = os.getenv("GCP_PROJECT_ID", "portfolio-projects-b1cf2")
    dataset_id = os.getenv("BQ_DATASET_ID", "timber")
    db = BigQueryDatabase(project_id=project_id, dataset_id=dataset_id)
    db.connect()
    return db


class _AuthError(Exception):
    pass


class RecentlyPlayedSyncService:

    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}

    # -- Lifecycle --

    async def startup(self):
        """Re-spawn sync tasks for all users who had auto-sync enabled before restart."""
        try:
            fs = await asyncio.to_thread(_get_firestore_client)
            docs = fs.collection("users").where("auto_sync", "==", True).stream()
            count = 0
            for doc in docs:
                uid = doc.id
                await self._spawn_task(uid)
                count += 1
            logger.info(f"Sync service started — {count} active task(s).")
        except Exception as e:
            logger.error(f"Sync service startup failed: {e}")

    async def shutdown(self):
        """Cancel all active sync tasks on server shutdown."""
        for task in list(self._tasks.values()):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()
        logger.info("Sync service shut down.")

    # -- Public API --

    async def enable(self, user_id: str):
        """Opt a user in: persist the flag to Firestore and start the sync task."""
        await asyncio.to_thread(self._write_auto_sync, user_id, True)
        await self._spawn_task(user_id)
        logger.info(f"Auto-sync enabled for user {user_id}")

    async def disable(self, user_id: str):
        """Opt a user out: cancel the task and clear the flag in Firestore."""
        self._cancel_task(user_id)
        await asyncio.to_thread(self._write_auto_sync, user_id, False)
        logger.info(f"Auto-sync disabled for user {user_id}")

    def cancel_task_only(self, user_id: str):
        """Cancel the task without touching Firestore. Used during full data deletion."""
        self._cancel_task(user_id)

    # -- Private helpers --

    async def _spawn_task(self, user_id: str):
        if user_id in self._tasks and not self._tasks[user_id].done():
            return  # already running
        task = asyncio.create_task(
            self._sync_loop(user_id), name=f"recently_played_sync_{user_id}"
        )
        self._tasks[user_id] = task

    def _cancel_task(self, user_id: str):
        task = self._tasks.pop(user_id, None)
        if task and not task.done():
            task.cancel()

    async def _sync_loop(self, user_id: str):
        logger.info(f"Sync loop started for user {user_id}")
        while True:
            try:
                await asyncio.to_thread(self._do_sync, user_id)
            except asyncio.CancelledError:
                logger.info(f"Sync loop cancelled for user {user_id}")
                raise
            except _AuthError as e:
                # Token is gone — disable silently so the user isn't stuck
                logger.warning(f"Auth failure for {user_id}, disabling auto-sync: {e}")
                await asyncio.to_thread(self._write_auto_sync, user_id, False)
                self._tasks.pop(user_id, None)
                return
            except Exception as e:
                logger.error(f"Sync error for user {user_id}: {e}")

            try:
                await asyncio.sleep(SYNC_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                logger.info(f"Sync loop cancelled during sleep for user {user_id}")
                raise

    def _do_sync(self, user_id: str):
        """Blocking sync: fetch recently-played tracks and ingest new events."""
        _ensure_ingestion_path()
        from auth.oauth_handler import get_spotify_client
        from recently_played_ingestion import ingest_recently_played

        sp = get_spotify_client(user_id)
        if not sp:
            raise _AuthError(f"No valid token for user {user_id}")

        # Read cursor from Firestore
        fs = _get_firestore_client()
        user_doc = fs.collection("users").document(user_id).get()
        cursor = user_doc.to_dict().get("last_synced_cursor") if user_doc.exists else None

        kwargs = {"limit": 50}
        if cursor:
            kwargs["after"] = int(cursor)

        response = sp.current_user_recently_played(**kwargs)
        items = response.get("items", [])

        if not items:
            logger.info(f"No new recently-played tracks for user {user_id}")
            return

        user_info = sp.current_user()
        db = _get_bigquery_db()
        try:
            count = ingest_recently_played(db, user_info, items)
            logger.info(f"Ingested {count} recently-played event(s) for user {user_id}")
        finally:
            db.close()

        # Update cursor to the played_at of the most recent item (index 0 = newest)
        from datetime import datetime
        new_cursor = int(
            datetime.fromisoformat(
                items[0]["played_at"].replace("Z", "+00:00")
            ).timestamp() * 1000
        )
        fs.collection("users").document(user_id).set(
            {"last_synced_cursor": new_cursor}, merge=True
        )

    def _write_auto_sync(self, user_id: str, enabled: bool):
        fs = _get_firestore_client()
        fs.collection("users").document(user_id).set(
            {"auto_sync": enabled}, merge=True
        )


# Module-level singleton — imported by routes.py and main.py
sync_service = RecentlyPlayedSyncService()
