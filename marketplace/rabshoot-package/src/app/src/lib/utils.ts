import clsx, { type ClassValue } from "clsx";
import type { Profile } from "./types";

export const cn = (...values: ClassValue[]) => clsx(values);

export const DAYS = ["sat", "sun", "mon", "tue", "wed", "thu", "fri"] as const;
const ORDER = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

/** "sun-thu" / "mon,wed" / "*" → set of day keys. */
export function expandDays(value: string): Set<string> {
  const v = (value || "*").trim().toLowerCase();
  if (v === "*" || !v) return new Set(ORDER);
  const out = new Set<string>();
  for (const part of v.split(",").map((p) => p.trim())) {
    if (part.includes("-")) {
      const [a, b] = part.split("-").map((p) => p.trim());
      let i = ORDER.indexOf(a);
      const j = ORDER.indexOf(b);
      if (i < 0 || j < 0) continue;
      for (;;) {
        out.add(ORDER[i]);
        if (i === j) break;
        i = (i + 1) % 7;
      }
    } else if (ORDER.includes(part)) out.add(part);
  }
  return out;
}

export function compactDays(days: Set<string>): string {
  if (days.size === 7) return "*";
  return ORDER.filter((d) => days.has(d)).join(",");
}

export const DAY_PRESETS: Record<string, string> = {
  sun_thu: "sun,mon,tue,wed,thu",
  mon_fri: "mon,tue,wed,thu,fri",
  everyday: "*",
};

export function localTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export function timezones(): string[] {
  try {
    return (Intl as any).supportedValuesOf("timeZone") as string[];
  } catch {
    return ["UTC", "Africa/Cairo", "Asia/Riyadh", "Asia/Dubai", "Europe/London", "America/New_York"];
  }
}

export function formatDateTime(iso: string | null | undefined, lang: string, timeZone?: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const options: Intl.DateTimeFormatOptions = {
    weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false,
  };
  try {
    return d.toLocaleString(lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB", timeZone ? { ...options, timeZone } : options);
  } catch {
    return d.toLocaleString(lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB", options);
  }
}

export function formatTime(iso: string | null | undefined, lang: string, timeZone?: string): string {
  if (!iso) return "—";
  const options: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit", hour12: false };
  const locale = lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB";
  try {
    return new Date(iso).toLocaleTimeString(locale, timeZone ? { ...options, timeZone } : options);
  } catch {
    return new Date(iso).toLocaleTimeString(locale, options);
  }
}

/** YYYY-MM-DD of an instant as seen in a time zone (now when iso is omitted). */
export function dayIn(timeZone: string, iso?: string | null): string {
  const d = iso ? new Date(iso) : new Date();
  try {
    return d.toLocaleDateString("en-CA", { timeZone });
  } catch {
    return d.toLocaleDateString("en-CA");
  }
}

/** A YYYY-MM-DD day moved by `n` days. */
export function shiftDay(day: string, n: number): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}

/** A YYYY-MM-DD day as "Tue, Sep 29" in the UI language. */
export function formatDay(day: string, lang: string): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(lang === "ar" ? "ar-EG" : "en-US",
    { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });
}

/** Milliseconds from now until a wall-clock date + time in a time zone (negative if past). */
export function msUntil(dateStr: string, time: string, timeZone: string): number {
  const [y, mo, d] = dateStr.split("-").map(Number);
  const [h, mi] = time.split(":").map(Number);
  const guess = Date.UTC(y, mo - 1, d, h, mi);
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-US", {
    timeZone, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  }).formatToParts(new Date(guess)).map((p) => [p.type, p.value]));
  const shown = Date.UTC(+parts.year, +parts.month - 1, +parts.day, +parts.hour, +parts.minute);
  return guess - (shown - guess) - Date.now();
}

export function relativeTime(iso: string | null | undefined, lang: string): string {
  if (!iso) return "—";
  const diff = (new Date(iso).getTime() - Date.now()) / 1000;
  const rtf = new Intl.RelativeTimeFormat(lang === "ar" ? "ar" : "en", { numeric: "auto" });
  const abs = Math.abs(diff);
  if (abs < 60) return rtf.format(Math.round(diff), "second");
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  return rtf.format(Math.round(diff / 86400), "day");
}

export const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function newProfile(timezone: string): Profile {
  return {
    id: "",
    name: "Daily report",
    enabled: true,
    sender_connection_id: null,
    delivery: {
      mode: "recipients", to: [], cc: [], bcc: [], thread: null, reply_all: true,
      subject: "{title} — {date}", sender_name: "",
    },
    code_sources: [],
    slack: {
      connection_id: null, conversations: [], ignore_messages: [], ignore_leftover_words: 2,
      thread_lookback_days: 7, include_bots: false,
    },
    ai_connection_id: null,
    schedule: { mode: "recurring", time: "18:00", days: "sun-thu", once_date: null, timezone, catch_up: true, skip_empty: true },
    report: {
      title: "Daily Report", language: "English", extra_instructions: "", max_points: 6,
      max_diff_chars_per_project: 20000, max_items_per_section: 50,
      sections: { code_changes: true, commits: false, merge_requests: true, issues: true, slack: true },
      branding: true,
    },
  };
}

/** Strip server-computed fields before sending a profile back. */
export function toProfile(p: Profile & Record<string, any>): Profile {
  const { problems: _a, next_run: _b, last_run: _c, running: _d, ...rest } = p;
  return rest as Profile;
}
