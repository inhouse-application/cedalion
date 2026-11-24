// The caller validates the chosen repository and serializes sends from all Zotero windows.
function assertNotLink(path) {
  if (Zotero.File.pathToFile(path).isSymlink()) throw new Error(`Symbolic link: ${path}`);
}

async function loadRepository(root) {
  const papers = PathUtils.join(root, "papers");
  assertNotLink(papers);
  const vocab = jsyaml.load(await IOUtils.readUTF8(PathUtils.join(root, "vocab", "domain.yaml")));
  if (!vocab || typeof vocab !== "object" || Array.isArray(vocab)) {
    throw new Error("Expected a mapping in vocab/domain.yaml");
  }
  const doiKeys = new Map();
  for (const directory of (await IOUtils.getChildren(papers)).sort()) {
    if ((await IOUtils.stat(directory)).type !== "directory") continue;
    assertNotLink(directory);
    const file = PathUtils.join(directory, "item.yaml");
    if (!await IOUtils.exists(file)) continue;
    const existing = jsyaml.load(await IOUtils.readUTF8(file));
    if (!existing || typeof existing !== "object" || Array.isArray(existing)) {
      throw new Error(`Expected a mapping in ${file}`);
    }
    if (existing.DOI) doiKeys.set(existing.DOI.trim().toLowerCase(), PathUtils.filename(directory));
  }
  return { papers, domains: new Set(Object.keys(vocab)), doiKeys };
}

async function writePaper(papers, paper) {
  const key = paper.citationKey;
  if (!key || key === "." || key === ".." || /[\\/\x00]/.test(key)) {
    throw new Error(`Invalid paper directory name: ${key}`);
  }
  // <key>.supplement.pdf in .cache/pdf holds another paper's supplement.
  if (/\.supplement$/i.test(key)) {
    throw new Error(`Citation key ends with the reserved suffix .supplement: ${key}`);
  }

  const directory = PathUtils.join(papers, key);
  const file = PathUtils.join(directory, "item.yaml");
  if (await IOUtils.exists(file)) return await skipSamePaper(file, paper);
  // These fields are required by tools/check.py. Leave an incomplete item in Zotero.
  for (const field of ["itemType", "title", "creators", "date", "DOI"]) {
    if (!paper[field]) throw new Error(`Missing ${field}`);
  }
  const yaml = jsyaml.dump(paper, { forceQuotes: true, lineWidth: -1 });
  await IOUtils.makeDirectory(directory, { createAncestors: false });
  assertNotLink(directory);
  return await publishNew(directory, "item.yaml", path => IOUtils.writeUTF8(path, yaml))
    ? "written" : await skipSamePaper(file, paper);
}

// A record under the same key with another DOI is a different paper: its PDF and tag must not be
// taken for this one, so the item fails instead of being reported as skipped.
async function skipSamePaper(file, paper) {
  const existing = String(jsyaml.load(await IOUtils.readUTF8(file))?.DOI ?? "").trim().toLowerCase();
  const doi = String(paper.DOI ?? "").trim().toLowerCase();
  if (existing && doi && existing !== doi) {
    throw new Error(`Citation key ${paper.citationKey} already holds another paper (DOI ${existing})`);
  }
  return "skipped";
}

// Stage a complete file beside its destination before publishing without replacement.
async function publishNew(directory, filename, write) {
  const file = PathUtils.join(directory, filename);
  if (await IOUtils.exists(file)) return false;
  const temporary = Zotero.File.pathToFile(PathUtils.join(directory, ".cedalion.tmp"));
  temporary.createUnique(temporary.NORMAL_FILE_TYPE, 0o600);
  try {
    await write(temporary.path);
    try {
      await IOUtils.move(temporary.path, file, { noOverwrite: true });
    } catch (error) {
      if (await IOUtils.exists(file)) return false;
      throw error;
    }
    return true;
  } finally {
    await IOUtils.remove(temporary.path, { ignoreAbsent: true });
  }
}

async function sendPaper({ papers, domains, doiKeys }, item, today) {
  const { paper, warnings } = mapPaper(item, domains, today, date => Zotero.Date.strToISO(date));
  const key = paper.citationKey;
  const doi = paper.DOI?.trim().toLowerCase();
  if (doi && doiKeys.has(doi)) {
    return { key, status: "duplicate", existingKey: doiKeys.get(doi), warnings };
  }
  const status = await writePaper(papers, paper);
  if (status === "written") doiKeys.set(doi, key);
  return { key, status, warnings };
}
