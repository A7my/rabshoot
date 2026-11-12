/** Theme, zoom and text size: a UI-only preference kept in localStorage so it applies before the engine is up. */
import { useSyncExternalStore } from "react";
import { isTauri } from "./platform";

export type ThemeMode = "system" | "light" | "dark";
export type Appearance = { theme: ThemeMode; zoom: number; textScale: number };

export const ZOOM_STEPS = [0.8, 0.9, 1, 1.1, 1.2, 1.3, 1.4, 1.5];
export const TEXT_SIZES = [
  { key: "small", scale: 0.9 },
  { key: "normal", scale: 1 },
  { key: "large", scale: 1.12 },
  { key: "xlarge", scale: 1.25 },
] as const;

const KEY = "rabshoot.appearance";
const DEFAULTS: Appearance = { theme: "system", zoom: 1, textScale: 1 };

function load(): Appearance {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? "{}") as Partial<Appearance>;
    return {
      theme: saved.theme === "light" || saved.theme === "dark" ? saved.theme : "system",
      zoom: ZOOM_STEPS.includes(saved.zoom ?? 1) ? saved.zoom! : 1,
      textScale: TEXT_SIZES.some((s) => s.scale === saved.textScale) ? saved.textScale! : 1,
    };
  } catch {
    return DEFAULTS;
  }
}

const media = window.matchMedia("(prefers-color-scheme: dark)");
let state = load();
let systemDark = media.matches;
const listeners = new Set<() => void>();
let snapshot = { ...state, dark: false };

function resolveDark() {
  return state.theme === "system" ? systemDark : state.theme === "dark";
}

function render() {
  const root = document.documentElement;
  const dark = resolveDark();
  root.classList.toggle("dark", dark);
  root.style.setProperty("--text-scale", String(state.textScale));
  if (!isTauri) root.style.fontSize = state.zoom === 1 ? "" : `${state.zoom * 100}%`;
  snapshot = { ...state, dark };
  listeners.forEach((l) => l());
}

async function syncNative(changed: { theme?: boolean; zoom?: boolean }) {
  if (!isTauri) return;
  if (changed.zoom) {
    const { getCurrentWebview } = await import("@tauri-apps/api/webview");
    await getCurrentWebview().setZoom(state.zoom).catch(() => undefined);
  }
  if (changed.theme) {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    const win = getCurrentWindow();
    await win.setTheme(state.theme === "system" ? null : state.theme).catch(() => undefined);
    if (state.theme === "system") {
      const current = await win.theme().catch(() => null);
      if (current) { systemDark = current === "dark"; render(); }
    }
  }
}

export function setAppearance(patch: Partial<Appearance>) {
  const changed = { theme: patch.theme !== undefined && patch.theme !== state.theme, zoom: patch.zoom !== undefined && patch.zoom !== state.zoom };
  state = { ...state, ...patch };
  localStorage.setItem(KEY, JSON.stringify(state));
  render();
  void syncNative(changed);
}

export function stepZoom(direction: 1 | -1) {
  const i = ZOOM_STEPS.indexOf(state.zoom);
  const next = ZOOM_STEPS[Math.min(ZOOM_STEPS.length - 1, Math.max(0, i + direction))];
  setAppearance({ zoom: next });
}

export function useAppearance() {
  return useSyncExternalStore(
    (l) => { listeners.add(l); return () => listeners.delete(l); },
    () => snapshot,
  );
}

media.addEventListener("change", (e) => {
  if (state.theme !== "system") return;
  systemDark = e.matches;
  render();
});

if (isTauri) {
  import("@tauri-apps/api/window").then(({ getCurrentWindow }) =>
    getCurrentWindow().onThemeChanged(({ payload }) => {
      if (state.theme !== "system") return;
      systemDark = payload === "dark";
      render();
    }),
  );
}

window.addEventListener("keydown", (e) => {
  if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
  if (e.key === "=" || e.key === "+") stepZoom(1);
  else if (e.key === "-" || e.key === "_") stepZoom(-1);
  else if (e.key === "0") setAppearance({ zoom: 1 });
  else return;
  e.preventDefault();
});

render();
void syncNative({ theme: true, zoom: state.zoom !== 1 });
