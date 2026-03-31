"""
Load SKILL.md files và parse thành instructions cho Agno agents.

SKILL.md format (theo Anthropic Agent Skills):
  ---
  name: skill-name
  description: ...
  ---
  # Body content

Optional: references/ subdirectory chứa .md files bổ sung.
  Khi include_references=True, nội dung references/ được auto-append vào body.
"""

from pathlib import Path


def load_skill(
    skill_name: str,
    skills_dir: str = "skills",
    include_references: bool = False,
) -> list[str]:
    """Đọc SKILL.md và trả về nội dung body làm instructions cho Agent.

    Args:
        skill_name: Tên thư mục skill (VD: "rule-analyzer", "code-generator")
        skills_dir: Thư mục gốc chứa tất cả skills
        include_references: Nếu True, auto-append nội dung từ references/*.md
                            vào cuối body. Thứ tự: alphabetical by filename.

    Returns:
        List[str] — body content (1 phần tử duy nhất)

    Raises:
        FileNotFoundError: Nếu SKILL.md không tồn tại
    """
    skills_root = Path(skills_dir).resolve()
    skill_path = (skills_root / skill_name / "SKILL.md").resolve()
    try:
        skill_path.relative_to(skills_root)
    except ValueError:
        raise ValueError(f"Invalid skill_name (path traversal blocked): {skill_name!r}")

    if not skill_path.exists():
        raise FileNotFoundError(f"SKILL.md không tìm thấy: {skill_path}")

    content = skill_path.read_text(encoding="utf-8")

    # Tách frontmatter (giữa 2 dấu ---) khỏi body
    body = _strip_frontmatter(content)

    # Auto-append references nếu được yêu cầu
    if include_references:
        refs_dir = skill_path.parent / "references"
        if refs_dir.exists():
            for ref_file in sorted(refs_dir.glob("*.md")):
                ref_content = ref_file.read_text(encoding="utf-8")
                body += f"\n\n---\n\n# Reference: {ref_file.stem}\n\n{ref_content}"

    # Trả về toàn bộ body (giữ dòng trống để bảo toàn format code template)
    return [body]


def list_skill_references(skill_name: str, skills_dir: str = "skills") -> list[str]:
    """Liệt kê tất cả reference files có trong skill.

    Returns:
        List tên files (VD: ["patterns.md", "templates.md"]).
        Rỗng nếu không có references/.
    """
    refs_dir = Path(skills_dir) / skill_name / "references"
    if not refs_dir.exists():
        return []
    return sorted(f.name for f in refs_dir.glob("*.md"))


def load_skill_reference(
    skill_name: str,
    ref_name: str,
    skills_dir: str = "skills",
) -> str:
    """Đọc 1 reference file cụ thể từ skill.

    Args:
        skill_name: Tên skill (VD: "code-generator")
        ref_name: Tên file reference (VD: "templates.md")
        skills_dir: Thư mục gốc

    Returns:
        Nội dung file reference.

    Raises:
        FileNotFoundError: Nếu file không tồn tại.
    """
    skills_root = Path(skills_dir).resolve()
    ref_path = (skills_root / skill_name / "references" / ref_name).resolve()
    try:
        ref_path.relative_to(skills_root)
    except ValueError:
        raise ValueError(f"Invalid ref_name (path traversal blocked): {ref_name!r}")
    if not ref_path.exists():
        raise FileNotFoundError(f"Reference không tìm thấy: {ref_path}")
    return ref_path.read_text(encoding="utf-8")


def _strip_frontmatter(content: str) -> str:
    """Bỏ YAML frontmatter (phần giữa --- ... ---), trả về body."""
    if not content.startswith("---"):
        return content

    # Tìm dấu --- thứ 2
    end_idx = content.find("---", 3)
    if end_idx == -1:
        return content

    return content[end_idx + 3:].strip()


def _extract_frontmatter(content: str) -> str:
    """Lấy phần YAML frontmatter."""
    if not content.startswith("---"):
        return ""

    end_idx = content.find("---", 3)
    if end_idx == -1:
        return ""

    return content[3:end_idx].strip()
