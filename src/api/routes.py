from fastapi import APIRouter, HTTPException, Request, Response, Cookie, UploadFile, File
from fastapi.responses import RedirectResponse
import asyncio
import json
import logging
import os
import sys
import tempfile
import math
import time
import uuid
import spotipy
from typing import List, Optional

from auth.oauth_handler import (
    SpotifyOAuthHandler, store_user_token, revoke_user_token, get_spotify_client,
    pick_app_index, assign_user_to_app, remove_user_from_app,
)
from spotipy.oauth2 import SpotifyOAuth
from api.websocket import manager

# In-memory upload job store (keyed by job_id)
# For AWS: swap this dict for DynamoDB / ElastiCache
upload_jobs: dict = {}

# Limits concurrent memory-intensive ingestion jobs to 1 so two simultaneous
# uploads don't OOM the 512 MB Cloud Run container. Raise to 2 if RAM is upgraded.
_ingestion_semaphore = asyncio.Semaphore(1)

# Number of GCS files to download and ingest per batch. Each batch gets a fresh
# SpotifyParser (empty caches) and BigQuery buffer, bounding peak RAM to
# ~150–250 MB per batch instead of growing proportionally with total file count.
_FILE_BATCH_SIZE = 5


def _prune_old_jobs():
    """Remove completed/errored jobs older than 1 hour to prevent memory growth."""
    cutoff = time.time() - 3600
    stale = [
        jid for jid, job in upload_jobs.items()
        if job.get("status") in ("complete", "error") and job.get("created_at", 0) < cutoff
    ]
    for jid in stale:
        upload_jobs.pop(jid, None)

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/health")
async def health_check():
    return {"status": "ok", "message": "Spotify AI Assistant API is running."}

@router.get("/chats/latest")
def get_latest_chat(exclude_id: Optional[str] = None, spotify_user_id: Optional[str] = Cookie(default=None, alias="__session")):
    """Returns the ID of the user's most recent chat session from Neo4j.

    Pass exclude_id to skip the session the user is currently on, so 'Previous Chat'
    always returns a genuinely different session.
    """
    if not spotify_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not manager._history_repo:
        raise HTTPException(status_code=503, detail="Database not connected")

    session_id = manager._history_repo.get_latest_session_id(spotify_user_id, exclude_session_id=exclude_id)
    if not session_id:
        return {"session_id": None}

    return {"session_id": session_id}

@router.get("/chats/{session_id}")
def get_chat_history(session_id: str, spotify_user_id: Optional[str] = Cookie(default=None, alias="__session")):
    """Returns the full text history of a specific chat session for the frontend to render."""
    if not spotify_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    # Load directly from the persistent store, bypassing the in-memory expiry check.
    # The session timeout only applies to the active agent context (WebSocket), not
    # to rendering stored history — previous chats are almost always older than the
    # in-memory TTL and would incorrectly return empty turns if we went through
    # manager.get_session().
    if not manager._history_repo:
        return {"turns": []}

    session = manager._history_repo.load_session(session_id)
    if not session:
        return {"turns": []}

    # We strip out the hidden 'step_results' context before sending to the frontend
    # because the React UI only needs to render the text strings, not the raw AI data.
    ui_turns = [
        {"query": t["query"], "response": t["response"], "timestamp": t["timestamp"]}
        for t in session.get("turns", [])
    ]

    return {"turns": ui_turns}

@router.post("/chats/{session_id}/save")
def save_chat(session_id: str, spotify_user_id: Optional[str] = Cookie(default=None, alias="__session")):
    """Explicitly saves the current session to Neo4j without evicting it from memory.
    Used by the frontend when navigating away from a chat.
    The WebSocket disconnect handler is the only thing that should evict from memory.
    """
    if not spotify_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    manager.save_session_only(session_id, user_id=spotify_user_id)
    return {"status": "saved"}

@router.get("/auth/status")
async def auth_status(request: Request):
    """Checks if the user has a valid session cookie."""
    user_id = request.cookies.get("__session")
    if user_id:
        return {"authenticated": True, "user_id": user_id}
    return {"authenticated": False}

@router.get("/auth/url")
async def get_auth_url():
    """Returns the Spotify authorization URL for the frontend to redirect to."""
    try:
        app_index = pick_app_index()
        handler = SpotifyOAuthHandler(app_index=app_index)
        sp_oauth = SpotifyOAuth(
            client_id=handler.client_id,
            client_secret=handler.client_secret,
            redirect_uri=handler.redirect_uri,
            scope=handler.scope,
            cache_path=".spotify_cache",
            show_dialog=True
        )
        state = f"{app_index}_{uuid.uuid4().hex}"
        auth_url = sp_oauth.get_authorize_url(state=state)
        return {"auth_url": auth_url}
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Auth URL error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/auth/login")
async def login():
    """Redirects the user to Spotify for authentication."""
    try:
        app_index = pick_app_index()
        handler = SpotifyOAuthHandler(app_index=app_index)
        sp_oauth = SpotifyOAuth(
            client_id=handler.client_id,
            client_secret=handler.client_secret,
            redirect_uri=handler.redirect_uri,
            scope=handler.scope,
            cache_path=".spotify_cache",
            show_dialog=True
        )
        state = f"{app_index}_{uuid.uuid4().hex}"
        auth_url = sp_oauth.get_authorize_url(state=state)
        return RedirectResponse(url=auth_url)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/callback")
@router.get("/auth/callback")
async def callback(request: Request):
    """Handles the redirect from Spotify after login."""
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code missing")

    try:
        # Parse the app index encoded in the OAuth state parameter
        state = request.query_params.get("state", "0_")
        try:
            app_index = int(state.split("_")[0])
        except (ValueError, IndexError):
            app_index = 0

        handler = SpotifyOAuthHandler(app_index=app_index)

        # Use a temp cache path unique to this request so concurrent logins
        # don't overwrite each other. We'll move the token to the per-user
        # path once we know the user_id.
        from spotipy.cache_handler import CacheFileHandler
        tmp_cache = f".spotify_cache_tmp_{uuid.uuid4().hex}"
        try:
            sp_oauth = handler.build_oauth(CacheFileHandler(cache_path=tmp_cache), show_dialog=True)
            token_info = sp_oauth.get_access_token(code)
        finally:
            # Always clean up the temp file regardless of outcome
            if os.path.exists(tmp_cache):
                os.remove(tmp_cache)

        # Identify the user from their access token
        sp = spotipy.Spotify(auth=token_info['access_token'])
        user_info = sp.current_user()
        user_id = user_info.get('id')

        _frontend = os.getenv("FRONTEND_URL", "http://127.0.0.1:5173")
        response = RedirectResponse(url=f"{_frontend}/?auth=success")

        if user_id:
            # Write the token to the per-user cache and register the in-memory client
            store_user_token(user_id, token_info, app_index=app_index)
            # Record which Spotify app this user is assigned to
            assign_user_to_app(user_id, app_index)

            response.set_cookie(
                key="__session",
                value=user_id,
                httponly=True,
                secure=os.getenv("FRONTEND_URL", "").startswith("https"),
                samesite="lax",
                max_age=3600 * 24 * 7  # 7 days
            )
            logger.info(f"Authenticated user: {user_id} (app {app_index})")

        return response
    except Exception as e:
        logger.error(f"Callback error: {e}")
        _frontend = os.getenv("FRONTEND_URL", "http://127.0.0.1:5173")
        return RedirectResponse(url=f"{_frontend}/?auth=error")

@router.get("/user/settings")
async def get_user_settings(spotify_user_id: Optional[str] = Cookie(default=None, alias="__session")):
    """Returns the user's account-level settings stored in Firestore."""
    if not spotify_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not manager._history_repo:
        raise HTTPException(status_code=503, detail="Database not connected")
    settings = manager._history_repo.get_user_settings(spotify_user_id)
    return {"auto_sync": bool(settings.get("auto_sync", False))}


@router.post("/user/autosync")
async def set_autosync(request: Request, spotify_user_id: Optional[str] = Cookie(default=None, alias="__session")):
    """Enables or disables the auto-sync background task for the current user."""
    if not spotify_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    from api.sync_service import sync_service
    body = await request.json()
    enabled = bool(body.get("enabled", False))
    if enabled:
        await sync_service.enable(spotify_user_id)
    else:
        await sync_service.disable(spotify_user_id)
    return {"status": "ok", "auto_sync": enabled}


@router.delete("/user/data")
async def delete_user_data(response: Response, spotify_user_id: Optional[str] = Cookie(default=None, alias="__session")):
    """Deletes all of the user's data: Neo4j nodes and user-specific cache files."""
    if not spotify_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Cancel any active sync task — no need to update Neo4j since the User node
    # is about to be deleted entirely.
    from api.sync_service import sync_service
    sync_service.cancel_task_only(spotify_user_id)

    errors = []

    # 1. Delete Firestore chat sessions for this user
    if manager._history_repo:
        try:
            manager._history_repo.delete_user_sessions(spotify_user_id)
            # Also delete the user's settings doc
            manager._history_repo.db.collection("users").document(spotify_user_id).delete()
            logger.info(f"Deleted Firestore data for user {spotify_user_id}")
        except Exception as e:
            logger.error(f"Failed to delete Firestore data for user {spotify_user_id}: {e}")
            errors.append(f"Session cleanup failed: {e}")

    # 2. Delete BigQuery listening events for this user
    try:
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../ingestion')))
        from bigquery_db import BigQueryDatabase
        bq = BigQueryDatabase(
            project_id=os.getenv("GCP_PROJECT_ID", "portfolio-projects-b1cf2"),
            dataset_id=os.getenv("BQ_DATASET_ID", "timber"),
        )
        bq.connect()
        try:
            bq.delete_user_data(spotify_user_id)
            logger.info(f"Deleted BigQuery data for user {spotify_user_id}")
        finally:
            bq.close()
    except Exception as e:
        logger.error(f"Failed to delete BigQuery data for user {spotify_user_id}: {e}")
        errors.append(f"Database cleanup failed: {e}")

    # 2. Evict any in-memory chat sessions for this user
    try:
        sessions_to_evict = [
            sid for sid, session in manager._sessions.items()
            if session.get("user_id") == spotify_user_id
        ]
        for sid in sessions_to_evict:
            manager._sessions.pop(sid, None)
    except Exception as e:
        logger.warning(f"Failed to evict in-memory sessions for user {spotify_user_id}: {e}")

    # 3. Clear any pending upload jobs for this user
    jobs_to_remove = [jid for jid, job in upload_jobs.items() if job.get("user_id") == spotify_user_id]
    for jid in jobs_to_remove:
        upload_jobs.pop(jid, None)

    # 4. Revoke OAuth token cache and remove app assignment
    try:
        revoke_user_token(spotify_user_id)
        remove_user_from_app(spotify_user_id)
    except Exception as e:
        logger.warning(f"Failed to revoke token for user {spotify_user_id}: {e}")

    # 5. Clear the session cookie
    response.delete_cookie(key="__session", httponly=True, secure=False, samesite="lax")

    if errors:
        raise HTTPException(status_code=500, detail=" | ".join(errors))

    return {"status": "success", "message": "All user data has been deleted."}


@router.post("/auth/logout")
async def logout(response: Response, spotify_user_id: Optional[str] = Cookie(default=None, alias="__session")):
    """Logs out the user by clearing their token cache and cookie."""
    if spotify_user_id:
        try:
            revoke_user_token(spotify_user_id)
        except Exception as e:
            logger.error(f"Error revoking token for user {spotify_user_id}: {e}")

    response.delete_cookie(
        key="__session",
        httponly=True,
        secure=False,
        samesite="lax"
    )
    return {"status": "success", "message": "Logged out successfully"}

_ACCEPTED_MIME_TYPES = {"application/json", "text/plain", "text/json", "application/octet-stream"}
_MAX_FILE_BYTES = 200 * 1024 * 1024  # 200 MB per file
_GCS_BUCKET = os.getenv("GCS_BUCKET", "timber-portfolio-bucket")


async def _stream_file_to_disk(file: UploadFile, temp_path: str) -> None:
    """Streams an UploadFile to disk in 1 MB chunks to avoid loading it fully into memory."""
    bytes_written = 0
    with open(temp_path, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            bytes_written += len(chunk)
            if bytes_written > _MAX_FILE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"'{file.filename}' exceeds the 200 MB per-file limit.",
                )
            f.write(chunk)


def _validate_and_combine(temp_paths: List[str], combined_path: str) -> int:
    """
    Validates and merges multiple JSON array files into one without loading all
    data into memory at once. Writes a valid JSON array by streaming one file at
    a time into the output, keeping only one file's worth of data in RAM.
    Returns total event count.
    """
    import ijson

    total = 0
    with open(combined_path, "w", encoding="utf-8") as out:
        out.write("[")
        first_event = True

        for tp in temp_paths:
            with open(tp, "rb") as f:
                # Peek at the first object to validate format before streaming the rest
                try:
                    parser = ijson.items(f, "item")
                    first = next(parser, None)
                except Exception:
                    raise HTTPException(status_code=400, detail="One of the uploaded files contains invalid JSON.")

                if first is None:
                    raise HTTPException(status_code=400, detail="Each file must be a non-empty JSON array.")
                if "master_metadata_track_name" not in first or "ts" not in first:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "One of the files doesn't look like a Spotify Extended Streaming History file. "
                            "Expected keys like 'master_metadata_track_name' and 'ts'."
                        ),
                    )

                # Write first item, then stream the rest one object at a time
                if not first_event:
                    out.write(",")
                out.write(json.dumps(first))
                first_event = False
                total += 1

                for item in parser:
                    out.write(",")
                    out.write(json.dumps(item))
                    total += 1

        out.write("]")

    return total


async def _run_ingestion_task(job_id: str, combined_path: str, user_id: str):
    """Runs the ingestion pipeline in a thread so it doesn't block the event loop."""
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../graph-rag')))
    from ingestion_service import run_ingestion

    logger.info("[upload][job=%s][user=%s] Ingestion task started. combined_path=%s", job_id, user_id, combined_path)

    def progress_cb(pct: int, msg: str):
        logger.info("[upload][job=%s][user=%s] Progress %d%% — %s", job_id, user_id, pct, msg)
        upload_jobs[job_id] = {"status": "processing", "progress": pct, "message": msg, "user_id": user_id, "created_at": upload_jobs[job_id].get("created_at")}

    t0 = time.monotonic()
    try:
        spotify_client = get_spotify_client(user_id)
        upload_jobs[job_id]["message"] = "Waiting for another upload to finish..."
        async with _ingestion_semaphore:
            result = await asyncio.to_thread(run_ingestion, combined_path, user_id, spotify_client, progress_cb)
        elapsed = round(time.monotonic() - t0, 1)
        logger.info(
            "[upload][job=%s][user=%s] Ingestion complete. total_events=%d duration=%.1fs",
            job_id, user_id, result["total_events"], elapsed,
        )
        created_at = upload_jobs[job_id].get("created_at")
        upload_jobs[job_id] = {
            "status": "complete",
            "progress": 100,
            "message": f"Done! {result['total_events']} events ingested.",
            "total_events": result["total_events"],
            "user_id": user_id,
            "created_at": created_at,
        }
    except Exception as e:
        elapsed = round(time.monotonic() - t0, 1)
        logger.exception("[upload][job=%s][user=%s] Ingestion failed after %.1fs", job_id, user_id, elapsed)
        created_at = upload_jobs[job_id].get("created_at")
        upload_jobs[job_id] = {"status": "error", "progress": 0, "message": str(e), "user_id": user_id, "created_at": created_at}
        try:
            if os.path.exists(combined_path):
                os.remove(combined_path)
        except OSError:
            pass


@router.post("/upload/signed-urls")
async def get_signed_urls(request: Request, spotify_user_id: Optional[str] = Cookie(default=None, alias="__session")):
    """Returns a GCS signed URL for each file so the frontend can upload directly to Cloud Storage."""
    if not spotify_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    body = await request.json()
    files = body.get("files", [])
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    for f in files:
        if not f.get("filename", "").endswith(".json"):
            raise HTTPException(status_code=400, detail=f"'{f.get('filename')}' is not a JSON file.")

    logger.info("[signed-urls][user=%s] Requested signed URLs for %d file(s): %s",
                spotify_user_id, len(files), [f["filename"] for f in files])
    try:
        import google.auth
        import google.auth.transport.requests
        from google.cloud import storage
        from datetime import timedelta

        credentials, project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(google.auth.transport.requests.Request())
        logger.info("[signed-urls][user=%s] Credentials refreshed. type=%s", spotify_user_id, type(credentials).__name__)

        # compute_engine credentials return 'default' for service_account_email.
        # Fetch the real email from the GCP metadata server instead.
        sa_email = getattr(credentials, "service_account_email", None)
        if not sa_email or sa_email == "default":
            import urllib.request as _urlrequest
            _meta_req = _urlrequest.Request(
                "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email",
                headers={"Metadata-Flavor": "Google"},
            )
            with _urlrequest.urlopen(_meta_req, timeout=3) as _resp:
                sa_email = _resp.read().decode()
        logger.info("[signed-urls][user=%s] Using service account: %s", spotify_user_id, sa_email)

        client = storage.Client(credentials=credentials, project=project)
        bucket = client.bucket(_GCS_BUCKET)

        result = []
        for f in files:
            blob_name = f"uploads/{spotify_user_id}/{uuid.uuid4().hex}_{f['filename']}"
            blob = bucket.blob(blob_name)
            upload_url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(minutes=15),
                method="PUT",
                content_type="application/json",
                service_account_email=sa_email,
                access_token=credentials.token,
            )
            result.append({"filename": f["filename"], "upload_url": upload_url, "gcs_path": blob_name})
            logger.info("[signed-urls][user=%s] Generated signed URL for %s → gs://%s/%s",
                        spotify_user_id, f["filename"], _GCS_BUCKET, blob_name)

        return {"files": result}
    except Exception as e:
        logger.exception("[signed-urls][user=%s] Failed to generate signed URLs", spotify_user_id)
        raise HTTPException(status_code=500, detail="Failed to generate upload URLs.")


async def _run_gcs_ingestion_task(job_id: str, gcs_paths: List[str], user_id: str):
    """Downloads files from GCS in batches of _FILE_BATCH_SIZE, ingesting each batch
    independently so peak RAM is bounded by batch size rather than total file count."""
    from google.cloud import storage

    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../graph-rag')))
    from ingestion_service import run_ingestion

    logger.info("[gcs-ingest][job=%s][user=%s] Task started. files=%d batch_size=%d paths=%s",
                job_id, user_id, len(gcs_paths), _FILE_BATCH_SIZE, gcs_paths)

    # Track leftover temp files so _cleanup() can remove them on error
    _active_temp_paths: List[str] = []
    _active_combined: List[str] = []  # one-element list for mutability in nested scope

    def _cleanup():
        for tp in _active_temp_paths:
            try:
                if os.path.exists(tp):
                    os.remove(tp)
                    logger.info("[gcs-ingest][job=%s] Cleaned up temp file: %s", job_id, tp)
            except OSError:
                pass
        if _active_combined:
            try:
                if os.path.exists(_active_combined[0]):
                    os.remove(_active_combined[0])
                    logger.info("[gcs-ingest][job=%s] Cleaned up combined file: %s", job_id, _active_combined[0])
            except OSError:
                pass

    t0 = time.monotonic()
    try:
        gcs_client = storage.Client()
        bucket = gcs_client.bucket(_GCS_BUCKET)
        spotify_client = get_spotify_client(user_id)

        num_batches = math.ceil(len(gcs_paths) / _FILE_BATCH_SIZE)
        total_events = 0

        for batch_idx in range(num_batches):
            batch_gcs_paths = gcs_paths[batch_idx * _FILE_BATCH_SIZE:(batch_idx + 1) * _FILE_BATCH_SIZE]
            batch_label = f"{batch_idx + 1}/{num_batches}"

            # --- download batch ---
            upload_jobs[job_id] = {
                "status": "processing",
                "progress": int(batch_idx * 100 / num_batches),
                "message": f"Downloading files (batch {batch_label})...",
                "user_id": user_id,
                "created_at": upload_jobs[job_id].get("created_at"),
            }
            batch_temp_paths = []
            for gcs_path in batch_gcs_paths:
                temp_path = os.path.join(
                    tempfile.gettempdir(), f"spotify_gcs_{user_id}_{uuid.uuid4().hex}.json"
                )
                _active_temp_paths.append(temp_path)
                t_dl = time.monotonic()
                bucket.blob(gcs_path).download_to_filename(temp_path)
                size_mb = os.path.getsize(temp_path) / 1_048_576
                logger.info("[gcs-ingest][job=%s] Downloaded gs://%s/%s → %s (%.2f MB, %.1fs)",
                            job_id, _GCS_BUCKET, gcs_path, temp_path, size_mb, time.monotonic() - t_dl)
                batch_temp_paths.append(temp_path)

            # --- validate + combine ---
            upload_jobs[job_id]["message"] = f"Validating files (batch {batch_label})..."
            combined_path = os.path.join(
                tempfile.gettempdir(), f"spotify_combined_{user_id}_{uuid.uuid4().hex}.json"
            )
            _active_combined.clear()
            _active_combined.append(combined_path)
            logger.info("[gcs-ingest][job=%s] Validating and combining %d file(s) (batch %s)...",
                        job_id, len(batch_temp_paths), batch_label)
            _validate_and_combine(batch_temp_paths, combined_path)
            combined_mb = os.path.getsize(combined_path) / 1_048_576
            logger.info("[gcs-ingest][job=%s] Combined file ready: %s (%.2f MB) (batch %s)",
                        job_id, combined_path, combined_mb, batch_label)

            # Delete downloaded temp files — combined file takes over
            for tp in batch_temp_paths:
                try:
                    if os.path.exists(tp):
                        os.remove(tp)
                        _active_temp_paths.remove(tp)
                except OSError:
                    pass

            # --- ingest ---
            # Scale progress so 0–100% spans the full job, not just one batch
            batch_base = int(batch_idx * 100 / num_batches)
            batch_span = int(100 / num_batches)

            def progress_cb(pct: int, msg: str, _base=batch_base, _span=batch_span):
                actual_pct = _base + int(pct * _span / 100)
                logger.info("[gcs-ingest][job=%s][user=%s] Progress %d%% — %s", job_id, user_id, actual_pct, msg)
                upload_jobs[job_id] = {
                    "status": "processing",
                    "progress": actual_pct,
                    "message": msg,
                    "user_id": user_id,
                    "created_at": upload_jobs[job_id].get("created_at"),
                }

            upload_jobs[job_id]["message"] = "Waiting for another upload to finish..."
            logger.info("[gcs-ingest][job=%s] Starting ingestion pipeline (batch %s)...", job_id, batch_label)
            async with _ingestion_semaphore:
                result = await asyncio.to_thread(run_ingestion, combined_path, user_id, spotify_client, progress_cb)
            # run_ingestion's finally block deletes combined_path
            _active_combined.clear()

            batch_events = result["total_events"]
            total_events += batch_events
            logger.info("[gcs-ingest][job=%s][user=%s] Batch %s complete. events=%d cumulative=%d elapsed=%.1fs",
                        job_id, user_id, batch_label, batch_events, total_events, round(time.monotonic() - t0, 1))

        elapsed = round(time.monotonic() - t0, 1)
        logger.info("[gcs-ingest][job=%s][user=%s] All batches complete. total_events=%d duration=%.1fs",
                    job_id, user_id, total_events, elapsed)

        created_at = upload_jobs[job_id].get("created_at")
        upload_jobs[job_id] = {
            "status": "complete",
            "progress": 100,
            "message": f"Done! {total_events} events ingested.",
            "total_events": total_events,
            "user_id": user_id,
            "created_at": created_at,
        }

        # Clean up GCS blobs after all batches succeed
        for gcs_path in gcs_paths:
            try:
                bucket.blob(gcs_path).delete()
                logger.info("[gcs-ingest][job=%s] Deleted GCS blob: gs://%s/%s", job_id, _GCS_BUCKET, gcs_path)
            except Exception:
                pass

    except Exception as e:
        elapsed = round(time.monotonic() - t0, 1)
        logger.exception("[gcs-ingest][job=%s][user=%s] Task failed after %.1fs", job_id, user_id, elapsed)
        created_at = upload_jobs[job_id].get("created_at")
        upload_jobs[job_id] = {"status": "error", "progress": 0, "message": str(e), "user_id": user_id, "created_at": created_at}
        _cleanup()
        # Best-effort GCS cleanup on failure
        try:
            gcs_client = storage.Client()
            bucket = gcs_client.bucket(_GCS_BUCKET)
            for gcs_path in gcs_paths:
                try:
                    bucket.blob(gcs_path).delete()
                except Exception:
                    pass
        except Exception:
            pass


@router.post("/upload/ingest")
async def ingest_from_gcs(request: Request, spotify_user_id: Optional[str] = Cookie(default=None, alias="__session")):
    """Triggers ingestion for files already uploaded to GCS via signed URLs."""
    if not spotify_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    body = await request.json()
    gcs_paths = body.get("gcs_paths", [])
    if not gcs_paths:
        raise HTTPException(status_code=400, detail="No GCS paths provided.")

    _prune_old_jobs()
    job_id = uuid.uuid4().hex
    upload_jobs[job_id] = {"status": "processing", "progress": 0, "message": "Starting ingestion...", "user_id": spotify_user_id, "created_at": time.time()}
    asyncio.create_task(_run_gcs_ingestion_task(job_id, gcs_paths, spotify_user_id))
    return {"job_id": job_id}


@router.post("/upload")
async def upload_history(
    files: List[UploadFile] = File(...),
    spotify_user_id: Optional[str] = Cookie(default=None, alias="__session"),
):
    """Accepts one or more Spotify Extended Streaming History JSON files and kicks off ingestion."""
    if not spotify_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    # Validate each file's extension and MIME type upfront before any I/O
    for file in files:
        if not file.filename.endswith(".json"):
            raise HTTPException(
                status_code=400,
                detail=f"'{file.filename}' is not a JSON file. Only .json files are accepted.",
            )
        if file.content_type and file.content_type not in _ACCEPTED_MIME_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"'{file.filename}' has an unexpected content type '{file.content_type}'.",
            )

    # Pre-assign temp paths before streaming so every file is tracked for cleanup
    # even if an error occurs mid-stream
    assigned = [
        (file, os.path.join(tempfile.gettempdir(), f"spotify_upload_{spotify_user_id}_{uuid.uuid4().hex}.json"))
        for file in files
    ]
    combined_path = os.path.join(
        tempfile.gettempdir(),
        f"spotify_combined_{spotify_user_id}_{uuid.uuid4().hex}.json",
    )

    def _cleanup():
        for _, tp in assigned:
            try:
                if os.path.exists(tp):
                    os.remove(tp)
            except OSError:
                pass
        try:
            if os.path.exists(combined_path):
                os.remove(combined_path)
        except OSError:
            pass

    try:
        for file, temp_path in assigned:
            await _stream_file_to_disk(file, temp_path)

        _validate_and_combine([tp for _, tp in assigned], combined_path)

    except HTTPException:
        _cleanup()
        raise
    except Exception as e:
        _cleanup()
        raise HTTPException(status_code=500, detail=f"Failed to process uploaded files: {e}")
    else:
        # Individual temp files are no longer needed — combined file takes over
        for _, tp in assigned:
            try:
                if os.path.exists(tp):
                    os.remove(tp)
            except OSError:
                pass

    _prune_old_jobs()
    job_id = uuid.uuid4().hex
    upload_jobs[job_id] = {"status": "processing", "progress": 0, "message": "Starting ingestion...", "user_id": spotify_user_id, "created_at": time.time()}

    asyncio.create_task(_run_ingestion_task(job_id, combined_path, spotify_user_id))

    return {"job_id": job_id}


@router.get("/upload/status/{job_id}")
async def upload_status(job_id: str, spotify_user_id: Optional[str] = Cookie(default=None, alias="__session")):
    """Returns the current status of an upload/ingestion job."""
    if not spotify_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    job = upload_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    return job


from api.websocket import chat_endpoint
router.add_api_websocket_route("/ws/chat", chat_endpoint)
