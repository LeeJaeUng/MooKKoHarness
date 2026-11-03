# ci

- 여기 두는 것: `check-all.sh`(제품 `scripts/ci/check-all.sh`가 `harness.lock` 판으로 부름)와 검사 본체(`check-*.py`·`.sh`), DB 검사(`db/`), 검사 표본(`fixtures/<검사>/good`·`bad`)과 표본 시험(`test_ci_checks.py`)
- 두지 않는 것: 개발 도구(`dev/`), 설정(`config/dev/`), 제품마다 다른 목록(제품 `docs/policy/`)
- 검사는 제품 저장소를 `MOOKKO_PRODUCT_ROOT`(또는 첫 인자)로 받고, 하네스 파일은 이 폴더 기준 경로로 찾습니다. 기계 전용 경로를 쓰지 않습니다.
