# Demo giám sát đám đông

Ứng dụng web chạy trên máy cá nhân, chỉ cần CPU. Phát video có sẵn hoặc livestream YouTube, đếm người bằng mô hình **MobileCount + Mask**, khoanh vùng đám đông, phân tích chuyển động bằng optical flow **Farneback**, và cảnh báo bất thường. Mỗi cảnh báo được lưu kèm ảnh và clip bằng chứng.

Demo đáp ứng các mục sau trong đề tài:

| Yêu cầu (de.md) | Trong demo |
|---|---|
| 3.1 Pipeline thời gian thực, lưu chuỗi thời gian | Hai luồng xử lý; bảng `samples` trong SQLite |
| 3.2 Heatmap mật độ trên khung hình | Chế độ hiển thị "Video + nhận diện", "Nền xám + nhận diện" |
| 3.3 Bất thường theo mật độ, ROI | Cảnh báo vượt sức chứa (vùng, toàn khung) và tăng đột ngột; vẽ vùng giám sát (tên, sức chứa, chiều đi) và vùng loại trừ trên web |
| 3.4 Bất thường theo chuyển động | Farneback; mô hình phát hiện bất thường (ngưỡng tốc độ, Isolation Forest, autoencoder UMN); đi ngược chiều quy định |
| 4.1 Cơ sở dữ liệu | SQLite: `samples`, `events` |
| 4.2 Dashboard | Video kèm lớp nhận diện, biểu đồ, danh sách cảnh báo có ảnh và clip |
| 5.3 Hiệu năng | FPS video, số lần phân tích mỗi giây, thời gian mỗi lần phân tích hiển thị trực tiếp |

## Cài đặt

Yêu cầu: [uv](https://docs.astral.sh/uv/), Node.js 20 trở lên.

```bash
cd demo/backend
uv sync                      # tạo .venv, cài PyTorch bản CPU và các thư viện

cd ../frontend
npm install
npm run build                # dựng giao diện vào frontend/dist
```

Hai model nằm ở `demo/models/` (không đưa lên git, chép từ `results/` tải về từ Kaggle). Mỗi cách lấy checkpoint có MAE test thấp nhất:

| File | Model | Nguồn | MAE / MSE (ShanghaiTech B) |
|---|---|---|---|
| `mask.pth` (mặc định) | MobileCount + Mask | `last_mc_c1_mask_s42_partB.pth` | 8,49 / 13,77 |
| `baseline.pth` | MobileCount (baseline) | `last_mc_baseline_s42_partB.pth` | 9,30 / 15,47 |

Mô hình phát hiện bất thường (giai đoạn 2) nằm ở `demo/models/anomaly/`, chép từ output của `anomaly_umn.ipynb`:

| File | Mô hình |
|---|---|
| `ae_umn_scene1.pth` + `_norm.npz` | Autoencoder (flow · mask + mật độ) train trên UMN bối cảnh bãi cỏ |
| `ae_umn_scene2.pth` + `_norm.npz` | như trên, bối cảnh trong nhà |
| `ae_umn_scene3.pth` + `_norm.npz` | như trên, bối cảnh quảng trường |

Ngưỡng tốc độ và Isolation Forest không cần file: chúng tự học trên camera trong lúc "học mức bình thường".

Đổi mô hình của cả hai giai đoạn ngay trên web, nút **Cấu hình** → **Mô hình**. Đổi mô hình đếm thì mô hình bất thường học lại; đổi mô hình bất thường thì học lại ngay từ các mẫu đã thu, không phải chờ. Muốn dùng thư mục khác thì đặt `CROWD_MODELS=đường/dẫn/thư_mục`. Loader tự nhận biết nhánh mask và ASPP từ checkpoint.

Video thử `data/videos/umn.avi` (tập UMN, 11 clip hoảng loạn ở 3 bối cảnh) để xem phát hiện bất thường. Vùng chữ đỏ "Abnormal Crowd Activity" của video đã được đặt sẵn làm vùng loại trừ (`data/zones/umn.avi.json`), để mô hình không đọc được nhãn. Học mức bình thường khoảng 12 giây đầu mỗi bối cảnh, trước lúc mọi người bỏ chạy.

Video thử: bản ghi 30 phút phố Temple Bar, Dublin, ở `data/videos/part_1794421962_000.webm`. Vùng loại trừ cho bản ghi này đã lưu sẵn ở `data/zones/` (giống livestream Dublin vì cùng góc camera) và tự nạp khi mở video.

## Chạy

```bash
cd demo/backend
uv run crowd-demo            # mở http://127.0.0.1:8000
```

Khi sửa giao diện có thể chạy chế độ phát triển: chạy `uv run crowd-demo`, rồi ở cửa sổ khác chạy `cd demo/frontend && npm run dev`, sau đó mở http://localhost:5173.

Chạy test backend: `cd demo/backend && uv run pytest`.

## Cách dùng

1. **Chọn nguồn**
   - *Video có sẵn:* chọn file trong `demo/data/videos/`, hoặc bấm "Tải lên…". Hỗ trợ `.mp4`, `.webm`, `.mkv`, `.avi`, `.mov`, `.ts`.
   - *Livestream YouTube:* dán link livestream đang phát. Mặc định là EarthCam Dublin.
   - Chọn đúng **múi giờ của camera** để giờ hiển thị và giờ trong log là giờ địa phương.
2. **Chế độ hiển thị** (trên khung video)
   - Chỉ video.
   - Video + nhận diện.
   - Chỉ nhận diện, trên nền đen.
   - Nền xám + nhận diện.
3. **Vẽ vùng:** bấm "Vẽ vùng" trên khung video.
   - Click để thêm điểm; double-click, hoặc click lại điểm đầu, để đóng vùng.
   - Bấm Esc để hủy vùng đang vẽ; click phải vào một vùng để xóa vùng đó.
   - Bấm "Lưu vùng" để lưu. Vùng được nhớ theo từng nguồn, lưu ở `data/zones/`.
   - *Vùng giám sát* là nơi đếm người. *Vùng loại trừ* bị bỏ qua, ví dụ biển quảng cáo, màn hình, đèn trang trí mà mô hình hay nhầm là người.
   - Mỗi vùng giám sát có **tên** và **sức chứa** riêng, sửa ở bảng "Vùng giám sát" bên phải (hoặc mục "Vùng" trong "Cấu hình"). Số người trong vùng vượt sức chứa thì có cảnh báo "Vượt sức chứa", áp dụng ngay, không cần học. Lối một chiều thì chọn thêm **chiều đi** cho phép.
4. **Học mức bình thường**
   - Sau vài giây chạy, hệ thống tự học trong 5 phút đầu. Có thể nhập số giây rồi bấm "Học lại" vào lúc cảnh đang bình thường.
   - Chỉ cảnh báo bất thường chuyển động cần học; các cảnh báo còn lại áp dụng ngay.
5. **Chọn mô hình** (nút "Cấu hình" → mục "Mô hình"), kèm kết quả nghiên cứu của mô hình đang chọn:
   - Giai đoạn 1, đếm người: MobileCount + Mask, baseline, hoặc bản tinh chỉnh Dublin (MAE / MSE trên ShanghaiTech B; MAE trên camera Dublin).
   - Giai đoạn 2, phát hiện bất thường: ngưỡng tốc độ, Isolation Forest flow + mask + mật độ, 3 autoencoder UMN (AUC trên UMN). Với autoencoder chọn thêm cách chuẩn hóa: theo camera, hoặc gốc UMN (chỉ hợp với video UMN).
6. **Cảnh báo**
   - Khung video chuyển viền đỏ, luật đang kích hoạt được tô đỏ.
   - Danh sách cảnh báo có ảnh bằng chứng. Click vào một cảnh báo để xem clip khoảng 5 giây trước và 5 giây sau sự kiện.
7. **Gắn nhãn** (trang "Gắn nhãn", chỉ quản trị): sửa điểm đầu người của bộ ảnh `data/labels/dublin_live/`.
   - "Chụp khung": lưu khung hiện tại của một camera đang chạy thành ảnh cần gắn nhãn.
   - "Tạo nhãn nháp": đặt điểm bằng mô hình (ưu tiên bản tinh chỉnh Dublin). Nháp có thể thiếu nhiều điểm, cần soát lại.
   - "Xuất dataset": tải file zip 960×540 cho notebook `finetune_dublin.ipynb`.
8. **Phân loại cảnh báo để lưu mẫu fine-tune:** mỗi cảnh báo tự lưu một mẫu ở `data/samples/<id>/`:
   ảnh gốc, mask, bản đồ mật độ, nhãn điểm nháp, đặc trưng chuyển động và ảnh xem trước.
   - Quản trị phân loại "Đúng" hoặc "Báo nhầm" trong chi tiết cảnh báo; trang Lịch sử xem lại theo phân loại.
   - "Gửi sang Gắn nhãn" để sửa điểm cho mô hình đếm; "Xuất mẫu đã phân loại" tải zip kèm `manifest.csv`.
   - Hệ thống chỉ lưu mẫu, **không tự học**; train lại làm riêng. Mẫu chưa phân loại bị xóa cùng thời hạn với clip.

Video được phát trễ vài giây để lớp phủ khớp với hình; độ trễ hiện trên khung video.

## Kiến trúc

```
Nguồn (file / YouTube HLS)
  │
  ├── Luồng đọc (FPS gốc) ── frame ──┬── bộ đệm vòng (6–12 s, ≤10 fps) ──→ clip bằng chứng
  │                                  └── ghép lớp phủ mới nhất ─→ JPEG ─→ /api/stream.mjpg
  │
  └── Luồng phân tích (CPU, ~1–3 lần/giây), lấy frame mới nhất:
        model MobileCount + Mask → density, mask
        → đếm theo vùng và ô lưới (density.py)
        → optical flow Farneback giữa frame hiện tại và frame ~0,2 s trước (motion.py)
        → đặc trưng lưới 8×8 (anomaly.py) → mô hình bất thường đang chọn → điểm bất thường
        → 4 cảnh báo (rules.py) → cảnh báo → ảnh + clip (evidence.py) → SQLite (storage.py)
        → cập nhật lớp phủ (overlay.py)

Trình duyệt: <img> MJPEG + canvas vẽ vùng; WebSocket /api/ws (trạng thái 2 lần/giây); REST để cấu hình
```

Video không phải chờ mô hình: lớp phủ chỉ cập nhật sau mỗi lần phân tích, nên **trễ hơn hình khoảng một lần phân tích** (0,5–0,7 s trên CPU).

| Module (`backend/src/crowd_demo/`) | Trách nhiệm |
|---|---|
| `config.py` | Đường dẫn, kích thước phân tích, các hằng số |
| `domain.py` | Kiểu dữ liệu dùng chung |
| `model.py` | MobileCount (+ mask), load checkpoint, suy luận trên CPU |
| `zones.py` | Vùng giám sát và vùng loại trừ (tọa độ chuẩn hóa 0–1) |
| `density.py` | Đếm theo vùng, tổng theo ô lưới, ô quá dày |
| `motion.py` | Farneback, các đặc trưng chuyển động |
| `anomaly.py` | Giai đoạn 2: đặc trưng lưới 8×8, ngưỡng tốc độ, Isolation Forest, autoencoder UMN |
| `rules.py` | 4 cảnh báo |
| `overlay.py` | Vẽ lớp nhận diện theo 4 chế độ |
| `storage.py` | SQLite |
| `evidence.py` | Bộ đệm frame, ảnh và clip H.264 |
| `sources.py` | Nguồn file (lặp, tua, tạm dừng) và YouTube (tự kết nối lại) |
| `pipeline.py` | Ghép các module, hai luồng xử lý |
| `api.py` | REST, WebSocket, MJPEG, file bằng chứng |

**Cơ sở dữ liệu** (`data/runs/<thời điểm>/crowd.db`, mỗi lần chạy một file):
- `samples(t, source, total, roi, excluded, max_cell, speed, entropy, counterflow, anomaly, anomaly_limit)`: mỗi lần phân tích một dòng.
- `events(id, t, source, rule, value, threshold, message, snapshot, clip)`: mỗi cảnh báo một dòng. Ảnh và clip nằm ở `data/runs/<thời điểm>/evidence/`.

**API chính:**

| Route | Chức năng |
|---|---|
| `GET/POST /api/videos` | Danh sách video, tải video lên |
| `POST /api/source` | Mở nguồn |
| `POST /api/stop` | Dừng nguồn |
| `POST /api/playback` | Phát, tạm dừng, tua (video có sẵn) |
| `PUT /api/view` | Đổi chế độ hiển thị |
| `GET /api/models`, `PUT /api/model` | Mô hình đếm (giai đoạn 1): danh sách kèm MAE/MSE, đổi mô hình |
| `GET /api/anomaly-models`, `PUT /api/anomaly-model` | Mô hình bất thường (giai đoạn 2): danh sách kèm AUC UMN, đổi mô hình và cách chuẩn hóa |
| `GET/PUT /api/zones` | Lấy và lưu vùng, kèm tên và sức chứa từng vùng (`roi_meta`) |
| `GET/PUT /api/rules` | Lấy và chỉnh luật |
| `POST /api/calibrate` | Học mức bình thường |
| `GET /api/series` | Chuỗi số liệu |
| `GET /api/events` | Danh sách cảnh báo |
| `GET /api/stream.mjpg` | Luồng video |
| `WS /api/ws` | Trạng thái trực tiếp |

## Cách phát hiện bất thường

**Đếm người.** Mô hình dự đoán density map (bằng 1/4 kích thước ảnh). Số người là tổng density trong vùng giám sát, trừ phần nằm trong vùng loại trừ. Nhánh mask cho xác suất "có người" ở từng ô 4×4 pixel; ngưỡng 0,5 của mask tạo ra đường bao vàng quanh vùng đám đông.

**Chuyển động.** Farneback tính vector (dx, dy) cho từng điểm ảnh giữa hai frame cách nhau khoảng 0,2 s, trên ảnh xám rộng 320 px. Chỉ giữ các điểm trong vùng giám sát, thuộc vùng có người (mask lớn hơn 0,5) và dịch chuyển ít nhất 0,5 px. Từ đó tính 4 đặc trưng:
- **Tốc độ:** độ dài vector trung bình chia cho thời gian giữa hai frame (px/s).
- **Hướng chính:** hướng của tổng các vector.
- **Mức hỗn loạn:** entropy của histogram 16 hướng, có trọng số theo độ dài vector, chuẩn hóa về 0–1. Bằng 0 khi mọi người đi cùng một hướng, bằng 1 khi hướng trải đều ra mọi phía.
- **Ngược chiều:** tỉ lệ (theo độ dài vector) các vector lệch hơn 120° so với hướng chính.

**Bốn cảnh báo.** Bất thường chuyển động phải đúng liên tục **2 giây** (chỉnh bằng "độ nhạy"); các cảnh báo khác **6 giây**. Mỗi đợt chỉ báo một lần, hai cảnh báo cùng loại cách nhau ít nhất **60 giây**. Số người làm mượt bằng trung vị 3 mẫu.

| Cảnh báo | Báo khi | Cần học |
|---|---|---|
| Bất thường chuyển động | điểm của mô hình giai đoạn 2 vượt ngưỡng học từ chính camera | có |
| Vượt sức chứa | số người trong một vùng, hoặc toàn khung, lớn hơn sức chứa người vận hành đặt | không |
| Tăng đột ngột | trong 60 giây tăng hơn max(10 người; 50% số cũ) | không |
| Đi ngược chiều | ở vùng đã chọn chiều đi, phần chuyển động lệch hơn 120° so với chiều đó vượt 40% (chỉnh được); bỏ qua khi quá ít chuyển động | không |


## Hiệu năng (máy thử)

Đo trên máy 12 nhân CPU, không dùng GPU, với livestream EarthCam Dublin 1920×1080, 30 FPS, ảnh phân tích rộng 960 px:

| Đại lượng | Giá trị |
|---|---|
| FPS video hiển thị | 25–28 |
| Tần suất phân tích (mô hình, flow, luật) | 1,5–1,6 lần/giây |
| Thời gian mỗi lần phân tích | 550–600 ms |
| Độ trễ lớp phủ so với hình | khoảng 0,6 s |
| Độ trễ phát cảnh báo sau khi điều kiện bắt đầu đúng | 3 lần phân tích, khoảng 2 s |

## Giới hạn đã biết

- Lớp phủ trễ hơn hình bằng thời gian một lần phân tích.
- Tốc độ chuyển động tính theo pixel/giây, chưa đổi ra m/s: người ở gần camera có vector dài hơn người ở xa. Vì các ngưỡng học từ chính camera đó, sai lệch này phần lớn được bù.
- Camera rung hoặc zoom làm cả khung hình chuyển động, có thể gây báo nhầm luật bất thường chuyển động.
- Mô hình học trên ShanghaiTech (ảnh ban ngày ở Thượng Hải). Với camera thật, đèn trang trí và biển hiệu đôi khi bị đếm thành người. Cách xử lý trong demo là vẽ vùng loại trừ.
- Livestream: lấy link qua yt-dlp mất khoảng 10–20 giây. Khi mạng chậm, luồng tự kết nối lại tối đa 5 lần.

## Hướng phát triển (chưa làm)

- **Autoencoder** trên chuỗi đặc trưng chuyển động: học từ dữ liệu bình thường, báo bất thường khi lỗi tái tạo cao. Cách này bắt được những dạng bất thường chưa có luật.
- **RAFT** thay cho Farneback khi cần optical flow chính xác hơn (cần GPU để chạy thời gian thực).
- **Hiệu chỉnh phối cảnh:** đổi số người mỗi ô thành người/m², và tốc độ thành m/s.
- **Đánh giá định lượng:** độ trễ và AUC trên dataset UMN (cảnh chạy tán loạn); MAE trên frame camera thật đã gán nhãn; tỉ lệ báo nhầm mỗi giờ trên bản ghi dài.
- **Thông báo** qua email hoặc Telegram khi có cảnh báo nghiêm trọng.
- **Nhiều camera** trên một dashboard; **dự đoán nguy cơ quá tải** từ xu hướng số người.
- Ngưỡng theo khung giờ (giờ cao điểm khác giờ vắng) khi có dữ liệu nhiều ngày.
