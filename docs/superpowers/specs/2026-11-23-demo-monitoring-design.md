# Web giám sát đám đông thực tế: nhiều camera, đăng nhập, lịch sử, thống kê

## Mục đích

Thầy yêu cầu đề tài có **ứng dụng thực tế**. Demo hiện tại chỉ chạy một nguồn mỗi lần, mỗi lần chạy một file SQLite riêng, không đăng nhập và không xem lại được lịch sử. Phần này biến demo thành một web giám sát như hệ thống thật:

- quản lý danh sách camera;
- cho nhiều camera chạy cùng lúc, nhưng vẫn tập trung vào một camera chính;
- có đăng nhập;
- lưu lịch sử lâu dài, truy xuất cảnh báo kèm clip, và thống kê.

## Mục tiêu

1. **Danh sách camera.** Mỗi camera có tên, nguồn (livestream YouTube hoặc file video), múi giờ, cờ "tự chạy", mô hình đếm, mô hình bất thường và cách chuẩn hóa, vùng giám sát (có tên, sức chứa), vùng loại trừ, và cấu hình luật. Mọi thứ lưu trong SQLite và còn nguyên sau khi khởi động lại.
2. **Nhiều camera chạy cùng lúc, tối đa 4.** Giao diện ghi rõ giới hạn này do phần cứng (CPU) và hiện tốc độ phân tích của từng camera. Bật camera thứ 5 thì bị từ chối, kèm thông báo.
3. **Tập trung vào một camera chính.**
   - Trang Giám sát giữ bố cục hiện tại (video lớn, số liệu, cảnh báo) cho camera chính.
   - Các camera đang chạy khác hiện thành ô nhỏ: ảnh trực tiếp làm mới khoảng mỗi giây, số người, trạng thái. Ô có cảnh báo nổi đỏ. Bấm vào ô thì camera đó thành camera chính.
4. **Đăng nhập bằng tài khoản khai báo trong biến môi trường.**
   - `CROWD_ADMIN_USER` và `CROWD_ADMIN_PASSWORD`: quản trị, làm được mọi việc.
   - `CROWD_VIEWER_USER` và `CROWD_VIEWER_PASSWORD` (không bắt buộc): chỉ xem. Được xem mọi thứ và xác nhận cảnh báo, nhưng không sửa camera, vùng, luật, mô hình, và không bật hay tắt camera.
   - Chưa đăng nhập thì mọi API, luồng video, file bằng chứng và WebSocket đều bị chặn.
5. **Nhật ký thao tác.** Ghi lại đăng nhập (cả thành công lẫn thất bại), đăng xuất, thêm, sửa, xóa, bật, tắt camera, sửa vùng, luật, mô hình, học lại, và xác nhận cảnh báo. Mỗi dòng có người làm, thời điểm và nội dung. Chỉ quản trị xem được.
6. **Xác nhận cảnh báo.** Cảnh báo có trạng thái "Chưa xử lý" hoặc "Đã xử lý", kèm người xử lý, thời điểm và ghi chú. Số cảnh báo chưa xử lý hiện trên thanh điều hướng.
7. **Trang Lịch sử cảnh báo.**
   - Lọc theo khoảng thời gian, camera, loại luật, trạng thái; có phân trang.
   - Mỗi dòng có ảnh thu nhỏ. Bấm vào để xem clip bằng chứng, ảnh lớn, và số người cùng điểm bất thường trong ±2 phút quanh sự kiện.
   - Xuất CSV danh sách đang lọc.
8. **Trang Thống kê**, chọn camera và khoảng thời gian (hôm nay, 7 ngày, 30 ngày, tự chọn):
   - thẻ tóm tắt: số người trung bình, số người cao nhất kèm thời điểm, tổng số cảnh báo, tỉ lệ đã xử lý;
   - số người theo thời gian (trung bình và cao nhất), tự gom theo phút, giờ hoặc ngày tùy độ dài khoảng;
   - bản đồ nhiệt số người trung bình theo giờ trong ngày × thứ trong tuần;
   - số cảnh báo theo ngày, chia theo loại luật.
9. **Lưu trữ.**
   - Một file `data/crowd.db` cho mọi camera.
   - Số liệu thô được gom thành từng phút ngay khi ghi.
   - Tự dọn: số liệu thô quá 3 ngày, clip và ảnh quá 30 ngày (đặt được qua biến môi trường). Bản ghi cảnh báo vẫn giữ, chỉ đánh dấu là đã xóa clip.
10. **Khởi động lại.** Camera có cờ "tự chạy" được bật lại lúc server khởi động. Nguồn livestream mất kết nối thì tự thử lại (đã có) và trạng thái hiện "mất tín hiệu".

## Không làm

- Không có cơ sở dữ liệu người dùng, không đăng ký tài khoản, không đổi mật khẩu trên web. Tài khoản chỉ nằm trong biến môi trường.
- Không dùng máy chủ cơ sở dữ liệu, hàng đợi hay dịch vụ ngoài. Chạy trên một máy bằng một lệnh, như bây giờ.
- Không chạy trên GPU, không ghi hình liên tục 24/7 (chỉ có clip cảnh báo).
- Không gửi cảnh báo qua email hay tin nhắn.

## Điều cần tránh

- Tài khoản không đúng mà vẫn xem được video hoặc file bằng chứng.
- Bật nhiều camera làm camera chính giật đến mức không dùng được. Đây là lý do giới hạn 4 camera và có thông báo về phần cứng.
- Mất lịch sử khi khởi động lại, hoặc ổ đĩa đầy vì clip.

## Ràng buộc

- Giữ nguyên ngăn xếp: FastAPI và SQLite cho backend, React, Vite, TypeScript và Recharts cho frontend.
- Chạy trên CPU. Hai mô hình đếm được dùng chung giữa các camera, không nạp lại cho từng camera.
- Đọc biến môi trường từ file `demo/backend/.env` nếu có (python-dotenv đã đi kèm `uvicorn[standard]`). File `.env` không đưa lên git; có sẵn `.env.example`.
- Giao diện theo thiết kế vừa làm: nền tối, Fira Sans và Fira Code, icon SVG.

## Quyết định của người dùng

- Chạy nhiều camera cùng lúc, tối đa 2–4. Giao diện báo đây là giới hạn phần cứng, và tập trung chủ yếu vào một camera.
- Đăng nhập cơ bản, tài khoản và mật khẩu lấy từ biến môi trường.
- Thống kê để truy xuất lịch sử; lưu lại clip cảnh báo.

## Quyết định của người viết thiết kế (cần kiểm tra)

- Có thêm tài khoản chỉ xem, không bắt buộc; nhật ký thao tác; xác nhận cảnh báo.
- Giới hạn là 4 camera, đặt được qua `CROWD_MAX_CAMERAS`.
- Phiên đăng nhập: cookie HttpOnly, SameSite=Lax, ký HMAC bằng `CROWD_SECRET`, hạn 12 giờ.
  - Thiếu `CROWD_SECRET` thì sinh ngẫu nhiên mỗi lần chạy, nên khởi động lại là phải đăng nhập lại.
  - Thiếu tài khoản quản trị thì dùng `admin` / `admin` và in cảnh báo rõ ra log.
- Đăng nhập sai thì chờ 0,5 giây rồi mới trả lời, để làm chậm dò mật khẩu.
- Chuyển trang bằng hash (`#/giam-sat`, `#/lich-su`, `#/thong-ke`, `#/camera`, `#/nhat-ky`), không thêm thư viện router.
- Ô camera phụ dùng ảnh chụp làm mới mỗi giây (`/snapshot.jpg`) thay vì nhiều luồng MJPEG, cho nhẹ.
- Lần chạy đầu, nếu chưa có camera nào, tự tạo sẵn 3 camera mẫu: livestream EarthCam Dublin, bản ghi Temple Bar và `umn.avi`. Vùng đã lưu cho các nguồn này được chuyển vào cơ sở dữ liệu.
- Dữ liệu ở `data/runs/` cũ không chuyển sang; vẫn để nguyên trên đĩa.

## Để người xây dựng tự quyết

- Bố cục cụ thể của trang Lịch sử, Thống kê, Camera và Nhật ký, miễn theo hệ thiết kế hiện tại.
- Kích thước phân trang, cách gom thời gian cụ thể (ngưỡng nào thì gom theo phút, giờ hay ngày).
- Cấu trúc module backend.
