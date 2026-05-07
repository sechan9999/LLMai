# AI 코딩 에이전트 오픈소스 비교 가이드

> **확인 시점**: 2026-05  
> **확인 방법**: 직접 사용(Claude Code, Vixcode), 공식 문서 기반(Aider, Open Interpreter, Goose)

---

## 왜 유용한가

AI 코딩 에이전트는 종류가 많다. 도구마다 지향점이 다르고 비용·모델·환경 지원도 다르다.
이 가이드는 대표적인 5개 도구를 한눈에 비교하여 **내 상황에 맞는 도구를 30초 안에 고를 수 있게** 돕는다.

---

## 도구 한눈에 비교 [FR-08-01]

| 도구 | 비용 | 기본 모델 | 로컬 LLM | 인터페이스 | 도구 호출 | 특화 기능 | 라이선스 |
|------|------|---------|:--------:|-----------|:--------:|---------|---------|
| **Claude Code** | 유료(구독) | Claude 4.x | 불가 | CLI + IDE | ~40개 | 최고 코드 품질, MCP | 상용 |
| **Aider** | 무료(API 비용) | GPT-4o / Claude | 가능 | CLI | 제한적 | Git 통합, 자동 커밋 | Apache 2.0 |
| **Open Interpreter** | 무료(API 비용) | GPT-4 / 로컬 | 가능 | CLI + Web | 시스템 실행 | 자연어로 코드 실행 | AGPL |
| **Goose** | 무료(API 비용) | Claude / GPT | 가능 | CLI | MCP 기반 | MCP 생태계, 확장 도구 | Apache 2.0 |
| **Vixcode (LLMai)** | 무료(완전 로컬) | Ollama 모델 | 필수 | CLI + Web | 6개 | 최소 구현, 학습용 | MIT |

**[확인됨]** Claude Code, Vixcode는 직접 사용·제작 검증.  
**[추측]** Aider, Open Interpreter, Goose의 세부 기능은 공식 문서(2026-05 기준) 기반이며 업데이트로 변경 가능.

---

## 상황별 선택 가이드 [FR-08-02]

### 시나리오 1: 업무 생산성 — 최고 품질이 필요하다
**추천: Claude Code**

Claude 최신 모델 + 공식 지원 + 최고 수준의 코드 이해력.
비용이 발생하지만 시간 대비 ROI가 가장 높다.
IDE(VS Code, JetBrains) 연동, MCP 서버 확장 모두 지원.

```bash
# 설치
npm install -g @anthropic-ai/claude-code
claude
```

---

### 시나리오 2: API 비용 없이 로컬에서 — 개인정보가 중요하다
**추천: Vixcode 또는 Aider + Ollama**

코드가 외부로 나가지 않고, 토큰 비용도 없다.
Vixcode는 Web UI 제공으로 접근이 쉽고, Aider는 Git 통합이 강력하다.

```bash
# Vixcode
git clone https://github.com/sechan9999/LLMai
pip install -e .
python run_server.py   # 브라우저 자동 오픈

# Aider + Ollama
pip install aider-chat
aider --model ollama/qwen2.5-coder
```

---

### 시나리오 3: Git 워크플로 자동화 — 커밋·브랜치 관리가 핵심이다
**추천: Aider**

변경 사항을 자동으로 Git commit하고, 파일별 diff를 관리한다.
"이 파일의 버그를 고쳐줘"라고 하면 수정 후 바로 커밋까지 처리.
여러 파일을 동시에 편집하는 대규모 리팩토링에 강하다.

```bash
pip install aider-chat
aider --model gpt-4o src/main.py src/utils.py
```

---

### 시나리오 4: MCP 생태계 활용 — 외부 도구와 연동하고 싶다
**추천: Goose (또는 Claude Code)**

MCP(Model Context Protocol) 서버를 통해 브라우저, 데이터베이스, API 등
외부 도구와 에이전트를 연결할 수 있다.
Block이 개발해 MCP 생태계와 긴밀하게 통합된다.

---

### 시나리오 5: 에이전트 아키텍처 학습 — 직접 뜯어보고 싶다
**추천: Vixcode**

vixcode 전체 코드는 6개 파일, ~800줄이다.
`vixcode/agent.py`를 보면 while 루프가 그대로 보인다.
`vixcode/tools.py`를 수정하면 도구를 바로 추가할 수 있다.
에이전트가 어떻게 동작하는지 이해하는 데 가장 적합한 최소 구현체.

---

## 도구별 장단점 [FR-08-04]

### Claude Code
**장점**
- 현존 최고 수준의 코드 이해·생성 품질
- MCP, IDE 플러그인, 훅 시스템 등 풍부한 생태계
- Anthropic 공식 지원 및 지속적 업데이트

**단점**
- 유료 구독 필요 (API 비용 별도)
- 로컬 LLM 교체 불가 — 인터넷 연결 필수
- 오프라인 환경에서 사용 불가

**적합한 사용자**: 코드 품질과 생산성이 최우선인 전문 개발자

---

### Aider
**장점**
- Git 통합이 매우 강력 — 수정 후 자동 커밋
- 다양한 모델 지원 (GPT, Claude, Gemini, Ollama)
- 멀티 파일 편집에 강함

**단점**
- CLI 전용 — 웹 UI 없음
- 대형 코드베이스에서 컨텍스트 관리가 까다로움
- 처음 설정 시 learning curve 존재

**적합한 사용자**: Git 중심 워크플로, 리팩토링 작업이 많은 개발자

---

### Open Interpreter
**장점**
- 자연어로 파일 정리, 데이터 분석, 시스템 작업 등 범용 자동화
- 로컬 및 원격 모델 모두 지원
- 코딩 외 일반 자동화 작업에도 활용 가능

**단점**
- AGPL 라이선스 — 상업적 사용 시 조건 확인 필요
- 코딩 특화 도구들에 비해 코드 작업 전문성이 낮음
- 보안 설정 주의 필요 (시스템 명령 실행 가능)

**적합한 사용자**: 코딩 외 자동화, 데이터 분석, 파일 관리 목적

---

### Goose
**장점**
- MCP 서버 생태계와 긴밀한 통합
- 확장 가능한 도구 시스템
- Apache 2.0 — 상업적 사용 자유

**단점**
- 커뮤니티 규모가 상대적으로 작음
- **[추측]** 문서화가 아직 발전 중

**적합한 사용자**: MCP 생태계를 활용하고 싶은 개발자, Block 스택 사용자

---

### Vixcode (LLMai)
**장점**
- 완전 로컬, API 비용 없음, 오프라인 동작
- MIT 라이선스 — 완전 자유
- 코드가 단순해서 직접 수정·확장 용이
- Web UI + CLI 동시 지원

**단점**
- 로컬 LLM 품질 한계 — 상용 모델 수준 기대 불가
- 도구 수 6개 (Claude Code ~40개 대비 제한적)
- 알파 수준 — 프로덕션 사용 비권장

**적합한 사용자**: 에이전트 학습, 로컬 실험, 개인 프로젝트

---

## Vixcode의 위치 [FR-08-03]

Vixcode는 성능 경쟁을 하지 않는다.

```
Claude Code: 최고 품질의 상용 에이전트
Aider:       Git 특화 오픈소스 에이전트
Vixcode:     에이전트 아키텍처를 배우기 위한 최소 구현체
```

**[확인됨]** 전체 에이전트 루프가 `vixcode/agent.py` 약 80줄 안에 담겨 있다.
이 코드를 읽으면 while 루프, 도구 호출, 컨텍스트 압축이 어떻게 작동하는지
**직접 눈으로 확인**할 수 있다.

"Claude Code가 어떻게 동작하는지 이해하고 싶다"는 목적이라면
Vixcode 코드를 읽고 수정해보는 것이 가장 빠른 학습 경로다.

---

## 주의사항

- 도구별 기능은 업데이트로 빠르게 변화한다. 최신 정보는 각 공식 문서 확인.
- **[확인됨]**: Claude Code, Vixcode — 직접 사용·제작 검증
- **[추측]**: Aider, Open Interpreter, Goose — 공식 문서 기반, 직접 심층 테스트 미완료
- 로컬 LLM 품질은 모델 선택에 크게 의존한다. `docs/tips/local-llm-setup.md` 참조.
