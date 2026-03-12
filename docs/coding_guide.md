# Coding Guide: Quy tắc Viết Code cho TargetLink Rule Checking

Tài liệu này quy định **cách tổ chức code**, **tách file rõ ràng**, và **coding patterns** cho dự án. Tham khảo từ agentic coder (`D:\targetlink\agentic\`) và chuẩn hóa lại cho **Agno framework**.

> **Nguyên tắc vàng**: KHÔNG BAO GIỜ đổ hết khai báo Tool + Class + Logic vào 1 file. Mỗi file chỉ làm MỘT việc.

---

## 1. Cấu trúc Thư mục Bắt Buộc

```
targetlink/
├── main.py                          # Entry point DUY NHẤT — chỉ gọi pipeline.run()
├── config.py                        # Cấu hình: API keys, LLM provider, paths
├── requirements.txt                 # Dependencies
├── .env                             # Secrets (KHÔNG commit)
│
├── schemas/                         # Pydantic models — DATA CONTRACT giữa agents
│   ├── __init__.py
│   ├── rule_schemas.py              # ParsedRule, RuleInput
│   ├── block_schemas.py             # BlockMappingData, BlockDictEntry
│   ├── code_schemas.py              # GeneratedCode, PatchedCode
│   ├── validation_schemas.py        # ValidationResult, ValidationStatus
│   └── report_schemas.py            # InspectionResult, FinalReport
│
├── tools/                           # Tool functions — KHẢ NĂNG của agents
│   ├── __init__.py
│   ├── xml_tools.py                 # read_xml_structure, test_xpath_query, deep_search_xml_text, read_parent_nodes
│   ├── search_tools.py              # fuzzy_search_json, read_dictionary
│   ├── code_tools.py                # write_python_file, read_python_file, patch_python_file, rewrite_advanced_code
│   └── sandbox_tools.py             # sandbox_execute_python, compare_json_result
│
├── agents/                          # Agent definitions — CHỈ khai báo Agent, KHÔNG chứa logic
│   ├── __init__.py
│   ├── agent0_rule_analyzer.py      # Khai báo Agent 0 + instructions + tools
│   ├── agent1_data_reader.py        # Khai báo Agent 1 + instructions + tools
│   ├── agent2_code_generator.py     # Khai báo Agent 2 + instructions + tools
│   ├── agent3_validator.py          # Khai báo Agent 3 + instructions + tools
│   ├── agent4_bug_fixer.py          # Khai báo Agent 4 + instructions + tools
│   └── agent5_inspector.py          # Khai báo Agent 5 + instructions + tools
│
├── skills/                          # Agent Skills — SKILL.md theo Anthropic format
│   ├── rule-analyzer/
│   │   └── SKILL.md                 # Agent 0 instructions
│   ├── data-reader/
│   │   └── SKILL.md                 # Agent 1 instructions
│   ├── code-generator/
│   │   └── SKILL.md                 # Agent 2 instructions
│   ├── validator/
│   │   └── SKILL.md                 # Agent 3 instructions
│   ├── bug-fixer/
│   │   └── SKILL.md                 # Agent 4 instructions
│   └── model-inspector/
│       └── SKILL.md                 # Agent 5 instructions
│
├── pipeline/                        # Orchestration logic — ĐIỀU PHỐI agents
│   ├── __init__.py
│   ├── runner.py                    # Hàm chạy pipeline chính: run_pipeline()
│   ├── router.py                    # Logic routing: Agent 3 → Agent 4 hay Agent 5?
│   └── retry.py                     # Logic retry + escalation policy
│
├── utils/                           # Helper functions — DÙNG CHUNG
│   ├── __init__.py
│   ├── slx_extractor.py             # Unzip .slx → trả về thư mục gốc XML tree
│   ├── skill_loader.py              # Load SKILL.md → list[str] cho Agno instructions
│   ├── logger.py                    # Logging config
│   └── file_helpers.py              # Path resolution, file I/O helpers
│
├── data/                            # Dữ liệu đầu vào từ User
│   ├── model.slx
│   ├── blocks.json
│   ├── rules.json
│   └── expected_results.json
│
├── generated_checks/                # Auto-generated bởi agents
│   └── .gitkeep
│
├── reports/                         # Auto-generated bởi agents
│   └── .gitkeep
│
└── docs/
    ├── architecture.md
    ├── agents_detail.md
    └── coding_guide.md              # File này
```

---

## 2. Nguyên tắc Tách File

### ❌ SAI — Đổ hết vào 1 file

```python
# ĐỪNG LÀM THẾ NÀY trong agent2_code_generator.py
from agno.agent import Agent
from agno.models.google import Gemini
from agno.tools import Toolkit
from pydantic import BaseModel
from lxml import etree

# Khai báo schema NGAY TRONG file agent?? → SAI
class GeneratedCode(BaseModel):
    rule_id: str
    file_path: str
    code_content: str

# Khai báo tool NGAY TRONG file agent?? → SAI
class XmlTools(Toolkit):
    def __init__(self):
        super().__init__(name="xml_tools")
        self.register(self.read_xml_structure)

    def read_xml_structure(self, xml_file: str, xpath: str) -> str:
        tree = self._get_tree(xml_file)
        # ... 50 dòng logic ...
        return result

# Logic pipeline NGAY TRONG file agent?? → SAI
def run_agent2(parsed_rule, block_data, model_dir):
    agent = Agent(
        model=Gemini(id="gemini-2.0-flash-001", vertexai=True, project_id="...", location="..."),
        tools=[XmlTools()],
    )
    result = agent.run(...)
    # ... routing logic ...
    if result.status == "error":
        run_agent4(result)  # Gọi agent khác ngay đây?? → SAI

# Tất cả 200+ dòng trong 1 file → KHÔNG AI MAINTAIN NỔI
```

### ✅ ĐÚNG — Mỗi file 1 trách nhiệm

**File `schemas/code_schemas.py`** — Chỉ khai báo data structure:
```python
from pydantic import BaseModel

class GeneratedCode(BaseModel):
    """Output của Agent 2/4/5: code Python đã sinh."""
    rule_id: str
    file_path: str
    code_content: str
    generation_note: str  # "first_gen" / "patched" / "rewritten"
```

**File `tools/xml_tools.py`** — Chỉ implement tool functions:
```python
from lxml import etree

def read_xml_structure(self, xml_file: str, xpath: str) -> str:
    """Đọc cấu trúc XML nodes trong 1 file cụ thể. READ-ONLY."""
    tree = self._get_tree(xml_file)
    nodes = tree.xpath(xpath)
    # ... logic xử lý ...
    return formatted_result

def test_xpath_query(self, xml_file: str, xpath: str) -> str:
    """Chạy thử XPath trên 1 file XML, trả về kết quả match."""
    tree = self._get_tree(xml_file)
    nodes = tree.xpath(xpath)
    # ... format results ...
    return json.dumps(results)
```

**File `agents/agent2_code_generator.py`** — Chỉ khai báo agent:
```python
from agno.agent import Agent
from agno.models.google import Gemini
from config import settings
from tools.xml_tools import XmlToolkit
from tools.code_tools import CodeToolkit
from utils.skill_loader import load_skill


def create_agent2(model_dir: str) -> Agent:
    return Agent(
        name="Code Generator",
        role="Senior Python Developer viết rule checking scripts",
        model=Gemini(
            id=settings.GEMINI_MODEL,
            vertexai=True,
            project_id=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
        ),
        tools=[
            XmlToolkit(model_dir=model_dir),
            CodeToolkit(output_dir=str(settings.GENERATED_CHECKS_DIR)),
        ],
        instructions=load_skill("code-generator"),
        markdown=True,
        show_tool_calls=True,
    )
```

**File `pipeline/runner.py`** — Chỉ điều phối:
```python
from agents.agent2_code_generator import agent2_code_generator
from pipeline.router import route_validation_result
from pipeline.retry import RetryManager

async def run_pipeline(rules, blocks, model_path, expected):
    # ... orchestration logic ...
```

---

## 3. Cách Viết Tools cho Agno (Agent Skills)

### 3.1 "Agent Skill" trong Agno nghĩa là gì?

Trong Agno, "Skill" = **Tool** = khả năng Agent thực hiện hành động cụ thể. Agno cung cấp 2 cách tạo Tool:

**Cách 1: Toolkit class** (dùng khi tools cần shared state, VD: model_dir dùng chung)
```python
from agno.tools import Toolkit

class XmlToolkit(Toolkit):
    def __init__(self, model_dir: str):
        super().__init__(name="xml_tools")
        self.model_dir = model_dir           # Thư mục gốc XML tree
        self._tree_cache = {}                 # Cache per-file
        self.register(self.list_xml_files)
        self.register(self.read_xml_structure)

    def list_xml_files(self) -> str:
        """Liệt kê tất cả file XML trong model tree. GỌI ĐẦU TIÊN."""
        ...

    def read_xml_structure(self, xml_file: str, xpath: str) -> str:
        """Đọc cấu trúc XML nodes tại XPath trong 1 file XML. READ-ONLY."""
        # Agent sẽ thấy docstring này và biết tool làm gì
        ...
```

**Cách 2: Function tool** (dùng khi tool đơn giản, không cần shared state)
```python
from agno.tools import tool

@tool
def fuzzy_search_json(keyword: str, json_path: str) -> str:
    """Tìm block trong file JSON bằng fuzzy matching. Trả về block match nhất."""
    ...
```

### 3.2 Quy tắc viết Tool

| Quy tắc | Lý do |
|---------|-------|
| Docstring BẮT BUỘC | LLM dùng docstring để hiểu tool làm gì và khi nào nên gọi |
| Trả về `str` | Agno truyền kết quả tool cho LLM dưới dạng text. Nếu trả dict/list → dùng `json.dumps()` |
| KHÔNG gọi agent khác trong tool | Tool chỉ làm 1 việc. Routing là việc của `pipeline/` |
| KHÔNG đọc config trực tiếp | Truyền config qua `__init__()` của Toolkit |
| KHÔNG side-effect ẩn | Nếu tool ghi file → nói rõ trong docstring |
| KHÔNG print() | Return kết quả, không print ra stdout |

### 3.3 Tổ chức file Tools

```
tools/
├── __init__.py              # Export tất cả Toolkits
├── xml_tools.py             # XmlToolkit class — cho Agent 2, 5
├── search_tools.py          # SearchToolkit class — cho Agent 1
├── code_tools.py            # CodeToolkit class — cho Agent 2, 4, 5
└── sandbox_tools.py         # SandboxToolkit class — cho Agent 3
```

**Ví dụ rút gọn `tools/xml_tools.py`:**

SLX sau khi unzip = XML tree (nhiều file XML). Agent KHÔNG có tool đọc toàn bộ — phải explore từng phần.

```python
"""
Tools cho việc khám phá XML tree từ model TargetLink.
SLX unzip = nhiều file XML, agent phải list_xml_files() trước rồi explore.
Tất cả operations đều READ-ONLY.
"""

import json
import re
from pathlib import Path
from lxml import etree
from agno.tools import Toolkit


class XmlToolkit(Toolkit):
    """Khám phá XML tree — KHÔNG đọc toàn bộ, explore từng phần."""

    def __init__(self, model_dir: str):
        super().__init__(name="xml_tools")
        self.model_dir = model_dir
        self._tree_cache: dict[str, etree._ElementTree] = {}  # Cache per-file

        self.register(self.list_xml_files)
        self.register(self.read_xml_structure)
        self.register(self.test_xpath_query)
        self.register(self.deep_search_xml_text)
        self.register(self.read_parent_nodes)

    def _get_tree(self, xml_file: str) -> etree._ElementTree:
        """Lazy load và cache XML tree cho từng file."""
        if xml_file not in self._tree_cache:
            full_path = Path(self.model_dir) / xml_file
            self._tree_cache[xml_file] = etree.parse(str(full_path))
        return self._tree_cache[xml_file]

    def list_xml_files(self) -> str:
        """Liệt kê tất cả file XML trong model tree. GỌI ĐẦU TIÊN."""
        xml_files = sorted(Path(self.model_dir).rglob("*.xml"))
        results = [{"path": str(f.relative_to(self.model_dir)), "size_kb": round(f.stat().st_size/1024, 1)}
                   for f in xml_files]
        return json.dumps(results, indent=2)

    def read_xml_structure(self, xml_file: str, xpath: str) -> str:
        """Đọc cấu trúc nodes tại XPath trong 1 file XML cụ thể. READ-ONLY."""
        tree = self._get_tree(xml_file)
        nodes = tree.xpath(xpath)
        # ... trả về tối đa 10 nodes, 20 children mỗi node ...

    def test_xpath_query(self, xml_file: str, xpath: str) -> str:
        """Verify XPath trên 1 file XML — tối đa 20 kết quả."""
        ...

    def deep_search_xml_text(self, xml_file: str, regex_pattern: str) -> str:
        """Regex search trong 1 file XML — tối đa 50 matches."""
        ...

    def read_parent_nodes(self, xml_file: str, xpath: str) -> str:
        """Đọc ancestry chain từ root → target node."""
        ...
```

---

## 4. Cách Viết Schemas (Pydantic Data Contracts)

### 4.1 Nguyên tắc

- Mỗi file schema chứa các models **liên quan** với nhau
- KHÔNG import tool hay agent trong file schema
- Schema chỉ dùng standard Python types + Pydantic types
- Mỗi field có comment giải thích

### 4.2 Tổ chức file Schemas

```
schemas/
├── __init__.py                  # Re-export tất cả
├── rule_schemas.py              # Agent 0 input/output
├── block_schemas.py             # Agent 1 output
├── code_schemas.py              # Agent 2/4/5 output
├── validation_schemas.py        # Agent 3 output
└── report_schemas.py            # Final output
```

**Ví dụ `schemas/validation_schemas.py`:**

```python
"""
Schemas cho Agent 3 (Validator) — Kết quả validation và routing.
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ValidationStatus(str, Enum):
    """Trạng thái sau khi Agent 3 chạy code và so sánh kết quả."""
    PASS = "PASS"
    CODE_ERROR = "CODE_ERROR"
    WRONG_RESULT = "WRONG_RESULT"
    FAILED_CODE_ERROR = "FAILED_CODE_ERROR"
    FAILED_WRONG_RESULT = "FAILED_WRONG_RESULT"
    SCHEMA_ERROR = "SCHEMA_ERROR"


class ValidationResult(BaseModel):
    """Output chính của Agent 3. Quyết định pipeline đi tiếp hay retry."""

    rule_id: str = Field(description="ID của rule đang check")
    status: ValidationStatus = Field(description="Kết quả validation")
    stdout: Optional[str] = Field(default=None, description="Standard output từ sandbox")
    stderr: Optional[str] = Field(default=None, description="Standard error từ sandbox")
    actual_result: Optional[dict] = Field(default=None, description="Kết quả chạy thực tế")
    expected_result: Optional[dict] = Field(default=None, description="Kết quả mong đợi từ user")
    retry_count: int = Field(default=0, ge=0, le=6, description="Số lần đã retry (max 3 cho Agent 4 + 3 cho Agent 5)")
    code_file_path: str = Field(description="Đường dẫn tới file code hiện tại")
```

---

## 5. Cách Viết Agents (Agno Agent Definitions)

### 5.1 Nguyên tắc

- File agent CHỈ khai báo: tên, model, tools, instructions
- KHÔNG viết logic xử lý trong file agent
- KHÔNG import schema của agent khác (tránh circular)
- Instructions lấy từ `skills/*/SKILL.md` via `load_skill()` — KHÔNG hardcode trong file agent

### 5.2 Ví dụ `agents/agent2_code_generator.py`

```python
"""
Agent 2: Code Generator (Copilot 1)
Vai trò: Đọc XML model thực tế → Sinh Python code kiểm tra rule.
"""

from agno.agent import Agent
from agno.models.google import Gemini

from config import settings
from tools.xml_tools import XmlToolkit
from tools.code_tools import CodeToolkit
from utils.skill_loader import load_skill


def create_agent2(model_dir: str) -> Agent:
    """Factory function tạo Agent 2 với config hiện tại.

    Dùng factory pattern vì model_dir thay đổi theo từng lần chạy.
    """
    return Agent(
        name="Code Generator",
        role="Senior Python Developer viết rule checking scripts",
        model=Gemini(
            id=settings.GEMINI_MODEL,
            vertexai=True,
            project_id=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
        ),
        tools=[
            XmlToolkit(model_dir=model_dir),
            CodeToolkit(output_dir=str(settings.GENERATED_CHECKS_DIR)),
        ],
        instructions=load_skill("code-generator"),
        markdown=True,
        show_tool_calls=True,
    )
```

### 5.3 Ví dụ `agents/agent3_validator.py`

```python
"""
Agent 3: Validator (Reviewer)
Vai trò: Chạy code trong sandbox → So sánh kết quả với expected.
"""

from agno.agent import Agent
from agno.models.google import Gemini

from config import settings
from tools.sandbox_tools import SandboxToolkit
from schemas.validation_schemas import ValidationResult
from utils.skill_loader import load_skill


def create_agent3(model_dir: str) -> Agent:
    """Factory function tạo Agent 3."""
    return Agent(
        name="Validator",
        role="QA Tester chạy code sandbox và đối chiếu kết quả",
        model=Gemini(
            id=settings.GEMINI_MODEL,
            vertexai=True,
            project_id=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
        ),
        tools=[
            SandboxToolkit(
                model_dir=model_dir,
                timeout=settings.SANDBOX_TIMEOUT,
            )
        ],
        instructions=load_skill("validator"),
        response_model=ValidationResult,
        structured_outputs=True,
    )
```

---

## 6. Cách Viết Skills (SKILL.md — Anthropic Agent Skills Format)

### 6.1 Tại sao dùng SKILL.md thay vì Python prompt files?

- **Chuẩn Anthropic Agent Skills**: File `.md` với YAML frontmatter (`name`, `description`) + body instructions
- Prompt thường DÀI (50-100 dòng) → tách ra file `.md` riêng cho dễ sửa, dễ review
- Markdown dễ đọc hơn Python list-of-strings, dễ bảo trì hơn
- `utils/skill_loader.py` tự động parse frontmatter và trả về body lines cho Agno `instructions`

### 6.2 Cấu trúc thư mục Skills

```
skills/
├── rule-analyzer/
│   └── SKILL.md          # Agent 0
├── data-reader/
│   └── SKILL.md          # Agent 1
├── code-generator/
│   └── SKILL.md          # Agent 2
├── validator/
│   └── SKILL.md          # Agent 3
├── bug-fixer/
│   └── SKILL.md          # Agent 4
└── model-inspector/
    └── SKILL.md          # Agent 5
```

### 6.3 Format SKILL.md

```markdown
---
name: code-generator
description: Senior Python Developer viết rule checking scripts cho TargetLink models
---

Bạn là Python Developer chuyên viết rule checking script cho TargetLink models.

## QUY TRÌNH LÀM VIỆC
1. Dùng `list_xml_files()` để xem model tree có những file XML nào
2. Dùng `read_xml_structure(xml_file, xpath)` để xem cấu trúc thực tế
3. Dùng `test_xpath_query(xml_file, xpath)` để verify XPath
4. Nếu XPath không match → thử biến thể khác, search ở file XML khác
5. Khi đã có XPath đúng → `write_python_file()` để lưu script

## YÊU CẦU CODE SINH RA
- Import: `from lxml import etree; import json, sys, os`
- Function `check_rule(model_dir: str) -> dict` nhận thư mục XML tree
- Code tự parse đúng file XML từ model_dir
- Return dict keys: rule_id, total_blocks, pass_count, fail_count, details
- Bọc XML access trong try-except (node có thể None)
- Có `if __name__ == '__main__'` để chạy standalone
- Print JSON ra stdout

## TUYỆT ĐỐI KHÔNG
- Không ghi/sửa file XML
- Không sinh code mà chưa dùng tool đọc XML thật trước
- Không đoán XPath — luôn verify bằng `test_xpath_query` trước
```

### 6.4 Cách load trong Agent

```python
from utils.skill_loader import load_skill

agent = Agent(
    instructions=load_skill("code-generator"),  # → list[str] từ SKILL.md body
    ...
)
```

### 6.5 Skill Loader (`utils/skill_loader.py`)

```python
"""Load SKILL.md files theo Anthropic Agent Skills format."""

from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent / "skills"


def load_skill(skill_name: str) -> list[str]:
    """Load SKILL.md, strip YAML frontmatter, trả về body lines."""
    skill_path = SKILLS_DIR / skill_name / "SKILL.md"
    content = skill_path.read_text(encoding="utf-8")

    # Strip YAML frontmatter (giữa hai dòng ---)
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            content = content[end + 3:]

    return [line for line in content.strip().splitlines()]
```

---

## 7. Cách Viết Pipeline (Orchestration)

### 7.1 Nguyên tắc

- Pipeline **KHÔNG chứa** logic của agent (agent tự quyết trong prompt)
- Pipeline chỉ lo: thứ tự gọi agent, truyền data, routing, retry
- Tách routing logic và retry logic ra file riêng

### 7.2 Ví dụ `pipeline/runner.py`

```python
"""
Pipeline chính: Điều phối 6 agents chạy tuần tự theo rule.
"""

import json
from pathlib import Path
from typing import Any

from schemas.rule_schemas import ParsedRule
from schemas.block_schemas import BlockMappingData
from schemas.code_schemas import GeneratedCode
from schemas.validation_schemas import ValidationResult, ValidationStatus
from schemas.report_schemas import FinalReport, RuleReport

from agents.agent0_rule_analyzer import create_agent0
from agents.agent1_data_reader import create_agent1
from agents.agent2_code_generator import create_agent2
from agents.agent3_validator import create_agent3
from agents.agent4_bug_fixer import create_agent4
from agents.agent5_inspector import create_agent5

from pipeline.router import route_validation
from pipeline.retry import RetryManager
from utils.slx_extractor import extract_slx
from utils.logger import logger


async def run_pipeline(
    model_path: str,
    blocks_path: str,
    rules_path: str,
    expected_path: str,
) -> FinalReport:
    """Chạy toàn bộ pipeline cho tất cả rules.

    Returns:
        FinalReport chứa kết quả tổng hợp.
    """
    # ── Bước 0: Chuẩn bị ──
    model_dir = extract_slx(model_path)  # Unzip .slx → trả về thư mục XML tree
    rules = json.loads(Path(rules_path).read_text())
    expected = json.loads(Path(expected_path).read_text())

    # ── Tạo agents (1 lần, dùng lại cho nhiều rules) ──
    agent0 = create_agent0()
    agent1 = create_agent1(blocks_path)
    agent2 = create_agent2(model_dir)
    agent3 = create_agent3(model_dir)
    agent4 = create_agent4()
    agent5 = create_agent5(model_dir)

    # ── Chạy từng rule ──
    rule_reports: list[RuleReport] = []

    for rule in rules:
        logger.info(f"Processing rule: {rule['rule_id']}")
        expected_for_rule = _find_expected(expected, rule["rule_id"])

        report = await _process_single_rule(
            rule=rule,
            expected=expected_for_rule,
            agents=(agent0, agent1, agent2, agent3, agent4, agent5),
        )
        rule_reports.append(report)

    return FinalReport(
        model_file=model_path,
        total_rules=len(rules),
        results=rule_reports,
    )


async def _process_single_rule(rule, expected, agents) -> RuleReport:
    """Xử lý 1 rule qua pipeline 6 agents."""
    agent0, agent1, agent2, agent3, agent4, agent5 = agents
    retry = RetryManager(max_retries=3)

    # ── Agent 0: Parse rule text ──
    parsed = await agent0.arun(rule["description"])
    logger.info(f"Agent 0 parsed: {parsed}")

    # ── Agent 1: Search block dictionary ──
    block_data = await agent1.arun(parsed)
    logger.info(f"Agent 1 found block: {block_data}")

    # ── Agent 2: Generate check code ──
    generated = await agent2.arun(f"Rule: {parsed}\nBlock info: {block_data}")
    logger.info(f"Agent 2 generated: {generated}")

    # ── Agent 3: Validate → Route to Agent 4 or 5 if needed ──
    validation = await agent3.arun(
        f"Code file: {generated}\nExpected: {expected}"
    )

    # ── Retry loop ──
    while not retry.is_exhausted(validation):
        next_agent, context = route_validation(validation, block_data)

        if next_agent == "agent4":
            fixed = await agent4.arun(context)
            validation = await agent3.arun(f"Code file: {fixed}\nExpected: {expected}")
            retry.increment("agent4")

        elif next_agent == "agent5":
            inspected = await agent5.arun(context)
            validation = await agent3.arun(f"Code file: {inspected}\nExpected: {expected}")
            retry.increment("agent5")

        else:
            break  # PASS hoặc exhausted

    return RuleReport.from_validation(rule["rule_id"], validation, retry.get_trace())


def _find_expected(expected_list: list, rule_id: str) -> dict:
    """Tìm expected result cho rule_id."""
    for item in expected_list:
        if item.get("rule_id") == rule_id:
            return item
    return {}
```

### 7.3 Ví dụ `pipeline/router.py`

```python
"""
Routing logic: Dựa vào ValidationResult, quyết định chuyển cho Agent nào.
"""

from schemas.validation_schemas import ValidationResult, ValidationStatus
from schemas.block_schemas import BlockMappingData


def route_validation(
    result: ValidationResult,
    block_data: BlockMappingData,
) -> tuple[str, str]:
    """Quyết định agent tiếp theo dựa trên kết quả validation.

    Returns:
        (next_agent, context_message) — VD: ("agent4", "Error: NoneType...")
    """
    if result.status == ValidationStatus.PASS:
        return ("done", "")

    if result.status == ValidationStatus.CODE_ERROR:
        context = (
            f"File bị lỗi: {result.code_file_path}\n"
            f"Error:\n{result.stderr}\n"
            f"Lần retry: {result.retry_count}"
        )
        return ("agent4", context)

    if result.status == ValidationStatus.WRONG_RESULT:
        context = (
            f"File code: {result.code_file_path}\n"
            f"Actual: {result.actual_result}\n"
            f"Expected: {result.expected_result}\n"
            f"Block info: {block_data.config_map_analysis}\n"
            f"Lần retry: {result.retry_count}"
        )
        return ("agent5", context)

    return ("failed", "")
```

### 7.4 Ví dụ `pipeline/retry.py`

```python
"""
Retry management và escalation policy.
"""


class RetryManager:
    """Quản lý số lần retry cho Agent 4 và Agent 5."""

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self.counts = {"agent4": 0, "agent5": 0}
        self.trace: list[dict] = []

    def increment(self, agent_name: str) -> None:
        self.counts[agent_name] += 1
        self.trace.append({"agent": agent_name, "attempt": self.counts[agent_name]})

    def is_exhausted(self, result) -> bool:
        """Check xem đã hết retry chưa."""
        if result.status == "PASS":
            return True  # Không cần retry nữa
        if result.status == "CODE_ERROR" and self.counts["agent4"] >= self.max_retries:
            return True
        if result.status == "WRONG_RESULT" and self.counts["agent5"] >= self.max_retries:
            return True
        return False

    def get_trace(self) -> list[dict]:
        return self.trace.copy()
```

---

## 8. Cách Viết Config

### 8.1 Ví dụ `config.py`

```python
"""
Configuration: Đọc từ .env, validate, export settings.
Pattern tham khảo từ agentic/config.py (Pydantic BaseSettings).
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Google Cloud Vertex AI ──
    GOOGLE_CLOUD_PROJECT: str               # BẮT BUỘC — GCP Project ID
    GOOGLE_CLOUD_LOCATION: str = "us-central1"
    GOOGLE_GENAI_USE_VERTEXAI: bool = True  # Luôn True — dùng Vertex AI
    GEMINI_MODEL: str = "gemini-2.0-flash-001"

    # ── Xác thực (tùy chọn — nếu dùng Service Account) ──
    GOOGLE_APPLICATION_CREDENTIALS: str = ""  # Path tới JSON key file, bỏ trống nếu dùng ADC

    # ── Paths ──
    BASE_DIR: Path = Path(__file__).parent
    GENERATED_CHECKS_DIR: Path = Path("generated_checks")
    REPORTS_DIR: Path = Path("reports")
    DATA_DIR: Path = Path("data")

    # ── Pipeline ──
    MAX_RETRY_AGENT4: int = 3
    MAX_RETRY_AGENT5: int = 3
    SANDBOX_TIMEOUT: int = 30  # seconds

    # ── XML ──
    # MODEL_DIR được set at runtime bởi pipeline sau khi extract .slx


settings = Settings()
```

### 8.2 File `.env`

```env
# ══════════════════════════════════════════════════════════
# Google Cloud Vertex AI Configuration
# ══════════════════════════════════════════════════════════

# BẮT BUỘC: GCP Project ID (tìm trong Google Cloud Console)
GOOGLE_CLOUD_PROJECT=my-project-id

# Region cho Vertex AI (mặc định us-central1)
GOOGLE_CLOUD_LOCATION=us-central1

# Bật Vertex AI mode cho google-genai SDK
GOOGLE_GENAI_USE_VERTEXAI=true

# Model Gemini (thay đổi nếu cần model khác)
GEMINI_MODEL=gemini-2.0-flash-001

# ══════════════════════════════════════════════════════════
# Xác thực — CHỌN 1 TRONG 2 CÁCH
# ══════════════════════════════════════════════════════════

# Cách 1 (Khuyến nghị cho dev local):
#   Chạy lệnh: gcloud auth application-default login
#   → Không cần set biến nào thêm

# Cách 2 (Cho CI/CD hoặc server):
#   Download Service Account JSON key từ GCP Console
#   Uncomment dòng dưới và set đúng path:
# GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account-key.json

# ══════════════════════════════════════════════════════════
# Pipeline Config
# ══════════════════════════════════════════════════════════

MAX_RETRY_AGENT4=3
MAX_RETRY_AGENT5=3
SANDBOX_TIMEOUT=30
```

---

## 9. Cách Viết `main.py`

```python
"""
Entry point duy nhất. Chỉ parse CLI args và gọi pipeline.
"""

import argparse
import asyncio

from pipeline.runner import run_pipeline
from utils.logger import setup_logger


def main():
    parser = argparse.ArgumentParser(description="TargetLink Rule Checking System")
    parser.add_argument("--model", required=True, help="Path to .slx model file")
    parser.add_argument("--blocks", required=True, help="Path to blocks.json")
    parser.add_argument("--rules", required=True, help="Path to rules.json")
    parser.add_argument("--expected", required=True, help="Path to expected_results.json")
    args = parser.parse_args()

    setup_logger()

    report = asyncio.run(run_pipeline(
        model_path=args.model,
        blocks_path=args.blocks,
        rules_path=args.rules,
        expected_path=args.expected,
    ))

    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
```

---

## 10. Bảng Tham Chiếu: Agentic Coder → TargetLink

Patterns học được từ `D:\targetlink\agentic\` (LangGraph) và áp dụng lại cho Agno:

| Pattern từ Agentic | Áp dụng cho TargetLink | File tham khảo |
|--------------------|-----------------------|----------------|
| Schema tách riêng (`models/tool_schemas.py`) | `schemas/*.py` — Pydantic models tách theo domain | `agentic/models/tool_schemas.py` |
| Tools tách theo nhóm (`agent/tools/*.py`) | `tools/*.py` — Toolkit classes theo chức năng | `agentic/agent/tools/file_ops.py` |
| Config qua Pydantic BaseSettings | `config.py` — validate + .env | `agentic/config.py` |
| Role-based tool access (Planner/Coder) | Agent 0-1 read-only, Agent 2-5 có write | `agentic/agent/graph.py` |
| Output truncation | Tool trả max 50 results, cắt text > 200 chars | `agentic/agent/tools/truncation.py` |
| Retry + doom loop detection | `pipeline/retry.py` — max 3 retries | `agentic/agent/nodes.py` |
| Sandbox execution | `tools/sandbox_tools.py` — subprocess isolation | `agentic/agent/sandbox.py` |
| Factory pattern cho agents | `create_agentX()` functions | Adapted from Agno docs |

---

## 11. Checklist Trước Khi Code

- [ ] Schema cho input/output của agent đã có trong `schemas/`?
- [ ] Tool đã viết trong `tools/`, có docstring, trả về `str`?
- [ ] Agent file chỉ khai báo, KHÔNG chứa logic?
- [ ] Skill nằm trong `skills/*/SKILL.md`, load qua `load_skill()`, KHÔNG hardcode?
- [ ] Pipeline routing nằm trong `pipeline/router.py`?
- [ ] Config đọc từ `.env`, KHÔNG hardcode credentials?
- [ ] Agent dùng `Gemini(vertexai=True, project_id=..., location=...)` (KHÔNG dùng `api_key=`)?
- [ ] XML access là READ-ONLY, bọc trong try-except?
- [ ] Output có truncation (max 50 results, max 200 chars per field)?
