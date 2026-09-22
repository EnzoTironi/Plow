---
name: kapso
description: WhatsApp message bodies Zoen sends through the relay. Reactions, quoted replies, typing, media, and contact cards use Kapso's Meta proxy shape. The agent never calls Kapso and never holds the API key.
---

# Kapso

Zoen is the talker. This skill is the message shape, not a second sender.
The relay at `auth.tryzoen.com` holds the Kapso key and posts to
`POST https://api.kapso.ai/meta/whatsapp/v24.0/{phone_number_id}/messages`
with `X-API-Key`. Do not call that URL. Do not look for `KAPSO_API_KEY`.

Source: [Send reaction](https://docs.kapso.ai/docs/whatsapp/send-messages/reaction)
and [Send a message](https://docs.kapso.ai/api/meta/whatsapp/messages/send-a-message).

## What you call

- Tapback: `python3 /opt/plow/zoen/react.py TYPE --message <wamid>`.
  TYPE is `like` `love` `laugh` `emphasize` `question` `dislike`.
- Text, photos, voice, and quotes: `zoen_imessage`.
  `reply_to` is the wamid being quoted.
- Progress at each step uses `purpose: "progress"`. The result uses `purpose: "answer"`.

## Reaction

The relay sends this. `emoji` is the glyph, not the word `like`.

```json
{
  "messaging_product": "whatsapp",
  "to": "15551234567",
  "type": "reaction",
  "reaction": { "message_id": "wamid......", "emoji": "👍" }
}
```

`react.py` names map to those glyphs: like 👍, love ❤️, laugh 😂, emphasize ‼️, question ❓, dislike 👎.
A raw `emoji` on the relay is passed through. Reactions only get a sent status, not delivered or read.

## Quoted reply

A reply quotes one bubble. The id sits in `context.message_id`, beside `type`, not inside `text`.

```json
{
  "messaging_product": "whatsapp",
  "to": "15551234567",
  "type": "text",
  "context": { "message_id": "wamid......" },
  "text": { "body": "Thanks for your message!", "preview_url": false }
}
```

Every WhatsApp bubble sets `reply_to` to the wamid in the turn note. If they quoted an older bubble, use that id. The relay places it in `context.message_id`. The same field quotes a photo or a voice note. A missing `reply_to` still quotes that bubble.

## Typing

Typing is a read receipt plus an indicator. It is not a message bubble. The relay sends it when a WhatsApp turn starts. It drops when the text goes out, or after about 25 seconds.

```json
{
  "messaging_product": "whatsapp",
  "status": "read",
  "message_id": "wamid......",
  "typing_indicator": { "type": "text" }
}
```

## Voice, media, contacts

A voice note is Opus in an `.ogg` file, with `voice: true`. Anything else is a plain audio file.

```json
{
  "messaging_product": "whatsapp",
  "to": "15551234567",
  "type": "audio",
  "audio": { "id": "<MEDIA_ID>", "voice": true }
}
```

Photos, video, and documents use `image`, `video`, or `document` with an uploaded `id`. A caption lives on that object. A quote adds the same `context.message_id`.

A contact card is `type: "contacts"`. `formatted_name` is the visible name. `phone` includes `+`. `wa_id` is digits only, and that is what shows the Message button.

```json
{
  "messaging_product": "whatsapp",
  "to": "15551234567",
  "type": "contacts",
  "contacts": [{
    "name": { "formatted_name": "Zoen", "first_name": "Zoen" },
    "phones": [{ "phone": "+553798136141", "type": "MOBILE", "wa_id": "553798136141" }]
  }]
}
```
