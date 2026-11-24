window.chooseCedalionRepository = async function () {
  const { FilePicker } = ChromeUtils.importESModule("chrome://zotero/content/modules/filePicker.mjs");
  const picker = new FilePicker();
  picker.init(window, "Choose Cedalion repository", picker.modeGetFolder);
  if (await picker.show() === picker.returnOK) {
    Zotero.Prefs.set("cedalion.repositoryPath", picker.file);
  }
};
