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

**Chuẩn so sánh chung.** Các bài trên UMN báo cáo AUC theo từng khung, tính riêng cho từng bối cảnh: 1 là bãi cỏ (1.453 khung), 2 là trong nhà (4.144 khung), 3 là quảng trường (2.142 khung). Nhiều bài báo cáo thêm AUC tổng. Mô hình chỉ train trên khung bình thường của chính bối cảnh đó; nhãn là nhãn gốc của video. Đề tài báo cáo theo đúng dạng này.

**Cách chia train của đề tài** theo Marsden và cộng sự [18]: với mỗi bối cảnh, 200 khung đầu của mỗi clip gộp lại làm tập train, mọi khung còn lại là tập test. Các bài khác dùng cùng chỉ số nhưng số khung train khác nhau, ví dụ 1000 khung mỗi bối cảnh [25] hoặc 760/1100/1000 khung [23]. Vì vậy chỉ [18] so được trực tiếp; các dòng khác dùng để định vị kết quả.

| Phương pháp | Nơi công bố | AUC BC1 | AUC BC2 | AUC BC3 | AUC tổng | Khung train | Nguồn số liệu |
|---|---|---|---|---|---|---|---|
| Optical flow [14] | CVPR 2009 | – | – | – | 0,84 | khác | Bảng 1 của [24] |
| Social Force [14] | CVPR 2009 | – | – | – | 0,96 | khác | Bảng 1 của [24] |
| Chaotic invariants [20] | CVPR 2010 | – | – | – | 0,99 | khác | Bảng 1 của [24] |
| Sparse reconstruction [15] | CVPR 2011 | 0,995 | 0,975 | 0,964 | – | khác | Bảng 1 của [24] |
| Matrix approximation [21] | ICIP 2012 | 0,994 | 0,971 | 0,996 | – | khác | Bảng 1 của [24] |
| Holistic + GMM [18] | ICIP 2016 | – | – | – | 0,929 | 200 khung đầu mỗi clip | **Cùng cách chia với đề tài** |
| Object-centric AE [22] | CVPR 2019 | – | 0,991 | – | 0,996 | khác | bài gốc |
| AED-Net [23] | 2019 | – | – | – | 0,997 | 760 / 1100 / 1000 | bài gốc |
| Training-less [24] | 2019 | 0,988 | 0,978 | 0,984 | 0,982 | không train | bài gốc |
| Scene perception [25] | – | 0,996 | 0,962 | 0,987 | 0,983 | 1000 mỗi bối cảnh | bài gốc |
| **Đề tài · IF-flow·mask+density** | | **0,991** | **0,973** | **0,961** | **0,959** | 200 khung đầu mỗi clip | `anomaly_umn.ipynb` |

Ghi chú:
- Hầu hết các bài đạt 0,95–0,99, và bối cảnh 2 (trong nhà) thường thấp nhất [22].
- Nhãn ảnh hưởng nhiều tới bối cảnh 2: một bài báo cáo AUC bối cảnh 2 là 78,4% với nhãn gốc và 95,6% với nhãn sửa tay [26]. Đề tài dùng nhãn gốc.
- Số của Commotion Measure [16] (0,98), MDT [19] (0,995), Plug-and-Play CNN [17] (0,98) và [13] (0,99) chỉ có ở dạng AUC tổng do bài khác trích lại, nên không đưa vào bảng.

**Kết quả của đề tài** (`anomaly_umn.ipynb`). Phương pháp tốt nhất là Isolation Forest trên flow trong mask người cộng mật độ người:
- AUC trung bình 3 bối cảnh **0,975**, AUC tổng **0,959**, EER 8,2%.
- **Vượt [18]** (0,929), bài duy nhất dùng cùng cách chia. Cũng vượt Optical flow (0,84) và ngang Social Force (0,96) [14].
- Bối cảnh 2, khó nhất, đạt 0,973: cao hơn [25] (0,962) và [21] (0,971), xấp xỉ [15] (0,975) và [24] (0,978).
- AUC trung bình thấp hơn các phương pháp tốt nhất khoảng 0,01 (0,978–0,987) và thấp hơn các bài gần mức trần (0,996–0,997 [22], [23]). Các bài này dùng nhiều khung train hơn.

**Đóng góp của mô hình đếm (ablation, AUC trung bình 3 bối cảnh):**

| Mô hình phát hiện | Chỉ flow | Flow trong mask | Thêm mật độ |
|---|---|---|---|
| Isolation Forest | 0,891 | 0,891 | **0,975** (+0,084) |
| Autoencoder | 0,922 | **0,943** (+0,021) | 0,936 (+0,014) |

- Thêm số người vào 4 đặc trưng toàn khung: 0,926 → 0,956 (+0,030).
- Mật độ giúp nhiều nhất ở bối cảnh 2: Isolation Forest từ 0,749 lên 0,973.
- Số người là đặc trưng đơn lẻ tách bình thường và bất thường rõ nhất: số người giảm mạnh khi đám đông bỏ chạy khỏi khung hình. Đây cũng là giới hạn cần ghi: trên camera thật, cảnh vắng người không phải lúc nào cũng là bất thường.

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
20. S. Wu, B. E. Moore, M. Shah. *Chaotic Invariants of Lagrangian Particle Trajectories for Anomaly Detection in Crowded Scenes.* CVPR 2010.
21. L. Wang, M. Dong. *Real-time Detection of Abnormal Crowd Behavior using a Matrix Approximation-based Approach.* ICIP 2012.
22. R. T. Ionescu, F. S. Khan, M.-I. Georgescu, L. Shao. *Object-centric Auto-encoders and Dummy Anomalies for Abnormal Event Detection in Video.* CVPR 2019. arXiv:1812.04960.
23. T. Wang, Z. Miao, Y. Chen, Y. Zhou, G. Shan, H. Snoussi. *AED-Net: An Abnormal Event Detection Network.* arXiv:1903.11891, 2019.
24. A. Sikdar, A. S. Chowdhury. *An Adaptive Training-less System for Anomaly Detection in Crowd Scenes.* arXiv:1906.00705, 2019.
25. X. Zhang, D. Ma, H. Yu, Y. Huang, P. Howell, B. Stevens. *Scene Perception Guided Crowd Anomaly Detection.* Bản tác giả, University of Portsmouth.
26. Patil và cộng sự. *Global Abnormal Events Detection in Crowded Scenes using Context Location and Motion-rich Spatio-temporal Volumes.* IET Image Processing, 2018.
