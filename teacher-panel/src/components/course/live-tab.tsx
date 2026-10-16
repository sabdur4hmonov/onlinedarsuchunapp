"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import useSWR from "swr";
import { CalendarPlusIcon, RadioIcon, RotateCcwIcon, XIcon } from "lucide-react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { LiveStatusBadge, RecordingStatusBadge } from "@/components/status-badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError, fetcher } from "@/lib/api";
import { fmt, formatDateTime, t } from "@/lib/i18n";
import type { LiveSession } from "@/lib/types";

const BUSY_RECORDING = new Set(["recording", "uploading", "processing"]);

export function LiveTab({ courseId }: { courseId: string }) {
  const key = `/teacher/courses/${courseId}/live-sessions`;
  const { data, isLoading, mutate } = useSWR<LiveSession[]>(key, fetcher, {
    refreshInterval: (latest) =>
      latest?.some((s) => s.status === "live" || BUSY_RECORDING.has(s.recording_status)) ? 5_000 : 0,
  });
  const [cancelling, setCancelling] = useState<LiveSession | null>(null);

  async function retry(session: LiveSession) {
    try {
      await api(`/teacher/live-sessions/${session.id}/recording/retry`, { method: "POST" });
      toast.success(t.live.retried);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t.app.genericError);
    }
    mutate();
  }

  return (
    <div className="grid gap-4">
      <ScheduleForm courseId={courseId} onCreated={() => mutate()} />
      {isLoading && <Skeleton className="h-24 rounded-xl" />}
      {data?.length === 0 && <p className="py-8 text-center text-muted-foreground">{t.live.empty}</p>}

      <div className="grid gap-2">
        {data?.map((s) => (
          <Card key={s.id} size="sm" data-testid="live-row">
            <CardContent className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="font-medium break-words">{s.title}</p>
                <p className="text-sm text-muted-foreground">{formatDateTime(s.started_at ?? s.scheduled_at)}</p>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <LiveStatusBadge status={s.status} />
                  {s.recording_status !== "none" && (
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                      {t.live.recording}: <RecordingStatusBadge status={s.recording_status} />
                    </span>
                  )}
                </div>
                {s.recording_status === "failed" && s.recording_error && (
                  <p className="mt-1 text-xs break-all text-destructive">{s.recording_error}</p>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {s.recording_status === "failed" && (
                  <Button variant="outline" size="sm" onClick={() => retry(s)} data-testid="recording-retry">
                    <RotateCcwIcon />
                    {t.live.retryRecording}
                  </Button>
                )}
                {(s.status === "scheduled" || s.status === "live") && (
                  <Link
                    href={`/courses/${courseId}/live/${s.id}`}
                    className={buttonVariants({ size: "sm", variant: s.status === "live" ? "destructive" : "default" })}
                    data-testid="live-open"
                  >
                    <RadioIcon />
                    {t.live.open}
                  </Link>
                )}
                {s.status === "scheduled" && (
                  <Button variant="ghost" size="sm" onClick={() => setCancelling(s)} data-testid="live-cancel">
                    <XIcon />
                    {t.live.cancel}
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <ConfirmDialog
        open={cancelling !== null}
        onOpenChange={(open) => !open && setCancelling(null)}
        title={t.live.cancel}
        description={fmt(t.live.cancelConfirm, { title: cancelling?.title ?? "" })}
        confirmLabel={t.live.cancel}
        onConfirm={async () => {
          if (!cancelling) return;
          try {
            await api(`/teacher/live-sessions/${cancelling.id}/cancel`, { method: "POST" });
            toast.success(t.live.cancelled);
            mutate();
          } catch (e) {
            toast.error(e instanceof ApiError ? e.message : t.app.genericError);
          }
        }}
      />
    </div>
  );
}

function ScheduleForm({ courseId, onCreated }: { courseId: string; onCreated: () => void }) {
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const formEl = e.currentTarget;
    const form = new FormData(formEl);
    const when = String(form.get("when") ?? "");
    if (!when) return;
    setBusy(true);
    try {
      await api(`/teacher/courses/${courseId}/live-sessions`, {
        method: "POST",
        // datetime-local is the teacher's local time; send it with the timezone offset
        json: { title: String(form.get("title")).trim(), scheduled_at: new Date(when).toISOString() },
      });
      toast.success(t.live.scheduled);
      formEl.reset();
      onCreated();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t.app.genericError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card size="sm">
      <CardContent>
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-[1fr_auto_auto] sm:items-end">
          <div className="grid gap-1">
            <Label htmlFor="live-title">{t.live.title}</Label>
            <Input id="live-title" name="title" required maxLength={255} />
          </div>
          <div className="grid gap-1">
            <Label htmlFor="live-when">{t.live.when}</Label>
            <Input id="live-when" name="when" type="datetime-local" required />
          </div>
          <Button type="submit" disabled={busy} data-testid="live-schedule">
            <CalendarPlusIcon />
            {t.live.schedule}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
