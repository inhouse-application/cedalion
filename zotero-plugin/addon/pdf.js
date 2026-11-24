// A supplement is cached beside the paper's PDF with its own provenance; it is never the paper's PDF.
function isSupplement(attachment) {
  return [attachment.getField("title"), attachment.attachmentFilename].some(name => /supplement/i.test(name || ""));
}

function pdfAttachments(item) {
  return item.getAttachments().map(id => Zotero.Items.get(id)).filter(attachment =>
    attachment.attachmentContentType === "application/pdf" &&
    attachment.attachmentLinkMode !== Zotero.Attachments.LINK_MODE_LINKED_URL
  );
}

async function localFiles(attachments) {
  const local = [];
  const missing = [];
  for (const attachment of attachments) {
    const path = await attachment.getFilePathAsync();
    if (path && (await IOUtils.stat(path)).type === "regular") local.push({ attachment, path });
    else missing.push(attachment.key);
  }
  local.sort((a, b) => a.attachment.dateAdded.localeCompare(b.attachment.dateAdded));
  return { local, missing };
}

async function choosePDF(item) {
  const candidates = pdfAttachments(item).filter(attachment => !isSupplement(attachment));
  if (!candidates.length) return { status: "no local PDF", warnings: [] };

  const best = await item.getBestAttachment();
  const { local, missing } = await localFiles(candidates);
  if (!local.length) return { status: "PDF not downloaded", warnings: [] };
  const chosen = local.find(({ attachment }) => attachment.id === best?.id) || local[0];
  return { ...chosen, warnings: missing.map(key => `PDF not downloaded (${key})`) };
}

async function chooseSupplement(item) {
  const candidates = pdfAttachments(item).filter(isSupplement);
  if (!candidates.length) return { status: "none", warnings: [] };

  const { local, missing } = await localFiles(candidates);
  if (!local.length) return { status: "supplement PDF not downloaded", warnings: [] };
  const warnings = missing.map(key => `supplement PDF not downloaded (${key})`);
  if (local.length > 1) warnings.push(`supplement PDFs skipped: ${local.length - 1}`);
  return { ...local[0], warnings };
}

function pdfVersion(title) {
  if (title === "Accepted Version") return "accepted-manuscript";
  if (title === "Submitted Version" || title === "Preprint PDF") return "preprint";
  if (title === "Published Version" || title.endsWith("Full Text PDF")) return "vor";
  return null;
}

async function cacheDirectory(root) {
  let directory = root;
  for (const part of [".cache", "pdf"]) {
    directory = PathUtils.join(directory, part);
    await IOUtils.makeDirectory(directory, { createAncestors: false });
    assertNotLink(directory);
  }
  return directory;
}

// Never replace a cached PDF: compare it with the selected file instead.
async function copyPDF(directory, name, source) {
  const filename = name + ".pdf";
  const copied = await publishNew(directory, filename, async temporary => {
    await IOUtils.copy(source, temporary);
    assertNotLink(temporary);
  });
  if (copied) return "copied";
  const target = PathUtils.join(directory, filename);
  assertNotLink(target);
  const [existing, selected] = await Promise.all([target, source].map(
    path => IOUtils.computeHexDigest(path, "sha256")
  ));
  return existing === selected ? "already present" : "conflict (different SHA-256)";
}

async function writeProvenance(directory, name, provenance) {
  const sidecar = name + ".yaml";
  if (await IOUtils.exists(PathUtils.join(directory, sidecar))) return;
  const data = await provenance();
  await publishNew(directory, sidecar, path => IOUtils.writeUTF8(path, jsyaml.dump(data)));
}

async function cachePDF(root, key, item, doi, result) {
  // <key>.supplement.pdf is another paper's supplement; a record already under such a key gets no PDF.
  if (/\.supplement$/i.test(key)) {
    throw new Error(`Citation key ends with the reserved suffix .supplement: ${key}`);
  }
  const choice = await choosePDF(item);
  result.warnings.push(...choice.warnings);
  if (!choice.attachment) {
    result.pdf = choice.status;
    return;
  }
  const version = pdfVersion(choice.attachment.getField("title"));
  if (!version) result.warnings.push("set version by hand");

  const directory = await cacheDirectory(root);
  result.pdf = await copyPDF(directory, key, choice.path);
  if (result.pdf.startsWith("conflict")) return;

  await writeProvenance(directory, key, async () => {
    let url = choice.attachment.getField("url");
    // A URL with a query string is often signed, expiring or tracking (e.g. ScienceDirect's
    // X-Amz-Security-Token, utm_source); the provenance is copied into committed records, so
    // prefer the DOI link then.
    if (!url || url.includes("?")) {
      // A skipped item can lack a DOI that is already present in its repository record.
      doi ||= jsyaml.load(await IOUtils.readUTF8(PathUtils.join(root, "papers", key, "item.yaml"))).DOI;
      if (doi) url = `https://doi.org/${doi}`;
      else if (!url) throw new Error("Cannot record PDF provenance without an attachment URL or DOI");
    }
    return version ? { url, version } : { url };
  });
}

async function cacheSupplement(root, key, item, result) {
  const choice = await chooseSupplement(item);
  result.warnings.push(...choice.warnings);
  if (!choice.attachment) {
    result.supplement = choice.status;
    return;
  }
  const version = pdfVersion(choice.attachment.getField("title"));
  if (!version) result.warnings.push("set supplement version by hand");

  const directory = await cacheDirectory(root);
  const name = key + ".supplement";
  result.supplement = await copyPDF(directory, name, choice.path);
  if (result.supplement.startsWith("conflict")) return;

  await writeProvenance(directory, name, () => {
    const url = choice.attachment.getField("url");
    // The article DOI does not identify the supplement, so there is no fallback URL.
    if (url && !url.includes("?")) return version ? { url, version } : { url };
    result.warnings.push("set supplement URL by hand");
    return version ? { version } : {};
  });
}
