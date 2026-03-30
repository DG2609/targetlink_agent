"""
config_reader.py — đọc Simulink ConfigSet từ .slx model.

Simulink lưu solver/codegen settings trong simulink/configSet0.xml.
Các components chính:
  - Simulink.SolverCC   — solver type, step size, ...
  - Simulink.RTWCC      — code gen: SystemTargetFile, TargetLang, ...
  - Simulink.OptimizationCC — optimization flags
  - Simulink.DataIOCC   — data I/O settings
  - Simulink.HardwareCC — hardware implementation

Dùng trong generated_checks/ cho model-level rules:
    from utils.config_reader import read_config_setting, read_all_config_settings
"""

from __future__ import annotations
import glob as _glob
import os as _os
from lxml import etree as _etree


def _find_config_set_file(model_dir: str) -> str | None:
    """Tìm file configSet*.xml trong model directory.

    Args:
        model_dir: Absolute path to unzipped .slx directory.

    Returns:
        Absolute path of first configSet*.xml found, or None.
    """
    # configSet[0-9]*.xml — exclude configSetInfo.xml (metadata, no @ClassName)
    pattern = _os.path.join(model_dir, "simulink", "configSet[0-9]*.xml")
    matches = sorted(_glob.glob(pattern))
    return matches[0] if matches else None


def read_config_setting(
    model_dir: str,
    class_name: str,
    setting_name: str,
) -> str | None:
    """Đọc 1 setting từ Simulink ConfigSet.

    Args:
        model_dir: Absolute path to unzipped .slx directory.
        class_name: ClassName của component. VD:
            "Simulink.SolverCC"  — solver settings
            "Simulink.RTWCC"     — code generation settings
            "Simulink.OptimizationCC" — optimization flags
            "Simulink.HardwareCC"    — hardware implementation
            "Simulink.DataIOCC"      — data I/O
        setting_name: Tên property. VD: "SystemTargetFile", "Solver", "TargetLang"

    Returns:
        Setting value (str), or None nếu không tìm thấy.

    Example:
        >>> val = read_config_setting(model_dir, "Simulink.RTWCC", "SystemTargetFile")
        >>> assert val == "ert.tlc"
    """
    config_file = _find_config_set_file(model_dir)
    if config_file is None:
        return None
    try:
        tree = _etree.parse(config_file)
    except _etree.XMLSyntaxError:
        return None

    for obj in tree.findall(f".//*[@ClassName='{class_name}']"):
        node = obj.find(f"P[@Name='{setting_name}']")
        if node is not None and node.text is not None:
            return node.text.strip()
    return None


def read_all_config_settings(
    model_dir: str,
    class_name: str,
) -> dict[str, str]:
    """Đọc TẤT CẢ settings của 1 ConfigSet component class.

    Args:
        model_dir: Absolute path to unzipped .slx directory.
        class_name: ClassName. VD: "Simulink.SolverCC", "Simulink.RTWCC"

    Returns:
        Dict {setting_name: value}. Empty dict nếu không tìm thấy.

    Example:
        >>> settings = read_all_config_settings(model_dir, "Simulink.RTWCC")
        >>> print(settings.get("SystemTargetFile"))  # "ert.tlc"
    """
    config_file = _find_config_set_file(model_dir)
    if config_file is None:
        return {}
    try:
        tree = _etree.parse(config_file)
    except _etree.XMLSyntaxError:
        return {}

    result: dict[str, str] = {}
    for obj in tree.findall(f".//*[@ClassName='{class_name}']"):
        for p in obj.findall("P"):
            name = p.get("Name", "")
            if name and p.text is not None:
                result[name] = p.text.strip()
    return result


def list_config_components(model_dir: str) -> list[str]:
    """Liệt kê tất cả ClassName components trong ConfigSet.

    Args:
        model_dir: Absolute path to unzipped .slx directory.

    Returns:
        List of ClassName strings. VD: ["Simulink.SolverCC", "Simulink.RTWCC", ...]
    """
    config_file = _find_config_set_file(model_dir)
    if config_file is None:
        return []
    try:
        tree = _etree.parse(config_file)
    except _etree.XMLSyntaxError:
        return []

    seen: set[str] = set()
    names: list[str] = []
    for obj in tree.findall(".//*[@ClassName]"):
        cn = obj.get("ClassName", "")
        if cn and cn != "Simulink.ConfigSet" and cn not in seen:
            seen.add(cn)
            names.append(cn)
    return names
