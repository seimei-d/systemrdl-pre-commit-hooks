from __future__ import annotations

import os
import pathlib
import shutil
import xml.etree.ElementTree as ET

import pytest

from pre_commit_scripts.systemrdl_to_ipxact.cli import (
    DEFAULT_INPUT_DIR,
    detect_standard,
    main,
    output_path,
)
from peakrdl_ipxact import Standard

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "sample.rdl"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A fake repo root with sample.rdl staged at the top level."""
    monkeypatch.chdir(tmp_path)
    shutil.copy(FIXTURE, tmp_path / "sample.rdl")
    return tmp_path


def _root_ns(xml_file: pathlib.Path) -> str:
    tree = ET.parse(xml_file)
    tag = tree.getroot().tag
    assert tag.startswith("{")
    return tag.split("}", 1)[0][1:]


def test_default_export_writes_under_ipxact_dir(repo):
    rc = main(["sample.rdl"])
    assert rc == 0
    out = repo / "ipxact" / "sample.xml"
    assert out.is_file()
    assert "1685-2014" in _root_ns(out)


def test_explicit_output_dir(repo, tmp_path):
    out_dir = tmp_path / "elsewhere"
    rc = main(["--output-dir", str(out_dir), "sample.rdl"])
    assert rc == 0
    assert (out_dir / "sample.xml").is_file()


def test_force_standard_2009(repo):
    rc = main(["--standard", "2009", "sample.rdl"])
    assert rc == 0
    out = repo / "ipxact" / "sample.xml"
    assert "1685-2009" in _root_ns(out)


def test_auto_detects_existing_2009(repo):
    target = repo / "ipxact" / "sample.xml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<spirit:component xmlns:spirit="http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009"/>\n'
    )
    rc = main(["sample.rdl"])
    assert rc == 0
    assert "1685-2009" in _root_ns(target)


def test_metadata_flags_appear_in_output(repo):
    rc = main([
        "--vendor", "acme.test",
        "--library", "widgets",
        "--version", "9.9",
        "sample.rdl",
    ])
    assert rc == 0
    text = (repo / "ipxact" / "sample.xml").read_text()
    assert "acme.test" in text
    assert "widgets" in text
    assert "9.9" in text


def test_non_rdl_file_skipped(repo):
    (repo / "notes.txt").write_text("hello")
    rc = main(["notes.txt"])
    assert rc == 0
    assert not (repo / "ipxact").exists()


def test_missing_file_returns_error(repo):
    rc = main(["does_not_exist.rdl"])
    assert rc == 1


def test_exclude_by_basename_glob(repo):
    (repo / "keep.rdl").write_text(FIXTURE.read_text())
    (repo / "skip_pkg.rdl").write_text(FIXTURE.read_text())
    rc = main(["--exclude", "*_pkg.rdl", "keep.rdl", "skip_pkg.rdl"])
    assert rc == 0
    assert (repo / "ipxact" / "keep.xml").is_file()
    assert not (repo / "ipxact" / "skip_pkg.xml").exists()


def test_exclude_by_path_glob(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    lib = tmp_path / "lib"
    lib.mkdir()
    shutil.copy(FIXTURE, lib / "leaf.rdl")
    shutil.copy(FIXTURE, tmp_path / "top.rdl")
    rc = main(["--exclude", "lib/*", "top.rdl", "lib/leaf.rdl"])
    assert rc == 0
    assert (tmp_path / "ipxact" / "top.xml").is_file()
    assert not (tmp_path / "ipxact" / "lib").exists()


def test_incdir_resolves_includes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    inc = tmp_path / "inc"
    inc.mkdir()
    (inc / "leaf.rdl").write_text(
        "addrmap LEAF { reg { field { sw=rw; hw=r; } X[31:0]; } R0 @ 0x0; };\n"
    )
    top = tmp_path / "top.rdl"
    top.write_text(
        "`include \"leaf.rdl\"\n"
        "addrmap top { LEAF L @ 0x0; };\n"
    )
    rc = main(["-I", str(inc), "top.rdl"])
    assert rc == 0
    assert (tmp_path / "ipxact" / "top.xml").is_file()


def test_default_input_dir_scan(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = tmp_path / DEFAULT_INPUT_DIR / "block"
    src.mkdir(parents=True)
    shutil.copy(FIXTURE, src / "sample.rdl")

    rc = main([])
    assert rc == 0
    assert (tmp_path / "ipxact" / "block" / "sample.xml").is_file()


def test_default_input_dir_missing_is_noop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = main([])
    assert rc == 0
    assert not (tmp_path / "ipxact").exists()


def test_detect_standard_helpers(tmp_path):
    f = tmp_path / "x.xml"
    assert detect_standard(f) is None
    f.write_text('<x xmlns="http://www.accellera.org/XMLSchema/IPXACT/1685-2014"/>')
    assert detect_standard(f) is Standard.IEEE_1685_2014


def test_output_path_mirrors_subdirs(tmp_path):
    repo_root = tmp_path
    nested = repo_root / "blocks" / "core"
    nested.mkdir(parents=True)
    rdl = nested / "core.rdl"
    rdl.write_text("")
    out = output_path(rdl, None, repo_root)
    assert out == repo_root / "ipxact" / "blocks" / "core" / "core.xml"
