export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;
    const start = Date.now();
    const cfRay = request.headers.get("cf-ray");
    const requestId = cfRay || crypto.randomUUID();
    const baseLog = { request_id: requestId, cf_ray: cfRay, method, path };

    logInfo("request_received", {
      ...baseLog,
      user_agent: request.headers.get("user-agent"),
      header_names: getHeaderNames(request.headers),
    });

    let result;
    try {
      if (path === "/telegram/feedback" || path === "/telegram/webhook") {
        result = await handleTelegramWebhook(request, env, ctx, baseLog);
      } else if (path === "/feedback") {
        result = await handleFeedback(request, env, baseLog);
      } else if (path === "/window/open") {
        result = await handleWindowOpen(request, env, baseLog);
      } else if (path === "/internal/smoke/session") {
        result = await handleSmokeSession(request, env, baseLog);
      } else if (path === "/healthz") {
        result = {
          response: new Response("OK", { status: 200 }),
          outcome: "ok",
          reason: "health_check",
        };
      } else {
        logInfo("route_not_found", { ...baseLog });
        result = {
          response: new Response("Not found", { status: 404 }),
          outcome: "blocked",
          reason: "route_not_found",
        };
      }
    } catch (error) {
      logError("request_error", {
        ...baseLog,
        error: serializeError(error),
        outcome: "error",
        reason: "exception",
      });
      result = {
        response: new Response("Internal error", { status: 500 }),
        outcome: "error",
        reason: "exception",
      };
    }

    const latencyMs = Date.now() - start;
    logInfo("request_handled", {
      ...baseLog,
      status: result.response.status,
      latency_ms: latencyMs,
      outcome: result.outcome,
      reason: result.reason,
      telegram_update_type: result.telegram_update_type,
      kv_key: result.kv_key,
    });

    return result.response;
  },
};

async function handleTelegramWebhook(request, env, ctx, baseLog) {
  if (request.method === "GET") {
    logInfo("telegram_webhook_probe", {
      ...baseLog,
      outcome: "ok",
      reason: "probe_get",
    });
    return {
      response: new Response("ok", { status: 200 }),
      outcome: "ok",
      reason: "probe_get",
    };
  }
  if (request.method !== "POST") {
    logWarn("telegram_webhook_rejected", {
      ...baseLog,
      outcome: "blocked",
      reason: "invalid_method",
    });
    return {
      response: new Response("Method not allowed", { status: 405 }),
      outcome: "blocked",
      reason: "invalid_method",
    };
  }
  const authError = ensureTelegramWebhookAuthorized(request, env);
  if (authError) {
    const reason =
      authError.status === 500 ? "missing_secret" : "auth_fail";
    const logFn = authError.status === 500 ? logError : logWarn;
    logFn(reason, {
      ...baseLog,
      outcome: "blocked",
      reason,
    });
    return {
      response: authError,
      outcome: "blocked",
      reason,
    };
  }
  logInfo("telegram_webhook_authorized", { ...baseLog, outcome: "ok" });
  let payload;
  let telegramUpdateType = "unknown";
  try {
    payload = await request.json();
  } catch {
    logWarn("telegram_webhook_bad_json", {
      ...baseLog,
      outcome: "blocked",
      reason: "bad_json",
    });
    return {
      response: new Response("Invalid JSON", { status: 400 }),
      outcome: "blocked",
      reason: "bad_json",
    };
  }
  if (payload?.callback_query) {
    telegramUpdateType = "callback_query";
  } else if (payload?.message) {
    telegramUpdateType = "message";
  }
  logInfo("telegram_webhook_parsed", {
    ...baseLog,
    telegram_update_type: telegramUpdateType,
  });
  const callback = payload?.callback_query;
  if (!callback) {
    logInfo("telegram_webhook_no_callback", {
      ...baseLog,
      outcome: "ok",
      reason: "no_callback",
      telegram_update_type: telegramUpdateType,
    });
    return {
      response: new Response("No callback", { status: 200 }),
      outcome: "ok",
      reason: "no_callback",
      telegram_update_type: telegramUpdateType,
    };
  }
  const allowedUserId = env.ALLOWED_TELEGRAM_USER_ID;
  const callbackUserId = callback.from?.id;
  const messageUserId = payload?.message?.from?.id;
  const updateUserId = callbackUserId ?? messageUserId;
  if (
    allowedUserId &&
    String(updateUserId ?? "") !== String(allowedUserId)
  ) {
    await answerCallback(env, callback.id, "🚫 Not authorized");
    logWarn("unauthorized_user", {
      ...baseLog,
      outcome: "blocked",
      reason: "unauthorized_user",
      telegram_update_type: telegramUpdateType,
      telegram_user_id: updateUserId ?? "unknown",
    });
    return {
      response: jsonResponse({ ok: true, ignored: true }),
      outcome: "blocked",
      reason: "unauthorized_user",
      telegram_update_type: telegramUpdateType,
    };
  }
  const data = callback.data;
  if (typeof data !== "string") {
    scheduleAnswer(env, ctx, callback.id, "Feedback non valido");
    logWarn("telegram_webhook_rejected", {
      ...baseLog,
      outcome: "blocked",
      reason: "invalid_data",
      telegram_update_type: telegramUpdateType,
    });
    return {
      response: new Response("Invalid data", { status: 200 }),
      outcome: "blocked",
      reason: "invalid_data",
      telegram_update_type: telegramUpdateType,
    };
  }
  const parsed = parseCallbackData(data);
  if (!parsed) {
    scheduleAnswer(env, ctx, callback.id, "Feedback non valido");
    logWarn("telegram_webhook_rejected", {
      ...baseLog,
      outcome: "blocked",
      reason: "invalid_callback_data",
      telegram_update_type: telegramUpdateType,
    });
    return {
      response: new Response("Invalid callback data", { status: 200 }),
      outcome: "blocked",
      reason: "invalid_callback_data",
      telegram_update_type: telegramUpdateType,
    };
  }
  const { runId, jobShortId, action, jobHash } = parsed;
  const sessionKey = `session:${runId}`;
  logInfo("kv_read", { ...baseLog, kv_key: sessionKey });
  const windowRaw = await env.JOB_SCOUT_KV.get(sessionKey, "json");
  if (!windowRaw) {
    scheduleAnswer(env, ctx, callback.id, "⏱ Session scaduta");
    logWarn("telegram_webhook_rejected", {
      ...baseLog,
      outcome: "blocked",
      reason: "session_missing",
      telegram_update_type: telegramUpdateType,
      kv_key: sessionKey,
    });
    return {
      response: new Response("Session missing", { status: 200 }),
      outcome: "blocked",
      reason: "session_missing",
      telegram_update_type: telegramUpdateType,
      kv_key: sessionKey,
    };
  }
  const now = Date.now();
  const openAt = Date.parse(windowRaw.open_at);
  const closeAt = Date.parse(windowRaw.close_at);
  const maxWindowMs = feedbackWindowMs(env);
  const maxCloseAt = openAt + maxWindowMs;
  const effectiveCloseAt = Math.min(closeAt, maxCloseAt);
  if (!Number.isFinite(openAt) || !Number.isFinite(closeAt)) {
    scheduleAnswer(env, ctx, callback.id, "Feedback non valido");
    logWarn("telegram_webhook_rejected", {
      ...baseLog,
      outcome: "blocked",
      reason: "window_invalid",
      telegram_update_type: telegramUpdateType,
      kv_key: sessionKey,
    });
    return {
      response: new Response("Window invalid", { status: 200 }),
      outcome: "blocked",
      reason: "window_invalid",
      telegram_update_type: telegramUpdateType,
      kv_key: sessionKey,
    };
  }
  if (now < openAt || now > effectiveCloseAt) {
    scheduleAnswer(env, ctx, callback.id, "⏱ Session scaduta");
    logWarn("telegram_webhook_rejected", {
      ...baseLog,
      outcome: "blocked",
      reason: "window_closed",
      telegram_update_type: telegramUpdateType,
      kv_key: sessionKey,
    });
    return {
      response: new Response("Window closed", { status: 200 }),
      outcome: "blocked",
      reason: "window_closed",
      telegram_update_type: telegramUpdateType,
      kv_key: sessionKey,
    };
  }
  const jobs = Array.isArray(windowRaw.jobs) ? windowRaw.jobs : [];
  const jobEntry = jobs.find((job) => job?.short_id === jobShortId);
  if (!jobEntry || jobEntry?.job_hash !== jobHash) {
    scheduleAnswer(env, ctx, callback.id, "Job non riconosciuto");
    logWarn("telegram_webhook_rejected", {
      ...baseLog,
      outcome: "blocked",
      reason: "job_not_found",
      telegram_update_type: telegramUpdateType,
      kv_key: sessionKey,
    });
    return {
      response: new Response("Job not found", { status: 200 }),
      outcome: "blocked",
      reason: "job_not_found",
      telegram_update_type: telegramUpdateType,
      kv_key: sessionKey,
    };
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
  }).catch((error) => {
    logError("kv_write_failed", {
      ...baseLog,
      kv_key: key,
      error: serializeError(error),
    });
  });
  const ackPromise = answerCallback(env, callback.id, "✅ Feedback salvato").catch(
    (error) => {
      logError("telegram_callback_failed", {
        ...baseLog,
        error: serializeError(error),
      });
    }
  );
  logInfo("kv_write_scheduled", {
    ...baseLog,
    kv_key: key,
    telegram_update_type: telegramUpdateType,
  });
  if (ctx) {
    ctx.waitUntil(writePromise);
    ctx.waitUntil(ackPromise);
  } else {
    await writePromise;
    await ackPromise;
  }
  return {
    response: jsonResponse({ ok: true }),
    outcome: "ok",
    reason: "feedback_recorded",
    telegram_update_type: telegramUpdateType,
    kv_key: key,
  };
}

async function handleSmokeSession(request, env, baseLog) {
  if (request.method !== "POST") {
    logWarn("smoke_session_rejected", {
      ...baseLog,
      outcome: "blocked",
      reason: "invalid_method",
    });
    return {
      response: new Response("Not found", { status: 404 }),
      outcome: "blocked",
      reason: "invalid_method",
    };
  }
  const auth = ensureSmokeAuthorized(request, env);
  if (!auth.ok) {
    logWarn("smoke_session_rejected", {
      ...baseLog,
      outcome: "blocked",
      reason: auth.reason,
    });
    return {
      response: new Response("Not found", { status: 404 }),
      outcome: "blocked",
      reason: auth.reason,
    };
  }
  const sessionId = crypto.randomUUID();
  const jobId = "job-001";
  const digestHash = await sha256Hex(sessionId);
  const jobHash = await buildJobHash(jobId, digestHash);
  const openAt = new Date().toISOString();
  const closeAt = new Date(Date.now() + 600 * 1000).toISOString();
  const windowPayload = {
    run_id: sessionId,
    open_at: openAt,
    close_at: closeAt,
    jobs: [
      {
        short_id: jobId,
        job_hash: jobHash,
        source: "smoke",
      },
    ],
  };
  const sessionKey = `session:${sessionId}`;
  await env.JOB_SCOUT_KV.put(sessionKey, JSON.stringify(windowPayload), {
    expirationTtl: 600,
  });
  logInfo("smoke_session_created", {
    ...baseLog,
    outcome: "ok",
    reason: "session_created",
    kv_key: sessionKey,
  });
  const callbackDataLike = buildCallbackData(
    sessionId,
    jobId,
    "like",
    jobHash
  );
  const callbackDataDislike = buildCallbackData(
    sessionId,
    jobId,
    "dislike",
    jobHash
  );
  return {
    response: jsonResponse({
      session_id: sessionId,
      job_id: jobId,
      callback_data_like: callbackDataLike,
      callback_data_dislike: callbackDataDislike,
    }),
    outcome: "ok",
    reason: "session_created",
    kv_key: sessionKey,
  };
}

function ensureTelegramWebhookAuthorized(request, env) {
  const secret = env.JOB_SCOUT_WEBHOOK_SECRET;
  if (!secret) {
    return new Response("Missing webhook secret", { status: 500 });
  }
  const provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token");
  if (!provided || provided !== secret) {
    return new Response("Unauthorized", { status: 401 });
  }
  return null;
}

function ensureSmokeAuthorized(request, env) {
  const secret = env.JOB_SCOUT_SMOKE_TOKEN;
  if (!secret) {
    return { ok: false, reason: "missing_smoke_secret" };
  }
  const provided = request.headers.get("X-Smoke-Token");
  if (!provided || provided !== secret) {
    return { ok: false, reason: "smoke_token_invalid" };
  }
  return { ok: true };
}

async function handleFeedback(request, env, baseLog) {
  if (request.method !== "POST") {
    logWarn("feedback_rejected", {
      ...baseLog,
      outcome: "blocked",
      reason: "invalid_method",
    });
    return {
      response: new Response("Method not allowed", { status: 405 }),
      outcome: "blocked",
      reason: "invalid_method",
    };
  }
  const payload = await readSignedJson(request, env);
  if (!payload.ok) {
    logWarn("feedback_rejected", {
      ...baseLog,
      outcome: "blocked",
      reason: "signature_invalid",
    });
    return {
      response: payload.response,
      outcome: "blocked",
      reason: "signature_invalid",
    };
  }
  const runId = payload.body?.run_id;
  if (!runId) {
    logWarn("feedback_rejected", {
      ...baseLog,
      outcome: "blocked",
      reason: "missing_run_id",
    });
    return {
      response: new Response("Missing run_id", { status: 400 }),
      outcome: "blocked",
      reason: "missing_run_id",
    };
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
  return {
    response: new Response(JSON.stringify(items), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
    outcome: "ok",
    reason: "feedback_listed",
  };
}

async function handleWindowOpen(request, env, baseLog) {
  if (request.method !== "POST") {
    logWarn("window_open_rejected", {
      ...baseLog,
      outcome: "blocked",
      reason: "invalid_method",
    });
    return {
      response: new Response("Method not allowed", { status: 405 }),
      outcome: "blocked",
      reason: "invalid_method",
    };
  }
  const payload = await readSignedJson(request, env);
  if (!payload.ok) {
    logWarn("window_open_rejected", {
      ...baseLog,
      outcome: "blocked",
      reason: "signature_invalid",
    });
    return {
      response: payload.response,
      outcome: "blocked",
      reason: "signature_invalid",
    };
  }
  const runId = payload.body?.run_id;
  if (!runId) {
    logWarn("window_open_rejected", {
      ...baseLog,
      outcome: "blocked",
      reason: "missing_run_id",
    });
    return {
      response: new Response("Missing run_id", { status: 400 }),
      outcome: "blocked",
      reason: "missing_run_id",
    };
  }
  const openAt = payload.body?.open_at;
  const closeAt = payload.body?.close_at;
  if (!openAt || !closeAt) {
    logWarn("window_open_rejected", {
      ...baseLog,
      outcome: "blocked",
      reason: "missing_window",
    });
    return {
      response: new Response("Missing window", { status: 400 }),
      outcome: "blocked",
      reason: "missing_window",
    };
  }
  const openAtMs = Date.parse(openAt);
  const closeAtMs = Date.parse(closeAt);
  if (!Number.isFinite(openAtMs) || !Number.isFinite(closeAtMs)) {
    logWarn("window_open_rejected", {
      ...baseLog,
      outcome: "blocked",
      reason: "invalid_window",
    });
    return {
      response: new Response("Invalid window timestamps", { status: 400 }),
      outcome: "blocked",
      reason: "invalid_window",
    };
  }
  const maxWindowMs = feedbackWindowMs(env);
  if (closeAtMs - openAtMs > maxWindowMs) {
    logWarn("window_open_rejected", {
      ...baseLog,
      outcome: "blocked",
      reason: "window_exceeds_max",
    });
    return {
      response: new Response("Window exceeds max duration", { status: 400 }),
      outcome: "blocked",
      reason: "window_exceeds_max",
    };
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
  logInfo("window_open_recorded", {
    ...baseLog,
    kv_key: `session:${runId}`,
  });
  return {
    response: new Response("OK", { status: 200 }),
    outcome: "ok",
    reason: "window_open_recorded",
    kv_key: `session:${runId}`,
  };
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
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  let responseBody;
  try {
    responseBody = await response.json();
  } catch {
    responseBody = null;
  }
  if (!response.ok) {
    logWarn("telegram_callback_failed", {
      status: response.status,
      description: responseBody?.description,
    });
  } else {
    logInfo("telegram_callback_sent", { status: response.status });
  }
}

function logInfo(event, fields = {}) {
  console.log(JSON.stringify({ level: "info", event, ...fields }));
}

function logWarn(event, fields = {}) {
  console.log(JSON.stringify({ level: "warn", event, ...fields }));
}

function logError(event, fields = {}) {
  console.error(JSON.stringify({ level: "error", event, ...fields }));
}

function redactHeaders(headers) {
  const redacted = {};
  if (!headers) {
    return redacted;
  }
  for (const [key, value] of headers.entries()) {
    if (shouldRedactHeader(key)) {
      redacted[key] = "[REDACTED]";
    } else {
      redacted[key] = value;
    }
  }
  return redacted;
}

function getHeaderNames(headers) {
  if (!headers) {
    return [];
  }
  return Array.from(headers.keys());
}

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function buildCallbackData(runId, jobShortId, action, jobHash) {
  const payload = `fb|${runId}|${jobShortId}|${action}|${jobHash}`;
  if (new TextEncoder().encode(payload).length >= 64) {
    throw new Error("callback_data exceeds Telegram limit");
  }
  return payload;
}

async function buildJobHash(jobKey, digestHash) {
  const payload = `${jobKey}:${digestHash}`;
  const digest = await sha256Hex(payload);
  return digest.slice(0, 8);
}

async function sha256Hex(payload) {
  const buffer = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(payload)
  );
  return [...new Uint8Array(buffer)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function shouldRedactHeader(headerName) {
  const name = headerName.toLowerCase();
  return [
    "authorization",
    "cookie",
    "set-cookie",
    "x-smoke-token",
    "x-telegram-bot-api-secret-token",
    "x-webhook-signature",
  ].includes(name);
}

function serializeError(error) {
  if (error instanceof Error) {
    return { message: error.message, stack: error.stack };
  }
  return { message: String(error) };
}
