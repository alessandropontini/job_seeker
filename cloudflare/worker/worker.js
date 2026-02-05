export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;
    if (path === "/telegram/feedback" || path === "/telegram/webhook") {
      return handleTelegramWebhook(request, env, ctx);
    }
    if (path === "/feedback") {
      return handleFeedback(request, env);
    }
    if (path === "/window/open") {
      return handleWindowOpen(request, env);
    }
    return new Response("Not found", { status: 404 });
  },
};

async function handleTelegramWebhook(request, env, ctx) {
  if (request.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }
  const authError = ensureTelegramWebhookAuthorized(request, env);
  if (authError) {
    return authError;
  }
  let payload;
  try {
    payload = await request.json();
  } catch {
    return new Response("Invalid JSON", { status: 400 });
  }
  const callback = payload?.callback_query;
  if (!callback) {
    return new Response("No callback", { status: 200 });
  }
  const allowedUserId = env.ALLOWED_TELEGRAM_USER_ID;
  const callbackUserId = callback.from?.id;
  if (
    allowedUserId &&
    String(callbackUserId ?? "") !== String(allowedUserId)
  ) {
    await answerCallback(env, callback.id, "🚫 Not authorized");
    return new Response("OK", { status: 200 });
  }
  const data = callback.data;
  if (typeof data !== "string") {
    scheduleAnswer(env, ctx, callback.id, "Feedback non valido");
    return new Response("Invalid data", { status: 200 });
  }
  const parsed = parseCallbackData(data);
  if (!parsed) {
    scheduleAnswer(env, ctx, callback.id, "Feedback non valido");
    return new Response("Invalid callback data", { status: 200 });
  }
  const { runId, jobShortId, action, jobHash } = parsed;
  const sessionKey = `session:${runId}`;
  const windowRaw = await env.JOB_SCOUT_KV.get(sessionKey, "json");
  if (!windowRaw) {
    scheduleAnswer(env, ctx, callback.id, "⏱ Session scaduta");
    return new Response("Session missing", { status: 200 });
  }
  const now = Date.now();
  const openAt = Date.parse(windowRaw.open_at);
  const closeAt = Date.parse(windowRaw.close_at);
  const maxWindowMs = feedbackWindowMs(env);
  const maxCloseAt = openAt + maxWindowMs;
  const effectiveCloseAt = Math.min(closeAt, maxCloseAt);
  if (!Number.isFinite(openAt) || !Number.isFinite(closeAt)) {
    scheduleAnswer(env, ctx, callback.id, "Feedback non valido");
    return new Response("Window invalid", { status: 200 });
  }
  if (now < openAt || now > effectiveCloseAt) {
    scheduleAnswer(env, ctx, callback.id, "⏱ Session scaduta");
    return new Response("Window closed", { status: 200 });
  }
  const jobs = Array.isArray(windowRaw.jobs) ? windowRaw.jobs : [];
  const jobEntry = jobs.find((job) => job?.short_id === jobShortId);
  if (!jobEntry || jobEntry?.job_hash !== jobHash) {
    scheduleAnswer(env, ctx, callback.id, "Job non riconosciuto");
    return new Response("Job not found", { status: 200 });
  }
  const userId = callback.from?.id ?? "unknown";
  const messageId = callback.message?.message_id ?? null;
  const key = `feedback:${runId}:${jobShortId}:${userId}`;
  const value = {
    action,
    job_short_id: jobShortId,
    job_hash: jobHash,
    ts: new Date().toISOString(),
    message_id: messageId,
    user_id: userId,
    source: jobEntry?.source ?? "unknown",
  };
  const writePromise = env.JOB_SCOUT_KV.put(key, JSON.stringify(value), {
    expirationTtl: 60 * 60 * 24 * 7,
  }).catch(() => {});
  const ackPromise = answerCallback(env, callback.id, "✅ Feedback salvato").catch(
    () => {}
  );
  if (ctx) {
    ctx.waitUntil(writePromise);
    ctx.waitUntil(ackPromise);
  } else {
    await writePromise;
    await ackPromise;
  }
  return new Response("OK", { status: 200 });
}

function ensureTelegramWebhookAuthorized(request, env) {
  const secret =
    env.TELEGRAM_WEBHOOK_SECRET || env.JOB_SCOUT_WEBHOOK_SECRET;
  if (!secret) {
    return new Response("Missing webhook secret", { status: 500 });
  }
  const provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token");
  if (!provided || provided !== secret) {
    return new Response("Unauthorized", { status: 401 });
  }
  return null;
}

async function handleFeedback(request, env) {
  if (request.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }
  const payload = await readSignedJson(request, env);
  if (!payload.ok) {
    return payload.response;
  }
  const runId = payload.body?.run_id;
  if (!runId) {
    return new Response("Missing run_id", { status: 400 });
  }
  const prefix = `feedback:${runId}:`;
  const list = await env.JOB_SCOUT_KV.list({ prefix });
  const items = [];
  for (const key of list.keys) {
    const value = await env.JOB_SCOUT_KV.get(key.name, "json");
    if (value) {
      items.push(value);
    }
  }
  return new Response(JSON.stringify(items), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

async function handleWindowOpen(request, env) {
  if (request.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }
  const payload = await readSignedJson(request, env);
  if (!payload.ok) {
    return payload.response;
  }
  const runId = payload.body?.run_id;
  if (!runId) {
    return new Response("Missing run_id", { status: 400 });
  }
  const openAt = payload.body?.open_at;
  const closeAt = payload.body?.close_at;
  if (!openAt || !closeAt) {
    return new Response("Missing window", { status: 400 });
  }
  const openAtMs = Date.parse(openAt);
  const closeAtMs = Date.parse(closeAt);
  if (!Number.isFinite(openAtMs) || !Number.isFinite(closeAtMs)) {
    return new Response("Invalid window timestamps", { status: 400 });
  }
  const maxWindowMs = feedbackWindowMs(env);
  if (closeAtMs - openAtMs > maxWindowMs) {
    return new Response("Window exceeds max duration", { status: 400 });
  }
  const windowPayload = {
    run_id: runId,
    open_at: openAt,
    close_at: closeAt,
    jobs: Array.isArray(payload.body.jobs) ? payload.body.jobs : [],
  };
  await env.JOB_SCOUT_KV.put(
    `session:${runId}`,
    JSON.stringify(windowPayload),
    { expirationTtl: 60 * 60 * 2 }
  );
  return new Response("OK", { status: 200 });
}

export function parseCallbackData(data) {
  if (!data.startsWith("fb|")) {
    return null;
  }
  const parts = data.split("|");
  if (parts.length !== 5) {
    return null;
  }
  const [_, runId, jobShortId, action, jobHash] = parts;
  if (!runId || !jobShortId || !action || !jobHash) {
    return null;
  }
  if (!isValidAction(action)) {
    return null;
  }
  return { runId, jobShortId, action, jobHash };
}

async function readSignedJson(request, env) {
  const secret = env.JOB_SCOUT_WEBHOOK_SECRET;
  if (!secret) {
    return {
      ok: false,
      response: new Response("Missing secret", { status: 500 }),
    };
  }
  const signature = request.headers.get("X-Webhook-Signature");
  const timestamp = request.headers.get("X-Webhook-Timestamp");
  const requestId = request.headers.get("X-Webhook-Id");
  if (!signature || !timestamp || !requestId) {
    return {
      ok: false,
      response: new Response("Missing signature", { status: 403 }),
    };
  }
  const requestKey = `req:${requestId}`;
  const existing = await env.JOB_SCOUT_KV.get(requestKey);
  if (existing) {
    return {
      ok: false,
      response: new Response("Duplicate request", { status: 409 }),
    };
  }
  const now = Math.floor(Date.now() / 1000);
  const ts = Number(timestamp);
  if (!Number.isFinite(ts) || Math.abs(now - ts) > 300) {
    return {
      ok: false,
      response: new Response("Stale signature", { status: 403 }),
    };
  }
  const bodyBuffer = await request.clone().arrayBuffer();
  const expected = await signPayload(secret, timestamp, bodyBuffer);
  if (expected !== signature) {
    return {
      ok: false,
      response: new Response("Invalid signature", { status: 403 }),
    };
  }
  await env.JOB_SCOUT_KV.put(requestKey, "1", {
    expirationTtl: 60 * 60 * 2,
  });
  let payload;
  try {
    payload = JSON.parse(new TextDecoder().decode(bodyBuffer));
  } catch {
    return {
      ok: false,
      response: new Response("Invalid JSON", { status: 400 }),
    };
  }
  return { ok: true, body: payload };
}

async function signPayload(secret, timestamp, bodyBuffer) {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const payload = new Uint8Array(
    encoder.encode(timestamp).length + 1 + bodyBuffer.byteLength
  );
  payload.set(encoder.encode(timestamp), 0);
  payload.set([46], encoder.encode(timestamp).length);
  payload.set(new Uint8Array(bodyBuffer), encoder.encode(timestamp).length + 1);
  const signature = await crypto.subtle.sign("HMAC", key, payload);
  return [...new Uint8Array(signature)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function feedbackWindowMs(env) {
  const minutes = Number(env.FEEDBACK_WINDOW_MINUTES || 60);
  if (!Number.isFinite(minutes) || minutes <= 0) {
    return 60 * 60 * 1000;
  }
  return minutes * 60 * 1000;
}

function isValidAction(action) {
  return [
    "L",
    "M",
    "D",
    "S",
    "X",
    "like",
    "maybe",
    "dislike",
    "love",
    "duplicate",
  ].includes(action);
}

function scheduleAnswer(env, ctx, callbackId, text) {
  const promise = answerCallback(env, callbackId, text).catch(() => {});
  if (ctx) {
    ctx.waitUntil(promise);
  }
  return promise;
}

async function answerCallback(env, callbackId, text) {
  const token = env.TELEGRAM_BOT_TOKEN;
  if (!token) {
    return;
  }
  const url = `https://api.telegram.org/bot${token}/answerCallbackQuery`;
  const payload = {
    callback_query_id: callbackId,
    text,
    show_alert: false,
  };
  await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
