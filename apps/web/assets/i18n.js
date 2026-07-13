(function (root) {
  "use strict";

  const STORAGE_KEY = "heyu_locale";
  const SUPPORTED = ["zh-CN", "zh-HK", "en"];
  const originals = new WeakMap();
  let locale = "zh-CN";
  let observer = null;
  let applying = false;

  const normalizeLocale = value => {
    const normalized = String(value || "").replace("_", "-").toLowerCase();
    if (normalized === "zh-hk" || normalized === "zh-tw" || normalized === "zh-hant") return "zh-HK";
    if (normalized === "zh" || normalized === "zh-cn" || normalized === "zh-sg" || normalized === "zh-hans") return "zh-CN";
    if (normalized === "en" || normalized.startsWith("en-")) return "en";
    return "";
  };

  const dictionaries = () => root.HeyuLocales || {};
  const interpolate = (value, variables = {}) => String(value).replace(
    /\{(\w+)\}/g,
    (match, name) => Object.prototype.hasOwnProperty.call(variables, name) ? variables[name] : match,
  );

  const t = (key, variables = {}) => {
    const selected = dictionaries()[locale] || {};
    const fallback = dictionaries()["zh-CN"] || {};
    return interpolate(selected.messages?.[key] ?? fallback.messages?.[key] ?? key, variables);
  };

  const phrase = value => {
    const selected = dictionaries()[locale] || {};
    const fallback = dictionaries()["zh-CN"] || {};
    return selected.phrases?.[value] ?? fallback.phrases?.[value] ?? value;
  };

  const remember = (node, kind, value) => {
    const record = originals.get(node) || {};
    if (!(kind in record)) record[kind] = value;
    originals.set(node, record);
    return record[kind];
  };

  const translateTextNode = node => {
    if (!node.nodeValue || !node.nodeValue.trim()) return;
    if (node.parentElement?.closest("script,style,[data-i18n-ignore],[data-business-data]")) return;
    const source = remember(node, "text", node.nodeValue);
    const leading = source.match(/^\s*/)?.[0] || "";
    const trailing = source.match(/\s*$/)?.[0] || "";
    const body = source.trim();
    const translated = phrase(body);
    node.nodeValue = `${leading}${translated}${trailing}`;
  };

  const translateElement = element => {
    if (!(element instanceof Element) || element.closest("[data-i18n-ignore],[data-business-data]")) return;
    const key = element.dataset.i18n;
    if (key) element.textContent = t(key);
    const attributes = [
      ["placeholder", "i18nPlaceholder"],
      ["aria-label", "i18nAriaLabel"],
      ["title", "i18nTitle"],
      ["alt", "i18nAlt"],
      ["content", "i18nContent"],
    ];
    for (const [attribute, datasetKey] of attributes) {
      if (!element.hasAttribute(attribute)) continue;
      const explicitKey = element.dataset[datasetKey];
      if (explicitKey) element.setAttribute(attribute, t(explicitKey));
      else element.setAttribute(attribute, phrase(remember(element, attribute, element.getAttribute(attribute))));
    }
  };

  const translateDocument = (rootNode = document) => {
    applying = true;
    try {
      const scope = rootNode instanceof Element ? rootNode : document.documentElement;
      translateElement(scope);
      scope.querySelectorAll("*").forEach(translateElement);
      const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) translateTextNode(walker.currentNode);
      document.documentElement.lang = locale;
      const titleKey = document.body.dataset.i18nTitle;
      const descriptionKey = document.body.dataset.i18nDescription;
      if (titleKey) document.title = t(titleKey);
      if (descriptionKey) document.querySelector('meta[name="description"]')?.setAttribute("content", t(descriptionKey));
      document.querySelectorAll("[data-locale]").forEach(button => {
        const active = button.dataset.locale === locale;
        button.classList.toggle("active", active);
        button.setAttribute("aria-pressed", String(active));
      });
    } finally {
      applying = false;
    }
  };

  const formatDate = (value, options = {}) => {
    if (!value) return "";
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat(locale === "en" ? "en-US" : locale, {
      dateStyle: "medium",
      timeStyle: "short",
      ...options,
    }).format(date);
  };

  const formatNumber = (value, options = {}) => new Intl.NumberFormat(
    locale === "en" ? "en-US" : locale,
    options,
  ).format(value);

  const setLocale = (nextLocale, { persist = true } = {}) => {
    const normalized = normalizeLocale(nextLocale) || "zh-CN";
    if (!SUPPORTED.includes(normalized)) return;
    locale = normalized;
    if (persist) localStorage.setItem(STORAGE_KEY, locale);
    translateDocument();
    document.dispatchEvent(new CustomEvent("heyu:localechange", { detail: { locale } }));
  };

  const localeFromUrl = () => normalizeLocale(new URLSearchParams(location.search).get("lang"));
  const browserLocale = () => {
    for (const value of navigator.languages || [navigator.language]) {
      const normalized = normalizeLocale(value);
      if (normalized) return normalized;
    }
    return "";
  };

  const init = () => {
    locale = localeFromUrl()
      || normalizeLocale(localStorage.getItem(STORAGE_KEY))
      || normalizeLocale(document.documentElement.lang)
      || browserLocale()
      || "zh-CN";
    document.addEventListener("click", event => {
      const button = event.target.closest("[data-locale]");
      if (button) setLocale(button.dataset.locale);
    });
    translateDocument();
    observer = new MutationObserver(records => {
      if (applying) return;
      applying = true;
      try {
        records.forEach(record => {
          record.addedNodes.forEach(node => {
            if (node.nodeType === Node.TEXT_NODE) translateTextNode(node);
            else if (node.nodeType === Node.ELEMENT_NODE) {
              translateElement(node);
              node.querySelectorAll("*").forEach(translateElement);
              const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
              while (walker.nextNode()) translateTextNode(walker.currentNode);
            }
          });
        });
      } finally {
        applying = false;
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  };

  root.HeyuI18n = {
    formatDate,
    formatNumber,
    getLocale: () => locale,
    init,
    normalizeLocale,
    phrase,
    setLocale,
    supportedLocales: [...SUPPORTED],
    t,
    translateDocument,
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})(globalThis);
