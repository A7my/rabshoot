import { History, KeyRound, LayoutDashboard, Plus, Settings } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, useNavigate } from "react-router-dom";
import { openUrl } from "../lib/platform";
import { cn } from "../lib/utils";

export const AUTHOR = "Mohamed Azmy";
export const AUTHOR_URL = "https://linkedin.com/in/mohamed-3zmy/";
export const PROJECT_URL = "https://github.com/A7my/rabshoot";

export function Brand({ size = "md" }: { size?: "md" | "lg" }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-3">
      <img src="/mark.png" alt="" className={size === "lg" ? "h-14 w-14" : "h-9 w-9"} />
      <div>
        <div className={cn("ltr font-extrabold leading-none tracking-tight", size === "lg" ? "text-3xl" : "text-lg")}>
          <span className="text-white">Rab</span><span className="text-gradient">Shoot</span>
        </div>
        <div className={cn("mt-1 text-muted", size === "lg" ? "text-sm" : "text-[10px] tracking-wide")}>{t("app.tagline")}</div>
      </div>
    </div>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const items = [
    { to: "/", icon: LayoutDashboard, label: t("nav.dashboard"), end: true },
    { to: "/connections", icon: KeyRound, label: t("nav.connections") },
    { to: "/history", icon: History, label: t("nav.history") },
    { to: "/settings", icon: Settings, label: t("nav.settings") },
  ];
  return (
    <div className="flex h-full">
      <aside className="flex w-60 shrink-0 flex-col border-e border-line bg-surface/60 p-4">
        <div className="mb-8 px-1 pt-1"><Brand /></div>
        <button onClick={() => navigate("/profiles/new")}
          className="mb-5 flex h-10 items-center justify-center gap-2 rounded-lg bg-brand text-sm font-medium text-white shadow-glow hover:brightness-110">
          <Plus className="h-4 w-4" /> {t("nav.newReport")}
        </button>
        <nav className="space-y-1">
          {items.map((it) => (
            <NavLink key={it.to} to={it.to} end={it.end}
              className={({ isActive }) => cn("flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                isActive ? "bg-primary/15 text-ink" : "text-muted hover:bg-surface2 hover:text-ink")}>
              <it.icon className="h-4 w-4" />
              {it.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto space-y-0.5 px-1 text-[11px] text-muted/70">
          <div>v{__APP_VERSION__}</div>
          <button type="button" onClick={() => openUrl(AUTHOR_URL)} className="hover:text-primary hover:underline">
            {t("app.by", { name: AUTHOR })}
          </button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl px-8 py-8">{children}</div>
      </main>
    </div>
  );
}
