# Nội dung gửi AI2

Gửi **hai file**: `VietDoc-AI2-handoff-20261126.zip` (task, review, source/patch và hướng dẫn) và `VietDoc-AI2-artifacts-20261126.zip` (D22 dev snapshot, native OCR và adapter checkpoint). Nếu AI2 đã có đúng các archive/hash thì không cần gửi lại gói artifacts.

Source: branch `fix/ai2-v1-training-evaluation` trên repo nhóm. Branch này xuất phát từ develop mới nhất, chưa tự merge vào develop và không bật model trong ứng dụng.

## Tin nhắn có thể gửi nguyên văn

Anh gửi em source branch `fix/ai2-v1-training-evaluation` và hai gói bàn giao để làm tiếp đến V1. Em đọc `docs/team/ai2-v1-completion-2026-11-26.md` trước, đối chiếu review và raw outputs trong packet.

Phần native OCR train48/dev16, G0/full D22 một epoch, checkpoint/reload và B0/M0/M1 dev đã chạy, không làm lại như việc chưa xong. Model hiện chưa được nhận: M0/M1 đều 0/16 qua raw serving contract; M1 còn schema/duplicate keys, nhầm bảng và tự điền thông tin ở crop/unreadable. Ưu tiên sửa các lỗi này, kiểm decoded target/mask, rồi mới chọn một hypothesis cho run tiếp. Không bỏ strict gate hoặc sửa gold để chạy qua.

Nếu branch hỗ trợ chưa merge, em tạo branch làm việc của em từ branch này, không cần đợi anh merge mới bắt đầu; sau merge đồng bộ lại develop. Không apply thêm patch nếu đã lấy branch. Chia các increment có logic và tests hoàn chỉnh, PR vào develop; không cần đợi xong toàn bộ V1 mới đẩy lượt đầu.

Trả sớm cho Data receipt IDs/hash/accounting của packet; cho AI1 ACK reader/partial-state đúng phạm vi; cho Backend interface/config/error fixtures và lệnh chạy service để các bạn làm song song. Những ACK consumer này phải kiểm thật, không đợi model đạt quality rồi mới trao. Task có checklist cụ thể.

Em sửa P1, lifecycle và tests ngay bằng D22. Quality run lớn hơn còn cần pilot đã QA của Data và OCR tương ứng của AI1; báo rõ packet/file/hash nào thiếu, không để tất cả việc dừng. Host test cũ đã dọn theo yêu cầu, không còn fine-tune chạy ngầm; môi trường/model phải khôi phục đúng pin khi cần GPU lần tiếp. Final chỉ chạy sau candidate freeze, không dùng final để tune.

## Nhắn Data/AI1/Backend cùng lúc

Xem `docs/team/cross-role-unblock-2026-11-26.md`. Data ưu tiên phát hành pilot/archive/manifest đã QA; AI1 xuất OCR pilot khi nhận Data, còn dev/stress/geometry làm ngay; Backend/Web làm B0 native, PG/security/browser và gửi suite/config E2E cho AI2. Không ai phải đợi toàn bộ model V1 mới làm phần độc lập. Phần final của Data, partial-v2 consumer acceptance và actual model E2E vẫn cần artifact/ACK thật của AI2.
