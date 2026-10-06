import { test } from "node:test";
import assert from "node:assert/strict";
import { page } from "../src/page.js";
import { setupMessage } from "../src/whatsapp.js";

// The connection pages and the WhatsApp setup text are fixed copy shown before Zoen knows the
// person's language, so they are English. The model still answers each person in their language.
const PORTUGUESE = /[ãõçâêô]|\b(você|não|conexões|autorização|conversa|seu|sua|pra|enviar)\b/i;

test("every connection page is English", async () => {
  for (const kind of ["welcome", "received", "denied", "expired", "used", "invalid", "confirm"]) {
    const html = await page(kind, {}).text();
    assert.match(html, /<html lang="en">/, kind);
    assert.doesNotMatch(html, PORTUGUESE, kind);
  }
});

test("the WhatsApp setup button is English", () => {
  const body = setupMessage({ to: "15550000000" }, "https://auth.example/whatsapp/start");
  const text = JSON.stringify(body);
  assert.doesNotMatch(text, PORTUGUESE);
  assert.equal(body.interactive.action.parameters.display_text, "Send the SMS");
});
