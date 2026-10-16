import { Studio } from "@/components/studio/studio";

export default async function LiveStudioPage({ params }: PageProps<"/courses/[courseId]/live/[sessionId]">) {
  const { courseId, sessionId } = await params;
  return <Studio courseId={courseId} sessionId={sessionId} />;
}
