"""
Tools cho việc đọc và truy vấn XML tree từ model TargetLink.
Tất cả operations đều READ-ONLY — không bao giờ ghi ngược lại file XML.

SLX sau khi unzip là 1 tree nhiều file XML, KHÔNG phải 1 file.
Agent phải dùng list_xml_files() trước, rồi khám phá từng file.
KHÔNG có tool đọc toàn bộ XML — agent phải explore từng phần.

Agents sử dụng: Agent 2 (Code Generator), Agent 5 (Inspector)
"""

import json
import re
from pathlib import Path
from lxml import etree
from agno.tools import Toolkit


class XmlToolkit(Toolkit):
    """Cung cấp khả năng khám phá XML tree cho Agent.

    Model TargetLink (.slx) sau khi unzip chứa NHIỀU file XML.
    Agent dùng list_xml_files() trước, rồi chọn file để khám phá.
    Tất cả tools đều READ-ONLY. XML tree được cache per-file.
    """

    def __init__(self, model_dir: str):
        super().__init__(name="xml_tools")
        self.model_dir = model_dir
        self._tree_cache: dict[str, etree._ElementTree] = {}

        self.register(self.list_xml_files)
        self.register(self.read_xml_structure)
        self.register(self.test_xpath_query)
        self.register(self.deep_search_xml_text)
        self.register(self.read_parent_nodes)

    def _get_tree(self, xml_file: str) -> etree._ElementTree:
        """Lazy load và cache XML tree cho từng file."""
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
        model_path = Path(self.model_dir)
        xml_files = sorted(model_path.rglob("*.xml"))

        results = []
        for xml_file in xml_files:
            rel_path = str(xml_file.relative_to(model_path)).replace("\\", "/")
            size_kb = round(xml_file.stat().st_size / 1024, 1)

            # Đọc root tag nhanh (không parse toàn bộ)
            root_tag = "?"
            children_count = 0
            try:
                tree = etree.parse(str(xml_file))
                root = tree.getroot()
                root_tag = root.tag
                children_count = len(root)
            except Exception:
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
        return summary + json.dumps(results, indent=2, ensure_ascii=False)

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
        return summary + json.dumps(results, indent=2, ensure_ascii=False)

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

        return f"[{xml_file}] Tìm thấy {len(results)} matches:\n" + json.dumps(results, indent=2, ensure_ascii=False)

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
        return summary + json.dumps(chain, indent=2, ensure_ascii=False)
