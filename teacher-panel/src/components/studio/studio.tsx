"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import useSWR from "swr";
import {
  ConnectionQuality,
  createLocalTracks,
  DisconnectReason,
  LocalVideoTrack,
  Room,
  RoomEvent,
  Track,
  VideoPresets,
  type LocalTrack,
} from "livekit-client";
import {
  ChevronLeftIcon,
  LoaderIcon,
  MicIcon,
  MicOffIcon,
  MonitorUpIcon,
  PhoneOffIcon,
  RadioIcon,
  UsersIcon,
  VideoIcon,
  VideoOffIcon,
  WifiIcon,
  WifiOffIcon,
} from "lucide-react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { LiveStatusBadge, RecordingStatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { api, ApiError, fetcher } from "@/lib/api";
import { fmt, formatDateTime, t } from "@/lib/i18n";
import type { LiveSession, TeacherLiveToken } from "@/lib/types";
import { cn } from "@/lib/utils";

type Phase = "idle" | "starting" | "connected" | "reconnecting" | "rejoining" | "ended" | "error";

// After a full disconnect (not the short network blips LiveKit handles itself) we fetch a fresh
// token and connect again: 2 s, 4 s, 8 s ... up to ~1 minute in total.
const REJOIN_DELAYS_MS = [2000, 4000, 8000, 15000, 30000];
// These disconnect reasons are final: retrying would fight the server or another tab
const FINAL_REASONS = new Set([
  DisconnectReason.CLIENT_INITIATED,
  DisconnectReason.DUPLICATE_IDENTITY,
  DisconnectReason.ROOM_DELETED,
  DisconnectReason.PARTICIPANT_REMOVED,
]);

export function Studio({ courseId, sessionId }: { courseId: string; sessionId: string }) {
  const key = `/teacher/live-sessions/${sessionId}`;
  const [phase, setPhase] = useState<Phase>("idle");
  const { data: session, mutate } = useSWR<LiveSession>(key, fetcher, {
    // While live or while the recording is being processed, keep the statuses fresh
    refreshInterval: (s) =>
      s && (s.status === "live" || ["recording", "uploading", "processing"].includes(s.recording_status)) ? 5000 : 0,
  });

  const roomRef = useRef<Room | null>(null);
  const tracksRef = useRef<LocalTrack[]>([]);
  const endingRef = useRef(false);
  const previewRef = useRef<HTMLVideoElement>(null);
  const screenRef = useRef<HTMLVideoElement>(null);

  const [micOn, setMicOn] = useState(true);
  const [camOn, setCamOn] = useState(true);
  const [screenOn, setScreenOn] = useState(false);
  const [viewers, setViewers] = useState(0);
  const [quality, setQuality] = useState<ConnectionQuality>(ConnectionQuality.Unknown);
  const [confirmEnd, setConfirmEnd] = useState(false);

  const stopLocalTracks = useCallback(() => {
    tracksRef.current.forEach((track) => track.stop());
    tracksRef.current = [];
  }, []);

  // Leave the room when the page is closed or the teacher navigates away
  useEffect(() => {
    return () => {
      endingRef.current = true;
      roomRef.current?.disconnect();
      stopLocalTracks();
    };
  }, [stopLocalTracks]);

  const countViewers = (room: Room) => setViewers(room.remoteParticipants.size);

  // Latest mic/camera choice, read when (re)publishing after a reconnect
  const micOnRef = useRef(true);
  const camOnRef = useRef(true);

  async function connect(): Promise<void> {
    // start is idempotent while the lesson is live: it only returns a fresh token
    const live = await api<TeacherLiveToken>(`/teacher/live-sessions/${sessionId}/start`, { method: "POST" });
    mutate(live.live_session, { revalidate: false });
    const opts = live.client_options;
    const room = new Room({
      adaptiveStream: opts.adaptive_stream,
      dynacast: opts.dynacast,
      videoCaptureDefaults: { resolution: VideoPresets.h720.resolution },
      publishDefaults: {
        simulcast: opts.simulcast,
        // Weak connections get 180p/360p, good ones the full 720p
        videoSimulcastLayers: [VideoPresets.h180, VideoPresets.h360],
      },
    });
    roomRef.current = room;

    room
      .on(RoomEvent.ParticipantConnected, () => countViewers(room))
      .on(RoomEvent.ParticipantDisconnected, () => countViewers(room))
      .on(RoomEvent.ConnectionQualityChanged, (q, participant) => {
        if (participant.isLocal) setQuality(q);
      })
      .on(RoomEvent.Reconnecting, () => setPhase("reconnecting"))
      .on(RoomEvent.Reconnected, () => {
        setPhase("connected");
        toast.success(t.studio.reconnected);
      })
      .on(RoomEvent.LocalTrackUnpublished, (pub) => {
        // Screen share ended from the browser's own "Stop sharing" bar
        if (pub.source === Track.Source.ScreenShare) setScreenOn(false);
      })
      .on(RoomEvent.Disconnected, (reason) => {
        if (endingRef.current || roomRef.current !== room) return;
        if (reason !== undefined && FINAL_REASONS.has(reason)) {
          setPhase("ended");
          mutate();
          return;
        }
        // Network gone for longer than LiveKit's own retries: rejoin with a fresh token
        void rejoin();
      });

    await room.connect(live.url, live.token);
    for (const track of tracksRef.current) {
      await room.localParticipant.publishTrack(track, {
        simulcast: opts.simulcast,
        source: track.kind === Track.Kind.Video ? Track.Source.Camera : Track.Source.Microphone,
      });
    }
    if (!micOnRef.current) await room.localParticipant.setMicrophoneEnabled(false);
    if (!camOnRef.current) await room.localParticipant.setCameraEnabled(false);
    countViewers(room);
    setPhase("connected");
  }

  async function rejoin(): Promise<void> {
    setPhase("rejoining");
    // The old room is already disconnected; forget it so its late events are ignored
    roomRef.current = null;
    for (const delay of REJOIN_DELAYS_MS) {
      await new Promise((resolve) => setTimeout(resolve, delay));
      if (endingRef.current) return;
      try {
        await connect();
        return;
      } catch {
        // backend or LiveKit still unreachable: wait longer and try again
      }
    }
    setPhase("error");
  }

  async function start() {
    setPhase("starting");
    endingRef.current = false;
    try {
      // 1) Camera + microphone first, so a lesson never starts without them
      tracksRef.current = await createLocalTracks({
        audio: { echoCancellation: true, noiseSuppression: true },
        video: { resolution: VideoPresets.h720.resolution },
      });
    } catch {
      setPhase("idle");
      toast.error(t.studio.devicesError);
      return;
    }
    const video = tracksRef.current.find((tr) => tr instanceof LocalVideoTrack);
    if (video && previewRef.current) video.attach(previewRef.current);
    try {
      // 2) Room + automatic recording on the backend, then publish
      await connect();
    } catch (e) {
      setPhase("error");
      toast.error(e instanceof ApiError ? e.message : t.app.genericError);
    }
  }

  async function toggleMic() {
    const next = !micOn;
    await roomRef.current?.localParticipant.setMicrophoneEnabled(next);
    micOnRef.current = next;
    setMicOn(next);
  }

  async function toggleCam() {
    const next = !camOn;
    await roomRef.current?.localParticipant.setCameraEnabled(next);
    camOnRef.current = next;
    setCamOn(next);
  }

  async function toggleScreen() {
    const room = roomRef.current;
    if (!room) return;
    try {
      const pub = await room.localParticipant.setScreenShareEnabled(!screenOn, { audio: false, resolution: VideoPresets.h1080.resolution });
      const on = !screenOn;
      setScreenOn(on);
      if (on && pub?.track && screenRef.current) pub.track.attach(screenRef.current);
    } catch {
      // The teacher closed the browser's "choose a screen" dialog
    }
  }

  async function endLesson() {
    endingRef.current = true;
    try {
      const ended = await api<LiveSession>(`/teacher/live-sessions/${sessionId}/end`, { method: "POST" });
      mutate(ended, { revalidate: false });
      toast.success(t.studio.ended);
    } catch (e) {
      endingRef.current = false;
      toast.error(e instanceof ApiError ? e.message : t.app.genericError);
      throw e;
    }
    await roomRef.current?.disconnect();
    roomRef.current = null;
    stopLocalTracks();
    setPhase("ended");
  }

  const inRoom = phase === "connected" || phase === "reconnecting" || phase === "rejoining";
  const canStart = session && (session.status === "scheduled" || session.status === "live") && !inRoom;

  return (
    <div className="grid gap-4">
      <Link
        href={`/courses/${courseId}?tab=live`}
        className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ChevronLeftIcon className="size-4" />
        {t.studio.backToCourse}
      </Link>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight break-words">{session?.title ?? t.studio.title}</h1>
          {session && (
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <LiveStatusBadge status={session.status} />
              <span>{formatDateTime(session.started_at ?? session.scheduled_at)}</span>
              {session.recording_status !== "none" && (
                <span className="flex items-center gap-1">
                  {t.live.recording}: <RecordingStatusBadge status={session.recording_status} />
                </span>
              )}
            </div>
          )}
        </div>
        {inRoom && (
          <div className="flex items-center gap-3 text-sm">
            <span className="flex items-center gap-1" data-testid="viewer-count">
              <UsersIcon className="size-4" />
              {fmt(t.studio.viewers, { count: viewers })}
            </span>
            <QualityIndicator quality={quality} />
          </div>
        )}
      </div>

      {(phase === "reconnecting" || phase === "rejoining") && (
        <div role="status" className="flex items-center gap-2 rounded-lg bg-amber-100 px-3 py-2 text-sm text-amber-900">
          <LoaderIcon className="size-4 animate-spin" />
          {phase === "reconnecting" ? t.studio.reconnecting : t.studio.rejoining}
        </div>
      )}

      <Card className="overflow-hidden p-0">
        <div className="relative aspect-video w-full bg-neutral-950">
          <video
            ref={previewRef}
            muted
            playsInline
            autoPlay
            className={cn("size-full object-contain", (!camOn || screenOn) && "hidden", "-scale-x-100")}
            aria-label={t.studio.preview}
            data-testid="camera-preview"
          />
          <video
            ref={screenRef}
            muted
            playsInline
            autoPlay
            className={cn("size-full object-contain", !screenOn && "hidden")}
          />
          {phase === "idle" && (
            <div className="absolute inset-0 flex items-center justify-center text-neutral-400">
              <VideoIcon className="size-12 opacity-40" />
            </div>
          )}
          {inRoom && (
            <span className="absolute top-3 left-3 flex items-center gap-1 rounded-full bg-red-600 px-2 py-0.5 text-xs font-semibold text-white">
              <RadioIcon className="size-3" /> LIVE
            </span>
          )}
        </div>
      </Card>

      <CardContent className="flex flex-wrap items-center justify-center gap-2 px-0">
        {canStart && (
          <Button size="lg" onClick={start} disabled={phase === "starting"} data-testid="studio-start">
            <RadioIcon />
            {phase === "starting" ? t.studio.starting : t.studio.start}
          </Button>
        )}
        {inRoom && (
          <>
            <Button variant={micOn ? "outline" : "destructive"} size="lg" onClick={toggleMic} data-testid="toggle-mic">
              {micOn ? <MicIcon /> : <MicOffIcon />}
              {t.studio.mic}
            </Button>
            <Button variant={camOn ? "outline" : "destructive"} size="lg" onClick={toggleCam} data-testid="toggle-cam">
              {camOn ? <VideoIcon /> : <VideoOffIcon />}
              {t.studio.camera}
            </Button>
            <Button variant={screenOn ? "secondary" : "outline"} size="lg" onClick={toggleScreen} data-testid="toggle-screen">
              <MonitorUpIcon />
              {screenOn ? t.studio.stopScreen : t.studio.screen}
            </Button>
            <Button variant="destructive" size="lg" onClick={() => setConfirmEnd(true)} data-testid="studio-end">
              <PhoneOffIcon />
              {t.studio.end}
            </Button>
          </>
        )}
      </CardContent>

      {session && !canStart && !inRoom && (session.status === "ended" || session.status === "cancelled") && (
        <p className="text-center text-muted-foreground" data-testid="studio-finished">
          {fmt(t.studio.recordingStatus, { status: t.live.recordingStatus[session.recording_status] })}
        </p>
      )}

      <ConfirmDialog
        open={confirmEnd}
        onOpenChange={setConfirmEnd}
        title={t.studio.end}
        description={t.studio.endConfirm}
        confirmLabel={t.studio.end}
        onConfirm={endLesson}
      />
    </div>
  );
}

function QualityIndicator({ quality }: { quality: ConnectionQuality }) {
  const level: Record<ConnectionQuality, { label: string; className: string }> = {
    [ConnectionQuality.Excellent]: { label: t.studio.qualityLevels.excellent, className: "text-emerald-600" },
    [ConnectionQuality.Good]: { label: t.studio.qualityLevels.good, className: "text-emerald-600" },
    [ConnectionQuality.Poor]: { label: t.studio.qualityLevels.poor, className: "text-amber-600" },
    [ConnectionQuality.Lost]: { label: t.studio.qualityLevels.lost, className: "text-destructive" },
    [ConnectionQuality.Unknown]: { label: t.studio.qualityLevels.unknown, className: "text-muted-foreground" },
  };
  const { label, className } = level[quality];
  return (
    <span className={cn("flex items-center gap-1", className)} title={t.studio.quality} data-testid="connection-quality">
      {quality === ConnectionQuality.Lost ? <WifiOffIcon className="size-4" /> : <WifiIcon className="size-4" />}
      {label}
    </span>
  );
}
