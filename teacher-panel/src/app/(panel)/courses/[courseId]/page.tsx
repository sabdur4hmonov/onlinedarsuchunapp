import { CourseView } from "./course-view";

export default async function CoursePage({ params, searchParams }: PageProps<"/courses/[courseId]">) {
  const { courseId } = await params;
  const { tab } = await searchParams;
  return <CourseView courseId={courseId} initialTab={typeof tab === "string" ? tab : "students"} />;
}
