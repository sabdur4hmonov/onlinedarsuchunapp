import { LoginForm } from "./login-form";

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const { next } = await searchParams;
  // Only same-site relative paths, never "//evil.example" or absolute URLs
  const safeNext = typeof next === "string" && next.startsWith("/") && !next.startsWith("//") ? next : "/courses";
  return (
    <main className="flex flex-1 items-center justify-center p-4">
      <LoginForm next={safeNext} />
    </main>
  );
}
