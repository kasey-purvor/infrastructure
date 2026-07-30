#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["rich>=13", "plotext>=5"]
# ///
"""temps — full-page hardware dashboard (a TOOL, not a service).

This is a *client*. LibreHardwareMonitor on the Windows side reads the physical
sensors (WSL is a VM and can't) and serves them as JSON on :8085. This polls that
endpoint and draws a clustered, colour-coded dashboard with a 30-minute history
chart. Close the terminal and it's gone — htop-shaped, not a daemon.

    temps          live dashboard, full-screen, refreshing in place (default)
    temps --once    one snapshot (no chart), then exit — for scripts/status bars
    temps -n 5      refresh every 5s instead of 2

History is in memory and fills as the tool runs; it isn't persisted across
restarts (that would be the collector *service* we deliberately didn't build).
Park it in a tmux pane and it accumulates hours.

Layout: rich.Layout (ratio'd regions that fill the screen, so no dead gaps).
Curation rule — only actionable sensors. Deliberately excluded: voltages,
per-core power/clock, the display-only AMD iGPU, NVMe lifetime totals, D3D
engine loads, idle/virtual NICs.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.request
from collections import defaultdict, deque
from urllib.error import URLError

from rich.console import Console, Group
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

DEFAULT_URL = "http://localhost:8085/data.json"
HIST_MINUTES = 30
BLOCKS = "▁▂▃▄▅▆▇█"

# Throttle/critical temp limits and nominal power ceilings — drive bar fill+colour.
LIM_CPU, LIM_GPU, LIM_GPU_HOT, LIM_DIMM, LIM_NVME, LIM_SATA = 95, 93, 105, 85, 86, 70
PPT_CPU, TGP_GPU = 162, 350  # Ryzen 9900X package power tracking; RTX 3090 board power

DRIVES = [
    ("Crucial T705", "CT2000T705", "Composite Temperature", LIM_NVME),
    ("Corsair MP700", "MP700", "Composite Temperature", LIM_NVME),
    ("Kingston SATA", "KINGSTON", "Temperature", LIM_SATA),
]

# Fan-header → friendly name, confirmed against HWiNFO (which labels the same
# Nuvoton headers). The enumeration order matches, and HWiNFO's skipped "Chassis
# 4" lines up with Fan #5 being the empty 0-RPM header — so CPU = Fan #2, AIO
# pump = Fan #7. Fan #5 (0 RPM) is auto-hidden.
FAN_LABELS = {
    "Fan #1": "Chassis 1", "Fan #2": "CPU", "Fan #3": "Chassis 2",
    "Fan #4": "Chassis 3", "Fan #6": "Chassis 5", "Fan #7": "AIO Pump",
    "GPU Fan 1": "GPU 1", "GPU Fan 2": "GPU 2",
}

_NUM = re.compile(r"-?\d+(?:\.\d+)?")


# ── data layer ────────────────────────────────────────────────────────────────
def fetch(url: str, timeout: float = 3.0) -> dict | None:
    try:
        import json
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.load(resp)
    except (URLError, TimeoutError, OSError, ValueError):
        return None


def parse_value(raw: str) -> tuple[float | None, str]:
    m = _NUM.search(raw)
    return (float(m.group()), raw[m.end():].strip()) if m else (None, "")


def extract(data: dict) -> list[dict]:
    """Flatten the tree into {device, category, sensor, value, unit} rows."""
    rows: list[dict] = []
    children = data.get("Children") or [{}]
    for device in children[0].get("Children", []):
        dname = device.get("Text", "")

        def walk(node: dict, parent: str) -> None:
            text = node.get("Text", "")
            value = node.get("Value")
            if isinstance(value, str) and value.strip():
                num_, unit = parse_value(value)
                if num_ is not None:
                    rows.append({"device": dname, "category": parent,
                                 "sensor": text, "value": num_, "unit": unit})
            for child in node.get("Children", []):
                walk(child, text)

        walk(device, "")
    return rows


def find(rows, sensor, *, device="", unit="", category="", prefix=False, agg="first") -> dict | None:
    hits = [
        r for r in rows
        if (not device or device.lower() in r["device"].lower())
        and (not unit or r["unit"] == unit)
        and (not category or r["category"] == category)
        and (r["sensor"].startswith(sensor) if prefix else r["sensor"] == sensor)
    ]
    if not hits:
        return None
    return max(hits, key=lambda r: r["value"]) if agg == "max" else hits[0]


def num(item) -> float | None:
    return item["value"] if item else None


# ── render helpers ──────────────────────────────────────────────────────────────
def sev(value, limit) -> str:
    if value is None:
        return "grey37"
    if limit:
        ratio = value / limit
        return "bold red" if ratio >= 0.90 else "yellow" if ratio >= 0.70 else "green"
    return "bold red" if value >= 85 else "yellow" if value >= 70 else "green"


def bar(frac, style, width) -> Text:
    frac = max(0.0, min(1.0, frac))
    filled = round(frac * width)
    out = Text()
    out.append("█" * filled, style=style)
    out.append("░" * (width - filled), style="grey37")
    return out


def grid4(value_justify="right") -> Table:
    g = Table.grid(padding=(0, 1))
    g.add_column()                      # label
    g.add_column(justify=value_justify)  # value
    g.add_column()                      # bar
    g.add_column()                      # tail
    return g


def vrow(g, label, value_text, frac, style, tail="", barw=18):
    g.add_row(label if isinstance(label, Text) else Text(label),
              value_text,
              bar(frac, style, barw) if frac is not None else Text(""),
              tail if isinstance(tail, Text) else Text(tail, style="grey50"))


def add_temp(g, label, value, limit, barw):
    if value is None:
        g.add_row(Text(label), Text("—", style="grey37"), Text(""), Text(""))
        return
    s = sev(value, limit)
    vrow(g, label, Text(f"{value:.1f}°", style=s), (value / limit if limit else None),
         s, (f"{value / limit * 100:.0f}%" if limit else ""), barw)


def add_pwr(g, label, watts, ceiling, barw, tail=""):
    if watts is None:
        g.add_row(Text(label), Text("—", style="grey37"), Text(""), Text(""))
        return
    s = sev(watts, ceiling)
    vrow(g, label, Text(f"{watts:.0f} W"), watts / ceiling, s,
         tail or f"{watts / ceiling * 100:.0f}%", barw)


def add_pct(g, label, pct, barw, value_suffix="%"):
    if pct is None:
        g.add_row(Text(label), Text("—", style="grey37"), Text(""), Text(""))
        return
    s = sev(pct, 100)
    vrow(g, label, Text(f"{pct:.0f}{value_suffix}"), pct / 100, s, "", barw)


def kbs(item) -> float:
    return 0.0 if not item else item["value"] * (1024 if item["unit"] == "MB/s" else 1.0)


def fmt_rate(kb) -> str:
    return f"{kb / 1024:.1f} MB/s" if kb >= 1024 else f"{kb:.0f} KB/s"


# ── panels ───────────────────────────────────────────────────────────────────
def cpu_cores(rows) -> list[float]:
    """Per-physical-core load %: fold the two SMT threads of each core together.

    LHM reports 24 logical threads ("CPU Core #1..24"); we average sibling pairs
    into 12 physical cores. Cores 1-6 sit on CCD1, 7-12 on CCD2. (Assumes Windows'
    standard AMD enumeration — SMT siblings adjacent, CCD0 first — which a
    single-threaded load test confirms.)
    """
    threads = [r for r in rows if r["category"] == "Load" and r["sensor"].startswith("CPU Core #")]
    threads.sort(key=lambda r: int(re.search(r"#(\d+)", r["sensor"]).group(1)))
    vals = [r["value"] for r in threads]
    return [sum(vals[i:i + 2]) / 2 for i in range(0, len(vals), 2)]  # 24 threads -> 12 cores


def die_block(label, die_temp, core_loads, first_core) -> Group:
    """A labelled per-die column for the per-core grid.

    Self-explaining: the header carries the die's temperature (°), the table is
    headed 'core / load' so the numbers are unambiguous, each row is one physical
    core's load (%), and the final row is the die's average load.
    """
    head = Text.assemble(
        (f"{label}  ", "bold"),
        (f"{die_temp:.0f}°" if die_temp is not None else "—°", sev(die_temp, LIM_CPU)),
        ("  die", "grey42"),
    )
    tbl = Table.grid(padding=(0, 2))
    tbl.add_column(justify="left")
    tbl.add_column(justify="right")
    tbl.add_row(Text("core", style="grey46"), Text("load", style="grey46"))
    for i, load in enumerate(core_loads):
        cstyle = "green" if load < 50 else "yellow" if load < 80 else "bold red"
        tbl.add_row(Text(f"C{first_core + i}", style="grey70"), Text(f"{load:.0f}%", style=cstyle))
    avg = sum(core_loads) / len(core_loads) if core_loads else 0.0
    tbl.add_row(Text("avg", style="grey46"), Text(f"{avg:.0f}%", style="bold grey78"))
    return Group(head, tbl)


def cpu_panel(rows) -> Panel:
    # left: whole-CPU rollup (overall temperature + load), centred vertically
    rollup = grid4()
    add_temp(rollup, "Tctl", num(find(rows, "Core (Tctl/Tdie)", device="Ryzen")), LIM_CPU, 14)
    clk = num(find(rows, "Cores (Average)", device="Ryzen"))
    add_pwr(rollup, "Power", num(find(rows, "Package", device="Ryzen", category="Powers")),
            PPT_CPU, 14, tail=f"{clk:.0f} MHz" if clk else "")
    add_pct(rollup, "Load", num(find(rows, "CPU Total", device="Ryzen")), 14)

    # right: per-core load laid out as two die columns (6 physical cores each)
    cores = cpu_cores(rows)
    ccd1 = die_block("CCD1", num(find(rows, "CCD1 (Tdie)", device="Ryzen")), cores[0:6], 1)
    ccd2 = die_block("CCD2", num(find(rows, "CCD2 (Tdie)", device="Ryzen")), cores[6:12], 7)

    outer = Table.grid(padding=(0, 3))
    outer.add_column(vertical="middle")  # rollup — centred against the taller die columns
    outer.add_column(vertical="top")     # CCD1
    outer.add_column(vertical="top")     # CCD2
    outer.add_row(rollup, ccd1, ccd2)
    return Panel(outer, title="CPU · Ryzen 9 9900X", title_align="left", border_style="cyan", padding=(0, 1))


def gpu_panel(rows) -> Panel:
    g = grid4()
    add_temp(g, "Core", num(find(rows, "GPU Core", device="NVIDIA", category="Temperatures")), LIM_GPU, 20)
    add_temp(g, "Hot spot", num(find(rows, "GPU Hot Spot", device="NVIDIA")), LIM_GPU_HOT, 20)
    add_temp(g, "Mem jct", num(find(rows, "GPU Memory Junction", device="NVIDIA")), LIM_GPU_HOT, 20)
    gclk = num(find(rows, "GPU Core", device="NVIDIA", category="Clocks"))
    add_pwr(g, "Power", num(find(rows, "GPU Package", device="NVIDIA", category="Powers")),
            TGP_GPU, 20, tail=f"{gclk:.0f} MHz" if gclk is not None else "")
    add_pct(g, "Util", num(find(rows, "GPU Core", device="NVIDIA", category="Load")), 20)
    used = num(find(rows, "GPU Memory Used", device="NVIDIA"))
    total = num(find(rows, "GPU Memory Total", device="NVIDIA"))
    if used and total:
        s = sev(used / total * 100, 100)
        vrow(g, "VRAM", Text(f"{used / 1024:.1f}/{total / 1024:.0f} GB"), used / total, s, "", 20)
    return Panel(g, title="GPU · RTX 3090", title_align="left", border_style="green", padding=(0, 1))


def memory_panel(rows) -> Panel:
    g = grid4()
    used = num(find(rows, "Memory Used", device="Total Memory"))
    avail = num(find(rows, "Memory Available", device="Total Memory"))
    usage = num(find(rows, "Memory", device="Total Memory", category="Load"))
    if used and avail:
        total = used + avail
        s = sev(usage or 0, 100)
        vrow(g, "RAM", Text(f"{used:.0f}/{total:.0f} GB"), used / total, s,
             f"{usage:.0f}%" if usage is not None else "", 12)
    for i in range(4):
        add_temp(g, f"DIMM {i}", num(find(rows, f"DIMM #{i}", category="Temperatures")), LIM_DIMM, 12)
    return Panel(g, title="Memory", title_align="left", border_style="magenta", padding=(0, 1))


def storage_panel(rows) -> Panel:
    g = Table.grid(padding=(0, 1))
    g.add_column(); g.add_column(justify="right"); g.add_column(); g.add_column()
    for label, dev, sensor, limit in DRIVES:
        t = num(find(rows, sensor, device=dev))
        rd, wr = kbs(find(rows, "Read Rate", device=dev)), kbs(find(rows, "Write Rate", device=dev))
        full = num(find(rows, "Used Space", device=dev))
        if rd < 0.1 and wr < 0.1:
            # idle: show capacity if the drive reports it, else just "idle"
            io = Text(f"{full:.0f}% full", style="grey50") if full is not None else Text("idle", style="grey37")
        else:
            io = Text()
            if wr >= 0.1:
                io.append("↑" + fmt_rate(wr) + " ", style="yellow")
            if rd >= 0.1:
                io.append("↓" + fmt_rate(rd), style="cyan")
        s = sev(t, limit)
        g.add_row(Text(label), Text(f"{t:.0f}°", style=s) if t is not None else Text("—", style="grey37"),
                  bar(t / limit, s, 8) if t is not None else Text(""), io)
    return Panel(g, title="Storage", title_align="left", border_style="blue", padding=(0, 1))


def cooling_panel(rows) -> Panel:
    temps = grid4()
    add_temp(temps, "Board", num(find(rows, "Motherboard", category="Temperatures")), None, 10)
    add_temp(temps, "Socket", num(find(rows, "CPU", device="ProArt", category="Temperatures")), LIM_CPU, 10)

    fans = []
    for r in rows:
        if r["unit"] == "RPM" and r["value"] > 0:
            duty = num(find(rows, r["sensor"], category="Controls"))
            fans.append((FAN_LABELS.get(r["sensor"], r["sensor"]), int(r["value"]), duty))

    fg = Table.grid(padding=(0, 2))
    for _ in range(4):
        fg.add_column()
    fg.columns[1].justify = fg.columns[3].justify = "right"

    def cell(fan):
        name, rpm, duty = fan
        val = Text(f"{rpm}", style="bold red" if rpm >= 3000 else "grey70")
        if duty is not None:
            val.append(f" {duty:.0f}%", style="grey50")
        return Text(name), val

    for i in range(0, len(fans), 2):
        left = cell(fans[i])
        right = cell(fans[i + 1]) if i + 1 < len(fans) else (Text(""), Text(""))
        fg.add_row(left[0], left[1], right[0], right[1])

    return Panel(Group(temps, Text("fans · rpm / duty", style="grey50"), fg),
                 title="Cooling", title_align="left", border_style="cyan", padding=(0, 1))


def hottest(rows) -> tuple[str, float, float] | None:
    cands = [
        ("CPU", num(find(rows, "Core (Tctl/Tdie)", device="Ryzen")), LIM_CPU),
        ("GPU hot-spot", num(find(rows, "GPU Hot Spot", device="NVIDIA")), LIM_GPU_HOT),
        ("GPU core", num(find(rows, "GPU Core", device="NVIDIA", category="Temperatures")), LIM_GPU),
    ]
    ranked = sorted(((v / lim, name, v) for name, v, lim in cands if v is not None), reverse=True)
    if not ranked:
        return None
    ratio, name, v = ranked[0]
    return name, v, ratio


def header_panel(rows, host) -> Panel:
    g = Table.grid(expand=True)
    g.add_column(justify="left")
    g.add_column(justify="right")
    cpu_w = num(find(rows, "Package", device="Ryzen", category="Powers")) or 0
    gpu_w = num(find(rows, "GPU Package", device="NVIDIA", category="Powers")) or 0
    left = Text.assemble((host, "bold"), "    ", ("⚡ ", "yellow"),
                         (f"{cpu_w + gpu_w:.0f} W", "bold"), ("  CPU+GPU", "grey50"))
    hot = hottest(rows)
    if hot:
        name, v, ratio = hot
        left.append("      hottest ", style="grey50")
        left.append(f"{name} {v:.0f}°", style=sev(v, v / ratio) if ratio else "grey70")
    right = Text(time.strftime("%H:%M:%S"), style="grey50")
    g.add_row(left, right)
    return Panel(g, border_style="grey37", padding=(0, 1))


def footer_text(rows, hist) -> Text:
    agg: dict[str, dict[str, float]] = defaultdict(lambda: {"up": 0.0, "down": 0.0})
    for r in rows:
        if r["sensor"] in ("Upload Speed", "Download Speed"):
            agg[r["device"]]["up" if r["sensor"] == "Upload Speed" else "down"] = kbs(r)
    net = ""
    if agg:
        dev, flow = max(agg.items(), key=lambda kv: kv[1]["up"] + kv[1]["down"])
        net = "net idle" if flow["up"] + flow["down"] < 0.1 else \
            f"net {dev} ↑{fmt_rate(flow['up'])} ↓{fmt_rate(flow['down'])}"
    return Text(f"  {net}{'  ·  ' if net else '  '}refresh {hist.interval:g}s · ctrl-c quit", style="grey50")


def chart_panel(hist, width, height) -> Panel:
    cpu, gpu = list(hist.get("cpu")), list(hist.get("gpu"))
    if len(cpu) < 2:
        return Panel(Text("collecting history…  (fills as it runs)", style="grey50"),
                     title="Temperature · last 30 min", title_align="left", border_style="grey50")
    try:
        import plotext as plt
        plt.clf()
        plt.theme("clear")
        n = len(cpu)
        plt.plot([-(n - 1 - i) * hist.interval / 60 for i in range(n)], cpu, marker="braille", color="cyan", label="CPU")
        m = len(gpu)
        plt.plot([-(m - 1 - i) * hist.interval / 60 for i in range(m)], gpu, marker="braille", color="green", label="GPU")
        plt.plotsize(max(40, width - 6), max(8, height - 3))
        plt.xlabel("minutes ago")
        body: Text = Text.from_ansi(plt.build())
    except Exception as exc:  # never let a chart glitch kill the dashboard
        body = Text(f"(chart unavailable: {exc})", style="grey37")
    return Panel(body, title="Temperature · last 30 min", title_align="left", border_style="grey50")


# ── assembly + loop ────────────────────────────────────────────────────────────
class History:
    def __init__(self, interval: float):
        self.interval = interval
        maxlen = max(2, int(HIST_MINUTES * 60 / interval))
        self.data: dict[str, deque] = defaultdict(lambda: deque(maxlen=maxlen))

    def push(self, rows) -> None:
        self.data["cpu"].append(num(find(rows, "Core (Tctl/Tdie)", device="Ryzen")) or 0.0)
        self.data["gpu"].append(num(find(rows, "GPU Core", device="NVIDIA", category="Temperatures")) or 0.0)

    def get(self, key) -> deque:
        return self.data[key]


def host_of(data) -> str:
    return (data.get("Children") or [{}])[0].get("Text") or "host"


def live_layout(rows, hist, console, host) -> Layout:
    lay = Layout()
    lay.split_column(
        Layout(header_panel(rows, host), name="header", size=3),
        Layout(name="top", ratio=3),
        Layout(name="mid", ratio=4),
        Layout(name="chart", ratio=4),
        Layout(footer_text(rows, hist), name="footer", size=1),
    )
    lay["top"].split_row(Layout(cpu_panel(rows), name="cpu"), Layout(gpu_panel(rows), name="gpu"))
    lay["mid"].split_row(Layout(memory_panel(rows), name="mem"),
                         Layout(storage_panel(rows), name="storage"),
                         Layout(cooling_panel(rows), name="cooling"))
    chart_h = max(10, int((console.height - 4) * 4 / 11))
    lay["chart"].update(chart_panel(hist, console.width, chart_h))
    return lay


def once_group(rows, hist, host) -> Group:
    def row(*panels):
        t = Table.grid(expand=True)
        for _ in panels:
            t.add_column(ratio=1)
        t.add_row(*panels)
        return t

    return Group(header_panel(rows, host),
                 row(cpu_panel(rows), gpu_panel(rows)),
                 row(memory_panel(rows), storage_panel(rows), cooling_panel(rows)),
                 footer_text(rows, hist))


def down_panel(url) -> Panel:
    return Panel(Text(f"LibreHardwareMonitor unreachable at {url} — retrying…\n"
                      "is LHM running on Windows? (it autostarts at login)", style="bold red"),
                 title="hwtemps", title_align="left", border_style="red")


def run_once(url, console, hist) -> int:
    data = fetch(url)
    if not data:
        console.print(down_panel(url))
        return 1
    rows = extract(data)
    hist.push(rows)
    console.print(once_group(rows, hist, host_of(data)))
    return 0


def run_live(url, console, hist) -> int:
    from rich.live import Live
    try:
        with Live(console=console, screen=True, auto_refresh=False) as live:
            while True:
                data = fetch(url)
                if data:
                    rows = extract(data)
                    hist.push(rows)
                    live.update(live_layout(rows, hist, console, host_of(data)))
                else:
                    live.update(down_panel(url))
                live.refresh()
                time.sleep(hist.interval)
    except KeyboardInterrupt:
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Full-page hardware dashboard (reads LibreHardwareMonitor on Windows).")
    parser.add_argument("--once", "-1", action="store_true", help="print one snapshot (no chart) and exit")
    parser.add_argument("--interval", "-n", type=float, default=2.0, metavar="SEC", help="live refresh interval (default: 2)")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"LHM endpoint (default: {DEFAULT_URL})")
    args = parser.parse_args()

    console = Console()
    hist = History(args.interval)
    return run_once(args.url, console, hist) if args.once else run_live(args.url, console, hist)


if __name__ == "__main__":
    sys.exit(main())
