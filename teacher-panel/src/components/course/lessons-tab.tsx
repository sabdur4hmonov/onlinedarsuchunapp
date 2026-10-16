"use client";

import { useRef, useState, type FormEvent } from "react";
import useSWR from "swr";
import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVerticalIcon, PlusIcon, RefreshCwIcon, Trash2Icon, UploadIcon } from "lucide-react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { LessonStatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError, fetcher } from "@/lib/api";
import { fmt, t } from "@/lib/i18n";
import type { Lesson, VideoUpload } from "@/lib/types";
import { uploadDirect } from "@/lib/upload";

export function LessonsTab({ courseId }: { courseId: string }) {
  const key = `/teacher/courses/${courseId}/lessons`;
  const { data, isLoading, mutate } = useSWR<Lesson[]>(key, fetcher, {
    // While something is being processed, re-read the list so webhooks' results show up
    refreshInterval: (latest) => (latest?.some((l) => l.status === "processing") ? 10_000 : 0),
  });
  const [progress, setProgress] = useState<Record<string, number>>({});
  const [deleting, setDeleting] = useState<Lesson | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 150, tolerance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  async function onDragEnd({ active, over }: DragEndEvent) {
    if (!data || !over || active.id === over.id) return;
    const from = data.findIndex((l) => l.id === active.id);
    const to = data.findIndex((l) => l.id === over.id);
    const reordered = arrayMove(data, from, to).map((l, i) => ({ ...l, position: i + 1 }));
    mutate(reordered, { revalidate: false });
    try {
      const saved = await api<Lesson[]>(`/teacher/courses/${courseId}/lessons/order`, {
        method: "PUT",
        json: { lesson_ids: reordered.map((l) => l.id) },
      });
      mutate(saved, { revalidate: false });
      toast.success(t.lessons.reordered);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t.app.genericError);
      mutate();
    }
  }

  async function upload(lesson: Lesson, file: File) {
    setProgress((p) => ({ ...p, [lesson.id]: 0 }));
    try {
      const creds = await api<VideoUpload>(`/teacher/lessons/${lesson.id}/video-upload`, { method: "POST" });
      mutate();
      await uploadDirect(creds.upload_url, creds.fields, file, (percent) =>
        setProgress((p) => ({ ...p, [lesson.id]: percent })),
      ).promise;
      setProgress((p) => ({ ...p, [lesson.id]: 100 }));
      await api(`/teacher/lessons/${lesson.id}/sync-status`, { method: "POST" });
      toast.success(t.lessons.uploadDone);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t.lessons.uploadFailed);
    } finally {
      setProgress(({ [lesson.id]: _done, ...rest }) => rest);
      mutate();
    }
  }

  async function refresh(lesson: Lesson) {
    try {
      await api(`/teacher/lessons/${lesson.id}/sync-status`, { method: "POST" });
      mutate();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t.app.genericError);
    }
  }

  return (
    <div className="grid gap-4">
      <NewLessonForm courseId={courseId} onCreated={() => mutate()} />
      {isLoading && <Skeleton className="h-24 rounded-xl" />}
      {data?.length === 0 && <p className="py-8 text-center text-muted-foreground">{t.lessons.empty}</p>}
      {data && data.length > 1 && <p className="text-xs text-muted-foreground">{t.lessons.dragHint}</p>}

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={data?.map((l) => l.id) ?? []} strategy={verticalListSortingStrategy}>
          <div className="grid gap-2">
            {data?.map((lesson) => (
              <LessonRow
                key={lesson.id}
                lesson={lesson}
                progress={progress[lesson.id]}
                onUpload={(file) => upload(lesson, file)}
                onRefresh={() => refresh(lesson)}
                onDelete={() => setDeleting(lesson)}
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={t.app.delete}
        description={fmt(t.lessons.deleteConfirm, { title: deleting?.title ?? "" })}
        confirmLabel={t.app.delete}
        onConfirm={async () => {
          if (!deleting) return;
          try {
            await api(`/teacher/lessons/${deleting.id}`, { method: "DELETE" });
            toast.success(t.lessons.deleted);
            mutate();
          } catch (e) {
            toast.error(e instanceof ApiError ? e.message : t.app.genericError);
          }
        }}
      />
    </div>
  );
}

function LessonRow({
  lesson,
  progress,
  onUpload,
  onRefresh,
  onDelete,
}: {
  lesson: Lesson;
  progress: number | undefined;
  onUpload: (file: File) => void;
  onRefresh: () => void;
  onDelete: () => void;
}) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({
    id: lesson.id,
  });
  const fileInput = useRef<HTMLInputElement>(null);
  const uploading = progress !== undefined;

  return (
    <Card
      ref={setNodeRef}
      size="sm"
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={isDragging ? "relative z-10 shadow-lg" : undefined}
      data-testid="lesson-row"
    >
      <CardContent className="flex flex-wrap items-center gap-3">
        <button
          ref={setActivatorNodeRef}
          {...attributes}
          {...listeners}
          type="button"
          className="cursor-grab touch-none rounded p-1 text-muted-foreground hover:bg-muted active:cursor-grabbing"
          aria-label={t.lessons.dragHint}
          data-testid="lesson-drag"
        >
          <GripVerticalIcon className="size-4" />
        </button>
        <span className="w-6 text-sm text-muted-foreground tabular-nums">{lesson.position}.</span>
        <div className="min-w-0 flex-1">
          <p className="font-medium break-words" data-testid="lesson-title">
            {lesson.title}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            {lesson.provider_video_id && <LessonStatusBadge status={lesson.status} />}
            {lesson.duration_seconds && (
              <span className="text-xs text-muted-foreground">
                {fmt(t.lessons.duration, { minutes: Math.round(lesson.duration_seconds / 60) })}
              </span>
            )}
          </div>
          {uploading && (
            <div className="mt-2 grid gap-1" data-testid="upload-progress">
              <Progress value={progress} />
              <span className="text-xs text-muted-foreground">{fmt(t.lessons.uploading, { percent: progress })}</span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-1">
          <input
            ref={fileInput}
            type="file"
            accept="video/*"
            className="hidden"
            data-testid="lesson-file"
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file) onUpload(file);
            }}
          />
          {lesson.provider_video_id && lesson.status === "processing" && (
            <Button variant="ghost" size="icon-sm" onClick={onRefresh} aria-label={t.lessons.refresh}>
              <RefreshCwIcon />
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            disabled={uploading}
            onClick={() => fileInput.current?.click()}
            data-testid="lesson-upload"
          >
            <UploadIcon />
            <span className="hidden sm:inline">{lesson.provider_video_id ? t.lessons.reupload : t.lessons.upload}</span>
          </Button>
          <Button variant="ghost" size="icon-sm" onClick={onDelete} aria-label={t.app.delete} data-testid="lesson-delete">
            <Trash2Icon />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function NewLessonForm({ courseId, onCreated }: { courseId: string; onCreated: () => void }) {
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const formEl = e.currentTarget;
    const title = String(new FormData(formEl).get("title") ?? "").trim();
    if (!title) return;
    setBusy(true);
    try {
      await api(`/teacher/courses/${courseId}/lessons`, { method: "POST", json: { title } });
      toast.success(t.lessons.created);
      formEl.reset();
      onCreated();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t.app.genericError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex gap-2">
      <Input name="title" placeholder={t.lessons.title} aria-label={t.lessons.title} required maxLength={255} />
      <Button type="submit" disabled={busy} data-testid="new-lesson">
        <PlusIcon />
        <span className="hidden sm:inline">{t.lessons.new}</span>
      </Button>
    </form>
  );
}
