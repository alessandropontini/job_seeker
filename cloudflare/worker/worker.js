export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    if (path === "/telegram/feedback" || path === "/telegram/webhook") {
      return handleTelegramWebhook(request, env);
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

async function handleTelegramWebhook(request, env) {
  if (request.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
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
  const data = callback.data;
  if (typeof data !== "string") {
    await answerCallback(env, callback.id, "Invalid feedback payload");
    return new Response("Invalid data", { status: 400 });
  }
  const parsed = parseCallbackData(data);
  if (!parsed) {
    await answerCallback(env, callback.id, "Invalid feedback payload");
    return new Response("Invalid callback data", { status: 400 });
  }
  const { runId, jobShortId, action, jobHash } = parsed;
  const sessionKey = `session:${runId}`;
  const windowRaw = await env.JOB_SCOUT_KV.get(sessionKey, "json");
  if (!windowRaw) {
    await answerCallback(env, callback.id, "⏱ Session expired");
    return new Response("Session missing", { status: 410 });
  }
  const now = Date.now();
  const openAt = Date.parse(windowRaw.open_at);
  const closeAt = Date.parse(windowRaw.close_at);
  const maxWindowMs = feedbackWindowMs(env);
  const maxCloseAt = openAt + maxWindowMs;
  const effectiveCloseAt = Math.min(closeAt, maxCloseAt);
  if (!Number.isFinite(openAt) || !Number.isFinite(closeAt)) {
    await answerCallback(env, callback.id, "Feedback window invalid");
    return new Response("Window invalid", { status: 400 });
  }
  if (now < openAt || now > effectiveCloseAt) {
    await answerCallback(env, callback.id, "⏱ Session expired");
    return new Response("Window closed", { status: 410 });
  }
  const jobs = Array.isArray(windowRaw.jobs) ? windowRaw.jobs : [];
  const jobEntry = jobs.find((job) => job?.short_id === jobShortId);
  if (!jobEntry || jobEntry?.job_hash !== jobHash) {
    await answerCallback(env, callback.id, "Unknown job");
    return new Response("Job not found", { status: 400 });
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
  await env.JOB_SCOUT_KV.put(key, JSON.stringify(value), {
    expirationTtl: 60 * 60 * 24 * 7,
  });
  await answerCallback(env, callback.id, "✅ Feedback recorded");
  return new Response("OK", { status: 200 });
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

function parseCallbackData(data) {
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
