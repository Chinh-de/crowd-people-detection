# So sánh kết quả với các công bố

## 1. Kết quả của đề tài trên ShanghaiTech Part B

Đánh giá trên 316 ảnh test. Checkpoint được chọn bằng 10% ảnh train tách làm validation, nên tập test chỉ dùng một lần.

| Mô hình (đề tài huấn luyện lại) | MAE ↓ | MSE ↓ | Tham số (triệu) | GMACs* |
|---|---|---|---|---|
| MCNN (baseline) | 36,59 | 59,34 | 0,13 | 21,10 |
| CSRNet (baseline) | 10,43 | 16,07 | 16,26 | 324,79 |
| MobileCount (baseline, lịch học cosine 400 epoch) | 9,43 | 15,91 | 1,96 | 7,47 |
| **MobileCount + Mask (cải tiến)** | **9,07** | **15,16** | 1,98 | 8,37 |

\* Ảnh đầu vào 1024×768.

## 2. So sánh với các công bố trên ShanghaiTech Part B

Số liệu lấy theo bảng kết quả trong các bài báo ở mục 5.

| Phương pháp | Nơi công bố | MAE ↓ | MSE ↓ | So với MobileCount + Mask (9,07 / 15,16) |
|---|---|---|---|---|
| MCNN [1] | CVPR 2016 | 26,4 | 41,3 | Kém hơn |
| Switching-CNN [2] | CVPR 2017 | 21,6 | 33,4 | Kém hơn |
| CP-CNN [3] | ICCV 2017 | 20,1 | 30,1 | Kém hơn |
| ACSCP [4] | CVPR 2018 | 17,2 | 27,4 | Kém hơn |
| SaCNN [5] | WACV 2018 | 16,2 | 25,8 | Kém hơn |
| C-CNN, mô hình nhẹ thời gian thực [6] | ICASSP 2020 | 14,9 | 22,1 | Kém hơn |
| Mask-aware Networks [7] | IEEE TCSVT 2019 | 11,7 | 16,4 | Kém hơn |
| CSRNet [8] | CVPR 2018 | 10,6 | 16,0 | Kém hơn (CSRNet nặng hơn khoảng 40 lần về tính toán) |
| SCNet [9] | BMVC 2018 | 9,3 | 14,4 | Tương đương |
| MobileCount [10] | Neurocomputing 2020 | 9,0 | 15,4 | Tương đương (MSE của đề tài thấp hơn) |
| Mask-aware Networks, backbone CSRNet [7] | IEEE TCSVT 2019 | 8,6 | 13,3 | Tốt hơn, nhưng dùng backbone nặng |

**Kết luận.** MobileCount + Mask chỉ có khoảng 2 triệu tham số và chạy được trên CPU, nhưng vẫn đạt:
- kết quả **tương đương** MobileCount gốc (9,0) và SCNet (9,3);
- kết quả **tốt hơn** CSRNet (10,6), C-CNN (14,9) và Mask-aware Networks (11,7).

Mask-aware Networks [7] cũng thêm một nhánh dự đoán mask có người / không người để hỗ trợ ước lượng mật độ, giống ý tưởng cải tiến của đề tài. Ý tưởng này còn tham khảo SFANet [11] và Counting with Focus for Free [12]. Điểm khác của đề tài là gắn nhánh mask vào một mô hình nhẹ, và dùng mask trong ứng dụng để khoanh vùng đám đông.

**Câu đề xuất đưa vào báo cáo:**

> Trên ShanghaiTech Part B, MobileCount + Mask đạt MAE 9,07 / MSE 15,16 với khoảng 1,98 triệu tham số. Kết quả này tương đương MobileCount gốc (9,0 / 15,4) và SCNet (9,3 / 14,4). Mô hình cũng tốt hơn CSRNet (10,6 / 16,0) dù khối lượng tính toán ít hơn khoảng 40 lần, và tốt hơn Mask-aware Networks (11,7 / 16,4), một phương pháp cùng dùng nhánh mask.

## 3. Lưu ý khi so sánh

1. **Kết quả của đề tài là một lần chạy (seed 42).** Notebook `final_mobilecount_cv.ipynb` sẽ cho trung bình ± độ lệch chuẩn qua 5 fold. Khi có số này thì thay vào bảng ở mục 1.
2. **Giao thức của đề tài chặt hơn.** Đề tài chọn checkpoint bằng tập validation. Repo C³ Framework và repo MobileCount thì đánh giá trên chính tập test trong lúc huấn luyện. So sánh vì vậy bất lợi cho đề tài, và kết quả "tương đương" vẫn là kết quả tốt.
3. **Nguồn của từng con số:**
   - MCNN, Switching-CNN, CP-CNN, ACSCP, SaCNN, CSRNet và C-CNN lấy theo Bảng 1 của [6].
   - Mask-aware lấy theo Bảng III của [7].
   - SCNet lấy theo Bảng 4 của [9].
   - MobileCount lấy theo README của repo chính thức.

   Khi đưa vào báo cáo chính thức, nên trích dẫn đúng bài gốc của từng phương pháp và đối chiếu lại số liệu với bài gốc.
4. Cột tham số trong bảng của [6] có vẻ bị lệch hàng (ví dụ ACSCP chỉ có 0,07M). Vì vậy cột đó không được dùng ở đây.

## 4. Hướng tiếp theo: phát hiện chuyển động bất thường trên tập UMN

UMN gồm 11 đoạn video ở 3 bối cảnh. Mỗi đoạn có đám đông đi lại bình thường rồi đột ngột chạy tán loạn. Chỉ số so sánh là AUC tính theo từng khung hình.

**Giao thức của đề tài** theo Marsden và cộng sự [18]. Với mỗi bối cảnh, 200 khung đầu của mỗi clip gộp lại làm tập train; mọi khung còn lại là tập test. Mỗi bối cảnh có một mô hình riêng.

| Phương pháp | Nơi công bố | AUC ↑ | Ghi chú |
|---|---|---|---|
| Đặc trưng holistic + GMM [18] | ICIP 2016 | 0,929 | **Cùng giao thức với đề tài** |
| Social Force [14] | CVPR 2009 | 0,97 | Do [18] trích lại |
| Commotion Measure [16] | ICIP 2015 | 0,98 | Do [18] trích lại |
| MDT [19] | CVPR 2010 | 0,995 | Do [18] trích lại |

Bảng tham khảo thêm, lấy theo Bảng 2 của [13]. Các số này có thể dùng giao thức khác:

| Phương pháp | Nơi công bố | AUC ↑ |
|---|---|---|
| Optical flow [14] | CVPR 2009 | 0,84 |
| Social Force [14] | CVPR 2009 | 0,96 |
| Sparse Reconstruction [15] | CVPR 2011 | 0,97 |
| Commotion Measure [16] | ICIP 2015 | 0,98 |
| Plug-and-Play CNN (TCP) [17] | WACV 2018 | 0,98 |
| Adversarial Discriminator [13] | WACV 2019 | 0,99 |

**Mục tiêu của đề tài.** Autoencoder học mẫu chuyển động bình thường từ các đặc trưng theo lưới: optical flow lấy trong mask người, cộng với mật độ từ MobileCount + Mask. Notebook: `anomaly_umn.ipynb`. Mục tiêu:
- **vượt** [18] (0,929), bài dùng cùng giao thức và cũng dựa trên đặc trưng tốc độ và mật độ;
- **tiệm cận** khoảng 0,97–0,98 (Social Force, Commotion Measure);
- **vượt** luật đặt tay của demo.

Phần ablation "chỉ dùng flow" so với "flow + mật độ" sẽ cho thấy mô hình đếm có đóng góp cho bài toán phát hiện bất thường.

## 5. Tài liệu tham khảo

1. Y. Zhang, D. Zhou, S. Chen, S. Gao, Y. Ma. *Single-Image Crowd Counting via Multi-Column Convolutional Neural Network.* CVPR 2016.
2. D. B. Sam, S. Surya, R. V. Babu. *Switching Convolutional Neural Network for Crowd Counting.* CVPR 2017.
3. V. A. Sindagi, V. M. Patel. *Generating High-Quality Crowd Density Maps using Contextual Pyramid CNNs.* ICCV 2017.
4. Z. Shen, Y. Xu, B. Ni, M. Wang, J. Hu, X. Yang. *Crowd Counting via Adversarial Cross-Scale Consistency Pursuit.* CVPR 2018.
5. L. Zhang, M. Shi, Q. Chen. *Crowd Counting via Scale-Adaptive Convolutional Neural Network.* WACV 2018.
6. X. Shi, X. Li, C. Wu, S. Kong, J. Yang, L. He. *A Real-Time Deep Network for Crowd Counting.* ICASSP 2020. arXiv:2002.06515.
7. S. Jiang, X. Lu, Y. Lei, L. Liu. *Mask-aware Networks for Crowd Counting.* IEEE Transactions on Circuits and Systems for Video Technology, 2019. arXiv:1901.00039.
8. Y. Li, X. Zhang, D. Chen. *CSRNet: Dilated Convolutional Neural Networks for Understanding the Highly Congested Scenes.* CVPR 2018.
9. Z. Wang, Z. Xiao, K. Xie, Q. Qiu, X. Zhen, X. Cao. *In Defense of Single-column Networks for Crowd Counting.* BMVC 2018. arXiv:1808.06133.
10. P. Wang, C. Gao, Y. Wang, H. Li, Y. Gao. *MobileCount: An Efficient Encoder-Decoder Framework for Real-Time Crowd Counting.* Neurocomputing, 2020.
11. L. Zhu, Z. Zhao, C. Lu, Y. Lin, Y. Peng, T. Yao. *Dual Path Multi-Scale Fusion Networks with Attention for Crowd Counting (SFANet).* arXiv:1902.01115, 2019.
12. Z. Shi, P. Mettes, C. G. M. Snoek. *Counting with Focus for Free.* ICCV 2019.
13. M. Ravanbakhsh, E. Sangineto, M. Nabi, N. Sebe. *Training Adversarial Discriminators for Cross-channel Abnormal Event Detection in Crowds.* WACV 2019. arXiv:1706.07680.
14. R. Mehran, A. Oyama, M. Shah. *Abnormal Crowd Behavior Detection using Social Force Model.* CVPR 2009.
15. Y. Cong, J. Yuan, J. Liu. *Sparse Reconstruction Cost for Abnormal Event Detection.* CVPR 2011.
16. H. Mousavi, M. Nabi, H. Kiani, A. Perina, V. Murino. *Crowd Motion Monitoring using Tracklet-based Commotion Measure.* ICIP 2015.
17. M. Ravanbakhsh, M. Nabi, H. Mousavi, E. Sangineto, N. Sebe. *Plug-and-Play CNN for Crowd Motion Analysis: An Application in Abnormal Event Detection.* WACV 2018.
18. M. Marsden, K. McGuinness, S. Little, N. E. O'Connor. *Holistic Features for Real-Time Crowd Behaviour Anomaly Detection.* ICIP 2016. arXiv:1606.05310.
19. V. Mahadevan, W. Li, V. Bhalodia, N. Vasconcelos. *Anomaly Detection in Crowded Scenes.* CVPR 2010.
