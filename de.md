
# Hệ thống đếm người, phát hiện đám đông bất thường phục vụ an ninh nơi công cộng (Crowd Anomaly Detection)

## 1. Mục đích

- Hiểu các kỹ thuật thị giác máy tính ứng dụng vào bài toán đếm người (**Crowd Counting**) trong cảnh đông đúc — nơi các phương pháp Object Detection thông thường hoạt động kém hiệu quả do người bị chồng lấn, che khuất lẫn nhau.
- Nắm được các phương pháp phát hiện hành vi/mật độ bất thường trong đám đông (**Crowd Anomaly Detection**): tăng đột biến mật độ, chuyển động hỗn loạn, dòng người di chuyển ngược chiều bất thường, tụ tập đông người tại khu vực cấm.
- Xây dựng được hệ thống giám sát thời gian thực có khả năng ước tính số lượng người, phát hiện các dấu hiệu bất thường và cảnh báo sớm phục vụ công tác an ninh tại nơi công cộng (ga tàu, quảng trường, sự kiện đông người, cổng trường/khu vực nhạy cảm).
- Thực hành xử lý bài toán đặc thù: dữ liệu đám đông có mật độ rất cao, đối tượng nhỏ, thay đổi liên tục — khác biệt với bài toán phát hiện đối tượng thưa (như xe cộ, biển số).

## 2. Các bước thực hiện

### Giai đoạn 1: Nghiên cứu lý thuyết nền tảng

#### 1.1. Tìm hiểu bài toán Crowd Counting

- Phân biệt hai hướng tiếp cận chính:

  - **Detection-based:** Sử dụng Object Detection để phát hiện và đếm từng người, chỉ hiệu quả với mật độ thấp đến trung bình.
  - **Density Estimation-based:** Dự đoán bản đồ mật độ (*density map*) cho toàn khung hình, sau đó tích phân để tính tổng số người. Phương pháp này hiệu quả hơn với đám đông rất dày đặc, không cần xác định vị trí từng cá thể.
- Tìm hiểu các kiến trúc mô hình Density Estimation phổ biến:

  - **MCNN (Multi-Column CNN).**
  - **CSRNet (Congested Scene Recognition Network).**
  - **MobileCount.**

  Đây là các hướng tiếp cận sử dụng mạng CNN để hồi quy bản đồ mật độ từ ảnh đầu vào. Bản đồ mật độ mục tiêu thường được tạo bằng cách áp dụng Gaussian kernel tại tọa độ đầu người.
- Tìm hiểu các bộ dữ liệu chuẩn cho bài toán đếm người:

  - ShanghaiTech Dataset (Part A/B).
  - UCF-QNRF.
  - JHU-CROWD++.

  Đây là các bộ dữ liệu ảnh đám đông được gán nhãn tọa độ đầu người.

#### 1.2. Tìm hiểu bài toán Crowd Anomaly Detection

- Tìm hiểu các dạng bất thường trong đám đông cần phát hiện:
  - **Tăng mật độ đột ngột:** Đám đông tụ tập nhanh bất thường, có nguy cơ chen lấn hoặc giẫm đạp.
  - **Chuyển động hỗn loạn (Panic Movement):** Mọi người chạy tán loạn theo nhiều hướng khác nhau thay vì di chuyển có trật tự.
  - **Dòng người ngược chiều (Counter-flow):** Có thể là dấu hiệu của sự cố hoặc tình huống bất thường.
  - **Tụ tập tại khu vực cấm/nhạy cảm:** Phát hiện dựa trên vùng ROI (*Region of Interest*) được định nghĩa trước.
- Tìm hiểu kỹ thuật trích xuất đặc trưng chuyển động:
  - **Optical Flow:** Tính toán vector chuyển động của các điểm ảnh hoặc vùng ảnh giữa những khung hình liên tiếp, làm cơ sở xác định hướng và tốc độ di chuyển của đám đông.
- Tìm hiểu các phương pháp phát hiện bất thường dựa trên đặc trưng chuyển động:
  - **Unsupervised Learning:** Sử dụng Autoencoder để tái tạo đặc trưng Optical Flow bình thường và phát hiện bất thường thông qua sai số tái tạo (*Reconstruction Error*).
  - **Phân tích thống kê:** Đánh giá độ đồng nhất hướng di chuyển, entropy của trường vector chuyển động.
  - **Social Force Model:** Mô hình hóa tương tác và chuyển động của các cá thể trong đám đông để hỗ trợ phát hiện hành vi bất thường.

### Giai đoạn 2: Chuẩn bị dữ liệu và mô hình đếm người

#### 2.1. Chuẩn bị dữ liệu

- Tải các bộ dữ liệu chuẩn như ShanghaiTech hoặc UCF-QNRF để huấn luyện và đánh giá mô hình Density Estimation.
- Thu thập hoặc quay video giám sát mẫu tại khu vực công cộng thực tế, hoặc sử dụng video giám sát công khai có sẵn để kiểm thử trên dữ liệu thực tế, không chỉ trên ảnh tĩnh trong dataset chuẩn.

#### 2.2. Xây dựng/huấn luyện mô hình Crowd Counting

- Sử dụng mô hình pretrained như CSRNet hoặc MCNN có sẵn trên GitHub làm baseline.
- Đánh giá độ chính xác trên tập test chuẩn bằng các chỉ số:
  - **MAE (Mean Absolute Error).**
  - **MSE (Mean Squared Error).**
- Nếu cần, fine-tune mô hình trên dữ liệu tự thu thập tại khu vực giám sát cụ thể để tăng độ chính xác, phù hợp với góc camera và điều kiện ánh sáng thực tế.

### Giai đoạn 3: Xây dựng pipeline xử lý thời gian thực

#### 3.1. Xây dựng module ước tính số lượng người theo thời gian thực

- Xây dựng pipeline xử lý:

  `Camera/Video → Frame Extraction → Density Estimation → Density Map → Count Estimation`
- Đưa từng khung hình qua mô hình Density Estimation để sinh bản đồ mật độ, sau đó tính tổng giá trị bản đồ để ước tính số lượng người trong khung hình.
- Tối ưu tốc độ xử lý bằng cách giảm độ phân giải đầu vào hoặc xử lý cách khung hình để đạt tốc độ gần thời gian thực.
- Lưu chuỗi số liệu mật độ theo thời gian (*Time Series*) để phục vụ phân tích xu hướng và phát hiện bất thường.

#### 3.2. Xây dựng module trực quan hóa mật độ (Heatmap)

- Overlay bản đồ mật độ dạng heatmap lên khung hình gốc.
- Giúp người giám sát trực quan hóa các khu vực đông người nhất trong khung hình.

#### 3.3. Xây dựng module phát hiện bất thường dựa trên mật độ

- Thiết lập ngưỡng cảnh báo theo số lượng người ước tính, ví dụ vượt quá sức chứa an toàn của khu vực.
- Phát hiện tốc độ tăng mật độ bất thường trong một khoảng thời gian ngắn. Tình huống này có thể nguy hiểm hơn mật độ cao nhưng ổn định.
- Cảnh báo khi mật độ trong một vùng ROI cụ thể, chẳng hạn khu vực cấm tụ tập hoặc lối thoát hiểm, vượt ngưỡng cho phép.

#### 3.4. Xây dựng module phát hiện bất thường dựa trên chuyển động (Optical Flow)

- Tính toán Optical Flow giữa các khung hình liên tiếp:
  - **Dense Optical Flow:** Sử dụng thuật toán Farneback trong OpenCV.
  - **RAFT:** Sử dụng mô hình học sâu nếu cần độ chính xác cao hơn.
- Trích xuất đặc trưng từ trường vector chuyển động:
  - Hướng di chuyển trung bình.
  - Độ phân tán hướng hoặc mức độ hỗn loạn.
  - Tốc độ di chuyển trung bình.
- Áp dụng mô hình phát hiện bất thường:
  - Autoencoder được huấn luyện trên đặc trưng chuyển động bình thường.
  - Ngưỡng thống kê dựa trên entropy hướng di chuyển.
- Gắn cờ các khung hình hoặc thời điểm có chuyển động hỗn loạn bất thường, có thể liên quan đến chạy tán loạn hoặc sự cố.

### Giai đoạn 4: Xây dựng hệ thống cảnh báo và giao diện giám sát

#### 4.1. Xây dựng cơ sở dữ liệu lưu trữ

- Lưu chuỗi thời gian về số lượng người ước tính theo từng thời điểm.
- Lưu các sự kiện cảnh báo bất thường đã phát hiện, bao gồm:
  - Thời gian xảy ra.
  - Loại bất thường.
  - Khung hình bằng chứng.
  - Camera nguồn.

#### 4.2. Xây dựng giao diện giám sát (Dashboard)

- Hiển thị luồng video với heatmap mật độ được overlay theo thời gian thực.
- Hiển thị biểu đồ số lượng người theo thời gian (*Line Chart*) để quan sát xu hướng tăng/giảm mật độ theo khung giờ.
- Hiển thị danh sách cảnh báo bất thường đã ghi nhận, kèm khung hình bằng chứng.
- Cho phép người giám sát xem lại đoạn video tương ứng với sự kiện.
- **Tùy chọn:** Tích hợp cảnh báo qua email hoặc thông báo đẩy khi phát hiện bất thường nghiêm trọng.

### Giai đoạn 5: Kiểm thử và đánh giá

#### 5.1. Kiểm thử độ chính xác đếm người

- So sánh số lượng người ước tính của mô hình với số liệu đếm thủ công trên các đoạn video có mật độ khác nhau:
  - Mật độ thưa.
  - Mật độ trung bình.
  - Mật độ rất đông.
- Tính sai số MAE để đánh giá độ chính xác của mô hình.

#### 5.2. Kiểm thử phát hiện bất thường

- Mô phỏng hoặc sử dụng video có sẵn về các tình huống:
  - Tụ tập đông đột ngột.
  - Mọi người chạy tán loạn.
- Có thể sử dụng video công khai về tình huống báo động giả hoặc sơ tán để kiểm tra khả năng phát hiện và cảnh báo đúng thời điểm.
- Đo độ trễ cảnh báo, tính từ lúc sự kiện bất thường xảy ra đến lúc hệ thống phát cảnh báo.
- Đánh giá tỷ lệ báo động giả (*False Positive*) khi đám đông đông nhưng vẫn di chuyển bình thường, có trật tự.

#### 5.3. Đánh giá hiệu năng thời gian thực

- Đo FPS xử lý của toàn bộ pipeline, bao gồm Density Estimation, Optical Flow và phân tích bất thường.
- Đánh giá khả năng đáp ứng yêu cầu xử lý thời gian thực.

#### 5.4. Tùy chọn nâng cao

- **Giám sát đa camera:** Tổng hợp mật độ từ nhiều camera trong cùng một khu vực, ví dụ nhiều lối vào của một sự kiện, vào dashboard trung tâm.
- **Nhận diện hành vi cụ thể:** Tích hợp Action Recognition để phát hiện các hành vi như ngã hoặc ẩu đả, sử dụng mô hình 3D-CNN hoặc Skeleton-based Action Recognition.
- **Dự đoán nguy cơ quá tải:** Xây dựng mô hình dự đoán nguy cơ tụ tập quá tải dựa trên xu hướng tăng mật độ theo chuỗi thời gian.

## 3. Yêu cầu kết quả đạt được

- Xây dựng hoặc huấn luyện thành công mô hình ước tính mật độ đám đông, đạt chỉ số MAE/MSE hợp lý trên tập dữ liệu chuẩn và đối chiếu với kết quả được công bố trong các bài báo tham khảo.
- Pipeline xử lý thời gian thực hoạt động ổn định, hiển thị số lượng người ước tính và heatmap mật độ trên luồng video.
- Module phát hiện bất thường dựa trên mật độ và chuyển động hoạt động chính xác, phát hiện đúng ít nhất 1–2 kịch bản bất thường mô phỏng như tụ tập đột ngột hoặc chuyển động hỗn loạn, với độ trễ cảnh báo chấp nhận được.
- Dashboard giám sát trực quan, hiển thị đầy đủ heatmap, biểu đồ xu hướng mật độ và danh sách cảnh báo kèm bằng chứng.
- Có báo cáo minh chứng đầy đủ:
  - Số liệu đánh giá độ chính xác đếm người.
  - Kết quả kiểm thử phát hiện bất thường.
  - Hiệu năng xử lý (FPS và độ trễ cảnh báo).
- Hoàn thiện mã nguồn bao gồm:
  - Mô hình Density Estimation.
  - Module Optical Flow/Anomaly Detection.
  - Dashboard.
  - Cơ sở dữ liệu.
  - Tài liệu mô tả kiến trúc hệ thống và hướng dẫn triển khai.

## 4. Tài liệu tham khảo

1. **CSRNet (Congested Scene Recognition Network)** — Bài báo gốc:https://arxiv.org/abs/1802.10062
2. **MCNN (Multi-Column CNN for Crowd Counting)** — Bài báo gốc:https://ieeexplore.ieee.org/document/7780439
3. **ShanghaiTech Crowd Counting Dataset:**https://www.kaggle.com/datasets/tthien/shanghaitech
4. **UCF-QNRF Dataset:**https://www.crcv.ucf.edu/data/ucf-qnrf/
5. **OpenCV Optical Flow Documentation:**https://docs.opencv.org/4.x/d4/dee/tutorial_optical_flow.html
6. **RAFT (Recurrent All-Pairs Field Transforms for Optical Flow)** — Bài báo gốc:https://arxiv.org/abs/2003.12039
7. **Mehran et al., “Abnormal Crowd Behavior Detection using Social Force Model”** — Tham khảo phương pháp Social Force Model phát hiện bất thường:https://ieeexplore.ieee.org/document/5206641
8. **PyTorch Documentation:**
   https://pytorch.org/docs/stable/index.html
