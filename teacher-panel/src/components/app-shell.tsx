"use client";

import Link from "next/link";
import { useState } from "react";
import { GraduationCapIcon, LogOutIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { t } from "@/lib/i18n";

export function AppShell({ children }: { children: React.ReactNode }) {
  const [leaving, setLeaving] = useState(false);

  async function logout() {
    setLeaving(true);
    await fetch("/api/auth/logout", { method: "POST" }).catch(() => null);
    window.location.assign("/login");
  }

  return (
    <div className="flex min-h-full flex-1 flex-col">
      <header className="sticky top-0 z-40 border-b bg-background/90 backdrop-blur">
        <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between gap-2 px-4">
          <Link href="/courses" className="flex items-center gap-2 font-semibold">
            <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <GraduationCapIcon className="size-4" />
            </span>
            <span className="hidden sm:inline">{t.app.name}</span>
            <span className="text-sm font-normal text-muted-foreground">{t.app.panel}</span>
          </Link>
          <Button variant="ghost" size="sm" onClick={logout} disabled={leaving} data-testid="logout">
            <LogOutIcon />
            <span className="hidden sm:inline">{t.app.logout}</span>
          </Button>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">{children}</main>
    </div>
  );
}
