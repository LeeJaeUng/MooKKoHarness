# 프론트엔드 규약 (TypeScript · React · Tailwind CSS)

대상: `web/` 모든 화면 코드. 스택 결정(2026-10-29): React + TypeScript + Tailwind CSS, pnpm 모노레포, 내부·로그인 뒤 화면은 Vite SPA(Rust 엔진이 정적 파일 서빙), SEO가 필요한 공개 화면만 Next.js(`web/apps/public*`). 목표 순서: 안정성 → 속도 → 모듈화 → 재사용(`README.md`).

## 1. 구조 (모듈화·재사용)

```
web/
  pnpm-workspace.yaml  pnpm-lock.yaml  package.json
  packages/
    config/   tsconfig·eslint·Tailwind 공용 설정 (모든 앱이 이것만 확장)
    tokens/   디자인 토큰(색·글꼴·간격·반경) → Tailwind 프리셋, CSS 변수
    ui/       공용 React 부품(표·차트·상태 배지·폼·레이아웃). 업무 지식 없음
    api/      proto/에서 생성한 Connect-ES 클라이언트(생성물만)
  apps/
    monitoring/  operations/  developers/  account/   (Vite SPA)
    public/                                            (Next.js, 그 단계에서)
```

- F-MOD-1 앱끼리 서로 import하지 않는다. 함께 쓰는 것은 `packages/`로 올린다. **[lint]** eslint `import/no-restricted-paths` **[검사]** `check-stack.py`
- F-MOD-2 `packages/ui`는 업무 지식이 없는 표시 부품만(데이터는 props로). 업무 로직은 앱의 `features/<기능>/`에. **[QA]**
- F-MOD-3 앱 안 구조: `routes/`(화면), `features/<기능>/`(그 기능의 부품·훅·상태), `lib/`(앱 공용). 파일 하나 300줄, 부품 하나 150줄 넘으면 나눈다. **[lint]** `max-lines` **[QA]**
- F-MOD-4 같은 부품·훅을 두 번 만들지 않는다. 두 번째로 필요해지면 `packages/ui`나 앱 `lib/`로 옮긴다. **[QA]**

## 2. 타입 안전 (안정성)

- F-TS-1 `tsconfig` strict 전부 + `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `noImplicitOverride`, `noFallthroughCasesInSwitch`, `verbatimModuleSyntax`. **[lint]** tsc
- F-TS-2 `any` 금지(`unknown` 후 좁히기), 단언(`as`)은 생성된 타입 경계에서만, 단언 `!` 금지. **[lint]** `@typescript-eslint/no-explicit-any`, `no-unsafe-*`, `no-non-null-assertion`, `consistent-type-assertions`
- F-TS-3 서버 데이터의 타입은 `packages/api`(proto 생성)에서만 온다. 손으로 쓴 응답 타입·`fetch` 요청 형식 금지. **[lint]** `no-restricted-globals: fetch`(api 패키지 밖) **[QA]**
- F-TS-4 `switch`는 모든 경우를 다룬다(빠지면 컴파일 실패). **[lint]** `switch-exhaustiveness-check`
- F-TS-5 처리되지 않은 Promise 금지. **[lint]** `no-floating-promises`, `no-misused-promises`

## 3. React (안정성·속도)

- F-RE-1 함수 부품과 훅만. 훅 규칙 지킴. **[lint]** `react-hooks/rules-of-hooks`, `exhaustive-deps`
- F-RE-2 서버 상태는 TanStack Query로만(캐시·재시도·취소). `useEffect`로 데이터 가져오기 금지. 화면 상태는 가까운 곳에 두고 전역 상태는 최소로. **[QA]**
- F-RE-3 실시간 갱신은 서버 푸시(gRPC-web 스트림·SSE)로, 주기 새로고침 금지. 받은 알림으로 해당 Query만 무효화. **[QA]**
- F-RE-4 재렌더 줄이기: 목록은 안정된 `key`, 큰 목록·표는 가상화, 비싼 계산은 잰 뒤 `useMemo`. 부품 안에서 부품 정의 금지. **[lint]** `react/no-unstable-nested-components`, `react/jsx-key` **[QA]**
- F-RE-5 오류 경계(Error Boundary)를 경로마다 두고, 오류는 Problem(`code`) 기준으로 보여 준다. 사용자 문구는 한국어. **[QA]**
- F-RE-6 경로(화면)마다 코드 나누기(lazy). 처음 받는 묶음 크기 상한을 둔다. **[벤치]** 빌드 크기 검사

## 4. 스타일 (Tailwind)

- F-UI-1 스타일은 Tailwind 유틸리티와 `packages/tokens` 토큰만. 하드코딩 색(`#123456`)·임의 값(`w-[37px]`)은 토큰이 없을 때만, 이유를 주석. 인라인 `style` 금지(계산된 크기 제외). **[lint]** eslint tailwind 규칙 **[QA]**
- F-UI-2 다른 CSS 프레임워크·CSS-in-JS 금지. **[검사]** `check-stack.py`
- F-UI-3 접근성: 의미 있는 태그, 키보드 조작, `alt`·`aria-*`, 대비. **[lint]** `jsx-a11y` 권장 규칙 **[QA]**

## 5. 보안·주소

- F-SEC-1 비밀값·토큰을 화면 코드·빌드 결과에 넣지 않는다. **[검사]** 비밀값 검사(Semgrep)
- F-SEC-2 API 주소를 코드에 두지 않는다: 같은 출처(same-origin) 상대 경로를 쓰거나 서버가 준 설정을 읽는다. **[lint]** `no-restricted-syntax`(URL 리터럴) **[QA]**
- F-SEC-3 `dangerouslySetInnerHTML`·`eval`·`new Function` 금지. **[lint]**
- F-SEC-4 쿠키 세션 + CSRF 토큰(엔진 BFF 규칙), 토큰을 `localStorage`에 두지 않는다. **[QA]**
- F-SEC-5 MooKKo의 모든 쿠키는 `__Host-` 접두어(Secure, Path=/, `Domain` 속성 없음). `Domain=mookko.com` 같은 상위 도메인 쿠키는 금지 — 같은 사이트의 사용자 콘텐츠 도메인(`links.mookko.com`)이 메인 쿠키를 읽거나 덮어쓰지 못하게(쿠키 던지기 방지). 공개 사용자 콘텐츠 페이지는 쿠키를 두지 않는다. **[QA]** (근거 `docs/spec/links/security.md` §2)

## 6. 의존성·도구

- F-DEP-1 pnpm만, `pnpm install --frozen-lockfile`, `pnpm audit`, 라이선스 허용 목록, npm 공식 레지스트리만(git·URL 의존성 금지). 새 패키지는 필요·대안·라이선스를 커밋 본문에. **[deny]** **[검사]** `check-stack.py`
- F-DEP-2 금지: 다른 화면 프레임워크(Vue·Svelte·Angular·jQuery·Solid·Preact·Lit), 다른 CSS 프레임워크(Bootstrap·Bulma·MUI·Chakra·antd), CSS-in-JS(styled-components·emotion), 공개 앱 밖 Next.js. **[검사]** `check-stack.py`
- F-DEP-3 서식은 Prettier(+ Tailwind 클래스 정렬 플러그인), 검사는 `tsc --noEmit`·`eslint --max-warnings 0`·`vite build`. **[lint]**

## 7. 이름

- F-NAME-1 부품 `PascalCase.tsx`, 훅 `useCamelCase.ts`, 그 밖 파일 `kebab-case.ts`, 상수 `SCREAMING_SNAKE_CASE`. 폴더는 `kebab-case`. **[lint]** `filenames`/`naming-convention`

## 8. 시험

- F-TEST-1 부품·훅은 Vitest + Testing Library(사용자 동작 기준), 화면 흐름은 Playwright. 서버는 생성된 클라이언트를 가짜로 바꿔 시험한다. **[QA]**

## 9. 규칙 끄기

- `eslint-disable`·`@ts-ignore`·`@ts-expect-error`·`@ts-nocheck` 금지. 필요하면 `docs/policy/lint-exceptions.json` 등록 뒤에만. **[검사]** `check-lint-escapes.py`

eslint·tsconfig·Tailwind 설정의 정본은 `web/packages/config`에 두고(화면 담당이 `web/`를 만들 때 이 규약대로), 모든 앱은 그것만 확장한다. 설정이 이 규약보다 약하면 QA `fail`.
