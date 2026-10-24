# Folder SPEC navigation

Mỗi working folder có SPEC ngay tại đó, không cần tra một bảng chung dài.

- [Java Backend/UI](../backend/SPEC.md), [Python AI/Data](../src/vietdoc/SPEC.md)
- [Tests](../tests/SPEC.md), [infra](../infra/SPEC.md)
- [Data](../datasets/SPEC.md), [artifacts](../artifacts/SPEC.md), [runtime](../storage/SPEC.md)
- [Requirements](SPEC.md), [docs](../docs/SPEC.md), [Git/PR](../.github/SPEC.md)
- [React legacy](../web/SPEC.md), [Alembic legacy](../migrations/SPEC.md), không implementation mới

[Root](../SPEC.md) chỉ index. Snapshot v1/git internals/cache/local verification không cần SPEC con; snapshot bất biến. Raw/model/runtime chỉ track đúng SPEC.md/.gitkeep, các assets khác ignored. Java code mới tạo folder nào thì thêm SPEC local ở folder đó, không tạo hàng loạt classes rỗng.
