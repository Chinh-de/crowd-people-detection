"""Điểm chạy: `uv run crowd-demo` rồi mở http://127.0.0.1:8000"""
import uvicorn

from .api import create_app


def run() -> None:
    uvicorn.run(create_app(), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()
