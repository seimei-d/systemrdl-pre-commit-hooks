# systemrdl-pre-commit-hooks

Collection of [pre-commit](https://pre-commit.com/) hooks for SystemRDL register-map
workflows: SystemRDL ⇄ IP-XACT conversion and AsciiDoc tables of address maps.

| Hook id | Direction / output | Trigger |
|---|---|---|
| [`systemrdl-to-ipxact`](#systemrdl-to-ipxact) | SystemRDL → IP-XACT XML | every staged `regmap/**/*.rdl` |
| [`asciidoc-addrmap`](#asciidoc-addrmap) | SystemRDL → AsciiDoc address-map table | every staged `regmap/**/*.rdl` |
| [`ipxact-to-systemrdl`](#ipxact-to-systemrdl) | IP-XACT XML → SystemRDL | one explicit file pair, configured in `args` |

All hooks share one Python package (`pre_commit_scripts`) and one virtualenv built
by pre-commit from `pyproject.toml` — no `additional_dependencies` needed.

## Quick start

In a consumer repo's `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/seimei-d/systemrdl-pre-commit-hooks
    rev: main      # replace with a tag once you cut one
    hooks:
      - id: systemrdl-to-ipxact
      - id: asciidoc-addrmap
      # - id: ipxact-to-systemrdl
      #   args: [--input=external/foo.xml, --output=regmap/foo.rdl]
```

Place SystemRDL sources under `regmap/`. On commit, the regenerated XML / AsciiDoc
files are written into `ipxact/` and `asciidoc/` respectively, mirroring the
**relative** path under `regmap/`:

```
regmap/blockA/regs.rdl  →  ipxact/blockA/regs.xml
                        →  asciidoc/blockA/regs.adoc
```

The `regmap/` prefix is stripped — output paths use the source layout *inside*
`--input-dir`, not the layout from repo root.

---

## `systemrdl-to-ipxact`

Compiles every staged `regmap/**/*.rdl` via the
[`peakrdl-ipxact`](https://peakrdl-ipxact.readthedocs.io/) Python API and writes
IP-XACT XML next to the source tree under `--output-dir`.

### CLI flags

| Flag | Default | Description |
|---|---|---|
| positional `FILES…` | — | RDL files to convert. Pre-commit fills these in automatically. |
| `--input-dir DIR` | `regmap` | Source root; output paths are computed relative to it. Also used for fallback scan when no files are passed. |
| `--output-dir DIR` | `<repo>/ipxact` | Where XML lands. Mirrors the source tree relative to `--input-dir`. |
| `-I/--incdir DIR` | — | Add a search path for `` `include `` directives. Repeatable. |
| `--exclude PATTERN` | — | fnmatch-style; matches against full path *and* basename. Repeatable. |
| `--vendor STR` | `example.org` | IP-XACT `<vendor>`. |
| `--library STR` | `mylibrary` | IP-XACT `<library>`. |
| `--version STR` | `1.0` | IP-XACT component `<version>`. |
| `--standard {auto,2009,2014}` | `auto` | `auto` reuses the existing target file's `xmlns` if any, else IEEE 1685-2014. |

### Example consumer config

```yaml
- id: systemrdl-to-ipxact
  args:
    - --vendor=acme.com
    - --library=peripherals
    - --version=1.2
    - --standard=2014
    - --output-dir=build/ipxact
    - -I=lib/rdl
    - --exclude=*_pkg.rdl
```

---

## `asciidoc-addrmap`

For each staged `regmap/**/*.rdl`, renders a one-row-per-block AsciiDoc table of
its **first-level** `addrmap` and `mem` children. Files without first-level
subsystems produce no output (any stale `.adoc` is removed).

The table columns:

| Block name | Block type | Start address | End address | Region size | Parameters |
|---|---|---|---|---|---|

- **Block type**: `mem` for memory regions, the addrmap *type* name otherwise.
- **Region size**: power-of-2 units — `B`, `KiB`, `MiB`, `GiB`.
- **Parameters**: `NAME=value, NAME=value, …` resolved from `inst.parameters`, or `—` if none.

Cells are padded so that pipe separators line up vertically in the raw `.adoc`.

### CLI flags

| Flag | Default | Description |
|---|---|---|
| positional `FILES…` | — | RDL files to render. Pre-commit fills these in automatically. |
| `--input-dir DIR` | `regmap` | Source root; same semantics as in `systemrdl-to-ipxact`. |
| `--output-dir DIR` | `<repo>/asciidoc` | Where `.adoc` lands. |
| `-I/--incdir DIR` | — | `` `include `` search path. Repeatable. |
| `--exclude PATTERN` | — | fnmatch on path + basename. Repeatable. |

### Pinning to a single aggregator file

If you want the table generated for one specific top-level file (and never for
leaf register blocks), override pre-commit's filename machinery in your config:

```yaml
- id: asciidoc-addrmap
  pass_filenames: false
  always_run: true
  args:
    - regmap/multiple_ss.rdl
    - --output-dir=docs/maps
```

### Example output

```
= Address map: ss

[cols="1,1,1,1,1,2",options="header"]
|===
| Block name | Block type | Start address | End address | Region size | Parameters
| abc        | ABC        | 0x00000000    | 0x00000003  | 4 B         | —
| bcd        | BCD        | 0x00001000    | 0x00001007  | 8 B         | P=7
| sram       | mem        | 0x00010000    | 0x00010FFF  | 4 KiB       | —
|===
```

---

## `ipxact-to-systemrdl`

Reverse direction. Imports a single IP-XACT XML file via
[`peakrdl-ipxact`](https://peakrdl-ipxact.readthedocs.io/)'s `IPXACTImporter` and
writes the result with [`peakrdl-systemrdl`](https://pypi.org/project/peakrdl-systemrdl/)
as a `.rdl` source file. Both source and target paths are required — there is no
batch / glob mode.

### CLI flags

| Flag | Required | Description |
|---|---|---|
| `-i/--input PATH` | yes | IP-XACT XML to import. **Errors with exit 1 if missing.** |
| `-o/--output PATH` | yes | Target SystemRDL file. Parent dirs are created. |
| `--flatten` | no | Strip the IP-XACT component/memoryMap wrapper. See below. |

### Consumer config

```yaml
- id: ipxact-to-systemrdl
  args:
    - --input=external/vendor_block.xml
    - --output=regmap/vendor_block.rdl
```

The hook is shipped with `pass_filenames: false` and `always_run: true` so the
file pair is always taken from `args:` rather than from pre-commit's diff.

### Caveats

- Without `--flatten`, round-tripped names get nested (`addrmap foo__foo_mmap { addrmap { … } };`)
  because IP-XACT has three layers (`component → memoryMap → addressBlock`) while
  SystemRDL has two. This comes from peakrdl's importer, not from us.
- `<busInterface>`, `<vendorExtensions>`, signed integer hints, and other
  IP-XACT-only constructs are dropped on the way back to RDL.

### Flattening (workaround for the wrapper)

Pass `--flatten` and the wrapper layer is dropped: if the imported top addrmap
contains exactly one addrmap child (the addressBlock), that child is exported
directly. The leading type name is also trimmed at the last `__` so the result
reads cleanly:

```yaml
- id: ipxact-to-systemrdl
  args:
    - --input=external/foo.xml
    - --output=regmap/foo.rdl
    - --flatten
```

```diff
- addrmap foo__foo_mmap {
-     addrmap {
-         reg { … } CTRL @ 0x0;
-     };
- };
+ addrmap foo {
+     reg { … } CTRL @ 0x0;
+ };
```

Skip `--flatten` if the source is a *real* multi-addressBlock IP-XACT component —
in that case the wrapper carries meaningful structure and stripping it would lose
data.

---

## Local development

Uses [`uv`](https://docs.astral.sh/uv/):

```bash
uv venv
uv pip install -e '.[test]'
uv run pytest -q
```

Run any CLI directly:

```bash
uv run systemrdl-to-ipxact regmap/foo.rdl
uv run asciidoc-addrmap regmap/multiple_ss.rdl
uv run ipxact-to-systemrdl --input external/foo.xml --output regmap/foo.rdl
```

### Behind a corporate PyPI mirror

If your `pip.conf` points at a mirror that doesn't carry `peakrdl-ipxact` /
`peakrdl-systemrdl`, add public PyPI as a fallback:

```ini
# ~/.config/pip/pip.conf
[global]
index-url = https://your.mirror/simple/
extra-index-url = https://pypi.org/simple/
```

`pre-commit` builds its hook venvs with the same `pip` configuration — no
hook-specific override needed.

## Adding a new hook

1. Create `src/pre_commit_scripts/<hook_name>/cli.py` exposing `main(argv=None) -> int`.
2. Add a `[project.scripts]` entry in `pyproject.toml`:
   `<hook-name> = "pre_commit_scripts.<hook_name>.cli:main"`.
3. Append a stanza to `.pre-commit-hooks.yaml` with the new `id`, `entry`, and
   either a `files:` regex (file-driven hook) or `pass_filenames: false` +
   `always_run: true` (config-driven hook).
4. Add tests under `tests/test_<hook_name>.py`.
