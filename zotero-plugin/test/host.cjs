// Node stand-ins for the Zotero/Gecko APIs used by the shipped bootstrap and scripts.
const fs = require("node:fs/promises");
const { readFileSync, lstatSync, openSync, closeSync } = require("node:fs");
const { randomUUID, createHash } = require("node:crypto");
const path = require("node:path");
const vm = require("node:vm");
const os = require("node:os");

const pluginDir = path.resolve(__dirname, "..");
const repoDir = path.dirname(pluginDir);
const today = "2026-11-20";

// Date parsing is provided by Zotero in the application. Model its return contract in Node.
function parseDate(value) {
  if (/^\d{4}(-\d\d(-\d\d)?)?$/.test(value)) return value;
  if (/^[A-Za-z]+ \d{4}$/.test(value)) {
    const time = Date.parse(value + " 00:00 GMT");
    if (Number.isFinite(time)) return new Date(time).toISOString().slice(0, 7);
  }
  return false;
}

async function plugin(root) {
  let menu;
  const alerts = [];
  const attachments = new Map();
  const scope = vm.createContext({
    PathUtils: { join: path.join, filename: path.basename },
    IOUtils: {
      async stat(name) {
        const stat = await fs.stat(name);
        return { type: stat.isFile() ? "regular" : stat.isDirectory() ? "directory" : "other" };
      },
      async exists(name) {
        try { await fs.access(name); return true; }
        catch (error) { if (error.code === "ENOENT") return false; throw error; }
      },
      async getChildren(dir) { return (await fs.readdir(dir)).map(child => path.join(dir, child)); },
      copy: (from, to) => fs.copyFile(from, to),
      computeHexDigest: async (name, method) => createHash(method).update(await fs.readFile(name)).digest("hex"),
      readUTF8: name => fs.readFile(name, "utf8"),
      makeDirectory: name => fs.mkdir(name).catch(error => { if (error.code !== "EEXIST") throw error; }),
      writeUTF8: (name, value) => fs.writeFile(name, value),
      async move(from, to, { noOverwrite }) {
        if (!noOverwrite) return fs.rename(from, to);
        await fs.link(from, to);
        await fs.unlink(from);
      },
      remove: (name, opts) => fs.rm(name, { force: opts.ignoreAbsent }),
    },
    Zotero: {
      Items: { get: id => attachments.get(id) },
      Attachments: { LINK_MODE_LINKED_URL: 3 },
      Prefs: { get: () => root },
      Date: { strToISO: parseDate, dateToSQL: () => today },
      File: { pathToFile: name => ({
        path: name,
        NORMAL_FILE_TYPE: 0,
        isSymlink: () => lstatSync(name).isSymbolicLink(),
        createUnique(type, mode) {
          this.path = name + "-" + randomUUID();
          closeSync(openSync(this.path, "wx", mode));
        },
      }) },
      PreferencePanes: { register() {} },
      MenuManager: { registerMenu(options) { [menu] = options.menus; } },
    },
    Services: {
      scriptloader: { loadSubScript(filename) {
        const file = filename === "vendor/js-yaml.js"
          ? path.join(pluginDir, "node_modules/js-yaml/dist/js-yaml.js")
          : path.join(pluginDir, "addon", filename);
        vm.runInContext(readFileSync(file, "utf8"), scope, { filename: file });
      } },
      prompt: { alert(window, title, message) { alerts.push(message); } },
    },
  });
  scope.Services.scriptloader.loadSubScript("bootstrap.js");
  await scope.startup({ id: "cedalion@test", rootURI: "" });
  function toItem(data, children = [], paths = {}, bestKey) {
    for (const child of children) {
      attachments.set(child.key, {
        id: child.key, key: child.key, dateAdded: child.dateAdded,
        attachmentContentType: child.contentType, attachmentLinkMode: child.linkMode === "linked_url" ? 3 : 1,
        attachmentFilename: child.filename || "",
        getField: field => child[field] || "",
        async getFilePathAsync() {
          const path = paths[child.key];
          return path && await scope.IOUtils.exists(path) ? path : false;
        },
      });
    }
    const tags = new Set((data.tags || []).map(({ tag }) => tag));
    return {
      key: data.key, isRegularItem: () => true, toJSON: () => data, getField: field => data[field],
      getAttachments: () => children.filter(child => child.itemType === "attachment").map(child => child.key),
      getBestAttachment: async () => attachments.get(bestKey),
      hasTag: tag => tags.has(tag), addTag: tag => tags.add(tag), removeTag: tag => tags.delete(tag),
      async saveTx() {},
    };
  }
  const sendPapers = (root, data, today) => scope.sendItems(root, data.map(item => toItem(item)), today);
  return { menu, alerts, scope, toItem, sendPapers, repositoryError: scope.repositoryError };
}

// A made-up domain vocabulary: the fixtures tag one paper "population" and use no other term.
const domainYAML = `population:
  name: Population
  definition: Synthetic term for the tests.
climate:
  name: Climate
  definition: Synthetic term for the tests.
`;

// An empty scrapbook: the three entries the plugin checks before it writes.
async function scrapbook(root, domain = domainYAML) {
  await fs.mkdir(path.join(root, "papers"), { recursive: true });
  await fs.mkdir(path.join(root, "vocab"), { recursive: true });
  await fs.writeFile(path.join(root, "AGENTS.md"), "");
  await fs.writeFile(path.join(root, "vocab/domain.yaml"), domain);
  return root;
}

async function repository(t) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "cedalion-test-"));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  return scrapbook(root);
}

const fixturesDir = path.join(__dirname, "fixtures");

function fixtureRecord(name, dir = fixturesDir) {
  return JSON.parse(readFileSync(path.join(dir, name + ".json"), "utf8"));
}

const fixture = (name, dir) => fixtureRecord(name, dir).item;

module.exports = { plugin, repository, scrapbook, domainYAML, fixture, fixtureRecord, repoDir, today, parseDate };
