"""MobileCount (MobileNetV2 + Light-Weight RefineNet), tùy chọn nhánh mask đám đông.

Kiến trúc giống notebook train trên Kaggle, nên checkpoint `best_mc_*.pth` load trực tiếp.
"""
import math
import os
import time
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision

from .domain import DensityResult

STRIDE = 4
DENSITY_SCALE = 100.0
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)


class ChainedResidualPool(nn.Module):
    """Chuỗi max pool 5×5 + conv 1×1 cộng dồn: gom ngữ cảnh rộng với rất ít tham số."""

    def __init__(self, channels: int, n_stages: int = 4):
        super().__init__()
        self.pool = nn.MaxPool2d(5, stride=1, padding=2)
        self.convs = nn.ModuleList([nn.Conv2d(channels, channels, 1, bias=False) for _ in range(n_stages)])

    def forward(self, x):
        top = x
        for conv in self.convs:
            top = conv(self.pool(top))
            x = x + top
        return x


class ASPP(nn.Module):
    """Ngữ cảnh đa tỉ lệ (chỉ để load được checkpoint có ASPP)."""

    def __init__(self, cin: int, cout: int, rates=(1, 2, 4)):
        super().__init__()
        self.branches = nn.ModuleList([
            nn.Sequential(nn.Conv2d(cin, cout, 1 if r == 1 else 3, padding=0 if r == 1 else r, dilation=r, bias=False),
                          nn.ReLU(inplace=True)) for r in rates])
        self.image_pool = nn.Sequential(nn.AdaptiveAvgPool2d(1), nn.Conv2d(cin, cout, 1, bias=False), nn.ReLU(inplace=True))
        self.merge = nn.Sequential(nn.Conv2d(cout * (len(rates) + 1), cout, 1, bias=False), nn.ReLU(inplace=True))

    def forward(self, x):
        feats = [b(x) for b in self.branches]
        feats.append(F.interpolate(self.image_pool(x), size=x.shape[-2:], mode="bilinear", align_corners=False))
        return self.merge(torch.cat(feats, dim=1))


class CountModel(nn.Module):
    def __init__(self, mask: bool = False, aspp: bool = False, channels: int = 64):
        super().__init__()
        f = torchvision.models.mobilenet_v2(weights=None).features
        self.encoder = nn.ModuleList([f[:4], f[4:7], f[7:14], f[14:18]])
        self.project = nn.ModuleList([nn.Conv2d(c, channels, 1, bias=False) for c in (24, 32, 96)])
        self.deep = ASPP(320, channels) if aspp else nn.Sequential(nn.Conv2d(320, channels, 1, bias=False), nn.ReLU(inplace=True))
        self.crp = nn.ModuleList([ChainedResidualPool(channels) for _ in range(4)])
        self.fuse = nn.ModuleList([nn.Conv2d(channels, channels, 1, bias=False) for _ in range(3)])
        self.head = nn.Sequential(nn.Conv2d(channels, channels, 3, padding=1), nn.ReLU(inplace=True), nn.Conv2d(channels, 1, 1))
        self.mask_head = (nn.Sequential(nn.Conv2d(channels, 32, 3, padding=1), nn.ReLU(inplace=True), nn.Conv2d(32, 1, 1))
                          if mask else None)

    def forward(self, x):
        feats = []
        for stage in self.encoder:
            x = stage(x)
            feats.append(x)
        y = self.crp[3](self.deep(feats[3]))
        for i in (2, 1, 0):
            y = F.interpolate(self.fuse[i](y), size=feats[i].shape[-2:], mode="bilinear", align_corners=False)
            y = self.crp[i](F.relu(self.project[i](feats[i]) + y))
        den = self.head(y)
        if self.mask_head is None:
            return den, None
        logit = self.mask_head(y)
        return den * torch.sigmoid(logit), logit


def load_model(path: Path) -> CountModel:
    """Load checkpoint, tự nhận biết nhánh mask và ASPP; chạy trên CPU."""
    torch.set_num_threads(max(1, (os.cpu_count() or 2) // 2))   # chừa một nửa nhân cho luồng đọc và vẽ video
    state = torch.load(path, map_location="cpu", weights_only=True)
    model = CountModel(mask=any(k.startswith("mask_head") for k in state),
                       aspp=any(k.startswith("deep.branches") for k in state))
    model.load_state_dict(state)
    return model.eval()


def warmup(model: CountModel, analysis_width: int, runs: int = 2) -> float:
    """Chạy thử trên frame 16:9 rỗng để PyTorch chuẩn bị sẵn kernel cho kích thước này.
    Lần suy luận đầu tiên chậm hơn nhiều; nếu để tới lúc đang phát video mới chạy thì luồng video bị nghẽn."""
    frame = np.zeros((round(analysis_width * 9 / 16), analysis_width, 3), np.uint8)
    start = time.perf_counter()
    for _ in range(runs):
        infer(model, frame, analysis_width)
    return time.perf_counter() - start


def infer(model: CountModel, frame_bgr: np.ndarray, analysis_width: int) -> DensityResult:
    """Density map (người mỗi ô 4×4 của frame phân tích) và mask xác suất."""
    h0, w0 = frame_bgr.shape[:2]
    scale = analysis_width / w0
    h, w = round(h0 * scale), analysis_width
    rgb = cv2.cvtColor(cv2.resize(frame_bgr, (w, h), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
    img = (rgb.astype(np.float32) / 255.0 - MEAN) / STD
    H, W = math.ceil(h / 32) * 32, math.ceil(w / 32) * 32
    img = np.pad(img, ((0, H - h), (0, W - w), (0, 0)))
    x = torch.from_numpy(np.ascontiguousarray(img.transpose(2, 0, 1)))[None]
    with torch.inference_mode():
        den, logit = model(x)
    hh, ww = math.ceil(h / STRIDE), math.ceil(w / STRIDE)
    density = den[0, 0, :hh, :ww].numpy() / DENSITY_SCALE
    mask = None if logit is None else torch.sigmoid(logit)[0, 0, :hh, :ww].numpy()
    return DensityResult(density=density, mask=mask, scale=scale)
