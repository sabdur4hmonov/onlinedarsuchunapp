// Mirrors of the backend response schemas (backend/app/schemas/*.py)

export type Course = {
  id: string;
  teacher_id: string;
  title: string;
  description: string | null;
  created_at: string;
};

export type CourseStudent = {
  id: string;
  full_name: string;
  phone: string;
  enrollment_status: "active" | "suspended";
  active_devices: number;
};

export type Device = {
  id: string;
  device_id: string;
  device_name: string;
  platform: string;
  bound_at: string;
  is_active: boolean;
};

export type LessonStatus = "uploading" | "processing" | "ready" | "failed";

export type Lesson = {
  id: string;
  course_id: string;
  title: string;
  description: string | null;
  position: number;
  provider: string | null;
  provider_video_id: string | null;
  status: LessonStatus;
  duration_seconds: number | null;
  created_at: string;
};

export type VideoUpload = { lesson: Lesson; upload_url: string; fields: Record<string, string> };

export type LiveStatus = "scheduled" | "live" | "ended" | "cancelled";
export type RecordingStatus = "none" | "recording" | "uploading" | "processing" | "ready" | "failed";

export type LiveSession = {
  id: string;
  course_id: string;
  title: string;
  scheduled_at: string;
  started_at: string | null;
  ended_at: string | null;
  status: LiveStatus;
  recording_status: RecordingStatus;
  recording_error: string | null;
  resulting_lesson_id: string | null;
  created_at: string;
};

export type ClientOptions = { adaptive_stream: boolean; dynacast: boolean; simulcast: boolean; auto_subscribe: boolean };

export type TeacherLiveToken = {
  live_session: LiveSession;
  url: string;
  token: string;
  expires_in: number;
  client_options: ClientOptions;
};

export type AuditEvent = {
  id: number;
  event_type: string;
  created_at: string;
  ip: string | null;
  actor: { id: string; full_name: string; phone: string; role: string } | null;
  details: Record<string, unknown>;
};
