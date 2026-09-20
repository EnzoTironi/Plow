export const HEADERS = {
  "Cache-Control": "no-store",
  "Referrer-Policy": "no-referrer",
  "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
  "X-Content-Type-Options": "nosniff",
};
export const capability = (value, min = 32) => typeof value === "string"
  && value.length >= min && value.length <= 256 && /^[A-Za-z0-9_-]+$/.test(value);
export const response = (data, status = 200) => Response.json(data, { status, headers: HEADERS });
export const digest = async (value) => Array.from(new Uint8Array(
  await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)),
), (byte) => byte.toString(16).padStart(2, "0")).join("");

export async function readBody(request) {
  if (!request.headers.get("Content-Type")?.startsWith("application/json")) throw new Error("json required");
  const reader = request.body?.getReader();
  if (!reader) throw new Error("body required");
  let text = "", size = 0;
  const decoder = new TextDecoder();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.length;
      if (size > 4096) throw new Error("body too large");
      text += decoder.decode(value, { stream: true });
    }
    return JSON.parse(text + decoder.decode());
  } finally {
    await reader.cancel();
  }
}
