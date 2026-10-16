"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import { t } from "@/lib/i18n";
import type { Course } from "@/lib/types";

/** Create (no `course`) or edit (with `course`) a course. */
export function CourseFormDialog({
  open,
  onOpenChange,
  course,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  course?: Course;
  onSaved: (course: Course) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const json = { title: String(form.get("title")).trim(), description: String(form.get("description") || "") || null };
    setBusy(true);
    setError(null);
    try {
      const saved = course
        ? await api<Course>(`/teacher/courses/${course.id}`, { method: "PATCH", json })
        : await api<Course>("/teacher/courses", { method: "POST", json });
      onSaved(saved);
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t.app.genericError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{course ? t.courses.editTitle : t.courses.new}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="course-title">{t.courses.name}</Label>
            <Input id="course-title" name="title" defaultValue={course?.title} required maxLength={255} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="course-description">{t.courses.description}</Label>
            <Textarea id="course-description" name="description" defaultValue={course?.description ?? ""} rows={3} />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t.app.cancel}
            </Button>
            <Button type="submit" disabled={busy}>
              {course ? t.app.save : t.app.create}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
