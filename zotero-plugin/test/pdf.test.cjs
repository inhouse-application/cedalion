const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const test = require("node:test");
const yaml = require("js-yaml");
const { plugin, repository, fixtureRecord, today } = require("./host.cjs");

const source = fixtureRecord("linked-pdf");
const pdf = source.children.find(child => child.contentType === "application/pdf");

async function setup(t) {
  const root = await repository(t);
  const local = path.join(root, "attachment.pdf");
  await fs.writeFile(local, Buffer.from([37, 80, 68, 70, 0, 255]));
  const host = await plugin(root);
  const send = async item => (await host.scope.sendItems(root, [item], today))[0];
  return { root, local, cache: path.join(root, ".cache/pdf"), ...host, send };
}

test("fixture children select the local PDF and preserve the attachment URL and version", async t => {
  const { root, local, toItem, scope } = await setup(t);
  for (const id of ["linked-pdf", "signed-pdf", "tracked-pdf", "generated-key"]) {
    const { item, children } = fixtureRecord(id);
    const expected = children.find(child => child.contentType === "application/pdf");
    const paths = Object.fromEntries(children.map(child => [child.key, local]));
    // Mark the non-PDF as best when available, even when a local snapshot exists.
    const selected = toItem(item, children, paths, children.find(c => c !== expected)?.key);
    const [result] = await scope.sendItems(root, [selected], today);
    if (!expected) {
      assert.equal(result.pdf, "no local PDF");
      continue;
    }
    assert.equal(result.pdf, "copied");
    const base = path.join(root, ".cache/pdf", result.key);
    assert.deepEqual(await fs.readFile(base + ".pdf"), await fs.readFile(local));
    const provenance = yaml.load(await fs.readFile(base + ".yaml", "utf8"));
    const stable = expected.url.includes("?") ? "https://doi.org/" + item.DOI : expected.url;
    assert.equal(provenance.url, stable);
    assert.equal(provenance.version, "vor");
  }
});

test("best local PDF wins; a missing best falls back to the earliest local PDF", async t => {
  const { local, toItem, scope } = await setup(t);
  const early = { ...pdf, key: "EARLY", dateAdded: "2023-05-01T12:00:00Z" };
  const late = { ...pdf, key: "LATE", dateAdded: "2025-05-01T12:00:00Z" };
  const linkedURL = { ...early, key: "URL", linkMode: "linked_url" };
  const children = [late, linkedURL, early];
  const choose = (paths, best) => scope.choosePDF(toItem(source.item, children, paths, best));
  assert.equal((await choose({ EARLY: local, LATE: local }, "LATE")).attachment.key, "LATE");
  assert.equal((await choose({ EARLY: local, LATE: local, URL: local }, "URL")).attachment.key, "EARLY");
  const fallback = await choose({ EARLY: local }, "LATE");
  assert.equal(fallback.attachment.key, "EARLY");
  assert.match(fallback.warnings[0], /PDF not downloaded.*LATE/);
  assert.equal((await choose({}, "LATE")).status, "PDF not downloaded");
});

test("all specified attachment titles map to repository version names", async t => {
  const { scope } = await setup(t);
  for (const [title, version] of [
    ["Accepted Version", "accepted-manuscript"], ["Submitted Version", "preprint"], ["Preprint PDF", "preprint"],
    ["Published Version", "vor"], ["Full Text PDF", "vor"], ["ScienceDirect Full Text PDF", "vor"],
    ["Author copy", null], ["", null],
  ]) assert.equal(scope.pdfVersion(title), version);
});

for (const status of ["written", "skipped", "duplicate"]) {
  test(`${status} metadata fills PDF and sidecar under the repository key and tags the item`, async t => {
    const { root, cache, local, toItem, send } = await setup(t);
    const data = { ...source.item, citationKey: "incoming" };
    const key = status === "duplicate" ? "existing" : data.citationKey;
    const file = path.join(root, "papers", key, "item.yaml");
    // A skipped record has no DOI to compare; one with another DOI is refused (M9).
    const prior = yaml.dump(status === "duplicate" ? { DOI: data.DOI } : { title: "Record without a DOI" });
    if (status !== "written") {
      await fs.mkdir(path.dirname(file));
      await fs.writeFile(file, prior);
    }
    const attachment = { ...pdf, title: "Author copy", url: "" };
    const item = toItem(data, [attachment], { [pdf.key]: local });
    const result = await send(item);
    assert.equal(result.status, status);
    assert.equal(result.pdf, "copied");
    assert.ok(result.warnings.includes("set version by hand"));
    assert.ok(item.hasTag("cedalion"));
    assert.deepEqual(await fs.readdir(cache), [key + ".pdf", key + ".yaml"]);
    assert.deepEqual(yaml.load(await fs.readFile(path.join(cache, key + ".yaml"), "utf8")), {
      url: "https://doi.org/" + data.DOI,
    });
    if (status !== "written") assert.equal(await fs.readFile(file, "utf8"), prior);
  });
}

test("same bytes can fill a missing sidecar; different bytes never relabel the cached PDF", async t => {
  const { local, cache, toItem, send } = await setup(t);
  const data = source.item;
  const item = toItem(data, [pdf], { [pdf.key]: local });
  const base = path.join(cache, data.citationKey);
  await fs.mkdir(cache, { recursive: true });
  await fs.copyFile(local, base + ".pdf");
  const before = await fs.stat(base + ".pdf", { bigint: true });
  assert.equal((await send(item)).pdf, "already present");
  assert.equal((await fs.stat(base + ".pdf", { bigint: true })).mtimeNs, before.mtimeNs);
  assert.equal(yaml.load(await fs.readFile(base + ".yaml", "utf8")).url, pdf.url);
  const ownerSidecar = "# owner provenance\nversion: preprint\n";
  await fs.writeFile(base + ".yaml", ownerSidecar);
  assert.equal((await send(item)).pdf, "already present");
  assert.equal(await fs.readFile(base + ".yaml", "utf8"), ownerSidecar);
  const cached = await fs.readFile(base + ".pdf");
  await fs.writeFile(local, "other PDF");
  assert.match((await send(item)).pdf, /conflict/);
  assert.equal(await fs.readFile(base + ".yaml", "utf8"), ownerSidecar);
  await fs.unlink(base + ".yaml");
  item.removeTag("cedalion");
  assert.match((await send(item)).pdf, /conflict/);
  assert.ok(item.hasTag("cedalion"));
  assert.deepEqual(await fs.readdir(cache), [data.citationKey + ".pdf"]);
  assert.deepEqual(await fs.readFile(base + ".pdf"), cached);
});

test("the menu reports every selection in order and leaves metadata errors untagged", async t => {
  const { menu, alerts, toItem, cache } = await setup(t);
  const missing = toItem(source.item, [pdf]);
  const bad = toItem({ ...source.item, citationKey: "bad", DOI: "" });
  const child = { key: "NOTE", isRegularItem: () => false };
  await menu.onCommand({ currentTarget: { ownerGlobal: {} } }, { items: [bad, child, missing] });
  const lines = alerts[0].split("\n");
  assert.deepEqual(lines.slice(0, 2), ["Regular items: 2", "Skipped items: 1"]);
  assert.equal(lines.length, 5);
  assert.match(lines[2], /^bad — item.yaml: error — PDF: not attempted.*Missing DOI/);
  assert.match(lines[3], /^NOTE — item.yaml: skipped — PDF: skipped/);
  assert.match(lines[4], /item.yaml: written — PDF: PDF not downloaded/);
  assert.ok(missing.hasTag("cedalion"));
  assert.equal(bad.hasTag("cedalion"), false);
  await assert.rejects(fs.stat(cache), { code: "ENOENT" });
});

test("a sidecar failure reports the copied PDF and a later send completes the operation", async t => {
  const { scope, local, toItem, send } = await setup(t);
  const item = toItem(source.item, [pdf], { [pdf.key]: local });
  const move = scope.IOUtils.move;
  scope.IOUtils.move = (from, to, options) => {
    if (to.endsWith(".yaml") && !to.endsWith("item.yaml")) throw new Error("Sidecar write failed");
    return move(from, to, options);
  };
  const first = await send(item);
  assert.equal(first.pdf, "copied");
  assert.ok(first.warnings.includes("Sidecar error: Sidecar write failed"));
  assert.equal(item.hasTag("cedalion"), false);
  scope.IOUtils.move = move;
  const retry = await send(item);
  assert.equal(retry.status, "duplicate");
  assert.equal(retry.pdf, "already present");
  assert.ok(item.hasTag("cedalion"));
});

test("a symlinked cache directory cannot redirect writes", async t => {
  const { root, local, toItem, send } = await setup(t);
  const outside = path.join(root, "elsewhere");
  await fs.mkdir(outside);
  await fs.symlink(outside, path.join(root, ".cache"));
  const item = toItem(source.item, [pdf], { [pdf.key]: local });
  const result = await send(item);
  assert.equal(result.pdf, "error");
  assert.equal(item.hasTag("cedalion"), false);
  assert.deepEqual(await fs.readdir(outside), []);
});

test("a skipped item without a DOI can recover provenance from its stored metadata", async t => {
  const { root, cache, local, toItem, send } = await setup(t);
  const data = { ...source.item, DOI: "" };
  const directory = path.join(root, "papers", data.citationKey);
  await fs.mkdir(directory);
  await fs.writeFile(path.join(directory, "item.yaml"), "DOI: 10.1000/original\n");
  const result = await send(toItem(data, [{ ...pdf, url: "" }], { [pdf.key]: local }));
  assert.equal(result.status, "skipped");
  const provenance = yaml.load(await fs.readFile(path.join(cache, data.citationKey + ".yaml"), "utf8"));
  assert.equal(provenance.url, "https://doi.org/10.1000/original");
});

test("tag save errors are reported per item and can be retried without new repository writes", async t => {
  const { root, scope, toItem, send } = await setup(t);
  const first = toItem(source.item);
  const second = toItem({ ...source.item, citationKey: "second", DOI: "10.1000/second" });
  first.saveTx = async () => { throw new Error("Read-only library"); };
  const [failed, next] = await scope.sendItems(root, [first, second], today);
  assert.equal(failed.status, "written");
  assert.ok(failed.warnings.includes("Tag error: Read-only library"));
  assert.equal(first.hasTag("cedalion"), false);
  assert.ok(second.hasTag("cedalion"));
  assert.equal(next.status, "written");
  first.saveTx = async () => {};
  assert.equal((await send(first)).status, "duplicate");
  assert.ok(first.hasTag("cedalion"));
});

const supplementRecord = fixtureRecord("supplement");
const [paperPDF, supplement] = supplementRecord.children;

async function withSupplementFile(t) {
  const host = await setup(t);
  const supplementFile = path.join(host.root, "supplement.pdf");
  await fs.writeFile(supplementFile, "supplement PDF");
  return { ...host, supplementFile };
}

test("supplements are detected by attachment title or file name, ignoring case", async t => {
  const { scope, toItem } = await setup(t);
  const cases = [
    [supplement, true],
    [{ ...supplement, key: "BYTITLE", title: "Supplementary Material", filename: "esm.pdf" }, true],
    [{ ...supplement, key: "BYNAME", title: "Full Text PDF", filename: "paper-SUPPLEMENT.pdf" }, true],
    [paperPDF, false],
  ];
  toItem(supplementRecord.item, cases.map(([child]) => child));
  for (const [child, expected] of cases) assert.equal(scope.isSupplement(scope.Zotero.Items.get(child.key)), expected);
});

test("a supplement is never the paper's PDF, even when Zotero prefers it", async t => {
  const { local, scope, toItem, supplementFile } = await withSupplementFile(t);
  const choose = (children, paths) => scope.choosePDF(toItem(supplementRecord.item, children, paths, supplement.key));
  const both = { [paperPDF.key]: local, [supplement.key]: supplementFile };
  assert.equal((await choose(supplementRecord.children, both)).attachment.key, paperPDF.key);
  assert.equal((await choose(supplementRecord.children, { [supplement.key]: supplementFile })).status, "PDF not downloaded");
  assert.equal((await choose([supplement], { [supplement.key]: supplementFile })).status, "no local PDF");
});

test("the supplement is cached beside the paper's PDF; provenance has no URL or version to guess", async t => {
  const { cache, local, menu, alerts, toItem, supplementFile } = await withSupplementFile(t);
  const paths = { [paperPDF.key]: local, [supplement.key]: supplementFile };
  const item = toItem(supplementRecord.item, supplementRecord.children, paths, supplement.key);
  await menu.onCommand({ currentTarget: { ownerGlobal: {} } }, { items: [item] });
  const key = supplementRecord.item.citationKey;
  assert.ok(alerts[0].includes(`${key} — item.yaml: written — PDF: copied — Supplement: copied — `));
  assert.match(alerts[0], /set supplement version by hand — set supplement URL by hand/);
  assert.ok(item.hasTag("cedalion"));
  const base = path.join(cache, key);
  const files = [".pdf", ".supplement.pdf", ".supplement.yaml", ".yaml"].map(suffix => key + suffix);
  assert.deepEqual(await fs.readdir(cache), files);
  assert.deepEqual(await fs.readFile(base + ".pdf"), await fs.readFile(local));
  assert.deepEqual(await fs.readFile(base + ".supplement.pdf"), await fs.readFile(supplementFile));
  assert.deepEqual(yaml.load(await fs.readFile(base + ".yaml", "utf8")), { url: paperPDF.url, version: "vor" });
  assert.deepEqual(yaml.load(await fs.readFile(base + ".supplement.yaml", "utf8")), {});
});

test("supplement provenance keeps a plain URL and a mapped version but never falls back to the DOI", async t => {
  const { cache, toItem, send, supplementFile } = await withSupplementFile(t);
  const url = "https://journal.example.org/articles/synth-0005/synth-0005-supplement.pdf";
  for (const [index, [fields, expected, warning]] of [
    [{ url, title: "Published Version" }, { url, version: "vor" }, false],
    [{ url: url + "?utm_source=mail" }, {}, true],
  ].entries()) {
    const data = { ...supplementRecord.item, citationKey: "paper" + index, DOI: "10.1/" + index };
    const result = await send(toItem(data, [{ ...supplement, ...fields }], { [supplement.key]: supplementFile }));
    assert.equal(result.pdf, "no local PDF");
    assert.equal(result.supplement, "copied");
    assert.equal(result.warnings.includes("set supplement URL by hand"), warning);
    const provenance = yaml.load(await fs.readFile(path.join(cache, data.citationKey + ".supplement.yaml"), "utf8"));
    assert.deepEqual(provenance, expected);
  }
});

test("several supplements copy the earliest local one and report the rest", async t => {
  const { root, cache, scope, toItem, send, supplementFile } = await withSupplementFile(t);
  const later = { ...supplement, key: "LATER", dateAdded: "2026-11-21T00:00:00Z" };
  const missing = { ...supplement, key: "MISSING", dateAdded: "2026-11-19T00:00:00Z" };
  const children = [later, supplement, missing];
  const laterFile = path.join(root, "later.pdf");
  await fs.writeFile(laterFile, "later supplement");
  const item = toItem(supplementRecord.item, children, { LATER: laterFile, [supplement.key]: supplementFile });
  const choice = await scope.chooseSupplement(item);
  assert.equal(choice.attachment.key, supplement.key);
  assert.deepEqual([...choice.warnings], ["supplement PDF not downloaded (MISSING)", "supplement PDFs skipped: 1"]);
  const result = await send(item);
  assert.equal(result.supplement, "copied");
  assert.ok(result.warnings.includes("supplement PDFs skipped: 1"));
  const cached = path.join(cache, supplementRecord.item.citationKey + ".supplement.pdf");
  assert.deepEqual(await fs.readFile(cached), await fs.readFile(supplementFile));
  const status = async (...children) => (await scope.chooseSupplement(toItem(supplementRecord.item, children, {}))).status;
  assert.equal(await status(...children), "supplement PDF not downloaded");
  assert.equal(await status(paperPDF), "none");
});

test("the summary reports a supplement that is not downloaded or absent", async t => {
  const { menu, alerts, local, toItem } = await setup(t);
  const notDownloaded = toItem(supplementRecord.item, supplementRecord.children, { [paperPDF.key]: local });
  const absent = toItem({ ...source.item, citationKey: "other" }, [pdf], { [pdf.key]: local });
  await menu.onCommand({ currentTarget: { ownerGlobal: {} } }, { items: [notDownloaded, absent] });
  const lines = alerts[0].split("\n");
  assert.match(lines[2], /PDF: copied — Supplement: supplement PDF not downloaded/);
  assert.match(lines[3], /PDF: copied — Supplement: none/);
  assert.ok(notDownloaded.hasTag("cedalion"));
});

for (const status of ["skipped", "duplicate"]) {
  test(`${status} metadata fills the supplement under the repository key; existing files are kept`, async t => {
    const { root, cache, toItem, send, supplementFile } = await withSupplementFile(t);
    const data = { ...supplementRecord.item, citationKey: "incoming" };
    const key = status === "duplicate" ? "existing" : data.citationKey;
    // A skipped record has no DOI to compare; one with another DOI is refused (M9).
    const prior = yaml.dump(status === "duplicate" ? { DOI: data.DOI } : { title: "Record without a DOI" });
    await fs.mkdir(path.join(root, "papers", key));
    await fs.writeFile(path.join(root, "papers", key, "item.yaml"), prior);
    const item = toItem(data, [supplement], { [supplement.key]: supplementFile });
    const base = path.join(cache, key + ".supplement");
    const first = await send(item);
    assert.equal(first.status, status);
    assert.equal(first.supplement, "copied");
    const ownerSidecar = `# owner provenance\nurl: https://example.org/${key}.pdf\nversion: vor\n`;
    await fs.writeFile(base + ".yaml", ownerSidecar);
    const second = await send(item);
    assert.equal(second.supplement, "already present");
    assert.equal(second.warnings.includes("set supplement URL by hand"), false);
    assert.equal(await fs.readFile(base + ".yaml", "utf8"), ownerSidecar);
    await fs.writeFile(supplementFile, "other supplement");
    await fs.unlink(base + ".yaml");
    assert.match((await send(item)).supplement, /conflict/);
    assert.deepEqual(await fs.readdir(cache), [key + ".supplement.pdf"]);
  });
}

test("a supplement sidecar failure leaves the item untagged until a later send completes it", async t => {
  const { scope, local, toItem, send, supplementFile } = await withSupplementFile(t);
  const item = toItem(supplementRecord.item, supplementRecord.children, { [paperPDF.key]: local, [supplement.key]: supplementFile });
  const move = scope.IOUtils.move;
  scope.IOUtils.move = (from, to, options) => {
    if (to.endsWith(".supplement.yaml")) throw new Error("Sidecar write failed");
    return move(from, to, options);
  };
  const first = await send(item);
  assert.equal(first.supplement, "copied");
  assert.ok(first.warnings.includes("Supplement sidecar error: Sidecar write failed"));
  assert.equal(item.hasTag("cedalion"), false);
  scope.IOUtils.move = move;
  const retry = await send(item);
  assert.equal(retry.supplement, "already present");
  assert.ok(item.hasTag("cedalion"));
});

test("a citation key ending in .supplement is refused, since it would share another paper's supplement cache", async t => {
  const root = await repository(t);
  const { scope } = await plugin(root);
  for (const key of ["sample.supplement", "Sample.SUPPLEMENT"]) {
    await assert.rejects(scope.writePaper(path.join(root, "papers"), { citationKey: key }),
                         /reserved suffix \.supplement/);
    await assert.rejects(fs.access(path.join(root, "papers", key)));
  }
});

test("a record already under a key ending in .supplement gets no cached PDF", async t => {
  const { root, scope, toItem, local } = await setup(t);
  const { item, children } = fixtureRecord("linked-pdf");
  const paths = Object.fromEntries(children.map(child => [child.key, local]));
  const result = { warnings: [] };
  await assert.rejects(scope.cachePDF(root, "sample.supplement", toItem(item, children, paths), item.DOI, result),
                       /reserved suffix \.supplement/);
  await assert.rejects(fs.access(path.join(root, ".cache/pdf/sample.supplement.pdf")));
});
