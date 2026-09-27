# Kế hoạch cải thiện chất lượng và thời gian sinh câu hỏi

Ngày lập: 2026-09-08

Trạng thái: Kế hoạch đề xuất; các hạng mục dưới đây chưa được coi là đã triển khai.

## 1. Mục tiêu và căn cứ

Tăng số câu đúng và dùng được cho cả Ornith, Qwen và DeepSeek, sau đó giảm thời gian tạo một câu đạt chất lượng. Validator chặt hơn giúp chặn lỗi nhưng không tự chứng minh model sinh tốt hơn.

Benchmark chẩn đoán vừa hoàn tất có một yêu cầu cho mỗi model/dạng, trên cùng một snapshot OCR:

| Chỉ số | Prompt đối chứng | Prompt thử nghiệm |
|---|---:|---:|
| Yêu cầu có câu qua validator | 7/21 | 6/21 |
| Câu dùng ngay theo đánh giá sơ bộ của trợ lý | 3/21 | 1/21 |
| Thời gian trung bình mỗi yêu cầu, gồm retry | 109,64 giây | 103,52 giây |

Prompt thử nghiệm đã được rút lại. Các sửa lỗi contract, hậu kiểm và đối chiếu nguồn vẫn được giữ. Các số liệu trên chỉ là kết quả chẩn đoán, chưa đủ để kết luận mức cải thiện ổn định của từng model.

Tài liệu liên quan:

- [Báo cáo benchmark ban đầu và cập nhật](MODEL_QUESTION_BENCHMARK_LOCAL.md).
- [Kết quả A/B ba model](artifacts/benchmarks/three-model-comparison-20260908.md).
- [Phạm vi artifact và cách chạy benchmark](artifacts/benchmarks/README.md).

## 2. Nguyên tắc triển khai

- Kiểm tra từng thay đổi trên cả ba model; không suy ra kết quả của model khác từ Ornith.
- Không ép một đoạn nguồn sinh đủ bảy dạng khi nguồn không phù hợp.
- Không tăng điểm bằng cách từ chối gần hết yêu cầu hoặc nới validator để nhận câu lỗi.
- Mỗi thử nghiệm chỉ thay một nhóm yếu tố chính, giữ các yếu tố còn lại cố định và lưu cấu hình chính xác.
- Bảo toàn các thay đổi hiện có của dự án. Việc đổi model mặc định hoặc routing phải dựa trên kết quả kiểm chứng.
- Không dùng ngưỡng “5/7 dạng” làm thước đo chất lượng; cần đo trên nhiều câu và từng dạng riêng biệt.

## 3. Bước 1 — Chốt bộ đo và kết quả đối chứng

### Công việc

- [ ] Cố định prompt đối chứng, phiên bản model, cấu hình inference, chính sách retry và dữ liệu đầu vào.
- [ ] Ghi phiên bản/hash của prompt, validator, mã chọn nguồn và snapshot OCR cho mỗi lượt chạy.
- [ ] Chấm lại mẫu hiện có theo một rubric thống nhất, bao gồm tính đúng kiến thức, đáp án, dạng câu, Bloom, tính tự đủ nghĩa và chất lượng phương án nhiễu.
- [ ] Tách số yêu cầu, số lần gọi model, số candidate, số câu được nhận và số câu dùng được.
- [ ] Ghi nhận riêng nguồn không đủ điều kiện, từ chối đúng và từ chối nhầm.

### Chỉ số bắt buộc

| Chỉ số | Cách tính hoặc cách đọc |
|---|---|
| Tỷ lệ qua validator | Số yêu cầu có câu qua validator / tổng yêu cầu |
| Tỷ lệ dùng ngay | Số yêu cầu có câu qua validator và đạt rubric nội dung / tổng yêu cầu |
| Chất lượng trong số câu được nhận | Số câu dùng ngay / số câu được nhận |
| Tỷ lệ retry | Số yêu cầu cần gọi sửa / tổng yêu cầu |
| Thời gian trên mỗi câu dùng ngay | Tổng thời gian xử lý yêu cầu, gồm retry và yêu cầu thất bại / số câu dùng ngay |
| Độ trễ | Trung vị và p95 theo từng model/dạng; ghi rõ phạm vi đo |
| Từ chối | Đối chiếu nguồn đã gán nhãn để phân biệt từ chối đúng và nhầm |

Nếu không có câu dùng ngay, thời gian trên mỗi câu dùng ngay là không xác định, không ghi bằng 0. Báo cáo riêng nhóm nguồn đủ điều kiện và nhóm nguồn thiếu dữ kiện để tránh sai lệch do thành phần dữ liệu.

### Đầu ra và điều kiện chuyển bước

Một cấu hình đối chứng có thể tái lập, rubric thống nhất và báo cáo lỗi theo model/dạng. Chưa sửa prompt tiếp trước khi chốt cách đo.

## 4. Bước 2 — Chọn nguồn phù hợp với dạng câu

### Công việc

- [ ] Xác định điều kiện tối thiểu của nguồn cho từng dạng, dùng thông tin nguồn thực tế thay vì chỉ kiểm tra độ dài.
- [ ] Với sắp xếp: yêu cầu quy trình tuyến tính có ít nhất bốn bước rõ; nhận diện vòng lặp, rẽ nhánh và bước bị OCR thiếu.
- [ ] Với ghép cột: yêu cầu ít nhất ba quan hệ khái niệm–đặc điểm đủ rõ để ghép xác định; phương án nhiễu không được tạo thêm một đáp án đúng mơ hồ.
- [ ] Với nhiều lựa chọn: yêu cầu nguồn hỗ trợ nhiều nhận định đúng độc lập và đủ căn cứ phân biệt lựa chọn sai.
- [ ] Với tình huống: yêu cầu kiến thức có thể áp dụng để chọn quyết định/hành động, đủ dữ kiện để xác định đáp án.
- [ ] Với các dạng còn lại: kiểm tra nguồn có ý hoàn chỉnh, đủ bằng chứng cho đáp án và không đòi phục dựng phần OCR bị mất.
- [ ] Khi nguồn không phù hợp, tìm đoạn khác trong phạm vi tài liệu/chủ đề được yêu cầu với số lần tìm có giới hạn.
- [ ] Nếu vẫn không đủ nguồn, trả lý do không thể sinh rõ ràng qua luồng xử lý hiện có.

### Kiểm chứng

Tạo mẫu nguồn đủ điều kiện, thiếu dữ kiện, OCR đứt đoạn và nguồn có vòng lặp. Kiểm tra việc chọn lại nguồn, từ chối đúng, từ chối nhầm và thời gian phát sinh. Không chỉ kiểm tra số câu bị loại.

### Đầu ra và điều kiện chuyển bước

Luồng chọn nguồn theo dạng có lý do truy vết được, không mở rộng ra ngoài phạm vi tài liệu. Chứng minh giảm yêu cầu sinh từ nguồn không phù hợp mà vẫn nhận được nguồn hợp lệ.

## 5. Bước 3 — Sửa cách sinh theo nhóm lỗi

### Thứ tự ưu tiên

1. Câu phụ thuộc “nêu trên”, “bước 4” hoặc dữ kiện không xuất hiện trong câu.
2. Sai đáp án, giải thích mâu thuẫn và bổ sung kiến thức không được nguồn hỗ trợ.
3. Ghép cột thiếu nhiễu hoặc quan hệ ghép không xác định.
4. Tình huống thực chất chỉ là câu hỏi lý thuyết.
5. Nhiều lựa chọn sai tập đáp án và sắp xếp nguồn có vòng lặp thành chuỗi tuyến tính.

### Công việc

- [ ] Thử rút gọn chỉ dẫn dư thừa hoặc mâu thuẫn trong prompt, từng thay đổi một.
- [ ] Làm rõ cấu trúc đầu ra theo từng dạng và kiểm tra ảnh hưởng trên cả ba model.
- [ ] Dùng code kiểm soát cấu trúc khóa, số lượng phương án và biểu diễn quan hệ đáp án; nội dung vẫn phải dựa trên nguồn.
- [ ] Đưa lỗi cụ thể vào yêu cầu sửa và giới hạn retry; không lặp lại yêu cầu chung khi lỗi không thể khắc phục từ nguồn.
- [ ] Chỉ thêm một lượt model kiểm tra/sửa nếu lợi ích chất lượng bù được độ trễ đo được.
- [ ] Bổ sung kiểm thử cho lỗi thực tế và các trường hợp hợp lệ gần ranh giới, tránh chặn nhầm bằng heuristic quá rộng.

### Đầu ra và điều kiện chuyển bước

Các thay đổi nhỏ có kết quả A/B trên bộ phát triển. Chỉ đưa cấu hình có bằng chứng cải thiện sang bước kiểm tra độc lập; lưu cả thử nghiệm thất bại để tránh lặp lại.

## 6. Bước 4 — Đánh giá trên dữ liệu độc lập

### Công việc

- [ ] Chọn nhiều chương/tài liệu và chia bộ phát triển với bộ kiểm tra độc lập; tránh trùng đoạn hoặc nội dung gần như giống nhau giữa hai bộ.
- [ ] Bảo đảm nguồn đủ điều kiện cho từng dạng trong bộ đo chất lượng sinh; chuẩn bị riêng nhóm nguồn cần từ chối.
- [ ] Chốt cấu hình ứng viên trước khi chạy bộ kiểm tra; không dùng kết quả bộ này để tiếp tục chỉnh rồi coi là kiểm tra độc lập.
- [ ] Chạy tối thiểu 10 yêu cầu cho mỗi dạng/model: 210 yêu cầu mỗi cấu hình hoặc 420 yêu cầu cho một lượt A/B đầy đủ, chưa tính retry và nhóm kiểm tra từ chối bổ sung.
- [ ] Cân bằng thứ tự chạy đối chứng/ứng viên và ghi nhận tải model, warm-up, cache để giảm sai lệch thời gian.
- [ ] Giữ prompt, phản hồi thô, lựa chọn nguồn, thời gian và lý do loại cho từng case.
- [ ] Xuất bộ chấm mù, tách khóa model/cấu hình khỏi nội dung đưa cho reviewer.
- [ ] Báo cáo theo từng model và từng dạng, kèm số lượng mẫu và độ bất định; 10 mẫu mỗi tổ hợp vẫn chỉ là mức tối thiểu.

### Đầu ra và điều kiện chuyển bước

Bảng kết quả đối chứng/ứng viên trên bộ kiểm tra độc lập, có đánh giá nội dung. Phần chấm của trợ lý là sơ bộ; nghiệm thu chất lượng sư phạm cần reviewer/giảng viên. Nếu chưa có người chấm, ghi rõ hạng mục đang chờ, không đánh dấu hoàn tất.

## 7. Bước 5 — Tối ưu thời gian trên cấu hình đạt chất lượng

### Công việc

- [ ] Giảm retry bằng cách xử lý đúng nhóm lỗi thường gặp ở lần sinh đầu.
- [ ] Giảm nguồn không liên quan trong context nhưng giữ đủ dữ kiện và bằng chứng.
- [ ] Điều chỉnh giới hạn đầu ra theo dữ liệu đo được, theo dõi JSON bị cắt hoặc câu bị thiếu.
- [ ] Đo trung vị, p95 và tổng thời gian trên mỗi câu dùng ngay cho từng model/dạng.
- [ ] Kiểm tra lại chất lượng sau mỗi thay đổi hiệu năng; chỉ giữ thay đổi không làm giảm chất lượng trên bộ kiểm tra.

### Đầu ra

Cấu hình chất lượng/thời gian đã kiểm chứng cho từng model. Nếu một model vẫn chưa đạt, nêu rõ dạng hỗ trợ, giới hạn và nguyên nhân; không tuyên bố cải thiện cho cả ba dựa trên điểm trung bình.

## 8. Điều kiện hoàn tất

- [ ] Từng model có bằng chứng cải thiện chất lượng so với đối chứng trên dữ liệu độc lập; mức giảm ở một dạng không bị che bởi điểm tổng.
- [ ] Các lỗi nghiêm trọng đã biết có kiểm thử chống tái diễn và được đối chiếu bằng dữ liệu sinh thật.
- [ ] Nguồn thiếu điều kiện được xử lý rõ ràng, có đo từ chối nhầm.
- [ ] Báo cáo phân biệt câu qua validator, câu dùng ngay và câu cần chỉnh sửa.
- [ ] Tối ưu thời gian được đánh giá trên mỗi câu dùng ngay, đồng thời giữ chất lượng.
- [ ] Ghi rõ dạng/model đạt, chưa đạt, mức độ bằng chứng và các hạng mục cần reviewer.

Chưa đặt một tỷ lệ nghiệm thu tuyệt đối tùy ý. Ngưỡng triển khai cần được chốt theo mục đích sử dụng và yêu cầu của giảng viên trước khi nghiệm thu. Hoàn tất sửa code không đồng nghĩa hoàn tất đánh giá chất lượng.

## 9. Công việc bắt đầu trước

Thực hiện Bước 1, sau đó Bước 2. Giữ cấu hình model mặc định hiện tại trong giai đoạn lấy đối chứng. Chỉ quyết định thay model hoặc routing khi có kết quả kiểm chứng theo từng dạng.

## 10. Trạng thái triển khai — 2026-09-08

Đã triển khai phần kỹ thuật của Bước 1 và Bước 2:

- Benchmark ghi riêng số yêu cầu, số lần gọi model, số candidate, số yêu cầu/candidate qua validator, retry, trung vị, p95 và thời gian trên mỗi yêu cầu dùng ngay.
- Manifest lưu commit/trạng thái working tree, hash prompt/validator/snapshot, cấu hình inference, retry, chính sách chọn nguồn và metadata model Ollama đọc được tại thời điểm chạy.
- Xuất riêng `blind-review.json`, `review-key.json` và `source-review.json`; có lệnh tổng hợp kết quả sau khi reviewer điền chấm mù mà không sửa dữ liệu thô.
- Retrieval đánh giá từng chunk theo dạng câu, tìm lại trong số candidate có giới hạn và lưu trace gồm nguồn đã xét, lý do loại và nguồn được chọn.
- Nếu không có nguồn phù hợp, plan item được đánh dấu `INSUFFICIENT_SOURCE_FOR_QUESTION_TYPE`, không gọi model và trả lý do qua summary/checkpoint hiện có.
- Sắp xếp yêu cầu ít nhất bốn bước đánh số tuyến tính; ghép cột yêu cầu ít nhất ba quan hệ rõ; nhiều lựa chọn yêu cầu nhiều dữ kiện độc lập; tình huống yêu cầu bằng chứng có khả năng áp dụng. Các dạng còn lại yêu cầu ý hoàn chỉnh và quan hệ có thể kiểm chứng.
- Retry hiện chỉ giữ phần ngữ cảnh cần thiết, bảo toàn mã lỗi và thêm quy tắc sửa theo đúng mã; benchmark không còn làm mất mã lỗi khi chuyển sang lượt sửa.
- Ghép cột bị loại nếu hai cột lặp gần nguyên cùng mô tả. Nhiều lựa chọn bị loại nếu chép lựa chọn vào thân câu hoặc nếu bất kỳ đáp án đúng nào không xuất hiện nguyên văn trong cùng `source_context` liên tục.
- Chỉ số `accepted_quality_rate` là `null` cho đến khi có ít nhất một câu đã qua validator được reviewer chấm, thay vì báo sai `0` khi chưa chấm.

Pilot nhỏ cho Bước 3 đã chạy trên cùng snapshot/chunk và cấu hình inference:

- Pilot 3 model × 2 dạng khó: cấu hình trung gian đạt kỹ thuật 1/6 nhưng câu duy nhất lặp mô tả ở cả hai cột; validator v4 loại đúng câu này, còn 0 câu dùng được.
- Pilot tiếp theo 2 model × 2 dạng đạt kỹ thuật 1/4 trước kiểm tra grounding mới; câu duy nhất chỉ có bằng chứng cho một trong hai đáp án đúng, nên revalidation v4 còn 0 câu.
- Lần xác nhận cuối riêng Ornith/nhiều lựa chọn vẫn 0/1 sau một retry. Vì vậy chưa có bằng chứng để chạy bộ 210 yêu cầu hoặc đổi model/routing; các artifact thất bại được giữ lại để không lặp lại cấu hình này.
- Pilot nguồn hợp lệ mới buộc JSON schema theo từng dạng: Ornith tạo đúng cấu trúc ngay lượt đầu cho cả ghép cột và nhiều lựa chọn, nhưng kiểm tra nội dung phát hiện câu ghép cột không có chỉ dẫn ghép và câu nhiều lựa chọn chọn sai một đặc trưng. Hai lỗ này đã có validator chống tái diễn; kết quả accepted ban đầu không được tính là câu dùng được.
- Sau khi chọn đúng chunk dạng danh sách, đối chiếu OCR an toàn và sửa duy nhất mẫu câu tham chiếu “được mô tả trong ngữ cảnh”, revalidation nhận 1 câu nhiều lựa chọn đúng kiến thức/đúng dạng. Câu này vẫn thiên về Bloom Nhớ hơn Bloom Hiểu, nên chưa được tính là bằng chứng hoàn tất chất lượng. Ghép cột vẫn 0 câu được nhận.
- Schema theo từng dạng đã được nối vào luồng Ollama production qua wrapper giới hạn đồng thời và fallback; Gemini tiếp tục dùng ràng buộc JSON trong prompt vì schema Ollama không bảo đảm tương thích với API Gemini hiện tại.
- Kiểm chứng tự động hiện tại: 275 test đạt, 9 test tích hợp bị bỏ qua, 21 subtest đạt; Ruff đạt.

Chưa đánh dấu hoàn tất phần thực nghiệm: cần chạy bộ đa tài liệu đủ 210 yêu cầu mỗi cấu hình, chấm mù bởi reviewer/giảng viên và đo từ chối đúng/nhầm trên nguồn đã gán nhãn. Chưa đổi model mặc định hoặc routing.
