"use client";

import useSWRInfinite from "swr/infinite";
import { ShieldAlertIcon, ShieldCheckIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { fetcher } from "@/lib/api";
import { formatDateTime, t } from "@/lib/i18n";
import type { AuditEvent } from "@/lib/types";
import { cn } from "@/lib/utils";

const PAGE = 50;
const ALARMING = new Set([
  "login_failed",
  "login_denied",
  "device_already_bound_to_other_account",
  "refresh_token_reuse_detected",
  "playback_denied",
  "live_join_denied",
  "recording_failed",
]);

function detailText(e: AuditEvent): string {
  const d = e.details;
  const parts: string[] = [];
  if (typeof d.reason === "string") parts.push(d.reason);
  if (typeof d.step === "string") parts.push(d.step);
  if (typeof d.device_id === "string") parts.push(`qurilma: ${d.device_id.slice(0, 18)}`);
  if (e.ip) parts.push(`IP: ${e.ip}`);
  return parts.join(" · ");
}

export function EventsTab({ courseId }: { courseId: string }) {
  const { data, size, setSize, isLoading, isValidating } = useSWRInfinite<AuditEvent[]>(
    (index, previous) => {
      if (previous && previous.length < PAGE) return null; // reached the end
      const before = previous?.at(-1)?.id;
      return `/teacher/courses/${courseId}/events?limit=${PAGE}${before ? `&before_id=${before}` : ""}`;
    },
    fetcher,
  );
  const events = data?.flat() ?? [];
  const hasMore = (data?.at(-1)?.length ?? 0) === PAGE;

  return (
    <div className="grid gap-2">
      {isLoading && <Skeleton className="h-24 rounded-xl" />}
      {!isLoading && events.length === 0 && <p className="py-8 text-center text-muted-foreground">{t.events.empty}</p>}
      <ul className="grid gap-2">
        {events.map((e) => {
          const alarm = ALARMING.has(e.event_type);
          return (
            <li
              key={e.id}
              className={cn("flex gap-3 rounded-lg border bg-background p-3", alarm && "border-destructive/30 bg-destructive/5")}
              data-testid="event-row"
              data-event-type={e.event_type}
            >
              {alarm ? (
                <ShieldAlertIcon className="mt-0.5 size-4 shrink-0 text-destructive" />
              ) : (
                <ShieldCheckIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              )}
              <div className="min-w-0 flex-1">
                <p className="font-medium">{t.events.types[e.event_type] ?? e.event_type}</p>
                <p className="text-sm text-muted-foreground">
                  {e.actor ? `${e.actor.full_name} (${e.actor.phone})` : "—"}
                </p>
                {detailText(e) && <p className="text-xs break-all text-muted-foreground">{detailText(e)}</p>}
              </div>
              <time className="shrink-0 text-xs text-muted-foreground tabular-nums" dateTime={e.created_at}>
                {formatDateTime(e.created_at)}
              </time>
            </li>
          );
        })}
      </ul>
      {hasMore && (
        <Button variant="outline" onClick={() => setSize(size + 1)} disabled={isValidating}>
          {t.events.loadMore}
        </Button>
      )}
    </div>
  );
}
