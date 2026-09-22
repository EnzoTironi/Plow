import assert from "node:assert/strict";
import test from "node:test";
import { inboundMessages, outboundEcho, rememberOutbound } from "../src/whatsapp.js";

test("a voice transcript object is the spoken text", () => {
  const messages = inboundMessages("whatsapp.message.received", {
    message: {
      id: "wamid.voice",
      type: "audio",
      from: "5511999999999",
      audio: { id: "media-voice", mime_type: "audio/ogg", voice: true },
      kapso: { direction: "inbound", transcript: { text: "manda o desenho da pirâmide" } },
    },
    conversation: { phone_number: "5511999999999", contact_name: "Enzo" },
  });
  assert.equal(messages.length, 1);
  assert.equal(messages[0].text, "manda o desenho da pirâmide");
  assert.equal(messages[0].kind, "audio");
  assert.equal(messages[0].voice, true);
  assert.equal(messages[0].text.includes("[object Object]"), false);
});

test("an empty transcript object does not become object Object", () => {
  const messages = inboundMessages("whatsapp.message.received", {
    message: {
      id: "wamid.voice2",
      type: "audio",
      from: "5511999999999",
      audio: { id: "media-voice", mime_type: "audio/ogg", voice: true },
      kapso: { direction: "inbound", transcript: { text: "" } },
    },
    conversation: { phone_number: "5511999999999" },
  });
  assert.equal(messages[0].text, "");
  assert.equal(messages[0].media_id, "media-voice");
});

test("a bubble we just sent is not a new inbound", () => {
  const box = { sent: [] };
  const now = 1_000_000;
  rememberOutbound(box, "5537999827561", "oi, sou o zoen", now);
  assert.equal(outboundEcho(box, "5537999827561", "oi, sou o zoen", now + 1000), true);
  assert.equal(outboundEcho(box, "5537999827561", "o que vc consegue fazer por mim?", now + 1000), false);
  assert.equal(outboundEcho(box, "5511999999999", "oi, sou o zoen", now + 1000), false);
});
