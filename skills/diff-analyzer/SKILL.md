---
name: diff-analyzer
description: Phân tích raw diff giữa 2 model versions → xác định chính xác config nằm ở đâu trong XML. Output structured ConfigDiscovery cho Agent 2 dùng trực tiếp.
---

# Diff Analyzer

Phân tích kết quả diff giữa 2 phiên bản model TargetLink → xác định ground truth cho config location.

Bạn nhận raw diff results (danh sách thay đổi XML giữa model before/after) và thông tin rule cần check.
Nhiệm vụ: **tổng quát hoá** từ thay đổi cụ thể trên 1-2 blocks → pattern áp dụng cho TẤT CẢ blocks cùng type.

## Input

Bạn nhận context gồm:
- `block_type`: BlockType cần check (VD: "Gain")
- `config_name`: Config cần check (VD: "SaturateOnIntegerOverflow")
- `block_mapping`: Thông tin block mapping từ Agent 1

Data được chia thành **2 PHẦN rõ ràng**:

### PART 1 — CODE GENERATION DATA
Dùng để xác định config nằm ở đâu, cách đọc, default value → Agent 2 viết code.

- **`CONFIG_LOCATIONS`**: JSON array — mỗi entry là 1 unique config location:
  ```json
  {
    "block_type": "Gain",
    "mask_type": "",
    "config_name": "SaturateOnIntegerOverflow",
    "location_type": "direct_P",
    "xpath": ".//Block[@SID='68']/P[@Name='SaturateOnIntegerOverflow']",
    "default_value": "off",
    "xpath_pattern": ".//Block[@BlockType='Gain']/P[@Name='SaturateOnIntegerOverflow']"
  }
  ```
  → Đã deduplicate + generalize XPath (SID → BlockType pattern).

- **`BLOCK_DEFAULTS_DICTIONARY`**: Dict tra cứu defaults từ bddefaults.xml:
  ```json
  {"Gain": {"SaturateOnIntegerOverflow": "off", "Gain": "1", ...}}
  ```
  → Nếu là TL block → ghi "không có defaults, suy luận từ diff context".

### PART 2 — VALIDATION DATA
Dùng để verify kết quả: block nào đổi, giá trị cũ/mới.

- **`CHANGED_BLOCKS`**: JSON array — chi tiết từng block bị thay đổi:
  ```json
  {
    "block_sid": "68",
    "block_name": "Gain1",
    "block_type": "Gain",
    "system_file": "simulink/systems/system_root.xml",
    "config_name": "SaturateOnIntegerOverflow",
    "old_value": "on",
    "new_value": null,
    "change_type": "removed"
  }
  ```
  → `new_value=null` nghĩa là config bị xoá → giá trị hiện tại = default.

- **`DIFF_SUMMARY`**: Tóm tắt: bao nhiêu blocks thay đổi cho block_type/config_name cụ thể.

## Output

Bạn output **ConfigDiscovery** structured object:

- **block_type**: BlockType hoặc MaskType mà rule cần check
- **mask_type**: Nếu block dùng MaskType (TL blocks), ghi MaskType ở đây
- **config_name**: Tên config cần check
- **location_type**: Config nằm ở ĐÂU trong XML:
  - `direct_P`: `<Block><P Name="ConfigName">value</P></Block>` — phổ biến nhất
  - `InstanceData`: `<Block><InstanceData><P Name="ConfigName">value</P></InstanceData></Block>` — Reference blocks
  - `MaskValueString`: pipe-separated trong `<P Name="MaskValueString">` — TargetLink masked blocks
- **xpath_pattern**: XPath TỔNG QUÁT (không chỉ cho 1 block cụ thể, mà cho TẤT CẢ blocks cùng type)
- **default_value**: Giá trị default khi config vắng trong XML
- **value_format**: Format giá trị (on/off, integer, string, fixdt(...))
- **notes**: Ghi chú quan trọng cho Agent 2

## Quy trình phân tích

### Bước 1: Xác định location_type

Từ raw diff, xem config thay đổi ở layer nào:
- Nếu diff hiện `[direct_P]` → config là thẻ `<P>` trực tiếp trong block
- Nếu diff hiện `[InstanceData]` → config nằm trong `<InstanceData>/<P>`
- Nếu diff hiện `[MaskValueString]` → config nằm trong chuỗi pipe-separated

### Bước 2: Tổng quát hoá XPath

Diff cho XPath cụ thể cho 1 block (VD: `.//Block[@SID='68']/P[@Name='X']`).
Bạn cần tổng quát thành pattern cho TẤT CẢ blocks cùng type:

- Direct P: `.//Block[@BlockType='{block_type}']/P[@Name='{config_name}']`
- InstanceData: `.//Block[@BlockType='{block_type}']/InstanceData/P[@Name='{config_name}']`
- MaskType blocks: `.//Block[P[@Name='MaskType' and text()='{mask_type}']]/P[@Name='{config_name}']`

### Bước 3: Xác định default value

**Quan trọng — 2 loại blocks:**

**Standard Simulink blocks** (Gain, Abs, Sum, Delay...):
- Diff có thể bao gồm `Default (from bddefaults.xml): value` — đây là ground truth
- Nếu không có, xem logic: config vắng trong XML = default
- Kết hợp với block_mapping.config_map_analysis để xác nhận

**TargetLink blocks** (MaskType = TL_Gain, TL_Abs...):
- bddefaults.xml KHÔNG có defaults cho TL blocks (TL blocks là SubSystem masked)
- TL defaults nằm trong TL library (dSPACE installation), không trong model
- Cách suy luận: nếu diff KHÔNG thay đổi config cho 1 số blocks cùng type
  → giá trị hiện tại của blocks đó CHÍNH LÀ default
- MaskValueString defaults: giá trị ban đầu khi drag block từ TL library vào model

**Chung:**
- Nếu diff cho thấy config thay đổi từ value A → value B:
  - Value trước khi sửa (old_value) CÓ THỂ là default (nếu user đổi từ default sang non-default)
  - Hoặc old_value là explicit value cũ
- Nếu không chắc chắn default → ghi trong notes: "default chưa xác định, cần Agent 2 verify"

### Bước 4: MaskValueString decode (nếu location_type = MaskValueString)

Khi config nằm trong MaskValueString:
- Raw diff sẽ hiện: `MaskValueString.ParamName: "old" → "new"`
- ParamName được map từ MaskNames (position-based)
- Ghi rõ trong notes: "Config nằm ở MaskValueString position N, MaskNames = ..."
- XPath pattern: dùng regex hoặc string search thay vì XPath trực tiếp

### Bước 5: Ghi notes đặc biệt

Ghi vào notes mọi thông tin hữu ích cho Agent 2:
- Nếu block dùng MaskType → ghi: "Block thực tế có BlockType='SubSystem', cần match bằng MaskType"
- Nếu config có nhiều formats → ghi: "Value có thể là 'on'/'off' hoặc '1'/'0'"
- Nếu config liên quan configs khác → ghi: "Config này chỉ visible khi Mode=X"

## Ví dụ

### Input:
```
block_type: Gain
config_name: SaturateOnIntegerOverflow
block_mapping: name_ui=Gain, config_map_analysis=direct match

DIFF_CHANGES_JSON:
[
  {
    "block_sid": "68",
    "block_name": "Gain1",
    "block_type": "Gain",
    "mask_type": "",
    "system_file": "simulink/systems/system_root.xml",
    "config_name": "SaturateOnIntegerOverflow",
    "old_value": "on",
    "new_value": "off",
    "default_value": "off",
    "location_type": "direct_P",
    "xpath": ".//Block[@SID='68']/P[@Name='SaturateOnIntegerOverflow']",
    "change_type": "modified"
  }
]

BLOCK_DEFAULTS_DICTIONARY (from bddefaults.xml):
{"Gain": {"SaturateOnIntegerOverflow": "off", "Gain": "1", "RndMeth": "Floor"}}
```

### Phân tích:
1. `location_type` = `direct_P` → config là `<P>` trực tiếp trong Block
2. `xpath` có pattern: `Block[@SID='...']/P[@Name='SaturateOnIntegerOverflow']` → generalize thành `Block[@BlockType='Gain']/P[@Name='...']`
3. `BLOCK_DEFAULTS_DICTIONARY` cho thấy default = `"off"` → khi config vắng trong XML = off
4. `mask_type` = empty → standard Simulink block, không phải TL

### Output (ConfigDiscovery):
```
block_type: Gain
mask_type: (empty)
config_name: SaturateOnIntegerOverflow
location_type: direct_P
xpath_pattern: .//Block[@BlockType='Gain']/P[@Name='SaturateOnIntegerOverflow']
default_value: off
value_format: on/off
notes: Config là direct <P> child của Block. Default "off" (từ bddefaults.xml). Cần scan TẤT CẢ system_*.xml files.
```
