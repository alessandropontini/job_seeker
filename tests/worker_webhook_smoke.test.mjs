import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import vm from "node:vm";

const workerPath = path.resolve("cloudflare/worker/worker.js");
const { createContext, SourceTextModule } = vm;
const supportsVmModules = typeof SourceTextModule === "function";
const maybeTest = supportsVmModules ? test : test.skip;

class MockKV {
  constructor(seed = {}) {
    this.store = new Map(Object.entries(seed));
    this.putCalls = [];
  }

  async get(key, type) {
    const value = this.store.get(key);
    if (value === undefined) {
      return null;
    }
    if (type === "json") {
      return JSON.parse(value);
    }
    return value;
  }

  async put(key, value) {
    this.store.set(key, value);
    this.putCalls.push({ key, value });
  }

  async list() {
    return { keys: [] };
  }
}

async function loadWorkerModule({ consoleOverride, fetchOverride } = {}) {
  if (!supportsVmModules) {
    throw new Error("SourceTextModule not available in this Node runtime");
  }
  const source = await readFile(workerPath, "utf8");
  const context = createContext({
    TextDecoder,
    TextEncoder,
    URL,
    Request,
    Response,
    crypto,
    fetch: fetchOverride ?? fetch,
    console: consoleOverride ?? console,
  });
  const module = new SourceTextModule(source, {
    context,
    identifier: workerPath,
  });
  await module.link(() => {
    throw new Error("Unexpected import in worker module");
  });
  await module.evaluate();
  return module.namespace;
}

function buildEnv({
  secret,
  kv,
  allowedUserId,
  telegramToken,
  smokeToken,
}) {
  return {
    JOB_SCOUT_WEBHOOK_SECRET: secret,
    TELEGRAM_BOT_TOKEN: telegramToken,
    FEEDBACK_WINDOW_MINUTES: 60,
    JOB_SCOUT_KV: kv,
    ALLOWED_TELEGRAM_USER_ID: allowedUserId,
    JOB_SCOUT_SMOKE_TOKEN: smokeToken,
  };
}

function buildRequest({ secretHeader, data } = {}) {
  const payload = {
    callback_query: {
      id: "cb1",
      data: data ?? "fb|run123|like|job1",
      from: { id: 42 },
      message: { message_id: 11 },
    },
  };
  const headers = new Headers({ "Content-Type": "application/json" });
  if (secretHeader) {
    headers.set("X-Telegram-Bot-Api-Secret-Token", secretHeader);
  }
  return new Request("https://example.com/telegram/feedback", {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
}

function seedSession(nowMs) {
  return {
    [`session:run123`]: JSON.stringify({
      run_id: "run123",
      open_at: new Date(nowMs - 1000).toISOString(),
      close_at: new Date(nowMs + 1000).toISOString(),
      jobs: [{ short_id: "job1", job_hash: "hash1", source: "dummy" }],
    }),
  };
}

maybeTest("telegram webhook rejects missing secret header", async () => {
  const { consoleMock, logs } = createConsoleMock();
  const module = await loadWorkerModule({ consoleOverride: consoleMock });
  const worker = module.default;
  const kv = new MockKV(seedSession(Date.now()));
  const env = buildEnv({ secret: "topsecret", kv });
  const response = await worker.fetch(buildRequest({ secretHeader: null }), env);
  assert.equal(response.status, 401);
  assert.equal(kv.putCalls.length, 0);
  assert.ok(findLogEvent(logs, "auth_fail"));
});

maybeTest("telegram webhook rejects wrong secret header", async () => {
  const { consoleMock, logs } = createConsoleMock();
  const module = await loadWorkerModule({ consoleOverride: consoleMock });
  const worker = module.default;
  const kv = new MockKV(seedSession(Date.now()));
  const env = buildEnv({ secret: "topsecret", kv });
  const response = await worker.fetch(buildRequest({ secretHeader: "wrong" }), env);
  assert.equal(response.status, 401);
  assert.equal(kv.putCalls.length, 0);
  assert.ok(findLogEvent(logs, "auth_fail"));
});

maybeTest("telegram webhook accepts correct secret header and writes KV", async () => {
  const { consoleMock, logs } = createConsoleMock();
  const fetchMock = createFetchMock();
  const module = await loadWorkerModule({
    consoleOverride: consoleMock,
    fetchOverride: fetchMock.fetch,
  });
  const worker = module.default;
  const kv = new MockKV(seedSession(Date.now()));
  const env = buildEnv({
    secret: "topsecret",
    kv,
    telegramToken: "token",
  });
  const response = await worker.fetch(
    buildRequest({ secretHeader: "topsecret" }),
    env
  );
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.deepEqual(body, { ok: true });
  assert.equal(kv.putCalls.length, 1);
  assert.ok(kv.store.has("feedback:run123:42:job1"));
  assert.ok(findLogEvent(logs, "request_received"));
  assert.ok(findLogEvent(logs, "request_handled"));
  assert.equal(fetchMock.calls.length, 1);
  assert.equal(
    fetchMock.calls[0].url,
    "https://api.telegram.org/bottoken/answerCallbackQuery"
  );
});

maybeTest("telegram webhook returns invalid callback data on malformed data", async () => {
  const { consoleMock, logs } = createConsoleMock();
  const module = await loadWorkerModule({ consoleOverride: consoleMock });
  const worker = module.default;
  const kv = new MockKV(seedSession(Date.now()));
  const env = buildEnv({ secret: "topsecret", kv });
  const response = await worker.fetch(
    buildRequest({ secretHeader: "topsecret", data: "LIKE_TEST" }),
    env
  );
  assert.equal(response.status, 200);
  const body = await response.text();
  assert.equal(body, "Invalid callback data");
  assert.equal(kv.putCalls.length, 0);
  assert.ok(findLogEvent(logs, "telegram_webhook_rejected"));
});

maybeTest("telegram webhook blocks non-allowed user feedback", async () => {
  const { consoleMock, logs } = createConsoleMock();
  const module = await loadWorkerModule({ consoleOverride: consoleMock });
  const worker = module.default;
  const kv = new MockKV(seedSession(Date.now()));
  const env = buildEnv({
    secret: "topsecret",
    kv,
    allowedUserId: "99",
  });
  const response = await worker.fetch(
    buildRequest({ secretHeader: "topsecret" }),
    env
  );
  assert.equal(response.status, 200);
  assert.equal(kv.putCalls.length, 0);
  assert.ok(findLogEvent(logs, "unauthorized_user"));
});

maybeTest("telegram webhook GET probe returns ok", async () => {
  const { consoleMock, logs } = createConsoleMock();
  const module = await loadWorkerModule({ consoleOverride: consoleMock });
  const worker = module.default;
  const kv = new MockKV();
  const env = buildEnv({ secret: "topsecret", kv });
  const response = await worker.fetch(
    new Request("https://example.com/telegram/feedback", { method: "GET" }),
    env
  );
  assert.equal(response.status, 200);
  assert.ok(findLogEvent(logs, "telegram_webhook_probe"));
});

maybeTest("parseCallbackData accepts the expected feedback payload format", async () => {
  const module = await loadWorkerModule();
  const { parseCallbackData } = module;
  const parsed = parseCallbackData("fb|run123|L|job1");
  assert.deepEqual(parsed, {
    runId: "run123",
    jobShortId: "job1",
    action: "L",
    jobHash: "",
  });
  assert.equal(parseCallbackData("fb|run123|job1|bad|hash1"), null);
});

maybeTest("internal smoke session returns callback data for valid token", async () => {
  const module = await loadWorkerModule();
  const worker = module.default;
  const kv = new MockKV();
  const env = buildEnv({ secret: "topsecret", kv, smokeToken: "smoke-123" });
  const request = new Request("https://example.com/internal/smoke/session", {
    method: "POST",
    headers: new Headers({ "X-Smoke-Token": "smoke-123" }),
  });
  const response = await worker.fetch(request, env);
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.ok(body.session_id);
  assert.ok(body.callback_data_like);
  assert.equal(body.job_id, "job-001");
  const parsed = module.parseCallbackData(body.callback_data_like);
  assert.ok(parsed);
  assert.equal(parsed.runId, body.session_id);
  assert.equal(parsed.jobShortId, body.job_id);
  const session = await kv.get(`session:${body.session_id}`, "json");
  assert.ok(session);
  assert.equal(session.jobs[0].job_hash, parsed.jobHash);
});

maybeTest("internal smoke session hides when token is missing", async () => {
  const module = await loadWorkerModule();
  const worker = module.default;
  const kv = new MockKV();
  const env = buildEnv({ secret: "topsecret", kv, smokeToken: "smoke-123" });
  const response = await worker.fetch(
    new Request("https://example.com/internal/smoke/session", {
      method: "POST",
    }),
    env
  );
  assert.equal(response.status, 404);
});

maybeTest("internal smoke session hides when token is invalid", async () => {
  const module = await loadWorkerModule();
  const worker = module.default;
  const kv = new MockKV();
  const env = buildEnv({ secret: "topsecret", kv, smokeToken: "smoke-123" });
  const response = await worker.fetch(
    new Request("https://example.com/internal/smoke/session", {
      method: "POST",
      headers: new Headers({ "X-Smoke-Token": "wrong" }),
    }),
    env
  );
  assert.equal(response.status, 404);
});

maybeTest("logs route_not_found for unknown paths", async () => {
  const { consoleMock, logs } = createConsoleMock();
  const module = await loadWorkerModule({ consoleOverride: consoleMock });
  const worker = module.default;
  const kv = new MockKV();
  const env = buildEnv({ secret: "topsecret", kv });
  const response = await worker.fetch(
    new Request("https://example.com/unknown", { method: "GET" }),
    env
  );
  assert.equal(response.status, 404);
  assert.ok(findLogEvent(logs, "route_not_found"));
});



maybeTest("yesterdayRomeDateStringFor handles CET and CEST boundaries", async () => {
  const module = await loadWorkerModule();
  const { yesterdayRomeDateStringFor } = module;
  const cet = yesterdayRomeDateStringFor("2025-01-15T07:00:00.000Z");
  const cest = yesterdayRomeDateStringFor("2025-07-15T06:00:00.000Z");
  assert.equal(cet, "2025-01-14");
  assert.equal(cest, "2025-07-14");
});

maybeTest("hasAlreadySentForDate detects dedupe state", async () => {
  const module = await loadWorkerModule();
  const { hasAlreadySentForDate } = module;
  assert.equal(hasAlreadySentForDate("2025-08-10", "2025-08-10"), true);
  assert.equal(hasAlreadySentForDate("2025-08-09", "2025-08-10"), false);
  assert.equal(hasAlreadySentForDate(null, "2025-08-10"), false);
});

maybeTest("buildFeedbackValue includes run_id in stored payload", async () => {
  const module = await loadWorkerModule();
  const { buildFeedbackValue } = module;
  const value = buildFeedbackValue({
    runId: "run-live-01",
    action: "L",
    jobShortId: "abc123",
    jobHash: "def45678",
    messageId: 99,
    userId: 42,
    source: "remotive",
  });
  assert.equal(value.run_id, "run-live-01");
  assert.equal(value.action, "L");
  assert.equal(value.source, "remotive");
});
function createFetchMock() {
  const calls = [];
  const fetchMock = async (url, options = {}) => {
    calls.push({ url, options });
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  return { fetch: fetchMock, calls };
}

function createConsoleMock() {
  const logs = [];
  return {
    logs,
    consoleMock: {
      log: (line) => logs.push(line),
      error: (line) => logs.push(line),
      warn: (line) => logs.push(line),
    },
  };
}

function findLogEvent(logs, eventName) {
  return logs.some((line) => {
    try {
      const parsed = JSON.parse(line);
      return parsed.event === eventName;
    } catch {
      return false;
    }
  });
}


maybeTest("feedback endpoint returns all events for same run", async () => {
  const module = await loadWorkerModule();
  const worker = module.default;
  const kv = new MockKV({
    "feedback:run123:42:job1": JSON.stringify({ run_id: "run123", job_short_id: "job1", action: "L" }),
    "feedback:run123:42:job2": JSON.stringify({ run_id: "run123", job_short_id: "job2", action: "D" }),
  });
  kv.list = async ({ prefix }) => ({
    keys: [...kv.store.keys()].filter((name) => name.startsWith(prefix)).map((name) => ({ name })),
  });
  const env = buildEnv({ secret: "topsecret", kv });
  const body = JSON.stringify({ run_id: "run123" });
  const ts = String(Math.floor(Date.now() / 1000));
  const requestId = "req-test-1";
  const sig = await signForTest("topsecret", ts, body);
  const response = await worker.fetch(
    new Request("https://example.com/feedback", {
      method: "POST",
      headers: new Headers({
        "Content-Type": "application/json",
        "X-Webhook-Timestamp": ts,
        "X-Webhook-Id": requestId,
        "X-Webhook-Signature": sig,
      }),
      body,
    }),
    env
  );
  assert.equal(response.status, 200);
  const payload = await response.json();
  assert.equal(payload.length, 2);
});


async function signForTest(secret, timestamp, body) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const payload = new TextEncoder().encode(`${timestamp}.${body}`);
  const signature = await crypto.subtle.sign("HMAC", key, payload);
  return [...new Uint8Array(signature)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
