const repositoryPreference = "cedalion.repositoryPath";
const commandLabel = "Send to Cedalion";

async function repositoryError(root) {
  if (!root) {
    return "Choose a repository folder in Settings → Cedalion.";
  }

  for (const [parts, type] of [
    [["AGENTS.md"], "regular"],
    [["papers"], "directory"],
    [["vocab", "domain.yaml"], "regular"],
  ]) {
    try {
      const entry = await IOUtils.stat(PathUtils.join(root, ...parts));
      if (entry.type === type) continue;
    } catch {
      // A missing or inaccessible marker also makes this folder unusable.
    }
    return `Check the repository folder in Settings → Cedalion. Expected ${parts.join("/")} (${type}).`;
  }
  return null;
}

let pendingSend = Promise.resolve();

async function sendItem(root, repository, item, today) {
  if (!item.isRegularItem()) {
    return {
      key: item.key, status: "skipped", pdf: "skipped", supplement: "skipped", warnings: ["note or attachment"],
    };
  }
  let key = item.key;
  let data, result;
  try {
    data = item.toJSON();
    key = data.citationKey || data.key;
    result = await sendPaper(repository, data, today);
  } catch (error) {
    return { key, status: "error", pdf: "not attempted", supplement: "not attempted", warnings: [error.message] };
  }

  result.pdf = result.supplement = "not attempted";
  const repositoryKey = result.existingKey || result.key;
  try {
    await cachePDF(root, repositoryKey, item, data.DOI, result);
  } catch (error) {
    const stage = result.pdf === "not attempted" ? "PDF" : "Sidecar";
    if (stage === "PDF") result.pdf = "error";
    result.warnings.push(`${stage} error: ${error.message}`);
    return result;
  }
  try {
    await cacheSupplement(root, repositoryKey, item, result);
  } catch (error) {
    const stage = result.supplement === "not attempted" ? "Supplement" : "Supplement sidecar";
    if (stage === "Supplement") result.supplement = "error";
    result.warnings.push(`${stage} error: ${error.message}`);
    return result;
  }

  let added = false;
  try {
    if (!item.hasTag("cedalion")) {
      added = item.addTag("cedalion");
      await item.saveTx();
    }
  } catch (error) {
    if (added) item.removeTag("cedalion");
    result.warnings.push(`Tag error: ${error.message}`);
  }
  return result;
}

async function sendItems(root, items, today) {
  const repository = await loadRepository(root);
  const results = [];
  for (const item of items) results.push(await sendItem(root, repository, item, today));
  return results;
}

function summaryLine(result) {
  const outcome = result.status === "duplicate"
    ? `duplicate (already in repository as ${result.existingKey})` : result.status;
  return [
    result.key, `item.yaml: ${outcome}`, `PDF: ${result.pdf}`, `Supplement: ${result.supplement}`, ...result.warnings,
  ].filter(Boolean).join(" — ").replace(/[\r\n]+/g, " ");
}

async function sendSelection(event, { items }) {
  const regularCount = items.filter(item => item.isRegularItem()).length;
  if (!regularCount) return;
  const window = event.currentTarget.ownerGlobal;
  const root = Zotero.Prefs.get(repositoryPreference);
  let results;
  try {
    const error = await repositoryError(root);
    if (error) throw new Error(error);
    const today = Zotero.Date.dateToSQL(new Date(), false).slice(0, 10);
    const send = pendingSend.then(() => sendItems(root, items, today));
    pendingSend = send.catch(() => {});
    results = await send;
  } catch (error) {
    results = items.map(item => ({
      key: item.key, status: item.isRegularItem() ? "error" : "skipped",
      pdf: "not attempted", supplement: "not attempted", warnings: [error.message],
    }));
  }
  const counts = `Regular items: ${regularCount}\nSkipped items: ${items.length - regularCount}`;
  Services.prompt.alert(window, commandLabel, [counts, ...results.map(summaryLine)].join("\n"));
}

async function startup({ id, rootURI }) {
  for (const script of ["vendor/js-yaml.js", "metadata.js", "repository.js", "pdf.js"]) {
    Services.scriptloader.loadSubScript(rootURI + script, this);
  }
  await Zotero.PreferencePanes.register({
    pluginID: id,
    label: "Cedalion",
    src: "preferences.xhtml",
    scripts: ["preferences.js"],
  });
  Zotero.MenuManager.registerMenu({
    pluginID: id,
    menuID: "send",
    target: "main/library/item",
    menus: [{
      menuType: "menuitem",
      onShowing(event, { items, menuElem, setEnabled }) {
        menuElem.setAttribute("label", commandLabel);
        setEnabled(items.some(item => item.isRegularItem()));
      },
      onCommand: sendSelection,
    }],
  });
}

// Zotero unregisters the menu and preference pane by plugin ID on shutdown.
function shutdown() {}
function install() {}
function uninstall() {}
