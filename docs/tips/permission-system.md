# Claude Code 권한 시스템 가이드

> **확인 시점**: 2026-05  
> **확인 방법**: vixcode 구현 및 permissions.py 직접 작성

---

## 왜 유용한가

에이전트는 파일을 삭제하거나 셸 명령을 실행할 수 있다.
권한 시스템은 **위험한 작업 전에 사용자 확인**을 받는 안전장치다.
이를 이해하면:
- 에이전트가 왜 특정 작업에서 멈추고 확인을 요청하는지 알 수 있다
- 프로젝트별로 자동 승인 범위를 조절할 수 있다
- 실수로 파일이 삭제되거나 명령이 실행되는 사고를 방지할 수 있다

---

## allow / ask / deny 3단계 [FR-06]

| 레벨 | 동작 | 기본 적용 도구 |
|------|------|-------------|
| `allow` | 자동 실행, 사용자 확인 없음 | read_file, list_files, search_code |
| `ask` | 실행 전 사용자 승인 필요 | write_file, edit_file, run_command |
| `deny` | 항상 차단 | (사용자 지정) |

**읽기 작업 = allow**, **쓰기·실행 = ask**가 안전한 기본값이다.

---

## settings.json 설정 예시 [FR-06]

### Claude Code 설정 (`~/.claude/settings.json` 또는 `.claude/settings.json`)

```json
{
  "permissions": {
    "allow": ["Read", "Glob", "Grep", "LS"],
    "ask": ["Write", "Edit", "MultiEdit", "Bash"],
    "deny": []
  }
}
```

### vixcode 설정 (`config.json`)

```json
{
  "ollama_url": "http://localhost:11434",
  "model": "qwen2.5-coder",
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

---

## 권한 요청 흐름

```
에이전트가 write_file 호출 시도
         ↓
권한 확인: "write_file" = ask
         ↓
사용자에게 승인 요청 전송
  [도구 미리보기] write_file
  경로: src/main.py
  내용: (첫 3줄 미리보기)...
  [승인] [거부]
         ↓
사용자 응답 대기 (asyncio.Queue)
         ↓
승인 → 도구 실행 / 거부 → 중단
```

**[확인됨]** `server/agent_ws.py`의 `asyncio.Queue`로 비동기 permission flow 구현.

---

## 위험 명령 추가 차단

`ask` 레벨과 별개로, Bash 도구는 다음 패턴을 **항상 차단**한다:

```
rm -rf /          → 루트에서 재귀 삭제
:(){ :|:& };:     → fork bomb (시스템 다운)
mkfs.*            → 파일시스템 포맷
dd if=.../dev/    → 원시 디스크 쓰기
shutdown/reboot   → 시스템 전원 명령
chmod -R 777 /    → 루트 전체 권한 개방
```

이 패턴들은 `ask`를 우회해 실행 요청이 와도 차단된다.

---

## 실용 팁

**자동화 신뢰 프로젝트**: 테스트·빌드 환경이 확실하다면 `run_command`를 `allow`로 변경.

```json
"run_command": "allow"
```

**읽기 전용 리뷰**: 코드 리뷰 목적이면 모든 쓰기 도구를 `deny`로 설정.

```json
"write_file": "deny",
"edit_file":  "deny",
"run_command": "deny"
```

---

## 주의사항

- `allow`로 설정한 도구는 에이전트가 **사전 확인 없이** 실행한다
- 권한 설정 변경 후 에이전트를 재시작해야 적용된다
- [확인됨] 경로 샌드박스(`_validate_path`)와 권한 시스템은 별개로 동작
  - 경로 샌드박스: 작업 디렉토리 외부 접근 차단
  - 권한 시스템: 작업 종류(읽기/쓰기)별 승인 제어
