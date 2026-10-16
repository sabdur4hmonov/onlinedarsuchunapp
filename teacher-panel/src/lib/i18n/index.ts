import { uz, type Messages } from "./uz";

// One language for now. Later: add ru.ts (`export const ru: Messages = {...}`) and pick by user setting.
const messages: Record<string, Messages> = { uz };

export const locale = "uz";
export const t: Messages = messages[locale];

/** fmt("Salom, {name}", { name: "Ali" }) -> "Salom, Ali" */
export function fmt(text: string, vars: Record<string, string | number>): string {
  return text.replace(/\{(\w+)\}/g, (_, key: string) => String(vars[key] ?? `{${key}}`));
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("uz-UZ", {
    timeZone: "Asia/Tashkent",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
