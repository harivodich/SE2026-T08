# Hồ sơ công việc AI-2

Thư mục được tạo ngày **29/10/2026** để lưu lại công việc đã làm và giải thích các
finding. Source đối chiếu ban đầu: `d608cc319e1184a6bcb097e0cffecfced91c8b42`,
nhánh `feature/AI2-M2_ai_service_docker`.

| Tài liệu | Nội dung |
|---|---|
| [HISTORY.md](HISTORY.md) | Những phần đã có, bản sửa dependency/decimal, checks lịch sử, push và phần còn thiếu |
| [Batch A: R04/R07/R08/R10](batch-a-r04-r07-r08-r10.md) | Giải thích bốn lỗi, đường đi gây lỗi, hướng sửa đề xuất và regression cases cần có |
| [Plan sửa bốn lỗi](2026-10-29-four-fixes-plan.md) | Các bước implementation, RED/GREEN và giới hạn kiểm chứng ngày 29/10 |
| [SPEC.md](SPEC.md) | Ownership, boundaries và checks của thư mục |

Đọc [kế hoạch vai trò](../ai-2-extraction.md), [workflow/gates](../workflow.md) và
[compute protocol](../../../specs/contracts/compute-api.md) để biết yêu cầu gốc.
Hồ sơ này không thay thế các tài liệu đó và không xác nhận một task đã được Lead nhận.

Khi bổ sung ghi chép, ghi ngày, source SHA, phạm vi thay đổi, command/kết quả thực,
phần chưa kiểm và consumer liên quan. Chỉ ghi đã sửa khi có code cùng regression
evidence; một giải thích hoặc đề xuất không phải implementation. Không chép token,
absolute private paths hoặc output chứng từ thật vào hồ sơ.

Trạng thái ngày 29/10/2026: dependency/decimal đã có trong commit `d608cc3`.
R04/R07/R08/R10 đã được sửa và có regression evidence trong HISTORY. Mốc commit/push
tra theo Git và hồ sơ bàn giao, không coi một lần sửa local là peer/Lead acceptance.
R05/R09/R14/R17 vẫn còn ngoài phạm vi lượt sửa này, chưa đóng toàn Batch A.
Model/OCR thực và G0/G1 chưa được nghiệm thu bởi hồ sơ này.
