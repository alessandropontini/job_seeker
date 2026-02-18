const REMOTIVE_API_URL = "https://remotive.com/api/remote-jobs";
const LIVE_RUN_TTL_SECONDS = 60 * 60 * 24 * 14;

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
      } else if (path === "/run_daily") {
        result = await handleRunDailyRoute(request, env, ctx, baseLog);
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

    return withRequestId(result.response, requestId);
  },

  async scheduled(controller, env, ctx) {
    const scheduledAt = new Date(controller.scheduledTime);
    const baseLog = {
      request_id: crypto.randomUUID(),
      trigger: "cron",
      cron: controller.cron,
      scheduled_time: scheduledAt.toISOString(),
    };
    if (!isRomeTargetHour(scheduledAt, 8)) {
      logInfo("live_daily_cron_outside_target_hour", baseLog);
      return;
    }
    const result = await runDailyLiveDigest(env, ctx, baseLog);
    if (result.ok) {
      logInfo("live_daily_scheduled_done", {
        ...baseLog,
        run_id: result.run_id,
        sent_count: result.sent_count,
      });
    } else {
      logWarn("live_daily_scheduled_skipped", {
        ...baseLog,
        reason: result.reason,
      });
    }
  },
};

async function handleRunDailyRoute(request, env, ctx, baseLog) {
  if (request.method !== "POST") {
    return {
      response: new Response("Method not allowed", { status: 405 }),
      outcome: "blocked",
      reason: "invalid_method",
    };
  }
  const auth = ensureSmokeAuthorized(request, env);
  if (!auth.ok) {
    return {
      response: new Response("Not found", { status: 404 }),
      outcome: "blocked",
      reason: auth.reason,
    };
  }
  const result = await runDailyLiveDigest(env, ctx, { ...baseLog, trigger: "http" });
  const status = result.ok ? 200 : 409;
  return {
    response: jsonResponse(result, status),
    outcome: result.ok ? "ok" : "blocked",
    reason: result.reason || "run_daily_completed",
  };
}

async function runDailyLiveDigest(env, ctx, baseLog) {
  if (String(env.JOB_SCOUT_ENV || "").toLowerCase() !== "live") {
    logWarn("live_daily_blocked", {
      ...baseLog,
      reason: "env_not_live",
    });
    return { ok: false, reason: "env_not_live" };
  }
  const required = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "JOB_SCOUT_KV"];
  for (const key of required) {
    if (!env[key]) {
      logError("live_daily_missing_binding", {
        ...baseLog,
        reason: "missing_binding",
        binding: key,
      });
      return { ok: false, reason: `missing_${key.toLowerCase()}` };
    }
  }

  const yesterday = yesterdayRomeDateString(new Date());
  const lastSentKey = "live:last_sent_date";
  const sentDate = await env.JOB_SCOUT_KV.get(lastSentKey);
  if (sentDate === yesterday) {
    logInfo("live_daily_skipped_already_sent", {
      ...baseLog,
      date_rome: yesterday,
    });
    return { ok: false, reason: "already_sent" };
  }

  const runId = await buildLiveRunId();
  const jobs = await fetchRemotiveJobs(baseLog);
  const filtered = selectLiveJobsForYesterday(jobs, yesterday);
  const finalJobs = filtered.jobs.length > 0 ? filtered.jobs : selectLiveFallbackJobs(jobs);
  const isFallback = filtered.jobs.length === 0;

  if (finalJobs.length === 0) {
    logWarn("live_daily_no_jobs", {
      ...baseLog,
      run_id: runId,
      date_rome: yesterday,
      reason: "empty_after_filter",
    });
    await persistLiveRun(env, {
      run_id: runId,
      date_rome: yesterday,
      fallback_used: isFallback,
      jobs: [],
      sent: false,
      reason: "empty_after_filter",
    });
    return { ok: false, reason: "no_jobs" };
  }

  const jobsWithIds = await buildDigestJobs(runId, finalJobs);
  const digestHash = await sha256Hex(JSON.stringify(jobsWithIds.map((job) => job.id)));
  const messageText = buildLiveDigestMessage({
    dateRome: yesterday,
    jobs: jobsWithIds,
    fallbackUsed: isFallback,
    missingSalaryCount: jobsWithIds.filter((job) => job.salary_missing).length,
  });

  const sendResult = await sendDigestTelegram(env, messageText, jobsWithIds);
  if (!sendResult.ok) {
    logError("live_daily_send_failed", {
      ...baseLog,
      run_id: runId,
      reason: sendResult.reason,
      sent_count: jobsWithIds.length,
    });
    return { ok: false, reason: "telegram_send_failed" };
  }

  const now = new Date();
  const openAt = now.toISOString();
  const closeAt = new Date(now.getTime() + feedbackWindowMs(env)).toISOString();
  const sessionPayload = {
    run_id: runId,
    open_at: openAt,
    close_at: closeAt,
    jobs: jobsWithIds.map((job) => ({
      short_id: job.short_id,
      job_hash: job.job_hash,
      source: job.source,
    })),
  };
  await env.JOB_SCOUT_KV.put(`session:${runId}`, JSON.stringify(sessionPayload), {
    expirationTtl: 60 * 60 * 2,
  });

  await persistLiveRun(env, {
    run_id: runId,
    digest_hash: digestHash,
    date_rome: yesterday,
    fallback_used: isFallback,
    sent: true,
    message_id: sendResult.message_id,
    jobs: jobsWithIds,
    sent_at: now.toISOString(),
  });
  await env.JOB_SCOUT_KV.put(lastSentKey, yesterday, { expirationTtl: LIVE_RUN_TTL_SECONDS });

  logInfo("live_daily_sent", {
    ...baseLog,
    run_id: runId,
    date_rome: yesterday,
    jobs_count: jobsWithIds.length,
    fallback_used: isFallback,
  });
  return { ok: true, run_id: runId, sent_count: jobsWithIds.length, fallback_used: isFallback };
}

async function fetchRemotiveJobs(baseLog) {
  const response = await fetch(REMOTIVE_API_URL, {
    method: "GET",
    headers: { "Accept": "application/json" },
  });
  if (!response.ok) {
    logWarn("live_source_failed", {
      ...baseLog,
      source: "remotive",
      status: response.status,
    });
    return [];
  }
  const payload = await response.json();
  if (!Array.isArray(payload?.jobs)) {
    return [];
  }
  return payload.jobs.map((job) => normalizeRemotiveJob(job));
}

function normalizeRemotiveJob(job) {
  const category = String(job?.category || "").toLowerCase();
  const title = String(job?.title || "");
  const location = String(job?.candidate_required_location || "");
  const publicationDate = String(job?.publication_date || "");
  const salaryRaw = String(job?.salary || "");
  const salaryMinEur = extractSalaryMinEur(salaryRaw);
  const roleKey = `${title} ${category}`.toLowerCase();
  const isLeadRole = roleKey.includes("lead") || roleKey.includes("manager");
  const locationKey = location.toLowerCase();
  const includesUk = /(uk|united kingdom|england|scotland|wales|northern ireland|london)/i.test(locationKey);
  const preferredLocation = /(europe|eu|italy|new york)/i.test(locationKey);
  const isRemote = /remote|worldwide|anywhere/i.test(location);
  const missingSalary = salaryMinEur === null;
  return {
    id: String(job?.id || ""),
    title,
    company: String(job?.company_name || "Unknown"),
    url: String(job?.url || ""),
    location,
    publication_date: publicationDate,
    source: "remotive",
    category,
    is_lead_role: isLeadRole,
    includes_uk: includesUk,
    preferred_location: preferredLocation,
    remote: isRemote,
    salary_min_eur: salaryMinEur,
    salary_missing: missingSalary,
  };
}

function selectLiveJobsForYesterday(jobs, yesterdayRome) {
  const filtered = jobs
    .filter((job) => job.id && job.url)
    .filter((job) => job.is_lead_role)
    .filter((job) => !job.includes_uk)
    .filter((job) => job.preferred_location)
    .filter((job) => job.salary_missing || (job.salary_min_eur ?? 0) >= 52000)
    .filter((job) => publicationRomeDateString(job.publication_date) === yesterdayRome)
    .sort((left, right) => scoreLiveJob(right) - scoreLiveJob(left))
    .slice(0, 6);
  return { jobs: filtered };
}

function selectLiveFallbackJobs(jobs) {
  return jobs
    .filter((job) => job.id && job.url)
    .filter((job) => job.is_lead_role)
    .filter((job) => !job.includes_uk)
    .filter((job) => job.preferred_location)
    .filter((job) => job.salary_missing || (job.salary_min_eur ?? 0) >= 52000)
    .sort((left, right) => scoreLiveJob(right) - scoreLiveJob(left))
    .slice(0, 4);
}

function scoreLiveJob(job) {
  let score = 0;
  if (job.remote) score += 3;
  if (!job.salary_missing) score += 2;
  if (job.location.toLowerCase().includes("italy")) score += 1;
  if (job.location.toLowerCase().includes("new york")) score += 1;
  return score;
}

async function buildDigestJobs(runId, jobs) {
  const usedShortIds = new Set();
  const digestHash = await sha256Hex(JSON.stringify(jobs.map((job) => job.id)));
  const output = [];
  for (const job of jobs) {
    const shortId = buildShortId(job.id, usedShortIds);
    const jobHash = await buildJobHash(job.id, digestHash);
    output.push({ ...job, short_id: shortId, job_hash: jobHash, run_id: runId });
  }
  return output;
}

function buildLiveDigestMessage({ dateRome, jobs, fallbackUsed, missingSalaryCount }) {
  const lines = [];
  lines.push(`🧭 Job Scout LIVE — digest ${dateRome}`);
  lines.push(
    fallbackUsed
      ? "⚠️ Finestra ieri vuota: invio fallback con migliori match recenti."
      : "✅ Finestra giornaliera: offerte pubblicate ieri (Europe/Rome)."
  );
  if (missingSalaryCount > 0) {
    lines.push(`ℹ️ ${missingSalaryCount} offerte senza salario dichiarato (flag: missing salary).`);
  }
  lines.push("");
  jobs.forEach((job, index) => {
    const salaryLabel = job.salary_missing ? "salary: missing" : `salary ≥ €${job.salary_min_eur}`;
    lines.push(`${index + 1}. ${job.title} — ${job.company}`);
    lines.push(`   📍 ${job.location} | ${salaryLabel}`);
    lines.push(`   🔗 ${job.url}`);
  });
  lines.push("");
  lines.push("Feedback rapido: 👍 interessante | 👎 no fit");
  return lines.join("\n");
}

async function sendDigestTelegram(env, text, jobs) {
  const token = env.TELEGRAM_BOT_TOKEN;
  const chatId = env.TELEGRAM_CHAT_ID;
  const keyboard = [];
  for (const job of jobs) {
    const likeData = buildCallbackData(job.run_id, job.short_id, "L", job.job_hash);
    const dislikeData = buildCallbackData(job.run_id, job.short_id, "D", job.job_hash);
    keyboard.push([
      { text: `👍 ${job.short_id}`, callback_data: likeData },
      { text: `👎 ${job.short_id}`, callback_data: dislikeData },
    ]);
  }
  const response = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_id: chatId,
      text,
      disable_web_page_preview: true,
      reply_markup: { inline_keyboard: keyboard.slice(0, 8) },
    }),
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok || payload?.ok !== true) {
    return { ok: false, reason: "status_not_ok" };
  }
  return { ok: true, message_id: payload?.result?.message_id ?? null };
}

async function persistLiveRun(env, record) {
  await env.JOB_SCOUT_KV.put(`live:run:${record.run_id}`, JSON.stringify(record), {
    expirationTtl: LIVE_RUN_TTL_SECONDS,
  });
}


function isRomeTargetHour(date, targetHour) {
  const hour = Number(
    new Intl.DateTimeFormat("en-GB", {
      timeZone: "Europe/Rome",
      hour: "2-digit",
      hour12: false,
    }).format(date)
  );
  return hour === targetHour;
}

function yesterdayRomeDateString(now) {
  const romeDate = new Date(now.toLocaleString("en-US", { timeZone: "Europe/Rome" }));
  romeDate.setDate(romeDate.getDate() - 1);
  return [
    romeDate.getFullYear(),
    String(romeDate.getMonth() + 1).padStart(2, "0"),
    String(romeDate.getDate()).padStart(2, "0"),
  ].join("-");
}

function publicationRomeDateString(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Rome",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function extractSalaryMinEur(rawSalary) {
  if (!rawSalary) {
    return null;
  }
  const normalized = rawSalary.toLowerCase();
  const hasEuro = /€|eur/.test(normalized);
  if (!hasEuro) {
    return null;
  }
  const matches = normalized.match(/\d[\d.,]*/g);
  if (!matches || matches.length === 0) {
    return null;
  }
  const values = matches
    .map((entry) => Number(entry.replace(/\./g, "").replace(",", ".")))
    .filter((value) => Number.isFinite(value) && value > 0)
    .map((value) => (value < 1000 ? value * 1000 : value));
  if (values.length === 0) {
    return null;
  }
  return Math.round(Math.min(...values));
}

async function buildLiveRunId() {
  const now = new Date();
  const compact = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Rome",
    year: "2-digit",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    hour12: false,
  })
    .format(now)
    .replace(/[^0-9]/g, "")
    .slice(0, 8);
  const nonce = (await sha256Hex(`${now.toISOString()}-${crypto.randomUUID()}`)).slice(0, 4);
  return `${compact}${nonce}`;
}

async function handleTelegramWebhook(request, env, ctx, baseLog) {
  const startedAt = Date.now();
  if (request.method === "GET") {
    logInfo("telegram_webhook_probe", {
      ...baseLog,
      outcome: "ok",
      reason: "webhook_probe",
    });
    return {
      response: textResponse("OK", 200, baseLog.request_id),
      outcome: "ok",
      reason: "webhook_probe",
    };
  }
  if (request.method !== "POST") {
    logWarn("telegram_webhook_rejected", {
      ...baseLog,
      outcome: "blocked",
      reason: "invalid_method",
    });
    return {
      response: textResponse("Method not allowed", 405, baseLog.request_id),
      outcome: "blocked",
      reason: "invalid_method",
    };
  }
  const authError = ensureTelegramWebhookAuthorized(request, env);
  if (authError) {
    const reason = authError.status === 500 ? "missing_secret" : "auth_fail";
    const logFn = authError.status === 500 ? logError : logWarn;
    logFn(reason, {
      ...baseLog,
      outcome: "forbidden",
      reason,
    });
    return {
      response: textResponse("Forbidden", authError.status, baseLog.request_id),
      outcome: "forbidden",
      reason,
    };
  }
  let payload;
  let telegramUpdateType = "unknown";
  try {
    payload = await request.json();
  } catch {
    return feedbackExit({
      baseLog,
      startedAt,
      outcome: "invalid_callback",
      errorCode: "bad_json",
      reason: "Invalid JSON payload",
      runId: null,
      jobShortId: null,
      action: null,
      responseMessage: "Invalid callback data",
      callbackId: null,
      env,
      ctx,
      responseStatus: 400,
      telegramUpdateType,
    });
  }
  if (payload?.callback_query) {
    telegramUpdateType = "callback_query";
  } else if (payload?.message) {
    telegramUpdateType = "message";
  }

  const callback = payload?.callback_query;
  if (!callback) {
    return {
      response: textResponse("No callback", 200, baseLog.request_id),
      outcome: "ok",
      reason: "no_callback",
      telegram_update_type: telegramUpdateType,
    };
  }

  const allowedUserId = env.ALLOWED_TELEGRAM_USER_ID;
  const callbackUserId = callback.from?.id;
  const messageUserId = payload?.message?.from?.id;
  const updateUserId = callbackUserId ?? messageUserId;
  if (allowedUserId && String(updateUserId ?? "") !== String(allowedUserId)) {
    return feedbackExit({
      baseLog,
      startedAt,
      outcome: "forbidden",
      errorCode: "forbidden_user",
      reason: "Telegram user not allowed",
      runId: null,
      jobShortId: null,
      action: null,
      responseMessage: "Forbidden",
      callbackId: callback.id,
      callbackText: "🚫 Not authorized",
      env,
      ctx,
      responseStatus: 403,
      telegramUserId: updateUserId ?? "unknown",
      telegramUpdateType,
    });
  }

  const data = callback.data;
  if (typeof data !== "string") {
    return feedbackExit({
      baseLog,
      startedAt,
      outcome: "invalid_callback",
      errorCode: "callback_data_type",
      reason: "callback data is not a string",
      runId: null,
      jobShortId: null,
      action: null,
      responseMessage: "Invalid callback data",
      callbackId: callback.id,
      callbackText: "Feedback non valido",
      env,
      ctx,
      responseStatus: 200,
      telegramUpdateType,
    });
  }

  const parsed = parseCallbackData(data);
  if (!parsed) {
    return feedbackExit({
      baseLog,
      startedAt,
      outcome: "invalid_callback",
      errorCode: "invalid_callback_data",
      reason: "Callback payload format invalid",
      runId: null,
      jobShortId: null,
      action: null,
      responseMessage: "Invalid callback data",
      callbackId: callback.id,
      callbackText: "Feedback non valido",
      env,
      ctx,
      responseStatus: 200,
      telegramUpdateType,
    });
  }

  const { runId, jobShortId, action, jobHash, legacy } = parsed;
  const sessionKey = `session:${runId}`;
  const windowRaw = await env.JOB_SCOUT_KV.get(sessionKey, "json");
  if (!windowRaw) {
    return feedbackExit({
      baseLog,
      startedAt,
      outcome: "session_missing",
      errorCode: "session_missing",
      reason: "session key not found",
      runId,
      jobShortId,
      action,
      responseMessage: "Session missing",
      callbackId: callback.id,
      callbackText: "⏱ Session scaduta",
      env,
      ctx,
      responseStatus: 200,
      telegramUpdateType,
      kvKey: sessionKey,
    });
  }

  const now = Date.now();
  const openAt = Date.parse(windowRaw.open_at);
  const closeAt = Date.parse(windowRaw.close_at);
  const maxWindowMs = feedbackWindowMs(env);
  const maxCloseAt = openAt + maxWindowMs;
  const effectiveCloseAt = Math.min(closeAt, maxCloseAt);
  if (!Number.isFinite(openAt) || !Number.isFinite(closeAt)) {
    return feedbackExit({
      baseLog,
      startedAt,
      outcome: "invalid_callback",
      errorCode: "window_invalid",
      reason: "session window has invalid timestamp",
      runId,
      jobShortId,
      action,
      responseMessage: "Invalid callback data",
      callbackId: callback.id,
      callbackText: "Feedback non valido",
      env,
      ctx,
      responseStatus: 200,
      telegramUpdateType,
      kvKey: sessionKey,
    });
  }
  if (now < openAt || now > effectiveCloseAt) {
    return feedbackExit({
      baseLog,
      startedAt,
      outcome: "session_missing",
      errorCode: "window_closed",
      reason: "feedback window closed",
      runId,
      jobShortId,
      action,
      responseMessage: "Session missing",
      callbackId: callback.id,
      callbackText: "⏱ Session scaduta",
      env,
      ctx,
      responseStatus: 200,
      telegramUpdateType,
      kvKey: sessionKey,
    });
  }

  const jobs = Array.isArray(windowRaw.jobs) ? windowRaw.jobs : [];
  const jobEntry = resolveFeedbackJob(jobs, { jobShortId, jobHash });
  if (!jobEntry) {
    return feedbackExit({
      baseLog,
      startedAt,
      outcome: "session_missing",
      errorCode: "job_not_in_session",
      reason: "job not found in session window",
      runId,
      jobShortId,
      action,
      responseMessage: "Session missing",
      callbackId: callback.id,
      callbackText: "Job non riconosciuto",
      env,
      ctx,
      responseStatus: 200,
      telegramUpdateType,
      kvKey: sessionKey,
    });
  }

  const userId = callback.from?.id ?? "unknown";
  const messageId = callback.message?.message_id ?? null;
  const key = legacy ? `feedback:${runId}:${userId}` : `feedback:${runId}:${userId}:${jobShortId}`;
  const value = buildFeedbackValue({
    runId,
    action,
    jobShortId,
    jobHash,
    messageId,
    userId,
    source: jobEntry?.source ?? "unknown",
  });
  const writePromise = env.JOB_SCOUT_KV.put(key, JSON.stringify(value), {
    expirationTtl: 60 * 60 * 24 * 7,
  }).catch((error) => {
    logError("kv_write_failed", {
      ...baseLog,
      kv_key: key,
      error: serializeError(error),
    });
  });
  const ackPromise = answerCallback(env, callback.id, "✅ Feedback salvato").catch((error) => {
    logError("telegram_callback_failed", {
      ...baseLog,
      error: serializeError(error),
    });
  });
  if (ctx) {
    ctx.waitUntil(writePromise);
    ctx.waitUntil(ackPromise);
  } else {
    await writePromise;
    await ackPromise;
  }

  logFeedbackEvent({
    ...baseLog,
    run_id: runId,
    job_short_id: jobShortId,
    action,
    outcome: "ok",
    error_code: null,
    reason: "feedback_recorded",
    duration_ms: Date.now() - startedAt,
    telegram_update_type: telegramUpdateType,
    kv_key: key,
  });

  return {
    response: textResponse("OK", 200, baseLog.request_id),
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
  const callbackDataLike = buildCallbackData(sessionId, jobId, "like", jobHash);
  const callbackDataDislike = buildCallbackData(sessionId, jobId, "dislike", jobHash);
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
  await env.JOB_SCOUT_KV.put(`session:${runId}`, JSON.stringify(windowPayload), {
    expirationTtl: 60 * 60 * 2,
  });
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
  if (parts.length === 4) {
    const [_, runId, action, jobShortId] = parts;
    if (!runId || !jobShortId || !action || !isValidAction(action)) {
      return null;
    }
    return { runId, jobShortId, action, jobHash: "", legacy: false };
  }
  if (parts.length === 5) {
    const [_, runId, action, jobShortId, jobHash] = parts;
    if (!runId || !jobShortId || !action || !jobHash || !isValidAction(action)) {
      return null;
    }
    return { runId, jobShortId, action, jobHash, legacy: false };
  }
  if (parts.length === 3) {
    const [_, runId, action] = parts;
    if (!runId || !action || !isValidAction(action)) {
      return null;
    }
    return { runId, jobShortId: "legacy", action, jobHash: "", legacy: true };
  }
  return null;
}

export function hasAlreadySentForDate(lastSentDate, targetDateRome) {
  return Boolean(lastSentDate) && String(lastSentDate) === String(targetDateRome);
}

export function buildFeedbackValue({ runId, action, jobShortId, jobHash, messageId, userId, source }) {
  return {
    run_id: runId,
    action,
    job_short_id: jobShortId,
    job_hash: jobHash,
    ts: new Date().toISOString(),
    message_id: messageId,
    user_id: userId,
    source,
  };
}

export function yesterdayRomeDateStringFor(value) {
  return yesterdayRomeDateString(new Date(value));
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
  const payload = new Uint8Array(encoder.encode(timestamp).length + 1 + bodyBuffer.byteLength);
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
  return ["L", "M", "D", "S", "X", "like", "maybe", "dislike", "love", "duplicate"].includes(action);
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

function feedbackExit({
  baseLog,
  startedAt,
  outcome,
  errorCode,
  reason,
  runId,
  jobShortId,
  action,
  responseMessage,
  callbackId,
  callbackText,
  env,
  ctx,
  responseStatus,
  telegramUpdateType,
  kvKey,
  telegramUserId,
}) {
  if (callbackId && callbackText) {
    scheduleAnswer(env, ctx, callbackId, callbackText);
  }
  logFeedbackEvent({
    ...baseLog,
    run_id: runId,
    job_short_id: jobShortId,
    action,
    outcome,
    error_code: errorCode,
    reason,
    duration_ms: Date.now() - startedAt,
    telegram_update_type: telegramUpdateType,
    kv_key: kvKey,
    telegram_user_id: telegramUserId,
  });
  return {
    response: textResponse(responseMessage, responseStatus, baseLog.request_id),
    outcome,
    reason: errorCode,
    telegram_update_type: telegramUpdateType,
    kv_key: kvKey,
  };
}

function resolveFeedbackJob(jobs, { jobShortId, jobHash }) {
  const byShortId = jobs.find((job) => job?.short_id === jobShortId);
  if (byShortId) {
    return byShortId;
  }
  if (jobHash) {
    return jobs.find((job) => job?.job_hash === jobHash) || null;
  }
  return null;
}

function logFeedbackEvent(fields) {
  const payload = {
    event: "feedback_callback",
    request_id: fields.request_id,
    run_id: fields.run_id,
    job_short_id: fields.job_short_id,
    action: fields.action,
    outcome: fields.outcome,
    error_code: fields.error_code,
    reason: fields.reason,
    duration_ms: fields.duration_ms,
    telegram_update_type: fields.telegram_update_type,
    kv_key: fields.kv_key,
    telegram_user_id: fields.telegram_user_id,
  };
  const level = fields.outcome === "ok" ? "info" : fields.outcome === "error" ? "error" : "warn";
  logEvent(level, payload);
}

function logInfo(event, fields = {}) {
  logEvent("info", { event, ...fields });
}

function logWarn(event, fields = {}) {
  logEvent("warn", { event, ...fields });
}

function logError(event, fields = {}) {
  logEvent("error", { event, ...fields });
}

function logEvent(level, fields = {}) {
  const line = JSON.stringify({ level, ...fields });
  if (level === "error") {
    console.error(line);
    return;
  }
  console.log(line);
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

function textResponse(message, status, requestId) {
  return new Response(`${message} (request_id=${requestId})`, {
    status,
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}

function withRequestId(response, requestId) {
  const headers = new Headers(response.headers);
  headers.set("X-Request-Id", requestId);
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

function buildCallbackData(runId, jobShortId, action, jobHash) {
  const hash8 = typeof jobHash === "string" ? jobHash.slice(0, 8) : "";
  const payload = hash8
    ? `fb|${runId}|${action}|${jobShortId}|${hash8}`
    : `fb|${runId}|${action}|${jobShortId}`;
  if (new TextEncoder().encode(payload).length > 64) {
    throw new Error("callback_data exceeds Telegram limit");
  }
  return payload;
}

function buildShortId(jobKey, used) {
  const normalized = String(jobKey || "");
  let counter = 0;
  while (true) {
    const digestBase = `${normalized}:${counter}`;
    const digest = digestBase
      .split("")
      .reduce((acc, char) => ((acc << 5) - acc + char.charCodeAt(0)) | 0, 0)
      .toString(16)
      .replace("-", "")
      .padStart(8, "0")
      .slice(0, 8);
    if (!used.has(digest)) {
      used.add(digest);
      return digest;
    }
    counter += 1;
  }
}

async function buildJobHash(jobKey, digestHash) {
  const payload = `${jobKey}:${digestHash}`;
  const digest = await sha256Hex(payload);
  return digest.slice(0, 8);
}

async function sha256Hex(payload) {
  const buffer = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(payload));
  return [...new Uint8Array(buffer)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function serializeError(error) {
  if (error instanceof Error) {
    return { message: error.message, stack: error.stack };
  }
  return { message: String(error) };
}
