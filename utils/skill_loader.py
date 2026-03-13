"""
Load SKILL.md files và parse thành instructions cho Agno agents.

SKILL.md format (theo Anthropic Agent Skills):
  ---
  name: skill-name
  description: ...
  ---
  # Body content
"""

from pathlib import Path


def load_skill(skill_name: str, skills_dir: str = "skills") -> list[str]:
    """Đọc SKILL.md và trả về nội dung body làm instructions cho Agent.

    Args:
        skill_name: Tên thư mục skill (VD: "rule-analyzer", "code-generator")
        skills_dir: Thư mục gốc chứa tất cả skills

    Returns:
        List[str] — mỗi dòng body content là 1 instruction string

    Raises:
        FileNotFoundError: Nếu SKILL.md không tồn tại
    """
    skill_path = Path(skills_dir) / skill_name / "SKILL.md"

    if not skill_path.exists():
        raise FileNotFoundError(f"SKILL.md không tìm thấy: {skill_path}")

    content = skill_path.read_text(encoding="utf-8")

    # Tách frontmatter (giữa 2 dấu ---) khỏi body
    body = _strip_frontmatter(content)

    # Trả về toàn bộ body (giữ dòng trống để bảo toàn format code template)
    return [body]


def load_skill_description(skill_name: str, skills_dir: str = "skills") -> str:
    """Đọc description từ YAML frontmatter của SKILL.md.

    Returns:
        Chuỗi description, hoặc "" nếu không tìm thấy.
    """
    skill_path = Path(skills_dir) / skill_name / "SKILL.md"

    if not skill_path.exists():
        return ""

    content = skill_path.read_text(encoding="utf-8")
    frontmatter = _extract_frontmatter(content)

    for line in frontmatter.splitlines():
        if line.strip().startswith("description:"):
            return line.split("description:", 1)[1].strip()

    return ""


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
