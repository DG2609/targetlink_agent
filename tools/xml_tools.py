"""
Tools cho việc đọc và truy vấn XML tree từ model TargetLink.
Tất cả operations đều READ-ONLY — không bao giờ ghi ngược lại file XML.

SLX sau khi unzip là 1 tree nhiều file XML, KHÔNG phải 1 file.
Agent phải dùng list_xml_files() trước, rồi khám phá từng file.
KHÔNG có tool đọc toàn bộ XML — agent phải explore từng phần.

Tích hợp:
  - LoopDetector: chặn agent gọi tool lặp liên tiếp cùng args
  - truncate_output: cắt output lớn để bảo vệ context window
  - shared_cache: chia sẻ parsed XML giữa Agent 2 & 5

Agents sử dụng: Agent 2 (Code Generator), Agent 5 (Inspector)
"""

import json
import logging
import re
import threading
from pathlib import Path

logger = logging.getLogger(__name__)
from lxml import etree
from agno.tools import Toolkit

from utils.loop_detector import LoopDetector
from utils.model_index import ModelIndex
from utils.output_truncator import truncate_output
from utils.block_discoverer import discover_blocks


class XmlToolkit(Toolkit):
    """Cung cấp khả năng khám phá XML tree cho Agent.

    Model TargetLink (.slx) sau khi unzip chứa NHIỀU file XML.
    Agent dùng list_xml_files() trước, rồi chọn file để khám phá.
    Tất cả tools đều READ-ONLY. XML tree được cache per-file.

    Features:
      - Loop detection: chặn agent xoay vòng gọi cùng tool/args
      - Output truncation: bảo vệ context window LLM
      - Shared cache: truyền shared_cache để Agent 2 & 5 chia sẻ parsed XML
    """

    def __init__(
        self,
        model_dir: str,
        shared_cache: dict[str, etree._ElementTree] | None = None,
    ):
        super().__init__(name="xml_tools")
        self.model_dir = model_dir
        self._tree_cache: dict[str, etree._ElementTree] = (
            shared_cache if shared_cache is not None else {}
        )
        self._cache_lock = threading.Lock()
        self._loop_detector = LoopDetector(max_repeats=3)
        self._model_index = ModelIndex(
            model_dir=model_dir, xml_cache=self._tree_cache,
        )

        self.register(self.list_xml_files)
        self.register(self.read_xml_structure)
        self.register(self.test_xpath_query)
        self.register(self.deep_search_xml_text)
        self.register(self.read_parent_nodes)
        self.register(self.build_model_hierarchy)
        self.register(self.find_blocks_recursive)
        self.register(self.query_config)
        self.register(self.trace_connections)
        self.register(self.read_raw_block_config)
        self.register(self.list_all_configs)
        self.register(self.trace_cross_subsystem)
        self.register(self.auto_discover_blocks)
        self.register(self.list_all_block_types)
        self.register(self.find_config_locations)

    def reset_loop_detector(self) -> None:
        """Reset loop detector — gọi khi chuyển sang agent khác dùng cùng toolkit."""
        self._loop_detector.reset()

    def _get_tree(self, xml_file: str) -> etree._ElementTree:
        """Lazy load và cache XML tree cho từng file. Thread-safe."""
        if xml_file not in self._tree_cache:
            with self._cache_lock:
                # Double-check sau khi lấy lock (tránh parse trùng)
                if xml_file not in self._tree_cache:
                    full_path = Path(self.model_dir) / xml_file
                    if not full_path.exists():
                        raise FileNotFoundError(f"File không tồn tại trong model tree: {xml_file}")
                    self._tree_cache[xml_file] = etree.parse(str(full_path))
        return self._tree_cache[xml_file]

    def _safe_xml_file(self, xml_file: str) -> str:
        """Validate xml_file không escape ra ngoài model_dir."""
        resolved = (Path(self.model_dir) / xml_file).resolve()
        model_resolved = Path(self.model_dir).resolve()
        if not str(resolved).startswith(str(model_resolved)):
            raise ValueError(f"Path traversal detected: {xml_file}")
        return xml_file

    # ──────────────────────────────────────────────
    # Tool 0: list_xml_files (GỌI ĐẦU TIÊN)
    # ──────────────────────────────────────────────

    def list_xml_files(self) -> str:
        """Liệt kê tất cả file XML có trong model tree.
        GỌI TOOL NÀY ĐẦU TIÊN khi bắt đầu khám phá model.

        SLX sau khi unzip chứa nhiều file XML (blockdiagram.xml, configSet, metadata...).
        Bạn cần xem danh sách này trước để biết file nào chứa thông tin cần tìm.

        Returns:
            JSON array các file XML, mỗi entry gồm: path (relative), size_kb, root_tag, children_count.
        """
        # Reset loop detector — agent mới bắt đầu khám phá
        self._loop_detector.reset()

        model_path = Path(self.model_dir)
        xml_files = sorted(model_path.rglob("*.xml"))

        results = []
        for xml_file in xml_files:
            rel_path = str(xml_file.relative_to(model_path)).replace("\\", "/")
            size_kb = round(xml_file.stat().st_size / 1024, 1)

            root_tag = "?"
            children_count = 0
            try:
                # Dùng _get_tree() để cache — tránh parse lại khi agent gọi tool khác
                tree = self._get_tree(rel_path)
                root = tree.getroot()
                root_tag = root.tag
                children_count = len(root)
            except Exception as e:
                logger.warning(f"list_xml_files: không parse {rel_path}: {e}")
                root_tag = "PARSE_ERROR"

            results.append({
                "path": rel_path,
                "size_kb": size_kb,
                "root_tag": root_tag,
                "children_count": children_count,
            })

        if not results:
            return "Không tìm thấy file XML nào trong model tree."

        return f"Model tree có {len(results)} file XML:\n" + json.dumps(results, indent=2, ensure_ascii=False)

    # ──────────────────────────────────────────────
    # Tool 1: read_xml_structure
    # ──────────────────────────────────────────────

    def read_xml_structure(self, xml_file: str, xpath: str) -> str:
        """Đọc cấu trúc XML nodes tại XPath trong 1 file XML cụ thể. READ-ONLY.

        Dùng khi cần xem block thực tế trông như thế nào trong model trước khi viết code.
        Trả về tối đa 10 nodes, mỗi node kèm tag, attributes, và 20 children đầu tiên.

        Args:
            xml_file: Đường dẫn relative tới file XML trong model tree.
                      VD: "simulink/blockdiagram.xml"
            xpath: Biểu thức XPath để tìm nodes.
                   VD: ".//Block[@BlockType='TL_Inport']"

        Returns:
            JSON mô tả các nodes tìm thấy (tag, attribs, children).
        """
        # Loop detection
        loop_hint = self._loop_detector.check(
            "read_xml_structure", xml_file=xml_file, xpath=xpath
        )
        if loop_hint:
            return loop_hint

        xml_file = self._safe_xml_file(xml_file)
        tree = self._get_tree(xml_file)

        try:
            nodes = tree.xpath(xpath)
        except etree.XPathError as e:
            return f"XPath syntax error: {e}"

        if not nodes:
            return f"Không tìm thấy node nào match XPath: {xpath} (trong {xml_file})"

        results = []
        for node in nodes[:10]:
            if not hasattr(node, "tag"):
                results.append({"type": "text_node", "value": str(node)[:200]})
                continue

            info = {
                "tag": node.tag,
                "attribs": dict(node.attrib),
                "text": (node.text or "").strip()[:100] or None,
                "children_count": len(node),
                "children": [
                    {
                        "tag": child.tag,
                        "attribs": dict(child.attrib),
                        "text": (child.text or "").strip()[:100] or None,
                    }
                    for child in node[:20]
                ],
            }
            results.append(info)

        summary = f"[{xml_file}] Tìm thấy {len(nodes)} nodes (hiển thị {len(results)}):\n"
        return truncate_output(
            summary + json.dumps(results, indent=2, ensure_ascii=False)
        )

    # ──────────────────────────────────────────────
    # Tool 2: test_xpath_query
    # ──────────────────────────────────────────────

    def test_xpath_query(self, xml_file: str, xpath: str) -> str:
        """Chạy thử câu lệnh XPath trên 1 file XML và trả về danh sách kết quả.
        Dùng để VERIFY XPath đúng trước khi viết vào code — đừng đoán, hãy test.

        Args:
            xml_file: Đường dẫn relative tới file XML.
                      VD: "simulink/blockdiagram.xml"
            xpath: Biểu thức XPath cần test.
                   VD: ".//Block[@BlockType='TL_Inport']/P[@Name='OutDataTypeStr']"

        Returns:
            JSON array tối đa 20 kết quả.
        """
        # Loop detection
        loop_hint = self._loop_detector.check(
            "test_xpath_query", xml_file=xml_file, xpath=xpath
        )
        if loop_hint:
            return loop_hint

        xml_file = self._safe_xml_file(xml_file)
        tree = self._get_tree(xml_file)

        try:
            nodes = tree.xpath(xpath)
        except etree.XPathError as e:
            return f"XPath syntax error: {e}"

        if not nodes:
            return f"XPath trả về 0 kết quả: {xpath} (trong {xml_file})"

        results = []
        for node in nodes[:20]:
            if isinstance(node, str):
                results.append({"type": "string", "value": node})
            elif isinstance(node, (int, float, bool)):
                results.append({"type": "number", "value": node})
            elif hasattr(node, "tag"):
                results.append({
                    "type": "element",
                    "tag": node.tag,
                    "text": (node.text or "").strip()[:200] or None,
                    "attribs": dict(node.attrib),
                })
            else:
                results.append({"type": "other", "value": str(node)[:200]})

        summary = f"[{xml_file}] XPath match {len(nodes)} kết quả (hiển thị {len(results)}):\n"
        return truncate_output(
            summary + json.dumps(results, indent=2, ensure_ascii=False)
        )

    # ──────────────────────────────────────────────
    # Tool 3: deep_search_xml_text
    # ──────────────────────────────────────────────

    def deep_search_xml_text(self, xml_file: str, regex_pattern: str) -> str:
        """Tìm kiếm Regex trên nội dung 1 file XML — cả text lẫn attribute values.
        Hữu ích khi cần tìm config bị ẩn, block bị đổi tên, hoặc không biết XPath.

        Trả về tối đa 50 kết quả, mỗi entry kèm XPath path để truy cập lại node.

        Args:
            xml_file: Đường dẫn relative tới file XML.
                      VD: "simulink/blockdiagram.xml"
            regex_pattern: Regex pattern (case-insensitive).
                           VD: "TL_Inport|Inport", "DataType.*int"

        Returns:
            JSON array các nodes match. Mỗi entry gồm: match_in, tag, value, xpath.
        """
        # Loop detection
        loop_hint = self._loop_detector.check(
            "deep_search_xml_text", xml_file=xml_file, regex_pattern=regex_pattern
        )
        if loop_hint:
            return loop_hint

        xml_file = self._safe_xml_file(xml_file)
        tree = self._get_tree(xml_file)
        root = tree.getroot()

        try:
            pattern = re.compile(regex_pattern, re.IGNORECASE)
        except re.error as e:
            return f"Regex syntax error: {e}"

        results = []

        for elem in root.iter():
            # Search trong text content
            if elem.text and pattern.search(elem.text):
                results.append({
                    "match_in": "text",
                    "tag": elem.tag,
                    "value": elem.text.strip()[:200],
                    "xpath": tree.getpath(elem),
                })

            # Search trong tail text
            if elem.tail and pattern.search(elem.tail):
                results.append({
                    "match_in": "tail",
                    "tag": elem.tag,
                    "value": elem.tail.strip()[:200],
                    "xpath": tree.getpath(elem),
                })

            # Search trong attribute values
            for attr_name, attr_val in elem.attrib.items():
                if pattern.search(attr_val):
                    results.append({
                        "match_in": f"attrib[@{attr_name}]",
                        "tag": elem.tag,
                        "value": attr_val[:200],
                        "xpath": tree.getpath(elem),
                    })

            if len(results) >= 50:
                results.append({"warning": "Đã đạt giới hạn 50 kết quả, có thể còn nhiều hơn."})
                break

        if not results:
            return f"Không tìm thấy gì match regex: {regex_pattern} (trong {xml_file})"

        return truncate_output(
            f"[{xml_file}] Tìm thấy {len(results)} matches:\n"
            + json.dumps(results, indent=2, ensure_ascii=False)
        )

    # ──────────────────────────────────────────────
    # Tool 4: read_parent_nodes
    # ──────────────────────────────────────────────

    def read_parent_nodes(self, xml_file: str, xpath: str) -> str:
        """Đọc chuỗi thẻ cha (ancestry chain) từ root xuống tới node tại XPath.
        Hữu ích để xem block có bị bọc trong SubSystem, Mode đặc biệt, hoặc Mask không.

        Args:
            xml_file: Đường dẫn relative tới file XML.
                      VD: "simulink/blockdiagram.xml"
            xpath: XPath tới node cần xem ancestry.
                   VD: "(.//Block[@BlockType='TL_Inport'])[1]"

        Returns:
            JSON array từ root → target node. Mỗi entry gồm: depth, tag, attribs.
        """
        # Loop detection
        loop_hint = self._loop_detector.check(
            "read_parent_nodes", xml_file=xml_file, xpath=xpath
        )
        if loop_hint:
            return loop_hint

        xml_file = self._safe_xml_file(xml_file)
        tree = self._get_tree(xml_file)

        try:
            nodes = tree.xpath(xpath)
        except etree.XPathError as e:
            return f"XPath syntax error: {e}"

        if not nodes:
            return f"Không tìm thấy node tại: {xpath} (trong {xml_file})"

        # Lấy node đầu tiên
        node = nodes[0]
        if not hasattr(node, "tag"):
            return f"Node tại XPath không phải element (có thể là text/attribute): {type(node)}"

        # Đi ngược lên cây
        chain = []
        current = node
        while current is not None:
            chain.append({
                "tag": current.tag,
                "attribs": dict(current.attrib),
            })
            current = current.getparent()

        # Reverse: root → target
        chain.reverse()
        for i, item in enumerate(chain):
            item["depth"] = i

        node_path = tree.getpath(node)
        summary = f"[{xml_file}] Ancestry chain cho node tại {node_path} ({len(chain)} levels):\n"
        return truncate_output(
            summary + json.dumps(chain, indent=2, ensure_ascii=False)
        )

    # ══════════════════════════════════════════════
    # Tools mới: Model-level (cross-file, hierarchy-aware)
    # ══════════════════════════════════════════════

    def build_model_hierarchy(self) -> str:
        """Xem cây subsystem của model: Root → SubSystem → Sub-SubSystem...

        Dùng ĐẦU TIÊN (cùng list_xml_files) để hiểu tổng quan cấu trúc model.
        Mỗi node cho biết: tên subsystem, file chứa, số blocks theo type.

        Returns:
            JSON cây subsystem kèm blocks_summary per level.
        """
        hierarchy = self._model_index.build_hierarchy()
        return truncate_output(
            "Model hierarchy:\n"
            + json.dumps(hierarchy, indent=2, ensure_ascii=False)
        )

    def find_blocks_recursive(self, block_type: str) -> str:
        """Tìm TẤT CẢ blocks of type xuyên mọi subsystem layers.

        Tìm cả BlockType lẫn MaskType (TargetLink blocks).
        Trả về kèm full subsystem path và tất cả configs.

        Args:
            block_type: Loại block cần tìm.
                        VD: "Gain", "Abs", "Sum", "Inport", "SubSystem"

        Returns:
            JSON list blocks kèm: name, sid, path, system_file, configs.
        """
        blocks = self._model_index.find_blocks_recursive(block_type)
        if not blocks:
            return f"Không tìm thấy block nào có type '{block_type}' trong model."
        return truncate_output(
            f"Tìm thấy {len(blocks)} blocks type='{block_type}':\n"
            + json.dumps(blocks, indent=2, ensure_ascii=False)
        )

    def query_config(self, block_type: str, config_name: str) -> str:
        """Rút CHỈ 1 config cụ thể từ tất cả blocks of type — gọn, targeted.

        Nếu config vắng trong block XML → tra bddefaults.xml để lấy default value.
        KHÔNG bỏ sót — scan tất cả subsystem layers.

        Dùng khi rule chỉ cần check 1 config trên 1 loại block.

        Args:
            block_type: VD: "Gain"
            config_name: VD: "SaturateOnIntegerOverflow"

        Returns:
            JSON list: [{block_name, sid, path, value, source:"explicit"|"default"|"not_found"}]
        """
        results = self._model_index.query_config(block_type, config_name)
        if not results:
            return f"Không tìm thấy block nào type='{block_type}' trong model."
        return truncate_output(
            f"Config '{config_name}' trên {len(results)} {block_type} blocks:\n"
            + json.dumps(results, indent=2, ensure_ascii=False)
        )

    def trace_connections(self, block_sid: str) -> str:
        """Trace signal connections (incoming/outgoing) cho 1 block by SID.

        Tìm block trong toàn model, parse Line elements trong cùng system file.
        Nếu endpoint là Inport/Outport → đó là cross-subsystem boundary.

        Dùng khi rule cần kiểm tra kết nối giữa blocks, hoặc trace signal flow.

        Args:
            block_sid: SID của block cần trace. VD: "68"

        Returns:
            JSON: {block info, incoming connections, outgoing connections}
        """
        result = self._model_index.trace_connections(block_sid)
        if "error" in result:
            return result["error"]
        return truncate_output(json.dumps(result, indent=2, ensure_ascii=False))

    def auto_discover_blocks(self, block_keyword: str) -> str:
        """Tự scan toàn bộ model → tìm TẤT CẢ blocks matching keyword.

        Scan tất cả system_*.xml files, match BlockType và MaskType (case-insensitive).
        Trả về dict keyed by SID kèm thông tin block, configs count, sample configs.

        Dùng khi cần biết model chứa bao nhiêu blocks loại nào, ở đâu, trước khi viết code.
        Khác find_blocks_recursive: tool này KHÔNG cần biết exact BlockType, chỉ cần keyword.

        Args:
            block_keyword: Keyword tìm kiếm (case-insensitive).
                           VD: "Gain", "Inport", "TL_", "Sum"

        Returns:
            JSON dict keyed by SID: {name, block_type, mask_type, system_file, path, configs_count}
        """
        results = discover_blocks(self.model_dir, block_keyword)
        if not results:
            return f"Không tìm thấy block nào match keyword '{block_keyword}' trong model."
        return truncate_output(
            f"Tìm thấy {len(results)} blocks match '{block_keyword}':\n"
            + json.dumps(results, indent=2, ensure_ascii=False)
        )

    def find_config_locations(self, config_name: str) -> str:
        """Reverse lookup: cho config name → tìm TẤT CẢ block types có config đó.

        Scan 2 nguồn:
          1. bddefaults.xml — block types nào có config này làm default
          2. Model XML — blocks nào EXPLICITLY set config này

        Dùng khi:
        - Rule chỉ nói về config mà KHÔNG nói rõ block nào
        - Cần biết config nằm ở bao nhiêu block types
        - Cần xác định scope check (check 1 block type hay tất cả?)

        Args:
            config_name: Tên config cần tra.
                         VD: "SaturateOnIntegerOverflow", "OutDataTypeStr"

        Returns:
            JSON: {
                defaults: [{block_type, default_value}],
                explicit: [{block_type, block_name, value, system_file}],
                all_block_types: ["Gain", "Abs", "Sum", ...]
            }
        """
        from utils.block_finder import get_block_identity
        from utils.defaults_parser import parse_bddefaults

        # 1. Từ bddefaults.xml
        defaults_map = parse_bddefaults(self.model_dir)
        defaults_results = []
        for block_type, configs in sorted(defaults_map.items()):
            if config_name in configs:
                defaults_results.append({
                    "block_type": block_type,
                    "default_value": configs[config_name],
                })

        # 2. Từ model XML (explicit)
        explicit_results = []
        systems_dir = Path(self.model_dir) / "simulink" / "systems"
        if systems_dir.exists():
            for xml_file in sorted(systems_dir.glob("system_*.xml")):
                try:
                    rel_path = str(xml_file.relative_to(Path(self.model_dir))).replace("\\", "/")
                    tree = self._get_tree(rel_path)
                    root = tree.getroot()
                except Exception as e:
                    logger.warning(f"find_config_locations: không parse {xml_file.name}: {e}")
                    continue

                for block in root.findall("Block"):
                    # Check direct <P>
                    node = block.find(f"P[@Name='{config_name}']")
                    found_in = "direct_P"

                    # Check InstanceData/<P>
                    if node is None:
                        inst = block.find("InstanceData")
                        if inst is not None:
                            node = inst.find(f"P[@Name='{config_name}']")
                            found_in = "InstanceData"

                    if node is not None:
                        identity = get_block_identity(block)
                        explicit_results.append({
                            "block_type": identity,
                            "block_name": block.get("Name", "Unknown"),
                            "value": (node.text or "").strip(),
                            "location": found_in,
                            "system_file": rel_path,
                        })

        # Tổng hợp tất cả block types
        all_types = set()
        for d in defaults_results:
            all_types.add(d["block_type"])
        for e in explicit_results:
            all_types.add(e["block_type"])

        result = {
            "config_name": config_name,
            "in_defaults": defaults_results,
            "in_model_explicit": explicit_results[:30],  # cap tránh quá lớn
            "explicit_total": len(explicit_results),
            "all_block_types_with_config": sorted(all_types),
            "total_block_types": len(all_types),
        }

        if not all_types:
            return f"Config '{config_name}' KHÔNG tìm thấy trong model (cả defaults lẫn explicit)."

        return truncate_output(
            f"Config '{config_name}' tìm thấy ở {len(all_types)} block types:\n"
            + json.dumps(result, indent=2, ensure_ascii=False)
        )

    def list_all_block_types(self) -> str:
        """Liệt kê TẤT CẢ block types có trong model — không cần biết trước keyword.

        Scan toàn bộ system_*.xml files, trả về mỗi block type kèm:
        - identity thật (MaskType > SourceType > BlockType)
        - raw BlockType (để biết dạng XML)
        - count (số lượng)

        Dùng khi:
        - Rule cấm/yêu cầu dùng block types cụ thể
        - Cần biết model có những blocks gì trước khi gen code
        - Cần phân biệt native vs Reference vs Masked blocks

        Returns:
            JSON list: [{identity, raw_block_type, count, sample_names}]
        """
        from utils.block_finder import get_block_identity

        systems_dir = Path(self.model_dir) / "simulink" / "systems"
        if not systems_dir.exists():
            return "Không tìm thấy thư mục simulink/systems/"

        # {identity: {raw_types: set, count: int, names: list}}
        type_map: dict[str, dict] = {}

        for xml_file in sorted(systems_dir.glob("system_*.xml")):
            try:
                rel_path = str(xml_file.relative_to(Path(self.model_dir))).replace("\\", "/")
                tree = self._get_tree(rel_path)
                root = tree.getroot()
            except Exception as e:
                logger.warning(f"list_all_block_types: không parse {xml_file.name}: {e}")
                continue

            for block in root.findall("Block"):
                identity = get_block_identity(block)
                raw_bt = block.get("BlockType", "Unknown")
                name = block.get("Name", "Unknown")

                if identity not in type_map:
                    type_map[identity] = {
                        "raw_types": set(),
                        "count": 0,
                        "names": [],
                    }
                type_map[identity]["raw_types"].add(raw_bt)
                type_map[identity]["count"] += 1
                if len(type_map[identity]["names"]) < 3:
                    type_map[identity]["names"].append(name)

        if not type_map:
            return "Model không chứa block nào."

        results = []
        for identity, info in sorted(type_map.items()):
            results.append({
                "identity": identity,
                "raw_block_type": sorted(info["raw_types"]),
                "count": info["count"],
                "sample_names": info["names"],
            })

        return truncate_output(
            f"Model có {len(results)} block types ({sum(r['count'] for r in results)} blocks total):\n"
            + json.dumps(results, indent=2, ensure_ascii=False)
        )

    def trace_cross_subsystem(
        self, block_sid: str, direction: str = "both", max_depth: int = 5,
    ) -> str:
        """Trace signal connections XUYÊN subsystem boundaries.

        Khi gặp Inport/Outport → tự follow vào/ra subsystem tương ứng.
        Dùng khi rule cần trace signal flow xuyên qua nhiều levels.

        Args:
            block_sid: SID block bắt đầu trace. VD: "68"
            direction: "incoming", "outgoing", hoặc "both" (mặc định "both")
            max_depth: Số bước tối đa cross subsystem (mặc định 5, tránh loop vô hạn)

        Returns:
            JSON: {block info, trace steps kèm crossing info}
        """
        result = self._model_index.trace_connections_cross_subsystem(
            block_sid, direction=direction, max_depth=max_depth,
        )
        if "error" in result:
            return result["error"]
        return truncate_output(json.dumps(result, indent=2, ensure_ascii=False))

    def list_all_configs(self, block_sid: str) -> str:
        """Liệt kê TẤT CẢ configs của 1 block: explicit từ XML + defaults từ bddefaults.xml.

        Merge hai nguồn: defaults (cho BlockType) → override bởi giá trị explicit trong block.
        Hữu ích khi cần biết block có bao nhiêu configs, config nào bị override, config nào dùng default.

        Args:
            block_sid: SID của block cần xem. VD: "68"

        Returns:
            JSON: {name, type, sid, configs: {config_name: {value, source}}, total_configs}
        """
        result = self._model_index.get_block_all_configs(block_sid)
        if "error" in result:
            return result["error"]
        return truncate_output(json.dumps(result, indent=2, ensure_ascii=False))

    def read_raw_block_config(self, block_sid: str) -> str:
        """Đọc TOÀN BỘ config của 1 block — dùng khi ESCALATION.

        ⚠ Dùng khi đã retry nhiều lần vẫn sai, cần xem raw data.
        Output truncated tại 100KB / 2000 dòng (vẫn rất lớn, đủ cho hầu hết blocks).

        Trả về: tất cả <P> configs, InstanceData, và raw XML.

        Args:
            block_sid: SID của block. VD: "68"

        Returns:
            JSON: {name, type, sid, raw_configs, instance_data, raw_xml}
        """
        result = self._model_index.read_raw_block_config(block_sid)
        if "error" in result:
            return result["error"]
        raw_json = json.dumps(result, indent=2, ensure_ascii=False)
        return truncate_output(raw_json, max_chars=100_000, max_lines=2000)
