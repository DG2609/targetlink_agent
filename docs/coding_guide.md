# Coding Guide: Quy tắc Viết Code cho TargetLink Rule Checking

Tài liệu này quy định **cách tổ chức code**, **tách file rõ ràng**, và **coding patterns** cho dự án. Tham khảo từ agentic coder (`D:\targetlink\agentic\`) và chuẩn hóa lại cho **Agno framework**.

> **Nguyên tắc vàng**: KHÔNG BAO GIỜ đổ hết khai báo Tool + Class + Logic vào 1 file. Mỗi file chỉ làm MỘT việc.

---

## 1. Cấu trúc Thư mục Bắt Buộc

```
targetlink/
├── main.py                          # Entry point DUY NHẤT — CLI args + pipeline
├── config.py                        # Cấu hình: LLM provider, paths, pipeline settings
├── requirements.txt                 # Dependencies
├── .env                             # Secrets & config (KHÔNG commit)
│
├── schemas/                         # Pydantic models — DATA CONTRACT giữa agents
│   ├── __init__.py
│   ├── rule_schemas.py              # RuleInput, RuleCondition, ParsedRule
│   ├── block_schemas.py             # BlockMappingData
│   ├── validation_schemas.py        # TestCase, ValidationStatus, ValidationResult
│   ├── report_schemas.py            # RuleReport, FinalReport
│   ├── diff_schemas.py              # ConfigChange, BlockChange, ModelDiff, ConfigDiscovery
│   └── agent_inputs.py              # Agent2Input, Agent5Input
│
├── tools/                           # Tool functions — KHẢ NĂNG của agents
│   ├── __init__.py
│   ├── xml_tools.py                 # XmlToolkit: hierarchy, blocks, config, XPath...
│   ├── search_tools.py              # SearchToolkit: fuzzy_search_json, read_dictionary
│   └── code_tools.py                # CodeToolkit: write/read/patch/rewrite code
│
├── agents/                          # Agent definitions — CHỈ khai báo, KHÔNG logic
│   ├── __init__.py
│   ├── agent0_rule_analyzer.py
│   ├── agent1_data_reader.py
│   ├── agent1_5_diff_analyzer.py    # Diff-based config discovery
│   ├── agent2_code_generator.py
│   ├── agent3_validator.py
│   ├── agent4_bug_fixer.py
│   └── agent5_inspector.py
│
├── skills/                          # Agent Skills — SKILL.md theo Anthropic format
│   ├── rule-analyzer/SKILL.md
│   ├── data-reader/SKILL.md
│   ├── diff-analyzer/SKILL.md       # Agent 1.5 instructions
│   ├── code-generator/SKILL.md
│   ├── validator/SKILL.md
│   ├── bug-fixer/SKILL.md
│   └── model-inspector/SKILL.md
│
├── pipeline/                        # Orchestration logic — ĐIỀU PHỐI agents
│   ├── __init__.py
│   ├── runner.py                    # Pipeline chính: run_pipeline()
│   ├── router.py                    # Routing: Agent 3 → Agent 4 hay 5?
│   ├── retry.py                     # Retry logic + escalation
│   ├── state_machine.py             # RetryStateMachine + loop detection
│   └── exploration_cache.py         # Knowledge handoff + cross-rule cache
│
├── utils/                           # Helper functions — DÙNG CHUNG
│   ├── __init__.py
│   ├── model_factory.py             # LLM factory: Gemini hoặc Ollama
│   ├── slx_extractor.py             # Unzip .slx → XML tree
│   ├── skill_loader.py              # Load SKILL.md → list[str]
│   ├── model_differ.py              # Pure Python XML diff (2 models)
│   ├── model_index.py               # Index model structure
│   ├── defaults_parser.py           # Parse bddefaults.xml
│   ├── block_discoverer.py          # Discover blocks in model
│   ├── input_validator.py           # Validate input files
│   ├── output_truncator.py          # Truncate large outputs
│   ├── loop_detector.py             # Detect agentic doom loops
│   └── logger.py                    # Logging config
│
├── tests/                           # Unit + integration tests
├── data/                            # Dữ liệu đầu vào
├── generated_checks/                # Auto-generated bởi agents
├── reports/                         # Auto-generated bởi agents
└── docs/                            # Tài liệu
```

---

## 2. Nguyên tắc Tách File

### SAI — Đổ hết vào 1 file

```python
# ĐỪNG LÀM THẾ NÀY trong agent2_code_generator.py
from agno.agent import Agent
from agno.models.google import Gemini    # SAI — import trực tiếp provider
from agno.tools import Toolkit
from pydantic import BaseModel

class GeneratedCode(BaseModel):          # Schema NGAY TRONG file agent — SAI
    ...

class XmlTools(Toolkit):                 # Tool NGAY TRONG file agent — SAI
    ...

def run_agent2(...):                     # Pipeline logic NGAY TRONG file agent — SAI
    agent = Agent(
        model=Gemini(id="...", vertexai=True, project_id="...", location="..."),
        ...
    )
```

### ĐÚNG — Mỗi file 1 trách nhiệm

**File `agents/agent2_code_generator.py`** — Chỉ khai báo agent:
```python
from agno.agent import Agent
from tools.xml_tools import XmlToolkit
from tools.code_tools import CodeToolkit
from utils.skill_loader import load_skill
from utils.model_factory import create_model      # Factory — không import Gemini/Ollama

def create_agent2(model_dir: str) -> Agent:
    return Agent(
        name="Code Generator",
        role="Senior Python Developer viết rule checking scripts",
        model=create_model(),                      # Gemini hoặc Ollama tuỳ config
        tools=[
            XmlToolkit(model_dir=model_dir),
            CodeToolkit(output_dir=str(settings.GENERATED_CHECKS_DIR)),
        ],
        instructions=load_skill("code-generator"),
        markdown=True,
        debug_mode=True,
        tool_call_limit=15,
    )
```

---

## 3. Cách Viết Tools cho Agno

### 3.1 "Agent Skill" trong Agno nghĩa là gì?

Trong Agno, "Skill" = **Tool** = khả năng Agent thực hiện hành động cụ thể. Agno cung cấp 2 cách tạo Tool:

**Cách 1: Toolkit class** (dùng khi tools cần shared state)
```python
from agno.tools import Toolkit

class XmlToolkit(Toolkit):
    def __init__(self, model_dir: str):
        super().__init__(name="xml_tools")
        self.model_dir = model_dir
        self.register(self.list_xml_files)
        self.register(self.read_xml_structure)

    def list_xml_files(self) -> str:
        """Liệt kê tất cả file XML trong model tree. GỌI ĐẦU TIÊN."""
        ...
```

**Cách 2: Function tool** (dùng khi tool đơn giản)
```python
from agno.tools import tool

@tool
def fuzzy_search_json(keyword: str, json_path: str) -> str:
    """Tìm block trong file JSON bằng fuzzy matching."""
    ...
```

### 3.2 Quy tắc viết Tool

| Quy tắc | Lý do |
|---------|-------|
| Docstring BẮT BUỘC | LLM dùng docstring để hiểu tool |
| Trả về `str` | Agno truyền kết quả tool cho LLM dưới dạng text |
| KHÔNG gọi agent khác trong tool | Routing là việc của `pipeline/` |
| KHÔNG đọc config trực tiếp | Truyền config qua `__init__()` |
| KHÔNG side-effect ẩn | Nếu tool ghi file → nói rõ trong docstring |
| KHÔNG print() | Return kết quả, không print stdout |

---

## 4. Model Factory Pattern

**Quan trọng**: Tất cả agents phải dùng `create_model()` từ `utils/model_factory.py`. KHÔNG import trực tiếp `Gemini` hay `Ollama` trong file agent.

```python
from utils.model_factory import create_model

# Model chính — cho agents cần tool calling mạnh (Agent 2, 4, 5)
model = create_model()

# Model nhỏ — cho agents đơn giản (Agent 0, 1, 1.5)
# Với Ollama: dùng OLLAMA_SMALL_MODEL nếu set, fallback OLLAMA_MODEL
# Với Gemini: luôn dùng cùng model
model = create_model(small=True)
```

Khi thêm agent mới, luôn:
1. Import `create_model` từ `utils/model_factory`
2. Dùng `create_model()` hoặc `create_model(small=True)` trong factory function
3. KHÔNG import `from agno.models.google import Gemini` hay `from agno.models.ollama import Ollama`

---

## 5. Cách Viết Schemas (Pydantic Data Contracts)

### Nguyên tắc
- Mỗi file schema chứa models **liên quan** với nhau
- KHÔNG import tool hay agent trong file schema
- Schema chỉ dùng standard Python types + Pydantic types

### Tổ chức file
```
schemas/
├── __init__.py
├── rule_schemas.py              # RuleInput, RuleCondition, ParsedRule (Agent 0)
├── block_schemas.py             # BlockMappingData (Agent 1)
├── validation_schemas.py        # TestCase, ValidationStatus, ValidationResult (Agent 3)
├── report_schemas.py            # RuleReport, FinalReport
├── diff_schemas.py              # ConfigChange, BlockChange, ModelDiff, ConfigDiscovery (Agent 1.5)
└── agent_inputs.py              # Agent2Input, Agent5Input (structured prompts)
```

---

## 6. Cách Viết Agents (Agno Agent Definitions)

### Nguyên tắc
- File agent CHỈ khai báo: tên, model, tools, instructions
- KHÔNG viết logic xử lý trong file agent
- KHÔNG import schema của agent khác
- Instructions lấy từ `skills/*/SKILL.md` via `load_skill()` — KHÔNG hardcode
- Dùng `create_model()` — KHÔNG import Gemini/Ollama trực tiếp

### Ví dụ
```python
"""
Agent 5: Model Inspector (Copilot 2)
Skill: skills/model-inspector/SKILL.md
"""

from agno.agent import Agent
from tools.xml_tools import XmlToolkit
from tools.code_tools import CodeToolkit
from utils.skill_loader import load_skill
from utils.model_factory import create_model


def create_agent5(xml_toolkit: XmlToolkit, output_dir: str) -> Agent:
    return Agent(
        name="Model Inspector",
        role="Data Detective điều tra XML tree tìm nguyên nhân kết quả sai",
        model=create_model(),
        tools=[xml_toolkit, CodeToolkit(output_dir=output_dir)],
        instructions=load_skill("model-inspector"),
        markdown=True,
        debug_mode=True,
        tool_call_limit=20,
    )
```

---

## 7. Cách Viết Skills (SKILL.md)

### Format
```markdown
---
name: code-generator
description: Senior Python Developer viết rule checking scripts
---

Bạn là Python Developer chuyên viết rule checking script cho TargetLink models.

## QUY TRÌNH LÀM VIỆC
1. Dùng `build_model_hierarchy()` để xem cây subsystem
2. Dùng `find_blocks_recursive()` để tìm blocks
...
```

### Load trong Agent
```python
from utils.skill_loader import load_skill

agent = Agent(
    instructions=load_skill("code-generator"),  # → list[str] từ SKILL.md body
    ...
)
```

---

## 8. Cách Viết Config

### `config.py` — Dual provider support

```python
from typing import Literal
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── LLM Provider ──
    LLM_PROVIDER: Literal["gemini", "ollama"] = "gemini"

    # ── Gemini (Vertex AI) ──
    GOOGLE_CLOUD_PROJECT: str = ""
    GOOGLE_CLOUD_LOCATION: str = "us-central1"
    GEMINI_MODEL: str = "gemini-2.0-flash-001"

    # ── Ollama (local) ──
    OLLAMA_MODEL: str = "qwen2.5:14b"
    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_SMALL_MODEL: str = ""  # Rỗng = dùng OLLAMA_MODEL

    # ── Pipeline ──
    MAX_RETRY_AGENT4: int = 3
    MAX_RETRY_AGENT5: int = 3
    SANDBOX_TIMEOUT: int = 30

    @model_validator(mode="after")
    def validate_provider_config(self):
        if self.LLM_PROVIDER == "gemini":
            if not self.GOOGLE_CLOUD_PROJECT.strip():
                raise ValueError("LLM_PROVIDER=gemini nhưng GOOGLE_CLOUD_PROJECT trống")
        return self
```

---

## 9. Cách Viết Pipeline (Orchestration)

### Nguyên tắc
- Pipeline **KHÔNG chứa** logic của agent
- Pipeline chỉ lo: thứ tự gọi agent, truyền data, routing, retry
- Tách routing, retry, state machine, exploration cache ra files riêng

### Pipeline files
```
pipeline/
├── runner.py              # Pipeline chính: run_pipeline()
├── router.py              # Routing: Agent 3 → Agent 4 hay 5?
├── retry.py               # Retry management
├── state_machine.py       # RetryStateMachine + loop detection
└── exploration_cache.py   # Knowledge handoff + cross-rule cache
```

---

## 10. Bảng Tham Chiếu: Agentic Coder → TargetLink

| Pattern từ Agentic | Áp dụng cho TargetLink | File |
|--------------------|-----------------------|------|
| Schema tách riêng | `schemas/*.py` — Pydantic models tách theo domain | `schemas/` |
| Tools tách theo nhóm | `tools/*.py` — Toolkit classes | `tools/` |
| Config qua BaseSettings | `config.py` — validate + .env + dual provider | `config.py` |
| Role-based tool access | Agent 0-1 read-only, Agent 2-5 có write | `agents/` |
| Output truncation | Tool trả max results, cắt text | `utils/output_truncator.py` |
| Retry + doom loop | `pipeline/retry.py` + `utils/loop_detector.py` | `pipeline/` |
| Sandbox execution | Agent 3 subprocess isolation | `agents/agent3_validator.py` |
| Factory pattern | `create_agentX()` + `create_model()` | `agents/`, `utils/model_factory.py` |
| Knowledge handoff | exploration_summary, previous_findings | `pipeline/exploration_cache.py` |
| Cross-rule cache | ExplorationCache reuse | `pipeline/exploration_cache.py` |

---

## 11. Checklist Trước Khi Code

- [ ] Schema cho input/output đã có trong `schemas/`?
- [ ] Tool đã viết trong `tools/`, có docstring, trả về `str`?
- [ ] Agent file chỉ khai báo, KHÔNG chứa logic?
- [ ] Agent dùng `create_model()` từ model_factory, KHÔNG import Gemini/Ollama trực tiếp?
- [ ] Skill nằm trong `skills/*/SKILL.md`, load qua `load_skill()`?
- [ ] Pipeline routing nằm trong `pipeline/router.py`?
- [ ] Config đọc từ `.env`, KHÔNG hardcode?
- [ ] XML access là READ-ONLY, bọc trong try-except?
- [ ] Output có truncation?
- [ ] tool_call_limit đã set cho agentic agents?
