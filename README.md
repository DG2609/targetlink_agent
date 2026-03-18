# TargetLink Model Rule Checking System

Hệ thống Multi-Agent AI (7 Agents) sử dụng framework **Agno**, **Pydantic**, và **LLM (Gemini hoặc Ollama)** để tự động đọc, hiểu, và kiểm tra các modeling rules của dSpace TargetLink trên file model `.slx` (không cần cài đặt MATLAB).

## Điểm nổi bật
- **Không cần MATLAB**: Đọc trực tiếp file `.slx` qua việc unzip cấu trúc XML.
- **Dual LLM Provider**: Hỗ trợ **Google Gemini (Vertex AI)** hoặc **Ollama (local)** — chuyển đổi qua 1 biến `.env`.
- **Agentic Workflow**: Các agents (Code Generator, Validator, Bug Fixer, Inspector) hoạt động tự trị — tự gọi tools nhiều lần, tự khám phá XML, tự viết/sửa code.
- **Diff-Based Config Discovery**: So sánh 2 version model để phát hiện config thay đổi (Agent 1.5).
- **Knowledge Handoff**: Agent 2 truyền exploration summary cho Agent 5, tích lũy qua các vòng retry.
- **Cross-Rule Cache**: Cache hierarchy/blocks/configs từ rule đầu để tái sử dụng cho các rules sau.
- **READ-ONLY Model**: Tuyệt đối không can thiệp, không ghi đè, không làm hỏng model gốc.

## Cấu trúc Thư mục

```
targetlink/
├── main.py                          # Entry point — CLI args + pipeline
├── config.py                        # Pydantic Settings — đọc .env, dual provider
├── requirements.txt                 # Dependencies
├── .env                             # Config (LLM provider, credentials)
│
├── agents/                          # Định nghĩa Agent (factory functions)
│   ├── agent0_rule_analyzer.py      # Agent 0: Parse rule text
│   ├── agent1_data_reader.py        # Agent 1: Search block dictionary
│   ├── agent1_5_diff_analyzer.py    # Agent 1.5: Diff-based config discovery
│   ├── agent2_code_generator.py     # Agent 2: Generate check code (agentic)
│   ├── agent3_validator.py          # Agent 3: Sandbox execute + validate
│   ├── agent4_bug_fixer.py          # Agent 4: Fix code errors
│   └── agent5_inspector.py          # Agent 5: Deep XML investigation (agentic)
│
├── tools/                           # Agno Toolkit classes
│   ├── xml_tools.py                 # XmlToolkit: hierarchy, blocks, config, XPath...
│   ├── search_tools.py              # SearchToolkit: fuzzy search, read dictionary
│   └── code_tools.py                # CodeToolkit: write/read/patch/rewrite code
│
├── schemas/                         # Pydantic Data Contracts giữa các Agent
│   ├── rule_schemas.py              # RuleInput, RuleCondition, ParsedRule
│   ├── block_schemas.py             # BlockMappingData
│   ├── validation_schemas.py        # TestCase, ValidationStatus, ValidationResult
│   ├── report_schemas.py            # RuleReport, FinalReport
│   ├── diff_schemas.py              # ConfigChange, BlockChange, ModelDiff, ConfigDiscovery
│   └── agent_inputs.py              # Agent2Input, Agent5Input (structured prompts)
│
├── pipeline/                        # Orchestration
│   ├── runner.py                    # Pipeline chính: run_pipeline()
│   ├── router.py                    # Routing: Agent 3 → Agent 4 hay 5?
│   ├── retry.py                     # Retry logic + escalation
│   ├── state_machine.py             # RetryStateMachine + loop detection
│   └── exploration_cache.py         # Knowledge handoff + cross-rule cache
│
├── utils/                           # Helpers
│   ├── model_factory.py             # LLM factory: Gemini hoặc Ollama
│   ├── slx_extractor.py             # Unzip .slx → XML tree
│   ├── skill_loader.py              # Load SKILL.md → Agno instructions
│   ├── model_differ.py              # Pure Python XML diff (2 models)
│   ├── model_index.py               # Index model structure
│   ├── defaults_parser.py           # Parse bddefaults.xml
│   ├── block_discoverer.py          # Discover blocks in model
│   ├── input_validator.py           # Validate input files
│   ├── output_truncator.py          # Truncate large outputs
│   ├── loop_detector.py             # Detect agentic doom loops (5 types)
│   └── logger.py                    # Logging config
│
├── skills/                          # Agent instructions (SKILL.md format)
│   ├── rule-analyzer/SKILL.md       # Agent 0
│   ├── data-reader/SKILL.md         # Agent 1
│   ├── diff-analyzer/SKILL.md       # Agent 1.5
│   ├── code-generator/SKILL.md      # Agent 2
│   ├── validator/SKILL.md           # Agent 3
│   ├── bug-fixer/SKILL.md           # Agent 4
│   └── model-inspector/SKILL.md     # Agent 5
│
├── data/                            # Dữ liệu đầu vào
│   ├── model.slx                    # File model TargetLink (READ-ONLY)
│   ├── blocks.json                  # Từ điển block
│   ├── rules.json                   # Luật cần kiểm tra
│   ├── expected_results.json        # Test case kết quả mong đợi
│   ├── input.json                   # Wrapper: model + blocks + rules
│   └── validate.json                # Wrapper: expected_results
│
├── generated_checks/                # Code Python sinh ra (auto-generated)
├── reports/                         # Báo cáo kết quả (auto-generated)
├── tests/                           # Unit + integration tests
│   ├── test_exploration_cache.py
│   ├── test_loop_detector.py
│   ├── test_model_differ.py
│   ├── test_model_factory.py
│   └── test_pipeline_integration.py
│
└── docs/                            # Tài liệu
    ├── architecture.md
    ├── agents_detail.md
    ├── coding_guide.md
    └── agent_io_spec.md
```

## Kiến trúc Pipeline

Hệ thống gồm **7 Agents** hoạt động theo pipeline:

1. **Agent 0 (Rule Analyzer)**: Đọc file luật (text) → Trích xuất block cần tìm, config cần check, và điều kiện.
2. **Agent 1 (Data Reader)**: Tìm kiếm block trong từ điển JSON (rapidfuzz, không LLM) → Phân tích description.
3. **Agent 1.5 (Diff Analyzer)** *(tuỳ chọn)*: So sánh 2 version model → Phát hiện config thay đổi → Cung cấp ground truth cho Agent 2 & 5.
4. **Agent 2 (Code Generator)**: Đọc XML tree thực tế qua tools → Sinh Python code check rule. **Agentic** — tự gọi 5-15 tools.
5. **Agent 3 (Validator)**: Chạy code sandbox → So sánh kết quả với test case. **Pure Python, không LLM.**
6. **Agent 4 (Bug Fixer)**: Nếu code lỗi Runtime/Syntax → Đọc traceback → Sửa code.
7. **Agent 5 (Inspector)**: Nếu kết quả sai → Điều tra sâu XML → Viết lại code. **Agentic** — tự gọi 8-20 tools.

**Context & Memory Flow:**
- Agent 2 → Agent 5: exploration_summary (những gì Agent 2 đã khám phá)
- Agent 5 retry N → retry N+1: previous_findings (tích lũy qua các vòng)
- Rule 1 → Rule 2+: cross-rule cache (hierarchy, blocks, configs)
- Agent 1.5 → Agent 2 & 5: config_discovery (ground truth từ diff)

*Chi tiết kiến trúc có tại `docs/architecture.md`.*

## Setup & Cài đặt

Yêu cầu: **Python 3.11+**

```bash
# 1. Clone repository & tạo virtual environment
python -m venv venv
# Windows: venv\Scripts\activate
# Mac/Linux: source venv/bin/activate

# 2. Cài đặt dependencies
pip install -r requirements.txt
```

### Chọn LLM Provider

Hệ thống hỗ trợ 2 provider, chuyển đổi qua biến `LLM_PROVIDER` trong `.env`:

#### Option A: Google Gemini (Vertex AI) — Cloud

```env
LLM_PROVIDER=gemini
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_GENAI_USE_VERTEXAI=true
GEMINI_MODEL=gemini-2.0-flash-001
```

Xác thực:
```bash
gcloud auth application-default login
```

> **Lưu ý**: Dùng **Vertex AI** (IAM-based), KHÔNG dùng Gemini API key.
> GCP project cần bật API `aiplatform.googleapis.com`.

#### Option B: Ollama — Local (chạy offline, không cần API key)

```bash
# 1. Cài Ollama: https://ollama.com
# 2. Pull model hỗ trợ tool calling
ollama pull qwen2.5:14b      # Model chính (~8GB RAM)
ollama pull qwen2.5:7b       # Model nhỏ cho agents đơn giản (~4GB RAM)
```

```env
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5:14b
OLLAMA_HOST=http://localhost:11434
OLLAMA_SMALL_MODEL=qwen2.5:7b
```

**Models Ollama hỗ trợ tool calling tốt:**
| Model | RAM | Ghi chú |
|-------|-----|---------|
| `qwen2.5:14b` | ~8GB | Khuyến nghị — cân bằng chất lượng/tốc độ |
| `qwen2.5:32b` | ~18GB | Chất lượng cao hơn |
| `qwen2.5:7b` | ~4GB | Dùng làm small model cho Agent 0, 1, 1.5 |
| `llama3.1:8b` | ~5GB | Alternative |
| `mistral-nemo` | ~4GB | Nhẹ nhất |

> **Small model**: Khi dùng Ollama, set `OLLAMA_SMALL_MODEL` để Agent 0, 1, 1.5 dùng model nhỏ hơn — tiết kiệm RAM.
> Bỏ trống = tất cả agents dùng chung `OLLAMA_MODEL`.

### File `.env` đầy đủ

```env
# ── LLM Provider ("gemini" hoặc "ollama") ──
LLM_PROVIDER=gemini

# ── Google Cloud Vertex AI (khi LLM_PROVIDER=gemini) ──
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_GENAI_USE_VERTEXAI=true
GEMINI_MODEL=gemini-2.0-flash-001

# ── Ollama (khi LLM_PROVIDER=ollama) ──
OLLAMA_MODEL=qwen2.5:14b
OLLAMA_HOST=http://localhost:11434
OLLAMA_SMALL_MODEL=qwen2.5:7b

# ── Pipeline ──
MAX_RETRY_AGENT4=3
MAX_RETRY_AGENT5=3
SANDBOX_TIMEOUT=30
```

### `requirements.txt`

```
agno>=1.1.13
google-genai>=1.0.0
ollama>=0.4.0
pydantic>=2.0
pydantic-settings>=2.0
lxml>=5.0
rapidfuzz>=3.0
python-dotenv>=1.0
```

> `agno>=1.1.13` bắt buộc — phiên bản cũ hơn có bug với Ollama tool calling.

## Hướng dẫn sử dụng

### Cách 1: Wrapper files (khuyến nghị)

```bash
python main.py --input data/input.json --validate data/validate.json
```

### Cách 2: Args riêng lẻ

```bash
python main.py --model data/model.slx --blocks data/blocks.json \
               --rules data/rules.json --expected data/expected_results.json
```

### Diff-based Config Discovery (tuỳ chọn)

So sánh model trước/sau để phát hiện config thay đổi — cung cấp ground truth cho Agent 2 & 5:

```bash
# Chạy pipeline với diff
python main.py --input data/input.json --validate data/validate.json \
               --model-before data/model_before.slx

# Chỉ xem diff, không chạy pipeline
python main.py --input data/input.json --validate data/validate.json \
               --model-before data/model_before.slx --diff-only
```

### CLI Options

| Option | Mô tả |
|--------|--------|
| `--input` | File input bundle (chứa model, blocks, rules) |
| `--validate` | File validation bundle (chứa expected_results) |
| `--model` | File model TargetLink (.slx) |
| `--blocks` | Từ điển block (blocks.json) |
| `--rules` | Luật cần kiểm tra (rules.json) |
| `--expected` | Test case kết quả mong đợi |
| `--model-before` | Model trước khi sửa (cho diff-based discovery) |
| `--diff-only` | Chỉ chạy diff, không chạy pipeline |
| `--output` | File output báo cáo JSON |
| `--log-level` | DEBUG, INFO, WARNING, ERROR |

## Định dạng File Đầu Vào

### `blocks.json` — Từ điển Block
```json
[
  {
    "name_ui": "Inport",
    "name_xml": "TL_Inport",
    "description": "Block nhận tín hiệu đầu vào. Config 'OutDataTypeStr' nằm ở thẻ <P Name='OutDataTypeStr'>. Giá trị mặc định: 'Inherit: auto'."
  }
]
```

### `rules.json` — Luật kiểm tra
```json
[
  {
    "rule_id": "R001",
    "description": "Tất cả khối Gain phải set SaturateOnIntegerOverflow = on"
  }
]
```

### `expected_results.json` — Test case kết quả mong đợi
```json
[
  {
    "rule_id": "R001",
    "expected_total_blocks": 19,
    "expected_pass": 18,
    "expected_fail": 1,
    "fail_details": [
      {"block_path": "model4_CcodeGeneration/Gain7", "actual_value": "off"}
    ]
  }
]
```

## Giới hạn đã biết (Known Limitations)

| Giới hạn | Mô tả |
|----------|-------|
| **Kích thước SLX** | File model > 500MB có thể gây chậm khi parse XML in-memory |
| **Retry tối đa** | Agent 4 và Agent 5 mỗi agent tối đa 3 lần retry |
| **LLM hallucination** | Code sinh ra có thể sai XPath nếu Description trong `blocks.json` mô tả không chính xác |
| **Nested SubSystem** | Model có SubSystem lồng > 10 cấp có thể cần Agent 5 nhiều vòng inspect |
| **Ollama tool calling** | Yêu cầu `agno>=1.1.13`. Chất lượng tool calling phụ thuộc model — `qwen2.5:14b` cho kết quả tốt nhất |

## Chạy Tests

```bash
pytest tests/ -v
```

## Tài liệu chi tiết

- [Kiến trúc hệ thống](docs/architecture.md) — Tech stack, data flow, error handling, context/memory design
- [Chi tiết kỹ thuật Agents](docs/agents_detail.md) — Pydantic schemas, tools, prompts cho từng Agent
- [Coding Guide](docs/coding_guide.md) — Quy tắc viết code, tách file, patterns
- [Agent I/O Spec](docs/agent_io_spec.md) — Input/Output format chi tiết
