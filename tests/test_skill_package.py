import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skill" / "chronovault-steward"
KIT = Path(os.environ.get("ULIYA_SKILL_KIT", str(ROOT.parent / "uliya-kit" / "uliya-skill-kit")))


def test_frontmatter_and_required_headings():
    src = (SKILL / "SKILL.md").read_text()
    meta = {}
    m = re.match(r"^---\n(.*?)\n---\n", src, re.S)
    assert m
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", meta["name"])
    assert len(meta["description"]) <= 1024 and "Use when" in meta["description"]
    for heading in ("# Goal", "# Required input", "# Workflow", "# Completion and failure"):
        assert re.search(rf"^{heading}\s*$", src, re.M), heading
    for status in ("completed", "failed", "cancelled", "waiting_user", "waiting_approval"):
        assert status in src


def test_every_reference_is_linked_and_no_scripts():
    src = (SKILL / "SKILL.md").read_text()
    for ref in (SKILL / "references").glob("*.md"):
        assert f"](references/{ref.name})" in src
    for md in SKILL.rglob("*.md"):
        text = md.read_text()
        assert not re.search(r"^```\s*(bash|sh|shell|python|js|javascript|ts)\b", text, re.M | re.I), md
        assert "cli.invoke" not in text
        assert not re.search(r"(?:^|\s)/(?:volume\d*|mnt|nas)/", text), md


def test_delegates_target_registered_agents():
    src = (SKILL / "SKILL.md").read_text()
    targets = re.findall(r"delegate --target ([a-z-]+) --instruction '", src)
    assert targets and set(targets) <= {"file-agent", "document-agent", "photo-agent", "knowledge-agent"}


def test_directory_name_matches_skill_name():
    src = (SKILL / "SKILL.md").read_text()
    name = re.search(r"^name:\s*(\S+)", src, re.M).group(1)
    assert SKILL.name == name


@pytest.mark.skipif(
    not (KIT / "scripts" / "check-skill.mjs").exists() or not shutil.which("node"),
    reason="official uliya-skill-kit checker not available (set ULIYA_SKILL_KIT)",
)
def test_official_uliya_checker_passes():
    out = subprocess.run(
        ["node", str(KIT / "scripts" / "check-skill.mjs"), str(SKILL)],
        capture_output=True, text=True,
    )
    result = json.loads(out.stdout)
    assert result["summary"]["errors"] == 0, result.get("diagnostics")
