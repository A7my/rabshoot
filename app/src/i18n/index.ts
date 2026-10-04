import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import ar from "./ar";
import en from "./en";

const fromUrl = new URLSearchParams(window.location.search).get("lang");
const saved = (fromUrl === "ar" || fromUrl === "en" ? fromUrl
  : (localStorage.getItem("rabshoot.lang") as "en" | "ar" | null)) ?? "en";

i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, ar: { translation: ar } },
  lng: saved,
  fallbackLng: "en",
  interpolation: { escapeValue: false },
  returnObjects: true,
});

export function applyLanguage(lang: "en" | "ar") {
  localStorage.setItem("rabshoot.lang", lang);
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  if (i18n.language !== lang) i18n.changeLanguage(lang);
}

applyLanguage(saved);

export default i18n;
