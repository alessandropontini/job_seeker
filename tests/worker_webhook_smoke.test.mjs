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

function buildEnv({ secret, kv, allowedUserId, telegramToken }) {
  return {
    JOB_SCOUT_WEBHOOK_SECRET: secret,
    TELEGRAM_BOT_TOKEN: telegramToken,
    FEEDBACK_WINDOW_MINUTES: 60,
    JOB_SCOUT_KV: kv,
    ALLOWED_TELEGRAM_USER_ID: allowedUserId,
  };
}

function buildRequest({ secretHeader }) {
  const payload = {
    callback_query: {
      id: "cb1",
      data: "fb|run123|job1|like|hash1",
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
  assert.equal(kv.putCalls.length, 1);
  assert.ok(kv.store.has("feedback:run123:job1:42"));
  assert.ok(findLogEvent(logs, "request_received"));
  assert.ok(findLogEvent(logs, "request_handled"));
  assert.equal(fetchMock.calls.length, 1);
  assert.equal(
    fetchMock.calls[0].url,
    "https://api.telegram.org/bottoken/answerCallbackQuery"
  );
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
  const parsed = parseCallbackData("fb|run123|job1|L|hash1");
  assert.deepEqual(parsed, {
    runId: "run123",
    jobShortId: "job1",
    action: "L",
    jobHash: "hash1",
  });
  assert.equal(parseCallbackData("fb|run123|job1|bad|hash1"), null);
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
