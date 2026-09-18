import { defineSchedule } from "eve/schedules";

export default defineSchedule({
  cron: "0 9 * * 1-5",
  markdown: "Scan tenant-scoped invoices approaching or past due. Produce proposals only. Stop on ambiguity and never send external communication without an approved, idempotent tool call.",
});
