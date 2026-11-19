# SPEC — VietDoc root

Điểm vào repo; Lead architecture/review, Backend bootstrap. Java/Spring Boot/Thymeleaf ở [backend](backend/SPEC.md), Python AI/Data ở [src](src/SPEC.md); mở SPEC ngay working folder.

- [requirements/contracts](specs/SPEC.md), [docs/ADR/UML/team](docs/SPEC.md)
- [tests](tests/SPEC.md), [infra](infra/SPEC.md), [Git/PR](.github/SPEC.md)
- [datasets](datasets/SPEC.md), [model/eval artifacts](artifacts/SPEC.md), [private runtime](storage/SPEC.md)
- [web legacy](web/SPEC.md), [migrations legacy](migrations/SPEC.md)
- [build/test scripts](scripts/SPEC.md), [CI/CD runbook](docs/cicd.md)

[Scope](specs/scope.md), [source structure](docs/source-structure.md), [architecture](docs/architecture.md) và [task theo vai trò](docs/team/README.md). Không folder tasks hoặc implementation TODO để lấp cây. Java manual/demo, Python compute boundary/baseline, Data generator/evaluator và AI-1 OCR/page/geometry/evidence đã có source; actual-provider integration và model quality cần evidence riêng, docs không là bằng chứng app chạy.

No secrets/raw dataset/weights/runtime in Git. Snapshot docs/design/v1 bất biến. [Git Flow](docs/git-flow.md): feature → develop; commit/push cần yêu cầu riêng.
