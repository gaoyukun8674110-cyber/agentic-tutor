"""Start the local FastAPI development server."""

import os
from pathlib import Path

import uvicorn

if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parent)
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
    )
