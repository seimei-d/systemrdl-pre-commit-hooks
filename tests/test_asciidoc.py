from __future__ import annotations

import pathlib
import shutil

import pytest

from pre_commit_scripts.asciidoc.cli import (
    DEFAULT_INPUT_DIR,
    _fmt_size,
    main,
)

FIXTURE_SS = pathlib.Path(__file__).parent / "fixtures" / "ss.rdl"
FIXTURE_LEAF = pathlib.Path(__file__).parent / "fixtures" / "sample.rdl"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _table_rows(adoc: str) -> list[list[str]]:
    """Parse table-pipe rows from an AsciiDoc dump into [[cell, ...], ...]."""
    rows = []
    for line in adoc.splitlines():
        if not line.startswith("|") or line.startswith("|==="):
            continue
        rows.append([c.strip() for c in line.split("|")[1:]])
    return rows


def test_renders_table_with_addrmap_and_mem(repo):
    shutil.copy(FIXTURE_SS, repo / "ss.rdl")
    rc = main(["ss.rdl"])
    assert rc == 0

    out = (repo / "asciidoc" / "ss.adoc").read_text()
    rows = _table_rows(out)
    assert rows[0] == [
        "Block name", "Block type",
        "Start address", "End address",
        "Region size", "Parameters",
    ]
    assert ["abc",  "ABC", "0x00000000", "0x00000003", "4 B",   "—"]   in rows
    assert ["bcd",  "BCD", "0x00001000", "0x00001007", "8 B",   "P=7"] in rows
    assert ["sram", "mem", "0x00010000", "0x00010FFF", "4 KiB", "—"]   in rows


def test_table_columns_are_aligned(repo):
    """Pipes must line up at the same positions across all rows."""
    shutil.copy(FIXTURE_SS, repo / "ss.rdl")
    assert main(["ss.rdl"]) == 0
    out = (repo / "asciidoc" / "ss.adoc").read_text()

    pipe_lines = [ln for ln in out.splitlines() if ln.startswith("| ")]
    assert len(pipe_lines) >= 2  # header + at least one row
    pipe_positions = {tuple(i for i, c in enumerate(ln) if c == "|") for ln in pipe_lines}
    assert len(pipe_positions) == 1, f"misaligned pipes: {pipe_positions}"


def test_skips_files_without_subsystems(repo):
    # sample.rdl has only registers at the top level, no addrmap/mem children.
    shutil.copy(FIXTURE_LEAF, repo / "sample.rdl")
    rc = main(["sample.rdl"])
    assert rc == 0
    assert not (repo / "asciidoc" / "sample.adoc").exists()


def test_explicit_output_dir(repo, tmp_path):
    shutil.copy(FIXTURE_SS, repo / "ss.rdl")
    out_dir = tmp_path / "elsewhere"
    rc = main(["--output-dir", str(out_dir), "ss.rdl"])
    assert rc == 0
    assert (out_dir / "ss.adoc").is_file()


def test_default_input_dir_scan(repo):
    src = repo / DEFAULT_INPUT_DIR / "block"
    src.mkdir(parents=True)
    shutil.copy(FIXTURE_SS, src / "ss.rdl")
    rc = main([])
    assert rc == 0
    assert (repo / "asciidoc" / "block" / "ss.adoc").is_file()


def test_stale_output_removed_when_subsystems_disappear(repo):
    target = repo / "asciidoc" / "leaf.adoc"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("stale")
    shutil.copy(FIXTURE_LEAF, repo / "leaf.rdl")
    rc = main(["leaf.rdl"])
    assert rc == 0
    assert not target.exists()


def test_missing_file_returns_error(repo):
    rc = main(["does_not_exist.rdl"])
    assert rc == 1


@pytest.mark.parametrize("size,expected", [
    (1, "1 B"),
    (1023, "1023 B"),
    (1024, "1 KiB"),
    (4 * 1024, "4 KiB"),
    (1024 * 1024, "1 MiB"),
    (16 * 1024 * 1024, "16 MiB"),
    (1024 * 1024 * 1024, "1 GiB"),
    (1500, "1500 B"),  # not a clean multiple of KiB
])
def test_fmt_size(size, expected):
    assert _fmt_size(size) == expected
