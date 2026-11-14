# SPEC - VT-029 execution evidence

Logs/results synthetic từ bài cá nhân MSSV23001863, 14/11/2026. Backend/test owner;
không thay Issue/PR approval authority hoặc source runnable. Không chứa raw datasets,
model/runtime storage hay credentials thật. Test passwords trong source là fictional.

RED/initial RED giữ nguyên lịch sử; green/coverage/regression/schema/mutation/load là
các lần chạy khác nhau, không cộng counts thành một suite. Xem ../VT-029-README.md
về lệnh, baseline và giới hạn. source-manifest.json giữ hashes source đã dùng tạo
báo cáo, không thay commit/PR. Mutation ban đầu trong temp copy; sau khi có quyền Git,
đã lặp lại trên nhánh local riêng. git-history.json, mutation-branch.txt và mutation.patch
ghi commit/evidence; restored-tc12.txt kiểm code đúng sau khi quay về nhánh nộp.
