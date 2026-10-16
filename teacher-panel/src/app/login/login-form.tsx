"use client";

import { useState, type FormEvent } from "react";
import { GraduationCapIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { t } from "@/lib/i18n";

export function LoginForm({ next }: { next: string }) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone: form.get("phone"), password: form.get("password") }),
      });
      if (res.ok) {
        window.location.assign(next);
        return;
      }
      const body = await res.json().catch(() => null);
      setError(body?.detail?.message ?? t.app.genericError);
    } catch {
      setError(t.app.genericError);
    }
    setBusy(false);
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader className="items-center text-center">
        <div className="mx-auto mb-2 flex size-12 items-center justify-center rounded-full bg-primary text-primary-foreground">
          <GraduationCapIcon className="size-6" />
        </div>
        <CardTitle className="text-xl">{t.login.title}</CardTitle>
        <CardDescription>{t.login.subtitle}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="phone">{t.login.phone}</Label>
            <Input
              id="phone"
              name="phone"
              type="tel"
              inputMode="tel"
              autoComplete="username"
              placeholder={t.login.phonePlaceholder}
              required
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="password">{t.login.password}</Label>
            <Input id="password" name="password" type="password" autoComplete="current-password" required />
          </div>
          {error && (
            <p role="alert" data-testid="login-error" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}
          <Button type="submit" size="lg" disabled={busy}>
            {busy ? t.login.submitting : t.login.submit}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
