# 로컬 LLM으로 AI 코딩 에이전트 실행하기

> **확인 시점**: 2026-05  
> **확인 방법**: qwen2.5-coder, gemma3:4b로 직접 실험

---

## 왜 유용한가

- **API 비용 없음**: 토큰 요금 없이 무제한 사용
- **인터넷 불필요**: 완전 오프라인 환경에서도 동작
- **프라이버시**: 코드가 외부 서버로 전송되지 않음
- **학습 목적**: 에이전트 아키텍처를 직접 뜯어볼 수 있음

---

## 단계별 설정 [FR-07]

### 1단계: Ollama 설치

```bash
# Linux / macOS
curl -fsSL https://ollama.com/install.sh | sh

# Windows
winget install Ollama.Ollama
```

설치 후 Ollama 서버를 실행한다:

```bash
ollama serve
# 기본 포트: http://localhost:11434
```

### 2단계: 모델 선택 기준

**핵심 조건: Function Calling(도구 호출) API 지원 여부**

에이전트는 LLM에게 "이 도구를 실행해라"고 JSON으로 지시한다.
이를 지원하지 않는 모델은 XML 폴백 모드로만 동작해 품질이 낮아진다.

| 모델 | Tool Use | 권장 용도 |
|------|:--------:|---------|
| `qwen2.5-coder:7b` | 네이티브 | 코딩 특화, 안정적 |
| `qwen2.5-coder:14b` | 네이티브 | 고성능 (RAM 12GB 이상) |
| `qwen3:8b` | 네이티브 | 범용, 최신 |
| `llama3.1:8b` | 네이티브 | Meta 범용 |
| `llama3.2:3b` | 네이티브 | 경량 (RAM 4GB) |
| `gemma3:4b` | XML 폴백 | 성능 제한적 |
| `phi3:mini` | XML 폴백 | 성능 제한적 |

**권장 시작 모델**: `qwen2.5-coder:7b` (8GB RAM에서 동작, 코딩 품질 우수)

### 3단계: 모델 다운로드

```bash
ollama pull qwen2.5-coder:7b

# 설치 확인
ollama list
```

### 4단계: API 동작 확인

```bash
curl http://localhost:11434/v1/models
# {"object":"list","data":[{"id":"qwen2.5-coder:7b",...}]}
```

### 5단계: llmai 연결

`config.json` 설정:

```json
{
  "ollama_url": "http://localhost:11434",
  "model": "qwen2.5-coder:7b",
  "permissions": {
    "read_file":   "allow",
    "list_files":  "allow",
    "search_code": "allow",
    "write_file":  "ask",
    "edit_file":   "ask",
    "run_command": "ask"
  }
}
```

서버 실행:

```bash
python run_server.py
# 브라우저가 자동으로 http://localhost:7777 열림
```

---

## Docker로 실행 (선택사항)

호스트 Ollama와 Docker 컨테이너를 연결할 때:

```yaml
# docker-compose.yml
services:
  llmai:
    build: .
    ports:
      - "7777:7777"
    environment:
      - OLLAMA_URL=http://host.docker.internal:11434
      - LLMAI_MODEL=qwen2.5-coder:7b
    extra_hosts:
      - "host.docker.internal:host-gateway"  # Linux 필수
```

```bash
docker-compose up -d
```

**[확인됨]** `host.docker.internal`로 컨테이너에서 호스트 Ollama 접근 검증.

---

## 문제 해결

| 증상 | 원인 | 해결 |
|------|------|------|
| 400 Bad Request | 모델이 tool use API 미지원 | XML 폴백 모드 자동 전환 (llmai) |
| 응답이 너무 느림 | 모델이 RAM 초과 | 더 작은 모델 선택 (3b/4b) |
| 도구 호출 오류 | XML 폴백 파싱 실패 | 네이티브 지원 모델로 교체 |
| 연결 거부 | Ollama 서버 미실행 | `ollama serve` 실행 |

---

## 주의사항

- **[확인됨]** gemma3:4b는 `/v1/chat/completions` tool 파라미터로 400 오류 반환
  → llmai에서 XML 폴백(`<tool_call>{...}</tool_call>`)으로 자동 처리
- **[확인됨]** qwen2.5-coder는 네이티브 function calling 안정 동작
- **[추측]** 모델별 tool use 지원 여부는 버전 업데이트로 변경될 수 있음
- 상용 Claude Code 수준의 정확도를 기대하기는 어렵다. 학습 및 로컬 실험 목적에 적합.
