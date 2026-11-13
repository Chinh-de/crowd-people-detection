from pathlib import Path

import cv2
import numpy as np
import pytest


def _write(path: Path, fourcc: str, n: int = 30, fps: float = 10, size=(320, 240)) -> Path | None:
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*fourcc), fps, size)
    if not w.isOpened():
        return None
    for i in range(n):
        f = np.full((size[1], size[0], 3), 40, np.uint8)
        x = (i * 8) % (size[0] - 40)
        f[100:140, x:x + 40] = (0, 200, 255)                 # hình vuông chạy ngang
        w.write(f)
    w.release()
    return path


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory) -> Path:
    return _write(tmp_path_factory.mktemp("vid") / "sample.mp4", "mp4v")


@pytest.fixture(scope="session")
def sample_webm(tmp_path_factory) -> Path:
    path = _write(tmp_path_factory.mktemp("vid") / "sample.webm", "VP80")
    if path is None or path.stat().st_size == 0:
        pytest.skip("Bản OpenCV này không ghi được VP80 (webm)")
    return path
