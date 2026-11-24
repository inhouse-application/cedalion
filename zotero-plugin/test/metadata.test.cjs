const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const test = require("node:test");
const yaml = require("js-yaml");
const { plugin, repository, fixture, today } = require("./host.cjs");

for (const id of ["linked-pdf", "signed-pdf", "tracked-pdf", "generated-key"]) {
  test(`${id} writes the expected YAML fields, values and order`, async t => {
    const root = await repository(t);
    const { sendPapers } = await plugin(root);
    const [result] = await sendPapers(root, [fixture(id)], today);
    assert.equal(result.status, "written", result.message);
    const written = yaml.load(await fs.readFile(path.join(root, "papers", result.key, "item.yaml"), "utf8"));
    const expected = yaml.load(await fs.readFile(path.join(__dirname, "expected", id + ".item.yaml"), "utf8"));
    assert.deepEqual(written, expected);
    assert.deepEqual(Object.keys(written), Object.keys(expected));
  });
}

test("dates preserve precision and unparsed dates appear in the menu summary", async t => {
  const root = await repository(t);
  const { scope, menu, alerts, toItem } = await plugin(root);
  for (const [date, expected] of [
    ["2025-03-18", "2025-03-18"], ["March 2024", "2024-03"], ["2023", "2023"], ["forthcoming", "forthcoming"],
  ]) {
    const source = { ...fixture("signed-pdf"), date };
    const { paper, warnings } = scope.mapPaper(source, new Set(), today, scope.Zotero.Date.strToISO);
    assert.equal(paper.date, expected);
    assert.deepEqual([...warnings], date === "forthcoming" ? ["Unparsed date: forthcoming"] : []);
  }
  await menu.onCommand({ currentTarget: { ownerGlobal: {} } }, {
    items: [toItem({ ...fixture("signed-pdf"), date: "forthcoming" })],
  });
  assert.match(alerts[0], /written.*Unparsed date: forthcoming/);
});

test("single-field names, generated key, PMID and PMCID come from source fields", async t => {
  const root = await repository(t);
  const { scope } = await plugin(root);
  const source = {
    ...fixture("generated-key"),
    title: "The NASA map of US cities",
    creators: [{ creatorType: "editor", lastName: "Smith" }, { creatorType: "author", name: "Mäp Lab" }],
    extra: "Noise: ignore\r\nPMID: 00042\r\nPMCID: PMC1234\r\n",
  };
  const { paper } = scope.mapPaper(source, new Set(), today, scope.Zotero.Date.strToISO);
  assert.equal(paper.citationKey, "maplabNASAMapUS2025");
  assert.deepEqual({ ...paper.creators[1] }, { creatorType: "author", name: "Mäp Lab" });
  assert.equal(paper.PMID, "00042");
  assert.equal(paper.PMCID, "PMC1234");
  assert.equal(paper.accessDate, today);
});

test("each send reloads the repository vocabulary", async t => {
  const root = await repository(t);
  const { sendPapers } = await plugin(root);
  const item = fixture("generated-key");
  const [first] = await sendPapers(root, [item], today);
  assert.equal(first.status, "written");
  await fs.writeFile(path.join(root, "vocab/domain.yaml"), "climate: Climate\n");
  const [result] = await sendPapers(root, [{ ...item, DOI: "10.1/new", citationKey: "other" }], today);
  const output = yaml.load(await fs.readFile(path.join(root, "papers", result.key, "item.yaml"), "utf8"));
  assert.deepEqual(output.tags, []);
});

test("duplicates use case-insensitive DOI before key collisions; existing files survive", async t => {
  const root = await repository(t);
  const { sendPapers } = await plugin(root);
  const item = { ...fixture("signed-pdf"), DOI: "10.1/Example" };
  const results = await sendPapers(root, [
    item, { ...item, citationKey: "other", DOI: "10.1/EXAMPLE" }, { ...item, DOI: "10.1/different" },
    { ...item, DOI: "" },
  ], today);
  // Same key, different DOI: another paper, refused; without a DOI to compare, skipped as before.
  assert.deepEqual(Array.from(results, result => result.status), ["written", "duplicate", "error", "skipped"]);
  assert.match(results[2].warnings.join(" "), /already holds another paper \(DOI 10\.1\/example\)/);
  assert.equal(results[2].pdf, "not attempted");
  assert.equal(results[1].existingKey, item.citationKey);
  assert.deepEqual(await fs.readdir(path.join(root, "papers")), [item.citationKey]);
  const file = path.join(root, "papers", item.citationKey, "item.yaml");
  assert.equal(yaml.load(await fs.readFile(file, "utf8")).DOI, item.DOI);
});

test("path-like keys and redirected paper directories cannot write outside papers", async t => {
  const root = await repository(t);
  const { sendPapers } = await plugin(root);
  const item = { ...fixture("signed-pdf"), citationKey: "../outside" };
  const [result] = await sendPapers(root, [item], today);
  assert.equal(result.status, "error");
  const outside = path.join(root, "outside");
  await fs.mkdir(outside);
  await fs.symlink(outside, path.join(root, "papers", "linked"));
  await assert.rejects(sendPapers(root, [{ ...item, citationKey: "linked" }], today), /Symbolic link/);
  assert.deepEqual(await fs.readdir(outside), []);
});

test("a destination appearing during publication survives and the temporary file is cleaned up", async t => {
  const root = await repository(t);
  const { scope, sendPapers } = await plugin(root);
  const move = scope.IOUtils.move;
  scope.IOUtils.move = async (from, to, options) => {
    await fs.writeFile(to, "title: existing\n");
    await move(from, to, options);
  };
  const [result] = await sendPapers(root, [fixture("signed-pdf")], today);
  assert.equal(result.status, "skipped");
  const directory = path.join(root, "papers", result.key);
  assert.deepEqual(await fs.readdir(directory), ["item.yaml"]);
  assert.equal(await fs.readFile(path.join(directory, "item.yaml"), "utf8"), "title: existing\n");
});
