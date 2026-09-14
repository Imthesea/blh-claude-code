from blh.extensions.skills import SkillLoader


def _write_skill(root, name, content):
    d = root / name
    d.mkdir()
    (d / "SKILL.md").write_text(content, encoding="utf-8")
    return d


def test_parse_frontmatter_basic():
    meta, body = SkillLoader.parse_frontmatter(
        "---\nname: code-review\ndescription: 审查代码\n---\n正文")
    assert meta == {"name": "code-review", "description": "审查代码"}
    assert body == "正文"


def test_parse_frontmatter_missing():
    meta, body = SkillLoader.parse_frontmatter("无 frontmatter")
    assert meta == {}
    assert body == "无 frontmatter"


def test_scan_catalog_and_load(tmp_path):
    _write_skill(tmp_path, "alpha", "---\nname: a\ndescription: 第一个\n---\nA body")
    _write_skill(tmp_path, "beta", "---\nname: b\ndescription: 第二个\n---\nB body")
    loader = SkillLoader(tmp_path)
    assert "a: 第一个" in loader.catalog()
    assert "b: 第二个" in loader.catalog()
    assert loader.load("a") == "---\nname: a\ndescription: 第一个\n---\nA body"


def test_load_unknown_lists_available(tmp_path):
    _write_skill(tmp_path, "alpha", "---\nname: a\ndescription: 第一个\n---\n")
    loader = SkillLoader(tmp_path)
    assert "Unknown skill 'nope'" in loader.load("nope")
    assert "a" in loader.load("nope")
