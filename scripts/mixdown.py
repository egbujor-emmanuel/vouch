#!/usr/bin/env python
"""Cut the recording at the sync flash and lay the narration onto it.

The recorder flashes one white frame immediately before the first spoken line
and reports, in walkthrough/audio/offsets.json, how many milliseconds after that
flash each line began. So the flash is time zero for both halves: find it in the
video, trim there, and place each line of audio at its reported offset. Nothing
is estimated, which is why the word highlight stays on the voice for the whole
run instead of drifting.

    python scripts/mixdown.py

Writes walkthrough/vouch-demo.mp4.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REC = ROOT / "walkthrough" / "final"
AUDIO = ROOT / "walkthrough" / "audio"
OUT = ROOT / "walkthrough" / "vouch-demo.mp4"

WHITE = 200.0  # a full-screen white frame sits near 255; the page never does


def run(cmd: list[str], cwd: Path | None = None) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if p.returncode:
        sys.exit(f"failed: {' '.join(cmd[:6])}…\n{p.stderr[-1500:]}")
    return p.stdout


def find_flash(src: Path) -> float:
    """Time in seconds just after the last white frame."""
    # The filter parser treats a colon as an argument separator, so the stats
    # file is named relative to a working directory rather than by full path.
    stats = REC / "stats.txt"
    run(["ffmpeg", "-v", "error", "-y", "-i", src.name,
         "-vf", "crop=400:300:440:210,signalstats,"
                "metadata=print:key=lavfi.signalstats.YAVG:file=stats.txt",
         "-f", "null", "-"], cwd=REC)

    times: list[float] = []
    t = None
    for line in stats.read_text(encoding="utf-8").splitlines():
        m = re.search(r"pts_time:([0-9.]+)", line)
        if m:
            t = float(m.group(1))
            continue
        m = re.search(r"YAVG=([0-9.]+)", line)
        if m and t is not None and float(m.group(1)) > WHITE:
            times.append(t)

    if not times:
        sys.exit("no sync flash found in the recording")

    # Chromium paints white before the page loads, so the flash is the *last*
    # run of white frames, not the first.
    runs: list[list[float]] = [[times[0]]]
    for a, b in zip(times, times[1:]):
        if b - a >= 0.25:
            runs.append([])
        runs[-1].append(b)
    last = runs[-1]
    print(f"  white runs: {len(runs)}, flash {last[0]:.2f}s to {last[-1]:.2f}s")
    return last[-1] + 0.04


def main() -> int:
    src = next(REC.glob("*.webm"), None)
    if src is None:
        sys.exit("no recording in walkthrough/final")
    offsets = json.loads((AUDIO / "offsets.json").read_text(encoding="utf-8"))
    timing = json.loads((AUDIO / "timing.json").read_text(encoding="utf-8"))

    start = find_flash(src)
    print(f"  trimming at {start:.2f}s")

    inputs: list[str] = ["-ss", f"{start:.3f}", "-i", str(src)]
    for t in timing:
        inputs += ["-i", str(AUDIO / t["file"])]

    delays = []
    for n, off in enumerate(offsets, start=1):
        ms = max(0, int(off["at"]))
        delays.append(f"[{n}:a]adelay={ms}|{ms}[a{n}]")
    mix = "".join(f"[a{n}]" for n in range(1, len(offsets) + 1))
    # normalize=0 keeps each line at the level it was spoken; loudnorm then puts
    # the whole track at a consistent broadcast level.
    fc = (";".join(delays) + ";" + mix +
          f"amix=inputs={len(offsets)}:normalize=0[m];"
          "[m]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,apad[a];"
          "[0:v]scale=1920:1080:flags=lanczos,fps=30,format=yuv420p[v]")

    run(["ffmpeg", "-v", "error", "-y", *inputs,
         "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-preset", "slow", "-crf", "18",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
         "-shortest", str(OUT)])

    info = run(["ffprobe", "-v", "error", "-show_entries", "format=duration,size",
                "-show_entries", "stream=codec_type,width,height",
                "-of", "default=nw=1", str(OUT)])
    print(info.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
