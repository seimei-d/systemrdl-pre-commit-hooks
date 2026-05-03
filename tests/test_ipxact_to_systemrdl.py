from __future__ import annotations

import pathlib
import shutil

import pytest

from pre_commit_scripts.ipxact_to_systemrdl.cli import main as i2r_main
from pre_commit_scripts.systemrdl_to_ipxact.cli import main as r2i_main

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "sample.rdl"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _make_ipxact(repo: pathlib.Path) -> pathlib.Path:
    """Generate a real IP-XACT XML to use as input."""
    shutil.copy(FIXTURE, repo / "sample.rdl")
    assert r2i_main(["--output-dir", "ipxact_in", "sample.rdl"]) == 0
    xml = repo / "ipxact_in" / "sample.xml"
    assert xml.is_file()
    return xml


def test_round_trip_writes_rdl(repo):
    xml = _make_ipxact(repo)
    out = repo / "out" / "sample.rdl"
    rc = i2r_main(["--input", str(xml), "--output", str(out)])
    assert rc == 0
    assert out.is_file()
    text = out.read_text()
    # The original sample addrmap was named "sample" — should appear in the regenerated RDL.
    assert "sample" in text
    assert "addrmap" in text


def test_flatten_strips_wrapper(repo):
    xml = _make_ipxact(repo)
    plain = repo / "plain.rdl"
    flat = repo / "flat.rdl"
    assert i2r_main(["--input", str(xml), "--output", str(plain)]) == 0
    assert i2r_main(["--input", str(xml), "--output", str(flat), "--flatten"]) == 0

    # Without --flatten the top is the IP-XACT wrapper "<name>__<name>_mmap".
    assert "__" in plain.read_text().splitlines()[0]
    # With --flatten the wrapper is gone.
    assert "__" not in flat.read_text().splitlines()[0]
    # And the actual content is still there.
    assert "CTRL" in flat.read_text()


def test_creates_parent_dirs(repo):
    xml = _make_ipxact(repo)
    out = repo / "deeply" / "nested" / "out.rdl"
    rc = i2r_main(["-i", str(xml), "-o", str(out)])
    assert rc == 0
    assert out.is_file()


def test_missing_input_returns_error(repo, capsys):
    rc = i2r_main(["--input", "nope.xml", "--output", "out.rdl"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "input file not found" in err
    assert not (repo / "out.rdl").exists()


def test_invalid_xml_returns_error(repo, capsys):
    bad = repo / "bad.xml"
    bad.write_text("<?xml version='1.0'?><not-ipxact/>")
    rc = i2r_main(["--input", str(bad), "--output", "out.rdl"])
    assert rc == 1


def test_missing_required_args_exits_nonzero(repo):
    with pytest.raises(SystemExit) as exc:
        i2r_main([])
    assert exc.value.code != 0
