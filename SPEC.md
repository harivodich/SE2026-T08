# SPEC — VietDoc root

Điểm vào repo; Lead architecture/review, Backend bootstrap. Java/Spring Boot/Thymeleaf ở [backend](backend/SPEC.md), Python AI/Data ở [src](src/SPEC.md); mở SPEC ngay working folder.

- [requirements/contracts](specs/SPEC.md), [docs/ADR/UML/team](docs/SPEC.md)
- [tests](tests/SPEC.md), [infra](infra/SPEC.md), [Git/PR](.github/SPEC.md)
- [datasets](datasets/SPEC.md), [model/eval artifacts](artifacts/SPEC.md), [private runtime](storage/SPEC.md)
- [web legacy](web/SPEC.md), [migrations legacy](migrations/SPEC.md)

[Scope](specs/scope.md), [source structure](docs/source-structure.md), [architecture](docs/architecture.md) và [task theo vai trò](docs/team/README.md). Không folder tasks, không implementation TODO để lấp cây. Python có OCR/page types, loader, OCR pretrained và tests theo [proposal AI-1](docs/ocr-input-proposal.md); package init còn scaffold, Java chưa app; docs không app proof.

No secrets/raw dataset/weights/runtime in Git. Snapshot docs/design/v1 bất biến. [Git Flow](docs/git-flow.md): bootstrap main theo Lead yêu cầu riêng; team feature→develop khi coding bắt đầu. Commit/push cần yêu cầu riêng.
