# Claude Code 도구 시스템 가이드

> **확인 시점**: 2026-05  
> **확인 방법**: llmai(로컬 에이전트) 구현 및 직접 실험

---

## 왜 유용한가

도구 시스템이 에이전트의 **실제 역량**을 결정한다.
어떤 도구가 있는지 알면:
- 에이전트에게 무엇을 시킬 수 있는지 파악된다
- JSON 스키마 패턴을 이해하면 커스텀 도구도 만들 수 있다
- 도구 호출 실패 원인을 진단할 수 있다

---

## 내장 도구 분류 (~40개) [FR-03]

### 파일 도구

| 도구 | 역할 | 주요 파라미터 |
|------|------|-------------|
| Read | 파일 읽기 (행 번호 포함) | path, offset, limit |
| Write | 파일 생성·덮어쓰기 | path, content |
| Edit | 정확한 문자열 치환 | path, old_string, new_string |
| MultiEdit | 다중 치환 | path, edits[] |
| Glob | 파일 패턴 검색 | pattern, path |

### 셸 도구

| 도구 | 역할 |
|------|------|
| Bash | 셸 명령 실행 (위험 명령 차단 포함) |

### 검색 도구

| 도구 | 역할 |
|------|------|
| Grep | ripgrep 기반 코드 검색 |
| WebFetch | URL에서 콘텐츠 가져오기 |
| WebSearch | 웹 검색 |

### 에이전트 도구

| 도구 | 역할 |
|------|------|
| Task/Agent | 서브에이전트 생성·위임 |
| TodoWrite | 작업 목록 관리 |

**[추측]** 상용 Claude Code의 정확한 도구 목록과 수량은 공식 미공개.  
**[확인됨]** llmai 로컬 구현에서 6개 핵심 도구 동작 검증.

---

## JSON 스키마 패턴 [FR-03]

모든 도구는 OpenAI function calling 형식의 JSON 스키마로 정의된다.

### 실제 예시: `read_file`

```json
{
  "type": "function",
  "function": {
    "name": "read_file",
    "description": "Read the contents of a file with line numbers.",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "Path to the file"
        },
        "offset": {
          "type": "integer",
          "description": "Start from this line (1-based)"
        },
        "limit": {
          "type": "integer",
          "description": "Number of lines to read"
        }
      },
      "required": ["path"]
    }
  }
}
```

### 실제 예시: `edit_file`

```json
{
  "type": "function",
  "function": {
    "name": "edit_file",
    "description": "Replace an exact unique string in a file.",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {"type": "string", "description": "File to edit"},
        "old_string": {"type": "string", "description": "Exact text to find (must be unique)"},
        "new_string": {"type": "string", "description": "Text to replace it with"}
      },
      "required": ["path", "old_string", "new_string"]
    }
  }
}
```

### 패턴 요약

```
{
  "type": "function",
  "function": {
    "name": "<스네이크_케이스_이름>",
    "description": "<LLM이 언제 이 도구를 쓸지 판단하는 설명>",
    "parameters": {
      "type": "object",
      "properties": {
        "<파라미터>": {"type": "<타입>", "description": "<설명>"}
      },
      "required": ["<필수_파라미터_목록>"]
    }
  }
}
```

**description이 LLM의 도구 선택을 결정한다.** 설명이 명확할수록 도구가 올바르게 호출된다.

---

## 위험 명령 차단 (Bash 도구)

Bash 도구는 실행 전 정규식 패턴으로 위험 명령을 차단한다.

```python
_DANGEROUS_PATTERNS = [
    r"rm\s+(-rf?|--recursive)\s+/",   # 루트에서 재귀 삭제
    r":()\{\s*:\|\s*:&\s*\};:",        # fork bomb
    r"mkfs\.",                          # 파일시스템 포맷
    r"dd\s+if=.*/dev/",                # 원시 디스크 쓰기
    r">\s*/dev/sd",                     # 장치 파일 덮어쓰기
    r"shutdown|reboot|halt|poweroff",  # 시스템 전원 명령
    r"chmod\s+-R\s+777\s+/",          # 루트 권한 전체 개방
]
```

**[확인됨]** `llmai/tools.py`에서 동일 패턴 구현 및 테스트 통과.

---

## 주의사항

- Edit 도구의 `old_string`은 파일 내에서 **유일해야** 한다. 중복 시 오류 반환.
- 도구 설명(description)이 빈약하면 LLM이 잘못된 도구를 선택한다.
- XML 폴백 모드에서는 도구 파라미터 파싱 오류가 더 자주 발생한다.
