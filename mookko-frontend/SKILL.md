---
name: mookko-frontend
description: MooKKo 프론트엔드 규약(TypeScript·React·Tailwind CSS, web/ pnpm 모노레포). web/ 아래 화면 코드를 쓰거나 고치거나 리뷰할 때 반드시 먼저 읽는다. Vite SPA(내부 화면), Next.js(공개 SEO 화면만), proto 생성 API 클라이언트, 토큰 기반 Tailwind.
---

# MooKKo 프론트엔드 규약 (요약)

정본은 `docs/policy/conventions/frontend.md`(규칙 번호 F-*). 이 요약과 다르면 정본이 맞다. 어기면 하네스 CI가 반영하지 않는다.

## 구조
- 화면 코드는 `web/`에만. `packages/config`(tsconfig·eslint·Tailwind 공용 설정), `packages/tokens`(디자인 토큰), `packages/ui`(업무 지식 없는 표시 부품), `packages/api`(proto 생성 클라이언트), `apps/<앱>`.
- 앱끼리 import 금지, 함께 쓸 것은 `packages/`로. 앱 안은 `routes/`·`features/<기능>/`·`lib/`(F-MOD-*).
- 내부·로그인 뒤 화면은 Vite SPA(엔진이 정적 파일 서빙, Node 서버 없음). Next.js는 `web/apps/public*`에서만.

## 꼭 지킬 것
- TypeScript strict 전부 + `noUncheckedIndexedAccess`·`exactOptionalPropertyTypes`. `any`·`!`·근거 없는 `as` 금지(F-TS-*).
- 서버 데이터는 `packages/api`(proto 생성)로만, 직접 `fetch`·손으로 쓴 응답 타입 금지. 서버 상태는 TanStack Query, `useEffect`로 데이터 가져오기 금지(F-TS-3, F-RE-2).
- 실시간은 서버 푸시로, 주기 새로고침 금지(F-RE-3).
- 재렌더 줄이기: 안정된 `key`, 큰 목록 가상화, 부품 안에 부품 정의 금지, 경로마다 lazy 나누기(F-RE-4·6).
- 스타일은 Tailwind 유틸리티 + `packages/tokens`만. 하드코딩 색·임의 값·인라인 style 최소, 다른 CSS 프레임워크·CSS-in-JS 금지(F-UI-*).
- API 주소를 코드에 두지 않는다(같은 출처 상대 경로). 토큰을 `localStorage`에 두지 않는다. `dangerouslySetInnerHTML`·`eval` 금지(F-SEC-*).
- 쿠키는 모두 `__Host-` 접두어, `Domain` 속성 금지(상위 도메인 쿠키 금지), 공개 사용자 콘텐츠 페이지는 쿠키 없음(F-SEC-5).
- 사용자 문구는 한국어, 오류는 Problem `code` 기준, 경로마다 오류 경계.
- pnpm만(`--frozen-lockfile`), npm 레지스트리만, 새 패키지는 필요·대안·라이선스를 커밋 본문에(F-DEP-*).
- 이름: 부품 `PascalCase.tsx`, 훅 `useX.ts`, 그 밖 `kebab-case.ts`(F-NAME-1).

## 규칙 끄기
`eslint-disable`·`@ts-ignore`·`@ts-expect-error`·`@ts-nocheck` 금지. 필요하면 `docs/policy/lint-exceptions.json` 등록 뒤에만.

## 끝내기 전에 (Linux)
`pnpm install --frozen-lockfile && pnpm -r exec tsc --noEmit && pnpm -r exec eslint . --max-warnings 0 && pnpm -r build && pnpm audit`, 그리고 저장소 `scripts/ci/check-all.sh`(스택·규칙 끄기 검사 포함). 결과를 보고에 적는다.
