"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { ChevronLeftIcon, PencilIcon } from "lucide-react";
import { toast } from "sonner";

import { CourseFormDialog } from "@/components/course-form-dialog";
import { EventsTab } from "@/components/course/events-tab";
import { LessonsTab } from "@/components/course/lessons-tab";
import { LiveTab } from "@/components/course/live-tab";
import { StudentsTab } from "@/components/course/students-tab";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { fetcher } from "@/lib/api";
import { t } from "@/lib/i18n";
import type { Course } from "@/lib/types";

const TABS = ["students", "lessons", "live", "events"] as const;

export function CourseView({ courseId, initialTab }: { courseId: string; initialTab: string }) {
  const { data: course, error, mutate } = useSWR<Course>(`/teacher/courses/${courseId}`, fetcher);
  const [tab, setTab] = useState<string>(TABS.includes(initialTab as (typeof TABS)[number]) ? initialTab : "students");
  const [editing, setEditing] = useState(false);

  function changeTab(value: string) {
    setTab(value);
    // Keep the tab in the URL so reload / back button land on the same tab
    window.history.replaceState(null, "", `?tab=${value}`);
  }

  if (error) return <p className="text-destructive">{error.message}</p>;

  return (
    <div className="grid gap-6">
      <div className="grid gap-2">
        <Link href="/courses" className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ChevronLeftIcon className="size-4" />
          {t.courses.title}
        </Link>
        <div className="flex items-start justify-between gap-3">
          {course ? (
            <div className="min-w-0">
              <h1 className="text-2xl font-semibold tracking-tight break-words" data-testid="course-title">
                {course.title}
              </h1>
              {course.description && <p className="mt-1 text-muted-foreground">{course.description}</p>}
            </div>
          ) : (
            <Skeleton className="h-8 w-64" />
          )}
          {course && (
            <Button variant="outline" size="sm" onClick={() => setEditing(true)} data-testid="edit-course">
              <PencilIcon />
              <span className="hidden sm:inline">{t.app.edit}</span>
            </Button>
          )}
        </div>
      </div>

      <Tabs value={tab} onValueChange={(v) => changeTab(String(v))}>
        <div className="-mx-4 overflow-x-auto px-4">
          <TabsList>
            {TABS.map((key) => (
              <TabsTrigger key={key} value={key} data-testid={`tab-${key}`}>
                {t.tabs[key]}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        <TabsContent value="students" className="pt-4">
          <StudentsTab courseId={courseId} />
        </TabsContent>
        <TabsContent value="lessons" className="pt-4">
          <LessonsTab courseId={courseId} />
        </TabsContent>
        <TabsContent value="live" className="pt-4">
          <LiveTab courseId={courseId} />
        </TabsContent>
        <TabsContent value="events" className="pt-4">
          <EventsTab courseId={courseId} />
        </TabsContent>
      </Tabs>

      {course && (
        <CourseFormDialog
          open={editing}
          onOpenChange={setEditing}
          course={course}
          onSaved={(saved) => {
            toast.success(t.courses.updated);
            mutate(saved, { revalidate: false });
          }}
        />
      )}
    </div>
  );
}
