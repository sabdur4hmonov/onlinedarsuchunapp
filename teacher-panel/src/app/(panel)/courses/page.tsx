"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { BookOpenIcon, PlusIcon } from "lucide-react";
import { toast } from "sonner";

import { CourseFormDialog } from "@/components/course-form-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { fetcher } from "@/lib/api";
import { t } from "@/lib/i18n";
import type { Course } from "@/lib/types";

export default function CoursesPage() {
  const { data, error, isLoading, mutate } = useSWR<Course[]>("/teacher/courses", fetcher);
  const [creating, setCreating] = useState(false);

  return (
    <div className="grid gap-6">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">{t.courses.title}</h1>
        <Button onClick={() => setCreating(true)} data-testid="new-course">
          <PlusIcon />
          {t.courses.new}
        </Button>
      </div>

      {isLoading && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-28 rounded-xl" />
          ))}
        </div>
      )}
      {error && <p className="text-destructive">{t.app.genericError}</p>}
      {data?.length === 0 && (
        <Card className="items-center py-12 text-center text-muted-foreground">
          <BookOpenIcon className="mx-auto size-10 opacity-40" />
          <p>{t.courses.empty}</p>
        </Card>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {data?.map((course) => (
          <Link key={course.id} href={`/courses/${course.id}`} className="group" data-testid="course-card">
            <Card className="h-full transition-colors group-hover:border-primary/40 group-hover:bg-accent/40">
              <CardHeader>
                <CardTitle className="line-clamp-2">{course.title}</CardTitle>
                {course.description && <CardDescription className="line-clamp-3">{course.description}</CardDescription>}
              </CardHeader>
            </Card>
          </Link>
        ))}
      </div>

      <CourseFormDialog
        open={creating}
        onOpenChange={setCreating}
        onSaved={() => {
          toast.success(t.courses.created);
          mutate();
        }}
      />
    </div>
  );
}
