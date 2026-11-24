"""Locate figure captions with the PDFFigures2 batch CLI."""

import json
import os
from pathlib import Path
import shutil
import subprocess


def locator_jar():
    tools = Path(os.environ.get("CEDALION_TOOLS", str(Path.home() / ".local/share/cedalion-tools")))
    jar = Path(os.environ.get("PDFFIGURES2_JAR", tools / "java-bench/pdffigures2.jar")).expanduser()
    if not jar.is_file():
        raise FileNotFoundError(f"PDFFigures2 JAR missing at {jar}. Install it as described in "
                                "README.md (Requirements) or set PDFFIGURES2_JAR.")
    if shutil.which("java") is None:
        raise FileNotFoundError("PDFFigures2 requires Java on PATH (tested with Java 21).")
    return jar.resolve()


def run_batch(pdf, out, jar, *, export_images=False):
    prefix = str(out) + os.sep
    command = ["java", "-XX:ActiveProcessorCount=4", "-Xmx2g", "-Djava.awt.headless=true",
               f"-Duser.home={out}", f"-Djava.io.tmpdir={out}", "-jar", str(jar),
               "-q", "-t", "1", "-c", "-d", prefix]
    if export_images:
        command.extend(["-m", prefix])
    command.append(str(pdf))
    env = dict(os.environ, OMP_NUM_THREADS="4", OPENBLAS_NUM_THREADS="4", CUDA_VISIBLE_DEVICES="")
    try:
        result = subprocess.run(command, cwd=out, env=env, capture_output=True, text=True,
                                errors="replace", timeout=300)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"PDFFigures2 timed out reading {pdf.name}") from exc
    if export_images:
        (out / "parser.log").write_text(result.stdout + result.stderr)
    output = out / f"{pdf.stem}.json"
    if result.returncode or not output.is_file():
        detail = (result.stderr or result.stdout).strip()[-1000:]
        raise RuntimeError(f"PDFFigures2 failed reading {pdf.name} (exit {result.returncode}). {detail}")


def caption_locations(pdf, out):
    data = json.loads((out / f"{pdf.stem}.json").read_text())
    for group, boundary in (("figures", "captionBoundary"), ("regionless-captions", "boundary")):
        for item in data[group]:
            if item["figType"] == "Figure":
                box = item[boundary]
                yield item, [item["page"] + 1, box["x1"], box["y1"], box["x2"], box["y2"]]
