import sys
import os
from dotenv import load_dotenv

# Define project root and add `src` to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
src_root = os.path.join(project_root, 'src')
if src_root not in sys.path:
    sys.path.insert(0, src_root)

# Load .env
load_dotenv(os.path.join(project_root, '.env'))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router as api_router

app = FastAPI(
    title="Spotify AI Assistant API",
    description="Backend API for the Spotify LLM project.",
    version="1.0.0",
)

# Allow React local dev server to communicate with the FastAPI backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
