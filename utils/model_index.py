"""
Pre-processed model index: hierarchy, block search, connections, config query.

Parse model 1 lần, query nhiều lần. Lazy loading + cache.
Giải quyết 3 vấn đề: hierarchy awareness, cross-subsystem search, targeted extraction.

Cấu trúc SLX (sau unzip):
  simulink/systems/system_root.xml     → root level blocks
  simulink/systems/system_N.xml        → subsystem content
  SubSystem block chứa <System Ref="system_N"/> → pointer tới file con
  Line elements: <P Name="Src">SID#out:1</P>, <P Name="Dst">SID#in:1</P>
"""

from pathlib import Path
from lxml import etree

from utils.defaults_parser import get_default_value


class ModelIndex:
    """Pre-processed model data: hierarchy, block index, connections.

    Dùng chung xml_cache với XmlToolkit để tránh parse lại.
    """

    def __init__(self, model_dir: str, xml_cache: dict | None = None):
        self.model_dir = model_dir
        self._xml_cache: dict[str, etree._ElementTree] = xml_cache if xml_cache is not None else {}
        self._hierarchy: dict | None = None

    # ──────────────────────────────────────────────
    # XML access (shared cache)
    # ──────────────────────────────────────────────

    def _get_tree(self, xml_file: str) -> etree._ElementTree:
        if xml_file not in self._xml_cache:
            full_path = Path(self.model_dir) / xml_file
            if not full_path.exists():
                raise FileNotFoundError(f"File không tồn tại: {xml_file}")
            self._xml_cache[xml_file] = etree.parse(str(full_path))
        return self._xml_cache[xml_file]

    # ══════════════════════════════════════════════
    # 1. HIERARCHY
    # ══════════════════════════════════════════════

    def build_hierarchy(self) -> dict:
        """Build cây subsystem từ system_root.xml, follow <System Ref>.

        Returns:
            Tree dict: {name, system_file, sid, children[], blocks_summary{}}
        """
        if self._hierarchy is not None:
            return self._hierarchy
        self._hierarchy = self._parse_system_node("Root", "simulink/systems/system_root.xml")
        return self._hierarchy

    def _parse_system_node(self, name: str, system_file: str) -> dict:
        node = {
            "name": name,
            "system_file": system_file,
            "children": [],
            "blocks_summary": {},
        }

        try:
            tree = self._get_tree(system_file)
        except FileNotFoundError:
            return node

        root = tree.getroot()

        # Đếm blocks theo type (chỉ direct children của System)
        block_counts: dict[str, int] = {}
        for block in root.findall("Block"):
            bt = block.get("BlockType", "Unknown")
            block_counts[bt] = block_counts.get(bt, 0) + 1
        node["blocks_summary"] = block_counts

        # Follow SubSystem → System Ref (recursive)
        for block in root.findall("Block[@BlockType='SubSystem']"):
            sub_name = block.get("Name", "Unknown")
            sid = block.get("SID", "")
            system_ref_elem = block.find("System")
            if system_ref_elem is not None:
                ref = system_ref_elem.get("Ref", "")
                if ref:
                    child_file = f"simulink/systems/{ref}.xml"
                    child = self._parse_system_node(sub_name, child_file)
                    child["sid"] = sid
                    node["children"].append(child)

        return node

    # ══════════════════════════════════════════════
    # 2. FIND BLOCKS RECURSIVE
    # ══════════════════════════════════════════════

    def find_blocks_recursive(self, block_type: str) -> list[dict]:
        """Tìm tất cả blocks of type xuyên mọi layers.

        Args:
            block_type: VD "Gain", "Abs", "Sum", "Inport", "SubSystem".

        Returns:
            List dicts: [{name, sid, block_type, path, system_file, configs{}}]
            configs chứa TẤT CẢ <P> values (explicit) — chưa merge defaults.
        """
        hierarchy = self.build_hierarchy()
        results: list[dict] = []
        self._collect_blocks(hierarchy, block_type, "", results)
        return results

    def _collect_blocks(
        self, node: dict, block_type: str, parent_path: str, results: list,
    ) -> None:
        current_path = f"{parent_path}/{node['name']}" if parent_path else node["name"]

        try:
            tree = self._get_tree(node["system_file"])
        except FileNotFoundError:
            return

        root = tree.getroot()

        # Tìm blocks trong file này (direct children của <System>)
        for block in root.findall("Block"):
            bt = block.get("BlockType", "")
            # Match cả BlockType và MaskType (TargetLink blocks)
            mask_type = ""
            for p in block.findall("P"):
                if p.get("Name") == "MaskType":
                    mask_type = (p.text or "").strip()
                    break

            if bt != block_type and mask_type != block_type:
                continue

            name = block.get("Name", "Unknown")
            sid = block.get("SID", "")

            # Rút tất cả configs (<P> trực tiếp + InstanceData/P)
            configs: dict[str, str] = {}
            for p in block.findall("P"):
                p_name = p.get("Name")
                if p_name:
                    configs[p_name] = (p.text or "").strip()

            # InstanceData (cho Reference blocks)
            instance_data = block.find("InstanceData")
            if instance_data is not None:
                for p in instance_data.findall("P"):
                    p_name = p.get("Name")
                    if p_name:
                        configs[f"InstanceData.{p_name}"] = (p.text or "").strip()

            # MaskValueString (pipe-separated params for masked blocks)
            mask_names_node = block.find("P[@Name='MaskNames']")
            mask_values_node = block.find("P[@Name='MaskValueString']")
            if mask_names_node is not None and mask_values_node is not None:
                names_text = mask_names_node.text or ""
                values_text = mask_values_node.text or ""
                m_names = names_text.split("|")
                m_values = values_text.split("|")
                for mi, m_name in enumerate(m_names):
                    m_name = m_name.strip()
                    if m_name and mi < len(m_values):
                        configs[f"MaskValue.{m_name}"] = m_values[mi].strip()

            results.append({
                "name": name,
                "sid": sid,
                "block_type": bt,
                "mask_type": mask_type,
                "path": current_path,
                "system_file": node["system_file"],
                "configs": configs,
            })

        # Recurse vào children
        for child in node.get("children", []):
            self._collect_blocks(child, block_type, current_path, results)

    # ══════════════════════════════════════════════
    # 3. QUERY CONFIG (targeted)
    # ══════════════════════════════════════════════

    def query_config(self, block_type: str, config_name: str) -> list[dict]:
        """Rút CHỈ 1 config từ tất cả blocks of type, kèm default fallback.

        Args:
            block_type: VD "Gain".
            config_name: VD "SaturateOnIntegerOverflow".

        Returns:
            [{block_name, sid, path, value, source:"explicit"|"default"|"not_found"}]
        """
        blocks = self.find_blocks_recursive(block_type)
        results: list[dict] = []

        for block in blocks:
            explicit = block["configs"].get(config_name)

            if explicit is not None:
                source = "explicit"
                value = explicit
            else:
                default = get_default_value(self.model_dir, block_type, config_name)
                if default is not None:
                    source = "default"
                    value = default
                else:
                    source = "not_found"
                    value = None

            results.append({
                "block_name": block["name"],
                "sid": block["sid"],
                "path": block["path"],
                "value": value,
                "source": source,
            })

        return results

    # ══════════════════════════════════════════════
    # 4. LIST ALL CONFIGS (explicit + defaults merged)
    # ══════════════════════════════════════════════

    def get_block_all_configs(self, block_sid: str) -> dict:
        """Lấy TẤT CẢ configs của 1 block: explicit <P> + defaults merged.

        Args:
            block_sid: SID của block.

        Returns:
            {name, type, sid, system_file,
             configs: {config_name: {value, source:"explicit"|"default"}},
             total_configs: int}
        """
        from utils.defaults_parser import parse_bddefaults

        hierarchy = self.build_hierarchy()
        system_file = self._find_block_system(hierarchy, block_sid)
        if not system_file:
            return {"error": f"Block SID={block_sid} không tìm thấy"}

        tree = self._get_tree(system_file)
        root = tree.getroot()

        block_elems = root.xpath(f".//Block[@SID='{block_sid}']")
        if not block_elems:
            return {"error": f"Block SID={block_sid} không tìm thấy trong {system_file}"}

        block = block_elems[0]
        block_type = block.get("BlockType", "Unknown")

        # Explicit configs từ <P> elements
        explicit_configs: dict[str, str] = {}
        for p in block.findall("P"):
            name = p.get("Name")
            if name:
                explicit_configs[name] = (p.text or "").strip()

        # InstanceData configs
        inst = block.find("InstanceData")
        if inst is not None:
            for p in inst.findall("P"):
                name = p.get("Name")
                if name:
                    explicit_configs[f"InstanceData.{name}"] = (p.text or "").strip()

        # MaskValueString configs
        mask_names_node = block.find("P[@Name='MaskNames']")
        mask_values_node = block.find("P[@Name='MaskValueString']")
        if mask_names_node is not None and mask_values_node is not None:
            m_names = (mask_names_node.text or "").split("|")
            m_values = (mask_values_node.text or "").split("|")
            for mi, m_name in enumerate(m_names):
                m_name = m_name.strip()
                if m_name and mi < len(m_values):
                    explicit_configs[f"MaskValue.{m_name}"] = m_values[mi].strip()

        # Defaults từ bddefaults.xml
        defaults_map = parse_bddefaults(self.model_dir)
        block_defaults = defaults_map.get(block_type, {})

        # Merge: defaults → override bởi explicit
        all_configs: dict[str, dict] = {}

        for config_name, default_value in block_defaults.items():
            all_configs[config_name] = {"value": default_value, "source": "default"}

        for config_name, explicit_value in explicit_configs.items():
            all_configs[config_name] = {"value": explicit_value, "source": "explicit"}

        return {
            "name": block.get("Name", "Unknown"),
            "type": block_type,
            "sid": block_sid,
            "system_file": system_file,
            "configs": all_configs,
            "total_configs": len(all_configs),
        }

    # ══════════════════════════════════════════════
    # 5. TRACE CONNECTIONS
    # ══════════════════════════════════════════════

    def trace_connections(self, block_sid: str) -> dict:
        """Trace signal connections cho 1 block (by SID).

        Tìm tất cả incoming/outgoing connections trong cùng system file.
        Nếu endpoint là Inport/Outport → ghi nhận đó là cross-subsystem boundary.

        Args:
            block_sid: SID của block cần trace. VD: "68".

        Returns:
            {block: {name, type, sid, system_file},
             incoming: [{name, type, sid, port}],
             outgoing: [{name, type, sid, port}]}
        """
        hierarchy = self.build_hierarchy()

        # Tìm block nằm ở system file nào
        system_file = self._find_block_system(hierarchy, block_sid)
        if not system_file:
            return {"error": f"Block SID={block_sid} không tìm thấy trong model"}

        tree = self._get_tree(system_file)
        root = tree.getroot()

        # Block info
        block_elems = root.xpath(f".//Block[@SID='{block_sid}']")
        if not block_elems:
            return {"error": f"Block SID={block_sid} không tìm thấy trong {system_file}"}

        block_elem = block_elems[0]
        block_info = {
            "name": block_elem.get("Name", "Unknown"),
            "type": block_elem.get("BlockType", "Unknown"),
            "sid": block_sid,
            "system_file": system_file,
        }

        # Build SID → block info map cho file này
        sid_map: dict[str, dict] = {}
        for b in root.findall("Block"):
            b_sid = b.get("SID", "")
            if b_sid:
                sid_map[b_sid] = {
                    "name": b.get("Name", "Unknown"),
                    "type": b.get("BlockType", "Unknown"),
                    "sid": b_sid,
                }

        # Parse Lines
        incoming: list[dict] = []
        outgoing: list[dict] = []

        for line in root.findall("Line"):
            src = self._line_endpoint(line, "Src")
            dsts = self._line_destinations(line)

            src_sid = src.split("#")[0] if src else ""
            src_port = src.split("#")[1] if src and "#" in src else ""

            # Block là source → outgoing
            if src_sid == block_sid:
                for dst in dsts:
                    dst_sid = dst.split("#")[0]
                    dst_port = dst.split("#")[1] if "#" in dst else ""
                    dst_info = sid_map.get(dst_sid, {"sid": dst_sid, "name": "?", "type": "?"})
                    outgoing.append({**dst_info, "port": dst_port})

            # Block là destination → incoming
            for dst in dsts:
                dst_sid = dst.split("#")[0]
                if dst_sid == block_sid:
                    src_info = sid_map.get(src_sid, {"sid": src_sid, "name": "?", "type": "?"})
                    incoming.append({**src_info, "port": src_port})

        return {
            "block": block_info,
            "incoming": incoming,
            "outgoing": outgoing,
        }

    # ══════════════════════════════════════════════
    # 5. CROSS-SUBSYSTEM CONNECTION TRACING
    # ══════════════════════════════════════════════

    def trace_connections_cross_subsystem(
        self, start_block_sid: str, direction: str = "both", max_depth: int = 5,
    ) -> dict:
        """Trace signal connections xuyên subsystem boundaries.

        Khi gặp Inport/Outport → follow vào/ra subsystem tương ứng.
        Outport trong child system → tìm SubSystem parent → tìm connection trong parent system.
        Inport trong child system → tìm SubSystem parent → tìm source signal.

        Args:
            start_block_sid: SID block bắt đầu.
            direction: "incoming", "outgoing", hoặc "both".
            max_depth: Số bước tối đa cross subsystem (tránh loop vô hạn).

        Returns:
            {block, trace: [{step, block, system_file, crossing}]}
        """
        hierarchy = self.build_hierarchy()
        system_file = self._find_block_system(hierarchy, start_block_sid)
        if not system_file:
            return {"error": f"Block SID={start_block_sid} không tìm thấy"}

        # Block info
        tree = self._get_tree(system_file)
        root = tree.getroot()
        block_elems = root.xpath(f".//Block[@SID='{start_block_sid}']")
        if not block_elems:
            return {"error": f"Block SID={start_block_sid} không tìm thấy trong {system_file}"}

        block_elem = block_elems[0]
        block_info = {
            "name": block_elem.get("Name", "Unknown"),
            "type": block_elem.get("BlockType", "Unknown"),
            "sid": start_block_sid,
            "system_file": system_file,
        }

        trace_result: list[dict] = []
        visited: set[str] = {start_block_sid}

        if direction in ("outgoing", "both"):
            self._trace_cross(
                hierarchy, start_block_sid, system_file, "outgoing",
                max_depth, visited, trace_result,
            )
        if direction in ("incoming", "both"):
            self._trace_cross(
                hierarchy, start_block_sid, system_file, "incoming",
                max_depth, visited, trace_result,
            )

        return {
            "block": block_info,
            "trace": trace_result,
            "total_steps": len(trace_result),
        }

    def _trace_cross(
        self, hierarchy: dict, block_sid: str, system_file: str,
        direction: str, remaining_depth: int, visited: set, trace: list,
    ) -> None:
        """Recursive tracing xuyên subsystem."""
        if remaining_depth <= 0:
            trace.append({"warning": f"Đạt max_depth, dừng trace"})
            return

        # Lấy connections trong cùng file
        same_file_result = self.trace_connections(block_sid)
        if "error" in same_file_result:
            return

        connections = (
            same_file_result.get("outgoing", []) if direction == "outgoing"
            else same_file_result.get("incoming", [])
        )

        for conn in connections:
            conn_sid = conn.get("sid", "")
            if conn_sid in visited:
                continue
            visited.add(conn_sid)

            conn_type = conn.get("type", "")

            trace.append({
                "direction": direction,
                "block": conn,
                "system_file": system_file,
                "crossing": "none",
            })

            # Outport trong child system → follow ra parent
            if conn_type == "Outport":
                parent_info = self._find_parent_subsystem(hierarchy, system_file)
                if parent_info:
                    trace[-1]["crossing"] = f"outport_to_parent:{parent_info['parent_file']}"
                    # Tìm SubSystem block trong parent system tương ứng
                    sub_sid = parent_info.get("subsystem_sid", "")
                    if sub_sid and sub_sid not in visited:
                        self._trace_cross(
                            hierarchy, sub_sid, parent_info["parent_file"],
                            direction, remaining_depth - 1, visited, trace,
                        )

            # Inport trong child system → trace từ parent
            elif conn_type == "Inport":
                parent_info = self._find_parent_subsystem(hierarchy, system_file)
                if parent_info:
                    trace[-1]["crossing"] = f"inport_from_parent:{parent_info['parent_file']}"
                    sub_sid = parent_info.get("subsystem_sid", "")
                    if sub_sid and sub_sid not in visited:
                        self._trace_cross(
                            hierarchy, sub_sid, parent_info["parent_file"],
                            "incoming", remaining_depth - 1, visited, trace,
                        )

            # SubSystem → follow vào child system file
            elif conn_type == "SubSystem":
                child_file = self._find_subsystem_file(hierarchy, conn_sid)
                if child_file:
                    trace[-1]["crossing"] = f"into_subsystem:{child_file}"
                    # Tìm Inport/Outport tương ứng trong child system
                    # (follow signal vào trong subsystem)

    def _find_parent_subsystem(self, hierarchy: dict, system_file: str) -> dict | None:
        """Tìm parent system file chứa SubSystem trỏ tới system_file này."""
        return self._search_parent(hierarchy, system_file, None, "")

    def _search_parent(
        self, node: dict, target_file: str, parent_node: dict | None, parent_file: str,
    ) -> dict | None:
        if node["system_file"] == target_file and parent_node is not None:
            # Tìm SID của SubSystem trong parent mà Ref tới target_file
            subsystem_sid = ""
            for child in parent_node.get("children", []):
                if child.get("system_file") == target_file:
                    subsystem_sid = child.get("sid", "")
                    break
            return {
                "parent_file": parent_file,
                "subsystem_sid": subsystem_sid,
            }
        for child in node.get("children", []):
            result = self._search_parent(child, target_file, node, node["system_file"])
            if result:
                return result
        return None

    def _find_subsystem_file(self, hierarchy: dict, subsystem_sid: str) -> str | None:
        """Tìm system file mà SubSystem block (by SID) trỏ tới."""
        return self._search_subsystem_file(hierarchy, subsystem_sid)

    def _search_subsystem_file(self, node: dict, target_sid: str) -> str | None:
        for child in node.get("children", []):
            if child.get("sid") == target_sid:
                return child["system_file"]
            result = self._search_subsystem_file(child, target_sid)
            if result:
                return result
        return None

    # ══════════════════════════════════════════════
    # 6. RAW BLOCK CONFIG (for escalation)
    # ══════════════════════════════════════════════

    def read_raw_block_config(self, block_sid: str) -> dict:
        """Đọc TOÀN BỘ config của 1 block — không truncate, không filter.

        Dùng cho escalation: khi retry nhiều lần vẫn fail, gửi raw data cho LLM.

        Args:
            block_sid: SID của block.

        Returns:
            {name, type, sid, system_file, raw_configs{}, instance_data{}, children_xml}
        """
        hierarchy = self.build_hierarchy()
        system_file = self._find_block_system(hierarchy, block_sid)
        if not system_file:
            return {"error": f"Block SID={block_sid} không tìm thấy"}

        tree = self._get_tree(system_file)
        root = tree.getroot()

        block_elems = root.xpath(f".//Block[@SID='{block_sid}']")
        if not block_elems:
            return {"error": f"Block SID={block_sid} không tìm thấy trong {system_file}"}

        block = block_elems[0]

        # Tất cả <P> configs
        raw_configs: dict[str, str] = {}
        for p in block.findall("P"):
            name = p.get("Name")
            ref = p.get("Ref")
            if name:
                raw_configs[name] = ref if ref else (p.text or "").strip()

        # InstanceData
        instance_data: dict[str, str] = {}
        inst = block.find("InstanceData")
        if inst is not None:
            for p in inst.findall("P"):
                name = p.get("Name")
                if name:
                    instance_data[name] = (p.text or "").strip()

        # Full XML string (cho trường hợp cần xem nested structure)
        raw_xml = etree.tostring(block, pretty_print=True, encoding="unicode")

        return {
            "name": block.get("Name", "Unknown"),
            "type": block.get("BlockType", "Unknown"),
            "sid": block_sid,
            "system_file": system_file,
            "raw_configs": raw_configs,
            "instance_data": instance_data,
            "raw_xml": raw_xml,
        }

    # ──────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────

    @staticmethod
    def _line_endpoint(line_elem, name: str) -> str:
        for p in line_elem.findall("P"):
            if p.get("Name") == name:
                return (p.text or "").strip()
        return ""

    @staticmethod
    def _line_destinations(line_elem) -> list[str]:
        dsts: list[str] = []
        # Direct Dst
        for p in line_elem.findall("P"):
            if p.get("Name") == "Dst":
                dsts.append((p.text or "").strip())
        # Branch destinations
        for branch in line_elem.findall("Branch"):
            for p in branch.findall("P"):
                if p.get("Name") == "Dst":
                    dsts.append((p.text or "").strip())
        return dsts

    def _find_block_system(self, node: dict, block_sid: str) -> str | None:
        """Tìm system file chứa block by SID (recursive)."""
        try:
            tree = self._get_tree(node["system_file"])
            root = tree.getroot()
            if root.xpath(f".//Block[@SID='{block_sid}']"):
                return node["system_file"]
        except FileNotFoundError:
            pass

        for child in node.get("children", []):
            result = self._find_block_system(child, block_sid)
            if result:
                return result
        return None
