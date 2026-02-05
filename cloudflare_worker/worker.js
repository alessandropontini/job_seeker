export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    if (path === "/telegram/webhook") {
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
  const { runId, jobShortId, action } = parsed;
  const windowKey = `window:${runId}`;
  const windowRaw = await env.JOB_SCOUT_KV.get(windowKey, "json");
  if (!windowRaw) {
    await answerCallback(env, callback.id, "⏱ Feedback window closed");
    return new Response("Window missing", { status: 410 });
  }
  const now = Date.now();
  const openAt = Date.parse(windowRaw.open_at);
  const closeAt = Date.parse(windowRaw.close_at);
  if (!Number.isFinite(openAt) || !Number.isFinite(closeAt)) {
    await answerCallback(env, callback.id, "Feedback window invalid");
    return new Response("Window invalid", { status: 400 });
  }
  if (now < openAt || now > closeAt) {
    await answerCallback(env, callback.id, "⏱ Feedback window closed");
    return new Response("Window closed", { status: 410 });
  }
  const jobs = Array.isArray(windowRaw.jobs) ? windowRaw.jobs : [];
  const jobAllowed = jobs.some((job) => job?.short_id === jobShortId);
  if (!jobAllowed) {
    await answerCallback(env, callback.id, "Unknown job");
    return new Response("Job not found", { status: 400 });
  }
  const userId = callback.from?.id ?? "unknown";
  const messageId = callback.message?.message_id ?? null;
  const key = `fb:${runId}:${userId}:${jobShortId}`;
  const value = {
    action,
    job_short_id: jobShortId,
    ts: new Date().toISOString(),
    message_id: messageId,
    user_id: userId,
  };
  await env.JOB_SCOUT_KV.put(key, JSON.stringify(value), {
    expirationTtl: 60 * 60 * 24 * 7,
  });
  await answerCallback(env, callback.id, "✅ Feedback recorded");
  return new Response("OK", { status: 200 });
}

async function handleFeedback(request, env) {
  if (request.method !== "GET") {
    return new Response("Method not allowed", { status: 405 });
  }
  if (!isAuthorized(request, env)) {
    return new Response("Forbidden", { status: 403 });
  }
  const url = new URL(request.url);
  const runId = url.searchParams.get("run_id");
  if (!runId) {
    return new Response("Missing run_id", { status: 400 });
  }
  const prefix = `fb:${runId}:`;
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
  if (!isAuthorized(request, env)) {
    return new Response("Forbidden", { status: 403 });
  }
  let payload;
  try {
    payload = await request.json();
  } catch {
    return new Response("Invalid JSON", { status: 400 });
  }
  const runId = payload?.run_id;
  if (!runId) {
    return new Response("Missing run_id", { status: 400 });
  }
  const openAt = payload?.open_at;
  const closeAt = payload?.close_at;
  if (!openAt || !closeAt) {
    return new Response("Missing window", { status: 400 });
  }
  const windowPayload = {
    run_id: runId,
    open_at: openAt,
    close_at: closeAt,
    jobs: Array.isArray(payload.jobs) ? payload.jobs : [],
  };
  await env.JOB_SCOUT_KV.put(
    `window:${runId}`,
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
  if (parts.length !== 4) {
    return null;
  }
  const [_, runId, jobShortId, action] = parts;
  if (!runId || !jobShortId || !action) {
    return null;
  }
  return { runId, jobShortId, action };
}

function isAuthorized(request, env) {
  const secret = env.WEBHOOK_SECRET;
  if (!secret) {
    return false;
  }
  const header = request.headers.get("X-Webhook-Secret");
  return header === secret;
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
