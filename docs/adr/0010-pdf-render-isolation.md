# ADR 0010 — Giới hạn render PDF ở upload

Status: Accepted — lựa chọn của Lead ngày 24/10/2026 khi xử lý R14.

## Quyết định

PDF một trang được render trong child JVM trước DB transaction. Child có heap tối đa 384 MiB, direct memory tối đa 64 MiB, timeout 15 giây và tối đa hai process đồng thời. Parent chỉ nhận PNG sau khi child kết thúc thành công, kiểm kích thước file và metadata pixel, rồi chuyển file vào private storage. Timeout, lỗi decode và PDF vượt profile trả lỗi có mã rõ ràng.

## Giới hạn

Giới hạn heap/JVM và số process không thay thế OS sandbox hoặc quota bộ nhớ toàn process. Cần đo trên PDF nặng và môi trường triển khai; không dùng kết quả test sample để suy ra đã chịu mọi PDF độc hại. Upload vẫn có orphan file khi process chết giữa ghi file và commit; `StorageReconciler` dọn sau một ngày.
