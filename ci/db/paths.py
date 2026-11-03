"""하네스 DB 검사가 제품 저장소를 찾는 곳(MooKKoHarness 2026-11-03).

제품 저장소 최상위는 MOOKKO_PRODUCT_ROOT(하네스 check-all이 넘김)이고, 없으면 지금 폴더다. 제품마다 다른 목록(예외·잠금·
유예·이름 CHECK 등록부·엔진 생성 고정 파일)은 제품의 docs/policy/db/에 둔다(하네스에는 두지 않음).
"""

from __future__ import annotations

import os
from pathlib import Path

DATA_REL = "docs/policy/db"


def product_root() -> Path:
    return Path(os.environ.get("MOOKKO_PRODUCT_ROOT") or ".").resolve()


def product_data(name: str) -> Path:
    return product_root() / DATA_REL / name
