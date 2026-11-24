"""Install the benchmark's Java parsers under CEDALION_TOOLS using Java 21 and curl."""

import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET


BASE = Path(os.environ["CEDALION_TOOLS"]).resolve() / "java-bench"
REV = "3d7ad46753d4a315cccd1c2bcab398380e88c534"
PDFFIG = BASE / f"pdffigures2-{REV}"
GROBID = BASE / "grobid-0.9.1"
MAVEN = BASE / "apache-maven-3.9.9/bin/mvn"
JVM = ["java", "-XX:ActiveProcessorCount=4", "-Xmx1g"]
CENTRAL = "https://repo.maven.apache.org/maven2"


def run(*args):
    subprocess.run(args, cwd=BASE, check=True)


def fetch(name, url, sha256):
    dest = BASE / name
    if not dest.exists():
        run("curl", "-fLsS", "--retry", "2", "--output", dest, url)
    with dest.open("rb") as data:
        h = hashlib.sha256()
        for chunk in iter(lambda: data.read(1048576), b""):
            h.update(chunk)
    if h.hexdigest() != sha256:
        raise ValueError(f"Unexpected download checksum: {dest}")


def classpath(name, coordinates):
    pom = ET.Element("project", xmlns="http://maven.apache.org/POM/4.0.0")
    for field, text in [("modelVersion", "4.0.0"), ("groupId", "bench"),
                        ("artifactId", name), ("version", "1")]:
        ET.SubElement(pom, field).text = text
    deps = ET.SubElement(pom, "dependencies")
    for coord in dict.fromkeys(coordinates):
        dep = ET.SubElement(deps, "dependency")
        for field, value in zip(("groupId", "artifactId", "version"), coord.split(":")):
            ET.SubElement(dep, field).text = value
    pom_path = BASE / f"{name}-runtime.xml"
    ET.ElementTree(pom).write(pom_path)
    cp_path = BASE / f"{name}.classpath"
    run(MAVEN, "-B", "-q", "-f", pom_path, f"-Dmaven.repo.local={BASE / 'm2'}",
        "org.apache.maven.plugins:maven-dependency-plugin:3.8.1:build-classpath",
        f"-Dmdep.outputFile={cp_path}")
    return cp_path.read_text().strip().split(os.pathsep)


def manifest_jar(name, main_class, jars, extra=()):
    # Keep jars separate in the local Maven tree. Standard manifest paths are relative.
    cp = "Class-Path: " + " ".join(Path(j).relative_to(BASE).as_posix() for j in jars)
    wrapped = cp[:70] + "".join("\n " + cp[i:i+69] for i in range(70, len(cp), 69))
    manifest = BASE / f"{name}.manifest"
    manifest.write_text(f"Manifest-Version: 1.0\nMain-Class: {main_class}\n{wrapped}\n\n")
    run(*JVM, "-m", "jdk.jartool/sun.tools.jar.Main", "--create", "--file",
        f"{name}.jar", "--manifest", manifest, *extra)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdffigures2-only", action="store_true", help="install just the caption locator")
    args = parser.parse_args()
    BASE.mkdir(parents=True, exist_ok=True)
    os.environ.update(MAVEN_OPTS=f"-XX:ActiveProcessorCount=4 -Duser.home={BASE} -Djava.io.tmpdir={BASE}",
                      OMP_NUM_THREADS="4", CUDA_VISIBLE_DEVICES="")
    fetch("maven.tar.gz", f"{CENTRAL}/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.tar.gz",
          "7a9cdf674fc1703d6382f5f330b3d110ea1b512b51f1652846d9e4e8a588d766")
    fetch("pdffigures2.tar.gz", f"https://codeload.github.com/allenai/pdffigures2/tar.gz/{REV}",
          "b1229be90055b5d282ef38f63458deee6bc0852b9192b9c5e7181a4231563ec6")
    if not MAVEN.exists():
        run("tar", "xzf", "maven.tar.gz")
    if not PDFFIG.exists():
        run("tar", "xzf", "pdffigures2.tar.gz")

    # The upstream build targets Scala 2.12. Use its Java-21-compatible patch release.
    sbt = (PDFFIG / "build.sbt").read_text()
    coords = ["org.scala-lang:scala-compiler:2.12.20"]
    for g, sep, a, v in re.findall(r'^\s*"([^"]+)"\s+(%{1,2})\s+"([^"]+)"\s+%\s+"([^"]+)"\s*,',
                                    sbt, re.MULTILINE):
        coords.append(f"{g}:{a}{'_2.12' if sep == '%%' else ''}:{v}")
    jars = classpath("pdffigures2", coords)
    classes = BASE / "classes"
    classes.mkdir(exist_ok=True)
    cp = os.pathsep.join(jars)
    src = PDFFIG / "src/main"
    run(*JVM, "-m", "jdk.compiler/com.sun.tools.javac.Main", "-cp", cp, "-d", classes,
        *sorted((src / "java").rglob("*.java")))
    run(*JVM, "-cp", f"{classes}{os.pathsep}{cp}", "scala.tools.nsc.Main", "-usejavacp",
        "-d", classes, *sorted((src / "scala").rglob("*.scala")))
    manifest_jar("pdffigures2", "org.allenai.pdffigures2.FigureExtractorBatchCli", jars,
                 ["-C", classes, ".", "-C", src / "resources", "."])

    if args.pdffigures2_only:
        return
    fetch("grobid.zip", "https://codeload.github.com/grobidOrg/grobid/zip/refs/tags/0.9.1",
          "640b33615466b7d9dc784d87212144608cf509b28c983b46ca6e36f8c8686ec9")
    core = "grobid-core-0.9.1.jar"
    fetch(core, f"https://github.com/grobidOrg/grobid/releases/download/0.9.1/{core}",
          "f9562d38e1ba798ffe5c1af7500ba8fe91b4e00c74a5eb457be1975b1a416f84")

    if not GROBID.exists():
        run("unzip", "-q", "grobid.zip")

    # The release jar contains localLibs; add the Maven runtime dependencies of grobid-core.
    gradle = (GROBID / "build.gradle").read_text()
    common = gradle.split('implementation "com.cybozu', 1)[1].split("tasks.register('sourceJar'", 1)[0]
    core_deps = gradle.split('implementation("xml-apis', 1)[1].split("    jar {", 1)[0]
    coords = re.findall(r"""^\s*(?:api|implementation|runtimeOnly)\s+["']([^"']+:[^"']+:[^"']+)["']""",
                        common + "\n" + core_deps, re.MULTILINE)
    coords.extend(["xml-apis:xml-apis:1.4.01", "org.jetbrains.kotlin:kotlin-stdlib:1.9.25"])
    manifest_jar("grobid", "org.grobid.core.main.batch.GrobidMain",
                 [BASE / core, *classpath("grobid", sorted(set(coords)))])


if __name__ == "__main__":
    main()
