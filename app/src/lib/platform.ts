/** Thin wrappers so the UI also runs in a normal browser during development. */

export const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export async function openUrl(url: string): Promise<void> {
  if (isTauri) {
    const { openUrl: open } = await import("@tauri-apps/plugin-opener");
    await open(url);
  } else {
    window.open(url, "_blank", "noopener");
  }
}

export async function engineInfo(): Promise<{ url: string; token: string }> {
  if (isTauri) {
    const { invoke } = await import("@tauri-apps/api/core");
    const info = await invoke<{ port: number; token: string }>("engine_info");
    return { url: `http://127.0.0.1:${info.port}`, token: info.token };
  }
  return {
    url: import.meta.env.VITE_ENGINE_URL || "http://127.0.0.1:8765",
    token: import.meta.env.VITE_ENGINE_TOKEN || "dev",
  };
}

export async function notify(title: string, body: string): Promise<void> {
  if (!isTauri) return;
  const n = await import("@tauri-apps/plugin-notification");
  let granted = await n.isPermissionGranted();
  if (!granted) granted = (await n.requestPermission()) === "granted";
  if (granted) n.sendNotification({ title, body });
}

export async function setAutostart(enabled: boolean): Promise<void> {
  if (!isTauri) return;
  const a = await import("@tauri-apps/plugin-autostart");
  if (enabled && !(await a.isEnabled())) await a.enable();
  if (!enabled && (await a.isEnabled())) await a.disable();
}

export function onShellEvent(name: string, callback: () => void): () => void {
  if (!isTauri) return () => undefined;
  let unlisten: (() => void) | undefined;
  let cancelled = false;
  import("@tauri-apps/api/event").then(({ listen }) =>
    listen(name, callback).then((fn) => (cancelled ? fn() : (unlisten = fn))),
  );
  return () => {
    cancelled = true;
    unlisten?.();
  };
}

export async function copyText(text: string): Promise<void> {
  await navigator.clipboard.writeText(text);
}
