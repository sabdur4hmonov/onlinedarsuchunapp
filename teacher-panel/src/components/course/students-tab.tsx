"use client";

import { useState, type FormEvent } from "react";
import useSWR from "swr";
import { MonitorSmartphoneIcon, RotateCcwIcon, UserMinusIcon, UserPlusIcon } from "lucide-react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError, fetcher } from "@/lib/api";
import { fmt, formatDateTime, t } from "@/lib/i18n";
import type { CourseStudent, Device } from "@/lib/types";

export function StudentsTab({ courseId }: { courseId: string }) {
  const key = `/teacher/courses/${courseId}/students`;
  const { data, isLoading, mutate } = useSWR<CourseStudent[]>(key, fetcher);
  const [removing, setRemoving] = useState<CourseStudent | null>(null);
  const [devicesOf, setDevicesOf] = useState<CourseStudent | null>(null);

  return (
    <div className="grid gap-4">
      <AddStudentForm courseId={courseId} onAdded={() => mutate()} />

      {isLoading && <Skeleton className="h-24 rounded-xl" />}
      {data?.length === 0 && <p className="py-8 text-center text-muted-foreground">{t.students.empty}</p>}

      <div className="grid gap-2">
        {data?.map((s) => (
          <Card key={s.id} size="sm" data-testid="student-row">
            <CardContent className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="font-medium">{s.full_name}</p>
                <p className="text-sm text-muted-foreground tabular-nums">{s.phone}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => setDevicesOf(s)} data-testid="student-devices">
                  <MonitorSmartphoneIcon />
                  {t.students.showDevices}
                  <Badge variant="secondary">{s.active_devices}</Badge>
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setRemoving(s)} data-testid="student-remove">
                  <UserMinusIcon />
                  <span className="hidden sm:inline">{t.students.remove}</span>
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        title={t.students.remove}
        description={fmt(t.students.removeConfirm, { name: removing?.full_name ?? "" })}
        confirmLabel={t.students.remove}
        onConfirm={async () => {
          if (!removing) return;
          try {
            await api(`/teacher/courses/${courseId}/students/${removing.id}`, { method: "DELETE" });
            toast.success(t.students.removed);
            mutate();
          } catch (e) {
            toast.error(e instanceof ApiError ? e.message : t.app.genericError);
          }
        }}
      />

      <DevicesDialog student={devicesOf} onClose={() => setDevicesOf(null)} onChanged={() => mutate()} />
    </div>
  );
}

function AddStudentForm({ courseId, onAdded }: { courseId: string; onAdded: () => void }) {
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const formEl = e.currentTarget;
    const phone = String(new FormData(formEl).get("phone") ?? "").trim();
    if (!phone) return;
    setBusy(true);
    try {
      await api(`/teacher/courses/${courseId}/enrollments`, { method: "POST", json: { student_phone: phone } });
      toast.success(t.students.added);
      formEl.reset();
      onAdded();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t.app.genericError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card size="sm">
      <CardContent>
        <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <div className="grid flex-1 gap-1">
            <label htmlFor="add-student-phone" className="text-sm font-medium">
              {t.students.add}
            </label>
            <Input
              id="add-student-phone"
              name="phone"
              type="tel"
              inputMode="tel"
              placeholder={t.login.phonePlaceholder}
              required
            />
            <p className="text-xs text-muted-foreground">{t.students.addHint}</p>
          </div>
          <Button type="submit" disabled={busy} className="sm:mb-5" data-testid="add-student">
            <UserPlusIcon />
            {t.students.add}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function DevicesDialog({
  student,
  onClose,
  onChanged,
}: {
  student: CourseStudent | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const key = student ? `/teacher/students/${student.id}/devices` : null;
  const { data, mutate } = useSWR<Device[]>(key, fetcher);
  // undefined = nothing to confirm, null = all devices, string = one device (devices.id)
  const [resetTarget, setResetTarget] = useState<string | null | undefined>(undefined);
  const active = data?.filter((d) => d.is_active) ?? [];

  async function reset(deviceId: string | null) {
    try {
      await api(`/teacher/students/${student!.id}/devices/reset`, {
        method: "POST",
        json: deviceId ? { device_id: deviceId } : {},
      });
      toast.success(t.students.resetDone);
      mutate();
      onChanged();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t.app.genericError);
    }
  }

  return (
    <Dialog open={student !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{fmt(t.students.devicesTitle, { name: student?.full_name ?? "" })}</DialogTitle>
        </DialogHeader>
        {!data && <Skeleton className="h-16" />}
        {data?.length === 0 && <p className="text-muted-foreground">{t.students.noDevices}</p>}
        <div className="grid gap-2">
          {data?.map((d) => (
            <div key={d.id} className="flex items-center justify-between gap-2 rounded-lg border p-3" data-testid="device-row">
              <div className="min-w-0">
                <p className="font-medium">
                  {d.device_name} <span className="text-muted-foreground">· {d.platform}</span>
                </p>
                <p className="text-xs text-muted-foreground">
                  {fmt(t.students.boundAt, { date: formatDateTime(d.bound_at) })} ·{" "}
                  {d.is_active ? t.students.deviceActive : t.students.deviceInactive}
                </p>
              </div>
              {d.is_active && (
                <Button variant="destructive" size="sm" onClick={() => setResetTarget(d.id)} data-testid="device-reset">
                  <RotateCcwIcon />
                  {t.students.reset}
                </Button>
              )}
            </div>
          ))}
        </div>
        {active.length > 1 && (
          <Button variant="outline" onClick={() => setResetTarget(null)}>
            {t.students.resetAll}
          </Button>
        )}
        <ConfirmDialog
          open={resetTarget !== undefined}
          onOpenChange={(open) => !open && setResetTarget(undefined)}
          title={t.students.reset}
          description={t.students.resetConfirm}
          confirmLabel={t.students.reset}
          onConfirm={() => reset(resetTarget ?? null)}
        />
      </DialogContent>
    </Dialog>
  );
}
