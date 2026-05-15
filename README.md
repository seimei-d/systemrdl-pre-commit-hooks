# systemrdl-pre-commit-hooks

Collection of [pre-commit](https://pre-commit.com/) hooks for SystemRDL register-map
workflows: SystemRDL ⇄ IP-XACT conversion and AsciiDoc tables of address maps.

| Hook id | Direction / output | Trigger |
|---|---|---|
| [`systemrdl-to-ipxact`](#systemrdl-to-ipxact) | SystemRDL → IP-XACT XML | every staged `regmap/**/*.rdl` |
| [`asciidoc-addrmap`](#asciidoc-addrmap) | SystemRDL → AsciiDoc address-map table | every staged `regmap/**/*.rdl` |
| [`ipxact-to-systemrdl`](#ipxact-to-systemrdl) | IP-XACT XML → SystemRDL | one explicit file pair, configured in `args` |
| [`systemrdl-to-verilog`](#systemrdl-to-verilog) | SystemRDL → SystemVerilog register block (`peakrdl-regblock`) | every staged `regmap/**/*.rdl` |
| [`systemrdl-to-uvm`](#systemrdl-to-uvm) | SystemRDL → UVM register model (`peakrdl-uvm`) | every staged `regmap/**/*.rdl` |

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

## `systemrdl-to-verilog`

Generates a synthesizable SystemVerilog register block (module + `_pkg`) from each
staged `regmap/**/*.rdl` using
[`peakrdl-regblock`](https://peakrdl-regblock.readthedocs.io/). Each RDL gets its
own output subdirectory (named after the source stem) so that several blocks can
coexist under one `--output-dir` without `*_pkg.sv` collisions:

```
regmap/blockA/regs.rdl  →  rtl/regmap/blockA/regs/regs.sv
                       →  rtl/regmap/blockA/regs/regs_pkg.sv
```

### CLI flags

| Flag | Default | Description |
|---|---|---|
| positional `FILES…` | — | RDL files to convert. Pre-commit fills these in automatically. |
| `--input-dir DIR` | `regmap` | Source root; output paths mirror layout under it. |
| `--output-dir DIR` | `rtl/regmap` | Where the generated `.sv` lands. |
| `-I/--incdir DIR` | — | `` `include `` search path. Repeatable. |
| `--exclude PATTERN` | — | fnmatch on path + basename. Repeatable. |
| `--cpuif {apb3,apb3-flat,apb4,apb4-flat,axi4-lite,axi4-lite-flat,avalon,avalon-flat,obi,obi-flat,wishbone,wishbone-flat,passthrough}` | `apb4-flat` | CPU interface. `-flat` variants expose plain signals; the non-flat variants reference a SystemVerilog `interface` (e.g. `apb4_intf`) that you must declare elsewhere in your design. |
| `--module-name TEMPLATE` | `{name}` | Module-name template. `{name}` is replaced with the top addrmap's name (e.g. `{name}_regs`). |
| `--package-name TEMPLATE` | `{name}_pkg` | Package-name template, same placeholders. |
| `--reset-polarity {active-low,active-high}` | `active-low` | Default reset polarity when the RDL doesn't pin one. |
| `--reset-sync {async,sync}` | `async` | Default reset synchronicity when the RDL doesn't pin one. |
| `--retime-read-fanin` | off | Insert a flop in the readback fan-in path (+1 read latency). |
| `--retime-read-response` | off | Insert a flop between the readback mux and CPU response logic (+1 read latency). |
| `--retime-external-reg/-regfile/-mem/-addrmap` | off | Retime outputs to external components of the corresponding kind. |
| `--hwif-report` | off | Also emit `<module>_hwif.rpt` describing `hwif_in` / `hwif_out`. |

### Running on a single file

The CLI accepts plain positional paths, so any `regmap/**/*.rdl` works as a
one-shot invocation outside pre-commit:

```bash
uv run systemrdl-to-verilog regmap/blockA/regs.rdl
# → rtl/regmap/blockA/regs/regs.sv
# → rtl/regmap/blockA/regs/regs_pkg.sv
```

With a non-default CPU interface, a custom module name, and a custom output dir:

```bash
uv run systemrdl-to-verilog \
    --cpuif=axi4-lite-flat \
    --module-name='{name}_regs' \
    --output-dir=build/rtl \
    regmap/blockA/regs.rdl
```

### Example consumer config

```yaml
- id: systemrdl-to-verilog
  args:
    - --cpuif=apb4-flat
    - --module-name={name}_regs
    - --reset-polarity=active-low
    - --reset-sync=async
    - --output-dir=rtl/regs
    - -I=lib/rdl
    - --exclude=*_pkg.rdl
```

---

## `systemrdl-to-uvm`

Generates a UVM register model (RAL) from each staged `regmap/**/*.rdl` using
[`peakrdl-uvm`](https://github.com/SystemRDL/PeakRDL-uvm). Unlike the regblock
hook (which produces a directory of synthesizable RTL), this hook writes **one
SystemVerilog file per RDL** containing a `package` with `uvm_reg` /
`uvm_reg_block` class definitions:

```
regmap/blockA/regs.rdl  →  dv/uvm_regmodel/blockA/regs_uvm.sv
```

The output is a *model only* — no bus adapter, no agent, no monitor. Wiring it
into a testbench is described under [Using the generated model](#using-the-generated-model-in-a-uvm-env).

### CLI flags

| Flag | Default | Description |
|---|---|---|
| positional `FILES…` | — | RDL files to convert. Pre-commit fills these in automatically. |
| `--input-dir DIR` | `regmap` | Source root; output paths mirror layout under it. |
| `--output-dir DIR` | `dv/uvm_regmodel` | Where the generated `.sv` lands. |
| `-I/--incdir DIR` | — | `` `include `` search path. Repeatable. |
| `--exclude PATTERN` | — | fnmatch on path + basename. Repeatable. |
| `--file-name TEMPLATE` | `{name}_uvm` | Output file-stem template. `{name}` = RDL filename stem. The same stem becomes the SystemVerilog **package** name. |
| `--as-include` | off | Emit an includable header (no `package … endpackage` wrapper). |
| `--no-reuse-classes` | off | Disable class-deduplication. Class names then follow each instance's hierarchical path. |
| `--use-factory` | off | Emit `\`uvm_object_utils` + `type_id::create()` so generated classes can be overridden via the UVM factory. |

### Running on a single file

```bash
uv run systemrdl-to-uvm regmap/blockA/regs.rdl
# → dv/uvm_regmodel/blockA/regs_uvm.sv  (package regs_uvm; …)
```

With factory support and a custom file/package name:

```bash
uv run systemrdl-to-uvm \
    --use-factory \
    --file-name='{name}_ral' \
    --output-dir=dv/ral \
    regmap/blockA/regs.rdl
# → dv/ral/blockA/regs_ral.sv  (package regs_ral; … with factory)
```

### Example consumer config

```yaml
- id: systemrdl-to-uvm
  args:
    - --output-dir=dv/uvm_regmodel
    - --file-name={name}_ral
    - --use-factory
    - -I=lib/rdl
    - --exclude=*_pkg.rdl
```

---

## Using the generated model in a UVM env

The exporter only produces a register-class hierarchy. To actually drive
registers through your bus, you need three more things on the testbench side:
**compile the file**, **write a bus adapter** (one-time, per bus type), and
**wire the model into your env**. Below is a minimal end-to-end skeleton based
on what `systemrdl-to-uvm` emits for `tests/fixtures/sample.rdl`.

### 1. What the generated file looks like

For an `addrmap sample` containing `CTRL` and `STATUS` regs, the hook emits a
single file with shape:

```systemverilog
// dv/uvm_regmodel/sample_uvm.sv
package sample_uvm;
    `include "uvm_macros.svh"
    import uvm_pkg::*;

    class sample__CTRL extends uvm_reg;
        rand uvm_reg_field enable;
        rand uvm_reg_field mode;
        function new(string name = "sample__CTRL");
            super.new(name, 32, UVM_NO_COVERAGE);
        endfunction
        virtual function void build();
            this.enable = new("enable");
            this.enable.configure(this, 1, 0, "RW", 0, 'h0, 1, 1, 0);
            this.mode   = new("mode");
            this.mode  .configure(this, 3, 1, "RW", 0, 'h0, 1, 1, 0);
        endfunction
    endclass

    class sample__STATUS extends uvm_reg; … endclass

    class sample extends uvm_reg_block;
        rand sample__CTRL   CTRL;
        rand sample__STATUS STATUS;
        function void build();
            this.default_map = create_map("reg_map", 0, 4, UVM_NO_ENDIAN);
            this.CTRL = new("CTRL");   this.CTRL.configure(this);
            this.CTRL.build();         this.default_map.add_reg(this.CTRL,   'h0);
            this.STATUS = new("STATUS"); this.STATUS.configure(this);
            this.STATUS.build();       this.default_map.add_reg(this.STATUS, 'h4);
        endfunction
    endclass
endpackage
```

Things to notice before going further:
- **Package name = file stem** (here `sample_uvm`). That's why we control naming
  via `--file-name`, not a separate `--package-name` flag — they're the same
  knob.
- **`UVM_NO_COVERAGE`** is hard-coded in the current exporter. Functional
  coverage on registers needs to be added manually on top.
- **`address bus width = 4` (bytes)** in `create_map(...)` is inferred from
  `regwidth = 32`. Override at base address level with `set_base_addr` (see
  below) — the offsets inside `default_map` are RDL offsets, not absolute.

### 2. Compile alongside UVM

It's a plain SV package. Add to your filelist:
```
+incdir+$UVM_HOME/src
$UVM_HOME/src/uvm.sv
dv/uvm_regmodel/sample_uvm.sv     # generated by the hook
dv/env/...                        # your env, agents, sequences
```
And in your env/test files:
```systemverilog
import uvm_pkg::*;
`include "uvm_macros.svh"
import sample_uvm::*;
```

### 3. The bus adapter (the missing piece)

The exporter is bus-agnostic, so you write a `uvm_reg_adapter` once per bus
type. It translates the abstract `uvm_reg_bus_op` ⇄ your agent's sequence item.
For a typical APB agent with an `apb_xact` item:

```systemverilog
class apb_reg_adapter extends uvm_reg_adapter;
    `uvm_object_utils(apb_reg_adapter)
    function new(string name = "apb_reg_adapter");
        super.new(name);
        supports_byte_enable = 0;   // set 1 if your IP honors PSTRB
        provides_responses   = 1;
    endfunction

    // UVM → bus
    virtual function uvm_sequence_item reg2bus(const ref uvm_reg_bus_op rw);
        apb_xact t = apb_xact::type_id::create("t");
        t.addr  = rw.addr;
        t.data  = rw.data;
        t.write = (rw.kind == UVM_WRITE);
        return t;
    endfunction

    // bus → UVM
    virtual function void bus2reg(uvm_sequence_item bus_item, ref uvm_reg_bus_op rw);
        apb_xact t;
        if (!$cast(t, bus_item)) `uvm_fatal(get_type_name(), "bad bus item")
        rw.kind   = t.write ? UVM_WRITE : UVM_READ;
        rw.addr   = t.addr;
        rw.data   = t.data;
        rw.status = (t.resp == 0) ? UVM_IS_OK : UVM_NOT_OK;
    endfunction
endclass
```

For AXI4-Lite, OBI, or Wishbone the shape is identical — only the field copy
inside `reg2bus`/`bus2reg` changes. If you already use a third-party UVC, it
almost certainly ships its own adapter; use that one.

### 4. Env: build, lock, connect, (predictor)

```systemverilog
class my_env extends uvm_env;
    sample              regmodel;      // generated class
    apb_agent           m_apb;
    apb_reg_adapter     m_adapter;
    uvm_reg_predictor#(apb_xact) m_predictor;
    `uvm_component_utils(my_env)

    function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        m_apb      = apb_agent       ::type_id::create("m_apb",      this);
        regmodel   = sample          ::type_id::create("regmodel",   this);
        regmodel.build();              // populate inner uvm_reg / fields
        regmodel.lock_model();         // freeze addresses & topology
        m_adapter  = apb_reg_adapter ::type_id::create("m_adapter");
        m_predictor= uvm_reg_predictor#(apb_xact)
                     ::type_id::create("m_predictor", this);
    endfunction

    function void connect_phase(uvm_phase phase);
        super.connect_phase(phase);
        // 1. Route register accesses through the APB agent's sequencer.
        regmodel.default_map.set_sequencer(m_apb.sequencer, m_adapter);
        // 2. Place the block at its system-level address (if not at 0).
        regmodel.default_map.set_base_addr('h4000_0000);
        // 3. (Optional) Passive prediction: model follows what the monitor sees,
        //    so mirror()/check() works even when other masters write.
        m_predictor.map     = regmodel.default_map;
        m_predictor.adapter = m_adapter;
        m_apb.monitor.ap.connect(m_predictor.bus_in);
    endfunction
endclass
```

Why each line matters:
- **`build()` then `lock_model()`** — without `lock_model`, address decoding is
  not finalized and `mirror`/`update` will misbehave.
- **`set_sequencer(seq, adapter)`** — this is what binds the abstract register
  model to a real bus driver. Skip this and any `reg.write()` will hang.
- **`set_base_addr(...)`** — RDL offsets are local to the addrmap. If the IP
  sits at, say, `0x4000_0000` on your SoC bus, you set it here (the model has
  no idea about system-level addressing otherwise).
- **Predictor is optional but usually wanted**. Without it, `mirror` / `check`
  only know about the writes the model *issued itself*. With it, the model
  stays in sync with anything the monitor sees on the bus — needed for
  multi-master scenarios or for trapping HW-driven changes to W1C / RC fields.

### 5. Using it from sequences

After all of the above, register accesses look like this:

```systemverilog
class my_seq extends uvm_sequence;
    `uvm_object_utils(my_seq)
    sample regmodel;     // handle passed in by the test

    virtual task body();
        uvm_status_e   status;
        uvm_reg_data_t rd;

        // Write by field (desired-value buffer + update())
        regmodel.CTRL.enable.set(1'b1);
        regmodel.CTRL.mode  .set(3'b011);
        regmodel.CTRL.update(status);     // emits one APB write of CTRL

        // Read & auto-check against the mirror
        regmodel.STATUS.mirror(status, UVM_CHECK);

        // Or raw read/write
        regmodel.CTRL.read (status, rd);
        regmodel.CTRL.write(status, 'hF);
    endtask
endclass
```

In the test:
```systemverilog
my_seq seq = my_seq::type_id::create("seq");
seq.regmodel = env.regmodel;
seq.start(env.m_apb.sequencer);
```

### 6. Common gotchas

- **Hanging on first `write()`** → you forgot `set_sequencer(adapter)`, or
  forgot to set the sequencer's run-phase objection handling. The model just
  hands the item to the sequencer; if no driver picks it up, it sits forever.
- **`mirror()` reports a mismatch for HW-only fields** → without a predictor,
  the model doesn't know about HW-driven changes. Add the predictor, or call
  `regmodel.STATUS.predict(value, .kind(UVM_PREDICT_READ))` manually.
- **Two `addrmap`s collide** → with `--no-reuse-classes` class names are
  globally unique. Without it, classes are deduplicated by lexical scope, which
  is fine for one model per package but can surprise you if you import several
  packages with overlapping RDL type names.
- **Want to override a class via the UVM factory** → you must regenerate with
  `--use-factory`. Otherwise `type_id::create()` is not emitted and factory
  overrides have nothing to hook into.
- **Coverage** → not emitted; the model passes `UVM_NO_COVERAGE`. If you need
  functional cover on register fields, build a small subclass that wraps the
  generated `uvm_reg_block` and adds `covergroup`s. Factory overrides
  (`--use-factory`) are the cleanest way to slot the subclass in without
  editing the generated file.

### 7. Pairing with `systemrdl-to-verilog`

The whole point of having both hooks is that **the same RDL drives both the
DUT and the model**. Recommended consumer config:

```yaml
- id: systemrdl-to-verilog
  args:
    - --cpuif=apb4-flat
    - --output-dir=rtl/regs
- id: systemrdl-to-uvm
  args:
    - --output-dir=dv/uvm_regmodel
    - --use-factory
```

Now any field added/moved/widened in `regmap/*.rdl` shows up in lock-step on
both sides on the next commit — the testbench can't drift away from the DUT,
which is the whole reason for RAL in the first place.

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
uv run systemrdl-to-verilog regmap/foo.rdl
uv run systemrdl-to-uvm regmap/foo.rdl
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
