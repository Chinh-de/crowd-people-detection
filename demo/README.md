# Demo giám sát đám đông

Ứng dụng web chạy trên máy cá nhân, chỉ cần CPU. Phát video có sẵn hoặc livestream YouTube, đếm người bằng mô hình **MobileCount + Mask**, khoanh vùng đám đông, phân tích chuyển động bằng optical flow **Farneback**, và cảnh báo bất thường. Mỗi cảnh báo được lưu kèm ảnh và clip bằng chứng.

Demo đáp ứng các mục sau trong đề tài:

| Yêu cầu (de.md) | Trong demo |
|---|---|
| 3.1 Pipeline thời gian thực, lưu chuỗi thời gian | Hai luồng xử lý; bảng `samples` trong SQLite |
| 3.2 Heatmap mật độ trên khung hình | Chế độ hiển thị "Video + nhận diện", "Nền xám + nhận diện" |
| 3.3 Bất thường theo mật độ, ROI | Luật quá đông, ô quá dày, tăng đột ngột; vẽ vùng giám sát và vùng loại trừ trên web |
| 3.4 Bất thường theo chuyển động | Farneback, luật hỗn loạn và ngược chiều |
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

Đổi model ngay trên web (nút **Model** dưới khung video); đổi model thì hệ thống học lại mức bình thường. Muốn dùng thư mục khác thì đặt `CROWD_MODELS=đường/dẫn/thư_mục`. Loader tự nhận biết nhánh mask và ASPP từ checkpoint.

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
2. **Chế độ hiển thị** (dưới khung video)
   - Chỉ video.
   - Video + nhận diện.
   - Chỉ nhận diện, trên nền đen.
   - Nền xám + nhận diện.
3. **Vẽ vùng:** bấm "Vẽ vùng giám sát / loại trừ".
   - Click để thêm điểm; double-click, hoặc click lại điểm đầu, để đóng vùng.
   - Bấm Esc để hủy vùng đang vẽ; click phải vào một vùng để xóa vùng đó.
   - Bấm "Lưu vùng" để lưu. Vùng được nhớ theo từng nguồn, lưu ở `data/zones/`.
   - *Vùng giám sát* là nơi đếm người. *Vùng loại trừ* bị bỏ qua, ví dụ biển quảng cáo, màn hình, đèn trang trí mà mô hình hay nhầm là người.
4. **Học mức bình thường**
   - Sau vài giây chạy, hệ thống tự học trong 5 phút đầu. Có thể bấm "Học mức bình thường" để học lại vào lúc cảnh đang bình thường.
   - Trong lúc học, chỉ ngưỡng **sức chứa tối đa** do người dùng đặt có hiệu lực.
5. **Chọn model:** MobileCount + Mask (có đường bao vùng đám đông) hoặc baseline, để so sánh trên cùng cảnh.
6. **Cảnh báo**
   - Khung video chuyển viền đỏ, luật đang kích hoạt được tô đỏ.
   - Danh sách cảnh báo có ảnh bằng chứng. Click vào một cảnh báo để xem clip khoảng 5 giây trước và 5 giây sau sự kiện.

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
        → 5 luật (rules.py) → cảnh báo → ảnh + clip (evidence.py) → SQLite (storage.py)
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
| `rules.py` | Học mức bình thường, 5 luật cảnh báo |
| `overlay.py` | Vẽ lớp nhận diện theo 4 chế độ |
| `storage.py` | SQLite |
| `evidence.py` | Bộ đệm frame, ảnh và clip H.264 |
| `sources.py` | Nguồn file (lặp, tua, tạm dừng) và YouTube (tự kết nối lại) |
| `pipeline.py` | Ghép các module, hai luồng xử lý |
| `api.py` | REST, WebSocket, MJPEG, file bằng chứng |

**Cơ sở dữ liệu** (`data/runs/<thời điểm>/crowd.db`, mỗi lần chạy một file):
- `samples(t, source, total, roi, excluded, max_cell, speed, entropy, counterflow)`: mỗi lần phân tích một dòng.
- `events(id, t, source, rule, value, threshold, message, snapshot, clip)`: mỗi cảnh báo một dòng. Ảnh và clip nằm ở `data/runs/<thời điểm>/evidence/`.

**API chính:**

| Route | Chức năng |
|---|---|
| `GET/POST /api/videos` | Danh sách video, tải video lên |
| `POST /api/source` | Mở nguồn |
| `POST /api/stop` | Dừng nguồn |
| `POST /api/playback` | Phát, tạm dừng, tua (video có sẵn) |
| `PUT /api/view` | Đổi chế độ hiển thị |
| `GET /api/models`, `PUT /api/model` | Danh sách model, đổi model |
| `GET/PUT /api/zones` | Lấy và lưu vùng |
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

**Học mức bình thường.** Trong N giây (mặc định 5 phút), hệ thống ghi lại các số đo rồi lấy trung vị *m* và độ lệch bền *σ = 1,4826 × MAD* (MAD là trung vị độ lệch tuyệt đối) cho từng đại lượng. Nhờ vậy ngưỡng tự khớp với từng camera và từng khung cảnh. Sau khi học xong, mức nền được tính lại mỗi 30 s theo 15 phút gần nhất, để theo kịp nhịp phố thay đổi trong ngày (phố đông dần lên vào buổi tối). Đổi lại, một đám đông tích tụ rất chậm (hơn 7–8 phút) sẽ thành "bình thường"; giới hạn cứng cho trường hợp này là ô **sức chứa tối đa**.

**Năm luật.** Mỗi luật phải đúng **liên tục 6 giây** mới cảnh báo (tính theo giây, không theo số lần phân tích, nên không phụ thuộc tốc độ máy). Mỗi đợt chỉ báo một lần, và hai cảnh báo cùng loại cách nhau ít nhất **60 giây**. Số người được làm mượt bằng trung vị 3 mẫu.

| Luật | Điều kiện |
|---|---|
| Quá đông | số người > *m* + max(3σ; 30%·*m*; 5 người); hoặc > sức chứa tối đa do người dùng đặt |
| Ô quá dày | ô lưới (64×64 px) đông nhất > max(4; 1,3 × phân vị 95 của lúc bình thường) |
| Tăng đột ngột | số người hiện tại − trung vị của khoảng [t − 60 s, t − 20 s] > max(10 người; 50%) |
| Hỗn loạn | tốc độ > *m* + 4·max(σ; 10%·*m*; 0,5) **và** mức hỗn loạn > *m* + 4·max(σ; 0,02) (chạy tán loạn theo nhiều hướng) |
| Ngược chiều | tỉ lệ ngược chiều > max(30%; *m* + 4·max(σ; 0,05)) |

Các mức sàn (5 người, 4 người/ô, 30%...) để lúc cảnh vắng hoặc đứng yên (σ ≈ 0) ngưỡng không bị kéo sát mức hiện tại. Trên giao diện, nút **i** cạnh tiêu đề "Luật cảnh báo" giải thích cơ chế chung, nút **i** ở từng luật hiện công thức với tham số và ngưỡng đang dùng, giá trị hiện tại, và lưu ý cho phố đi bộ hai chiều.

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
- Camera rung hoặc zoom làm cả khung hình chuyển động, có thể gây báo nhầm luật hỗn loạn.
- Mô hình học trên ShanghaiTech (ảnh ban ngày ở Thượng Hải). Với camera thật, đèn trang trí và biển hiệu đôi khi bị đếm thành người. Cách xử lý trong demo là vẽ vùng loại trừ.
- Livestream: lấy link qua yt-dlp mất khoảng 10–20 giây. Khi mạng chậm, luồng tự kết nối lại tối đa 5 lần.

## Hướng phát triển (chưa làm)

- **Autoencoder** trên chuỗi đặc trưng chuyển động: học từ dữ liệu bình thường, báo bất thường khi lỗi tái tạo cao. Cách này bắt được những dạng bất thường chưa có luật.
- **RAFT** thay cho Farneback khi cần optical flow chính xác hơn (cần GPU để chạy thời gian thực).
- **Hiệu chỉnh phối cảnh:** đổi số người mỗi ô thành người/m², và tốc độ thành m/s.
- **Hướng đi quy định cho từng vùng giám sát:** luật ngược chiều so với hướng do người vận hành đặt, thay vì so với hướng chính.
- **Đánh giá định lượng:** độ trễ và AUC trên dataset UMN (cảnh chạy tán loạn); MAE trên frame camera thật đã gán nhãn; tỉ lệ báo nhầm mỗi giờ trên bản ghi dài.
- **Thông báo** qua email hoặc Telegram khi có cảnh báo nghiêm trọng.
- **Nhiều camera** trên một dashboard; **dự đoán nguy cơ quá tải** từ xu hướng số người.
- Ngưỡng theo khung giờ (giờ cao điểm khác giờ vắng) khi có dữ liệu nhiều ngày.
