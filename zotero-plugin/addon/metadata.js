// Keep the fallback in sync with tools/add_scrap.py's citation_key().
const stopwords = new Set((
  "a an the some from on in to of do with der die das ein eine einer eines einem einen un une la le " +
  "les el las los al uno una unos unas de des del d and or for by at as is are"
).split(" "));

function asciiFold(text) {
  return text.normalize("NFKD").replace(/[^\x00-\x7f]/g, "");
}

function citationKey(item, year) {
  if (item.citationKey?.trim()) return item.citationKey;
  const author = item.creators?.find(creator => creator.creatorType === "author");
  const family = asciiFold(author?.lastName || author?.name || "anon").toLowerCase().replace(/[^a-z]/g, "");
  const words = asciiFold(item.title || "").match(/[A-Za-z0-9]+/g) || [];
  const shortTitle = words.filter(word => !stopwords.has(word.toLowerCase())).slice(0, 3)
    .map(word => word[0].toUpperCase() + word.slice(1)).join("");
  return family + shortTitle + year;
}

function populatedFields(record) {
  return Object.fromEntries(Object.entries(record).filter(([, value]) =>
    value != null && (typeof value !== "string" || value.trim() !== "") &&
    (!Array.isArray(value) || value.length > 0)
  ));
}

function mapPaper(item, domains, today, parseDate) {
  const warnings = [];
  const parsed = item.date && parseDate(item.date);
  const time = /^\d{4}(-\d{2}(-\d{2})?)?$/.test(parsed) ? Date.parse(parsed) : NaN;
  const isoDate = Number.isFinite(time) && new Date(time).toISOString().startsWith(parsed) ? parsed : null;
  if (item.date && !isoDate) warnings.push(`Unparsed date: ${item.date}`);
  const creators = (item.creators || []).map(({ creatorType, name, firstName, lastName }) =>
    populatedFields(name ? { creatorType, name } : { creatorType, firstName, lastName })
  );
  const extra = item.extra || "";
  const paper = populatedFields({
    itemType: item.itemType,
    citationKey: citationKey(item, isoDate ? isoDate.slice(0, 4) : ""),
    title: item.title,
    creators,
    publicationTitle: item.publicationTitle,
    journalAbbreviation: item.journalAbbreviation,
    volume: item.volume,
    issue: item.issue,
    pages: item.pages,
    date: isoDate || item.date,
    DOI: item.DOI,
    ISSN: item.ISSN,
    PMID: /^PMID:[ \t]*(\d+)[ \t]*\r?$/m.exec(extra)?.[1],
    PMCID: /^PMCID:[ \t]*(PMC\d+)[ \t]*\r?$/m.exec(extra)?.[1],
    url: item.url,
    language: item.language,
    rights: item.rights,
    accessDate: item.accessDate?.slice(0, 10) || today,
    libraryCatalog: item.libraryCatalog,
  });
  paper.tags = (item.tags || []).filter(({ tag }) => domains.has(tag)).map(({ tag }) => ({ tag }));
  return { paper, warnings };
}
