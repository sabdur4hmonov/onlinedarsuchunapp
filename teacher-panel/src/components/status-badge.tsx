import { Badge } from "@/components/ui/badge";
import { t } from "@/lib/i18n";
import type { LessonStatus, LiveStatus, RecordingStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const tone = {
  neutral: "bg-muted text-muted-foreground",
  progress: "bg-amber-100 text-amber-900 dark:bg-amber-500/20 dark:text-amber-200",
  good: "bg-emerald-100 text-emerald-900 dark:bg-emerald-500/20 dark:text-emerald-200",
  bad: "bg-destructive/10 text-destructive",
  live: "bg-red-600 text-white",
};

function StatusBadge({ label, kind, testId }: { label: string; kind: keyof typeof tone; testId?: string }) {
  return (
    <Badge variant="secondary" className={cn("font-medium", tone[kind])} data-testid={testId}>
      {kind === "live" && <span className="mr-1 inline-block size-1.5 animate-pulse rounded-full bg-white" />}
      {label}
    </Badge>
  );
}

const lessonKind: Record<LessonStatus, keyof typeof tone> = {
  uploading: "progress",
  processing: "progress",
  ready: "good",
  failed: "bad",
};
export function LessonStatusBadge({ status }: { status: LessonStatus }) {
  return <StatusBadge label={t.lessons.status[status]} kind={lessonKind[status]} testId="lesson-status" />;
}

const liveKind: Record<LiveStatus, keyof typeof tone> = {
  scheduled: "neutral",
  live: "live",
  ended: "neutral",
  cancelled: "bad",
};
export function LiveStatusBadge({ status }: { status: LiveStatus }) {
  return <StatusBadge label={t.live.status[status]} kind={liveKind[status]} testId="live-status" />;
}

const recordingKind: Record<RecordingStatus, keyof typeof tone> = {
  none: "neutral",
  recording: "live",
  uploading: "progress",
  processing: "progress",
  ready: "good",
  failed: "bad",
};
export function RecordingStatusBadge({ status }: { status: RecordingStatus }) {
  return <StatusBadge label={t.live.recordingStatus[status]} kind={recordingKind[status]} testId="recording-status" />;
}
