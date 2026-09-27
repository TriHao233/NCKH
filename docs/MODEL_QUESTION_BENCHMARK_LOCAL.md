# Báo cáo benchmark sinh câu hỏi bằng mô hình cục bộ

Ngày chạy: 2026-09-08

Môi trường: Ollama 0.33.3, Intel Arc Pro 140T, Vulkan/iGPU

Tài liệu thử nghiệm: `Giao_Trinh_Lap_Trinh_Can_Ban_Chuong_1.pdf`

## Mục tiêu

So sánh Ornith 1.5 9B, Qwen 2.5 7B và DeepSeek-R1 8B khi sinh bảy dạng câu hỏi qua pipeline OCR, retrieval, sinh câu hỏi và hậu kiểm của hệ thống.

Mỗi tổ hợp model/dạng câu hỏi chỉ sinh một câu. Kết quả này phù hợp để phát hiện lỗi rõ ràng và chọn hướng tối ưu tiếp theo, nhưng chưa đủ để khẳng định chất lượng production.

## Mô hình

| Tên dùng trong Ollama | Kiến trúc/kích thước | Quantization |
|---|---|---|
| `ornith:latest` | Ornith 1.5, 9B | Q4_K_M |
| `qwen2.5:7b` | Qwen 2.5, 7.6B | Q4_K_M |
| `deepseek-r1:latest` | DeepSeek-R1, 8.2B | Q4_K_M |

## Cách đọc kết quả

- **Đạt kỹ thuật:** đầu ra qua schema và validator hiện tại, được pipeline lưu nhận.
- **Dùng ngay:** nội dung đúng, đúng dạng câu hỏi và có chất lượng sư phạm chấp nhận được mà không cần sửa.
- Một câu qua validator vẫn có thể không dùng được nếu sai kiến thức, trùng đáp án hoặc không đúng mục tiêu của dạng câu.

## Kết quả theo dạng câu hỏi

| Dạng câu hỏi | Ornith 1.5 | Qwen 2.5 7B | DeepSeek-R1 8B |
|---|---|---|---|
| Trắc nghiệm | Đạt; tốt, đáp án đúng nhưng phương án nhiễu dễ và đáp án đúng dài hơn rõ rệt — 106,04s | Không đạt; sai schema, `options=null`, tự tạo CLO và nguồn không hợp lệ — 156,81s | Không đạt; câu hỏi vòng vo, nguồn sai và có phát biểu sai rằng Java là ngôn ngữ tự nhiên — 176,57s |
| Đúng/sai | Không đạt kỹ thuật do so khớp keyword quá chặt; nội dung thực tế đúng — 121,55s | Đạt; nội dung đúng và có thể dùng — 146,46s | Không đạt; biến mệnh đề thành câu hỏi và diễn giải ngược tài liệu về tính kết thúc — khoảng 129s |
| Điền khuyết | Không đạt; lần thử lại mơ hồ và nguồn không nguyên văn — 141,41s | Đạt; đáp án đúng nhưng thân câu quá dài — 121,50s | Đạt kỹ thuật nhưng kém; câu hỏi gần như tự nêu đáp án — 151,82s |
| Ghép cột | Không đạt; sai cấu trúc, thiếu phương án nhiễu bắt buộc — 163,73s | Không đạt; sai schema/cấu trúc ghép cặp — 125,42s | Không đạt; không hiểu cấu trúc ghép cột và lần thử lại chuyển thành điền khuyết — 186,44s |
| Tình huống | Đạt kỹ thuật, nội dung đúng nhưng chỉ là câu lý thuyết, không có tình huống — 102,90s | Không đạt; trả về câu điền khuyết — 119,41s | Đạt kỹ thuật, đáp án đúng nhưng chỉ là trắc nghiệm lý thuyết — 95,29s |
| Sắp xếp | Đạt kỹ thuật nhưng không dùng được; bịa thuật toán chia Euclid không có trong nguồn — 133,14s | Không đạt; trộn thuật toán UCLN với giải phương trình — 123,41s | Không đạt; thứ tự `2,4,3,1` sai vì bước nhận đầu vào phải đứng đầu — 193,17s |
| Nhiều lựa chọn | Đạt kỹ thuật nhưng không dùng được; các lựa chọn A/C/E trùng nhau và đều được đánh dấu đúng — 180,99s | Không đạt; sai loại câu và nguồn không nguyên văn — 139,42s | Không đạt; chỉ có một đáp án đúng nên không phải multi-select — 241,93s |

## Tổng hợp chất lượng

| Model | Qua validator | Dùng ngay | Nhận xét |
|---|---:|---:|---|
| Ornith 1.5 9B | 4/7 | 1/7 | Tuân thủ cấu trúc tốt nhất, nhưng validator hiện tại vẫn để lọt lỗi ngữ nghĩa nghiêm trọng. |
| Qwen 2.5 7B | 2/7 | 1/7 | Nhanh nhất; tốt nhất ở đúng/sai, điền khuyết có thể dùng sau biên tập. |
| DeepSeek-R1 8B | 2/7 | 0/7 | Hay suy diễn, không tuân thủ đúng dạng câu và chậm nhất trong phép thử này. |

## Tốc độ suy luận trực tiếp

Phép đo cùng prompt, không bao gồm toàn bộ OCR/retrieval:

| Model | CPU tổng | GPU tổng | CPU output | GPU output | Thay đổi output |
|---|---:|---:|---:|---:|---:|
| Qwen 2.5 7B | 38,40s | 26,81s | 11,65 tok/s | 13,17 tok/s | +13,0% |
| DeepSeek-R1 8B | 45,16s | 39,10s | 10,32 tok/s | 11,41 tok/s | +10,6% |
| Ornith 1.5 9B | 44,19s | 37,03s | 9,68 tok/s | 10,55 tok/s | +9,0% |

Tốc độ xử lý prompt trên GPU tăng khoảng 3,1–3,24 lần so với CPU. Với prompt dài, Ornith giảm từ 134,1 giây xuống 58,5 giây, nhanh hơn 2,29 lần về tổng thời gian.

Thời gian từng dạng trong bảng chất lượng không hoàn toàn đồng nhất: các lượt Ornith chạy lại OCR đầy đủ, còn phần lớn lượt Qwen và DeepSeek tái sử dụng index sau lượt khởi tạo. Vì vậy, không nên dùng tổng thời gian E2E đó để xếp hạng tốc độ model; bảng suy luận trực tiếp phía trên là phép so sánh phù hợp hơn.

## Kết luận

1. Nếu buộc chọn một model mặc định, ưu tiên **Ornith 1.5** vì có tỷ lệ tuân thủ kỹ thuật cao nhất và tạo được câu trắc nghiệm tốt nhất.
2. Có thể cân nhắc route **đúng/sai** và **điền khuyết** sang Qwen sau khi bổ sung kiểm soát độ dài và chất lượng câu.
3. Chưa nên dùng DeepSeek-R1 làm model sinh câu hỏi mặc định.
4. Chưa nên bật rộng rãi ghép cột, sắp xếp, tình huống và nhiều lựa chọn trước khi sửa prompt và validator.

## Việc nên sửa tiếp

- Chuẩn hóa so khớp `source_context` và `source_keywords` để không loại câu đúng chỉ vì khác biệt nhỏ như “sẽ”, dấu câu hoặc khoảng trắng.
- Kiểm tra trùng phương án theo ngữ nghĩa sau khi chuẩn hóa chữ hoa, dấu câu và khoảng trắng.
- Với nhiều lựa chọn, bắt buộc có ít nhất hai đáp án đúng, ít nhất một đáp án sai và không có lựa chọn trùng nghĩa.
- Với sắp xếp, xác minh thứ tự từ đoạn nguồn thay vì chỉ kiểm tra schema.
- Với tình huống, yêu cầu có chủ thể, bối cảnh và quyết định/hành động cần áp dụng kiến thức.
- Bổ sung few-shot đúng schema cho ghép cột, sắp xếp và nhiều lựa chọn.
- Chạy benchmark mở rộng trên nhiều chương/tài liệu, tối thiểu 10 câu cho mỗi dạng và mỗi model, sau đó chấm mù bởi giảng viên/reviewer.

## Giới hạn

- Mỗi model chỉ được thử một câu trên mỗi dạng (`n=1`).
- Chỉ dùng một tài liệu giáo trình.
- Chưa có corpus CTDL chuẩn hoặc UAT giảng viên.
- Chưa đo authenticated load test nhiều người dùng đồng thời.
- Đây là đánh giá local/staging, không phải production acceptance.

## Cập nhật xử lý tồn đọng — 2026-09-08

Các số liệu phía trên là kết quả lịch sử, không được thay bằng kết quả sau sửa.

- Đã thống nhất đối chiếu `source_context` và gắn evidence vào chunk: dung sai Unicode, chữ hoa/thường, khoảng trắng OCR và dấu câu phân cách; evidence lưu lại vẫn là đoạn nguyên văn kèm offset của chunk thật. Không ghép nguồn từ nhiều chunk, không bỏ phủ định, số liệu hoặc toán tử.
- Keyword chấp nhận khác biệt từ “sẽ” và dấu câu. Với mệnh đề Sai, loại keyword thuộc phần `false_mutation.original` đã bị thay thế, nhưng vẫn yêu cầu ít nhất một neo không đổi và xác minh cả original/replacement.
- Hợp đồng dữ liệu chung chặn phương án trùng sau chuẩn hóa, bao gồm nhập thủ công/import và sinh AI. Ghép cột kiểm tra riêng từng cột. Giữ phân biệt toán tử, số thập phân và phủ định. Đây là kiểm tra trùng văn bản chuẩn hóa, chưa chứng minh tương đương ngữ nghĩa của mọi cách diễn đạt.
- Nhiều lựa chọn vẫn bắt buộc ít nhất hai đáp án đúng và một đáp án sai; bổ sung chặn phương án trùng và yêu cầu câu dẫn báo rõ chọn nhiều đáp án. Không suy ra tính đúng của đáp án chỉ từ số lượng khóa.
- Sắp xếp chỉ được nhận khi có ít nhất bốn bước đánh số liên tiếp trong trích dẫn, từng phương án khớp trọn một bước và đáp án theo đúng thứ tự nguồn. Từ chối nguồn không chứng minh được trình tự tuyến tính, bao gồm vòng lặp/quay lại/rẽ nhánh được nhận diện. Quy tắc này chủ động giảm số câu được nhận; quy trình diễn đạt tự do cần reviewer, không tự coi là đã xác minh.
- Tình huống có kiểm tra chủ thể, dấu hiệu bối cảnh và câu hỏi quyết định/hành động. Điền khuyết chặn thân câu quá 320 ký tự và lộ nguyên đáp án. Các kiểm tra ngôn ngữ này là heuristic, không thay chấm chất lượng sư phạm.
- Đã thử few-shot JSON và ràng buộc prompt mạnh hơn cho ghép cột, sắp xếp, nhiều lựa chọn. A/B thực tế cho kết quả xấu hơn nên phần thay đổi prompt này đã được rút khỏi working tree; không giữ tối ưu chưa có bằng chứng. Việc chặn model tự đổi dạng hoặc bịa mã CLO ngoài danh sách vẫn nằm ở hậu kiểm.
- Bổ sung `backend/scripts/benchmark_questions_local.py`: mặc định 10 mẫu cho mỗi dạng/model, hỗ trợ nhiều snapshot OCR, giữ raw response/prompt/lý do loại, xuất `blind-review.json` tách `review-key.json`, và `--replay` để kiểm tra lại phản hồi cũ với validator hiện tại. Công cụ không xóa dữ liệu và không lưu câu thử vào ngân hàng.

Kiểm chứng tự động hiện tại: **275 passed, 9 skipped, 21 subtests passed**; Ruff đạt. Các test tích hợp bị skip không được tính là đã đạt.

Đã chạy A/B thật với cả Ornith, Qwen và DeepSeek trên đủ bảy dạng, cùng snapshot OCR và cùng validator. Prompt đối chứng đạt kỹ thuật 7/21 và dùng ngay 3/21; prompt thử nghiệm đạt kỹ thuật 6/21 và dùng ngay 1/21. Thời gian trung bình giảm từ 109,64 xuống 103,52 giây/câu (-5,6%), nhưng Ornith nhanh hơn 20,5%, Qwen chậm hơn 9,3% và DeepSeek gần như không đổi. Vì chất lượng giảm, prompt thử nghiệm đã được rút lại. Báo cáo chi tiết: `artifacts/benchmarks/three-model-comparison-20260908.md`.

Chưa đóng các hạng mục cần đánh giá thực nghiệm: benchmark mở rộng đủ ba model trên nhiều chương/tài liệu, tối thiểu 10 câu mỗi tổ hợp; chấm mù bởi giảng viên; corpus CTDL chuẩn; UAT và authenticated load test. Chưa có căn cứ đổi kết luận production acceptance hay khẳng định đã giải quyết mọi lỗi ngữ nghĩa của model.

Pilot nhỏ tiếp theo trên một chunk có bốn quan hệ khái niệm–mô tả đã xác nhận JSON schema giúp Ornith trả đúng số khóa ngay lượt đầu, nhưng validator cũ vẫn nhận nhầm một câu ghép cột không có chỉ dẫn ghép và một câu nhiều lựa chọn có tập đáp án sai. Validator mới yêu cầu mô tả ghép nằm trong cùng trích dẫn, chặn nhiễu lặp mệnh đề đáp án, và yêu cầu đáp án multi-select là mệnh đề nguồn đủ nghĩa thay vì nhãn ngắn. Một sửa deterministic hẹp loại bỏ tham chiếu “được mô tả trong ngữ cảnh” đã cứu được một câu multi-select đúng kiến thức/đúng dạng khi replay; câu vẫn chưa đạt chắc mức Bloom Hiểu. Ghép cột vẫn chưa có câu dùng được, vì vậy chưa chạy benchmark 210 yêu cầu và chưa thay model/routing.
