const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const test = require("node:test");
const { plugin, repository, fixture } = require("./host.cjs");

test("accepts the repository and rejects an unset path", async t => {
  const root = await repository(t);
  const { repositoryError } = await plugin(root);
  assert.equal(await repositoryError(root), null);
  assert.match(await repositoryError(""), /Choose a repository/);
});

for (const marker of ["AGENTS.md", "papers", "vocab/domain.yaml"]) {
  test(`rejects a missing or wrong-type ${marker}`, async t => {
    const root = await repository(t);
    const { repositoryError } = await plugin(root);
    const entry = path.join(root, marker);
    await fs.rm(entry, { recursive: true });
    assert.ok((await repositoryError(root)).includes(marker));
    if (marker === "papers") await fs.writeFile(entry, "");
    else await fs.mkdir(entry);
    assert.ok((await repositoryError(root)).includes(marker));
  });
}

test("enables regular selections and reports skipped items in a mixed selection", async t => {
  const { menu, alerts, toItem } = await plugin(await repository(t));
  const regular = toItem(fixture("generated-key"));
  const child = { key: "NOTE0001", isRegularItem: () => false };
  const event = { currentTarget: { ownerGlobal: {} } };
  for (const [items, enabled] of [[[], false], [[child], false], [[regular], true], [[child, regular, child], true]]) {
    const labels = {};
    let actual;
    menu.onShowing(event, {
      items,
      menuElem: { setAttribute(name, value) { labels[name] = value; } },
      setEnabled(value) { actual = value; },
    });
    assert.equal(actual, enabled);
    assert.equal(labels.label, "Send to Cedalion");
  }
  await menu.onCommand(event, { items: [child] });
  await menu.onCommand(event, { items: [child, regular, child] });
  assert.equal(alerts.length, 1);
  assert.match(alerts[0], /Regular items: 1\nSkipped items: 2/);
  assert.match(alerts[0], /odegaardnunezSyntheticGriddedCounts2025 — item.yaml: written — PDF: no local PDF/);
});

test("send displays the folder error for an invalid repository", async t => {
  const root = await repository(t);
  await fs.unlink(path.join(root, "AGENTS.md"));
  const { menu, alerts } = await plugin(root);
  await menu.onCommand({ currentTarget: { ownerGlobal: {} } }, { items: [{ isRegularItem: () => true }] });
  assert.equal(alerts.length, 1);
  assert.match(alerts[0], /Expected AGENTS\.md/);
  assert.deepEqual(await fs.readdir(path.join(root, "papers")), []);
});

test("manifest declares the release updates.json URL and matches package.json version", async () => {
  const pkg = JSON.parse(await fs.readFile(path.join(__dirname, "..", "package.json"), "utf8"));
  const manifest = JSON.parse(await fs.readFile(path.join(__dirname, "..", "addon", "manifest.json"), "utf8"));
  assert.equal(manifest.version, pkg.version);
  assert.equal(manifest.applications.zotero.id, "cedalion@cedalion.local");
  assert.equal(
    manifest.applications.zotero.update_url,
    "https://github.com/inhouse-application/cedalion/releases/latest/download/updates.json",
  );
  assert.ok(manifest.applications.zotero.strict_min_version);
  assert.ok(manifest.applications.zotero.strict_max_version);
});
