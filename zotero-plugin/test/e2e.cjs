// T2 on a made-up scrapbook: (a) the fixtures are mapped and written, match their golden files and pass
// tools/check.py; (b) sending them again to a scrapbook that already holds them reports duplicates and
// changes no file.
const assert = require("node:assert/strict");
const { createHash } = require("node:crypto");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const yaml = require("js-yaml");
const { plugin, scrapbook, fixture, fixtureRecord, repoDir, today } = require("./host.cjs");

// Fixture name -> the key of the record the second send finds (generated-key shares linked-pdf's DOI).
const duplicates = {
  "linked-pdf": "odegaard-nunezSyntheticGriddedCounts2025",
  "generated-key": "odegaard-nunezSyntheticGriddedCounts2025",
  "signed-pdf": "roeSameBlockLayout2026",
  "tracked-pdf": "xuSeamlessGlobalMapping2026",
};

async function withFolder(run) {
  const parent = await fs.mkdtemp(path.join(os.tmpdir(), "cedalion-e2e-"));
  try {
    await run(path.join(parent, "scrapbook"));
  } finally {
    await fs.rm(parent, { recursive: true, force: true });
  }
}

async function snapshot(root, dir = root, entries = new Map()) {
  for (const entry of await fs.readdir(dir, { withFileTypes: true })) {
    const file = path.join(dir, entry.name);
    if (entry.isDirectory()) await snapshot(root, file, entries);
    else {
      const content = await fs.readFile(file);
      const { mtimeNs } = await fs.stat(file, { bigint: true });
      entries.set(path.relative(root, file), [createHash("sha256").update(content).digest("hex"), mtimeNs]);
    }
  }
  return entries;
}

// tools/check.py from this tool root on the given scrapbook only (never one found from the environment).
function check(book) {
  const env = { ...process.env };
  delete env.CEDALION_SCRAPBOOK;
  execFileSync("pixi", ["run", "--manifest-path", path.join(repoDir, "pixi.toml"), "python",
                        path.join(repoDir, "tools/check.py"), "--scrapbook", book],
               { cwd: repoDir, stdio: "inherit", env });
}

// (a) Write each fixture into an empty scrapbook and compare it with its golden file.
async function writes(book, ids, record, expectedDir) {
  const { scope } = await plugin(book);
  const { domains, papers } = await scope.loadRepository(book);
  for (const id of ids) {
    const { paper } = scope.mapPaper(record(id).item, domains, today, scope.Zotero.Date.strToISO);
    assert.equal(await scope.writePaper(papers, paper), "written");
    const written = await fs.readFile(path.join(papers, paper.citationKey, "item.yaml"), "utf8");
    const expected = await fs.readFile(path.join(expectedDir, id + ".item.yaml"), "utf8");
    assert.deepEqual(yaml.load(written), yaml.load(expected));
  }
  assert.equal((await fs.readdir(papers)).length, ids.length);
}

// (b) Send every fixture with its attachments to a scrapbook that already holds them.
async function resends(book, expected, record) {
  const before = await snapshot(book);
  const { scope, toItem } = await plugin(book);
  const ids = Object.keys(expected);
  const items = ids.map(id => {
    const { item, children } = record(id);
    return toItem(item, children); // No attachment file is on disk.
  });
  const results = await scope.sendItems(book, items, today);
  for (const [index, id] of ids.entries()) {
    assert.equal(results[index].status, "duplicate");
    assert.equal(results[index].existingKey, expected[id]);
    assert.ok(items[index].hasTag("cedalion"));
    console.log(`T2(b) ${id}: already in the scrapbook as ${results[index].existingKey}`);
  }
  assert.deepEqual(await snapshot(book), before);
  console.log(`T2(b) verified ${before.size} files; 0 added, removed, modified or rewritten`);
}

async function main() {
  const ids = Object.keys(duplicates);
  await withFolder(async book => {
    await scrapbook(book);
    await writes(book, ids, id => fixtureRecord(id), path.join(__dirname, "expected"));
    console.log(`T2(a) wrote ${ids.length} fixture records and matched all ${ids.length} golden files`);
    check(book);
  });

  await withFolder(async book => {
    await scrapbook(book);
    const { scope } = await plugin(book);
    const { domains, papers } = await scope.loadRepository(book);
    for (const id of ["linked-pdf", "signed-pdf", "tracked-pdf"]) {
      const { paper } = scope.mapPaper(fixture(id), domains, today, scope.Zotero.Date.strToISO);
      await scope.writePaper(papers, paper);
    }
    await resends(book, duplicates, id => fixtureRecord(id));
  });
}

module.exports = { snapshot, check, writes, resends };

if (require.main === module) main().catch(error => { console.error(error); process.exitCode = 1; });
