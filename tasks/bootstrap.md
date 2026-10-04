# Bootstrap workspace — 2026-10-04

## Scope và acceptance

Thiết lập repo local tại `D:\SE`, origin `https://github.com/harivodich/SE2026.AI-02.1.git`, nhập bộ thiết kế, stable project guidance và backlog W1. Không tạo application, tải model/data, training, push, PR hoặc deployment. Người dùng cho phép một commit local cho đúng bootstrap files sau review; không có authorization commit cho task sau.

## Evidence trước thay đổi

- `D:\SE` trống, không thuộc repository tổ tiên; không có `D:\AGENTS.md`/`D:\SE\AGENTS.md` trước bootstrap.
- Git đã cài: `2.55.0.windows.3`; không cài mới.
- Remote `git ls-remote --symref` trả exit 0 và không có refs; remote hiện rỗng.
- TLS Schannel không hoạt động trong sandbox; OpenSSL per-command đọc remote thành công, không disable certificate verification. Đặt OpenSSL chỉ trong repo config local.
- Sandbox process khác chủ sở hữu workspace; dùng `-c safe.directory=D:/SE` cho lệnh cần thiết, không đổi global trust.
- Sandbox helper có lỗi refresh; những thao tác bị ảnh hưởng dùng quyền ngoài sandbox qua approval mechanism, trong phạm vi repo được yêu cầu.

## Thay đổi

- Repo mới branch `main`, remote origin như trên.
- `docs/design/v1` giữ đủ snapshot gốc; schema/architecture/source structure/UML có bản làm việc riêng.
- README, AGENTS, scope/approval, ADR Proposed, backlog W1, .gitignore và .gitattributes.
- Không có source placeholder/dependencies/.env.example vì chưa có runtime config.

## Kiểm tra cuối lượt

- Root `D:/SE`, branch `main`, origin đúng URL; đọc remote được nhưng chưa kiểm chứng quyền push.
- 86 bootstrap files được stage theo manifest tên file cụ thể; không gom file khác. Staged diff/whitespace review pass.
- 41/41 snapshot files có SHA-256 trùng bộ gốc; architecture/source structure/schema/UML working copies cũng trùng nguồn.
- 13 JSON files parse được; bốn active schemas resolve đủ 33 `$ref` nội bộ, không fetch network.
- 20 SVG XML parse được và 20 PlantUML blocks có start/end (gồm 10 bản archive + 10 working copies); không là PlantUML compiler verification.
- 126 local Markdown/HTML links trỏ tới file tồn tại trong repo.
- Ignore checks pass cho secrets/env/caches/raw dataset/model/storage; manifest, fictional examples, schema và `.env.example` không bị ignore.
- Scan heuristic không thấy private key/GitHub PAT/AWS access-key/OpenAI-token patterns; không là proof-of-absence hoặc security audit đầy đủ.
- Không chạy full JSON Schema compiler, PlantUML compiler, app tests, inference hoặc training. Verification trong snapshot là evidence lượt thiết kế trước.

## Handoff

Người dùng đã cung cấp identity; `user.name=harivodich`, `user.email=harivodich@gmail.com` được cấu hình chỉ trong repo, không sửa config global. Bộ bootstrap được lưu trong một commit local sau final diff/secret review; kiểm kết quả bằng `git log -1` và `git status`. Không push/PR/deploy; cần yêu cầu riêng. Không có ứng dụng/model/runtime trong commit này.

## Task tiếp theo

Đọc [W1 backlog](week-01.md). Lead khóa contracts/ADR; Backend triển khai Pydantic contracts/tests trước consumer wiring; Data chuẩn bị fictional samples/manifest; AI-1 OCR/geometry fixtures; AI-2 baseline/spike protocol. Không bắt đầu toàn bộ ứng dụng trong bootstrap task.
