import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { createContext, SourceTextModule } from "node:vm";

const workerPath = path.resolve("cloudflare/worker/worker.js");

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

async function loadWorker() {
  const source = await readFile(workerPath, "utf8");
  const context = createContext({
    TextDecoder,
    TextEncoder,
    URL,
    Request,
    Response,
    crypto,
    fetch,
  });
  const module = new SourceTextModule(source, {
    context,
    identifier: workerPath,
  });
  await module.link(() => {
    throw new Error("Unexpected import in worker module");
  });
  await module.evaluate();
  return module.namespace.default;
}

function buildEnv({ secret, kv }) {
  return {
    JOB_SCOUT_WEBHOOK_SECRET: secret,
    TELEGRAM_BOT_TOKEN: undefined,
    FEEDBACK_WINDOW_MINUTES: 60,
    JOB_SCOUT_KV: kv,
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

test("telegram webhook rejects missing secret header", async () => {
  const worker = await loadWorker();
  const kv = new MockKV(seedSession(Date.now()));
  const env = buildEnv({ secret: "topsecret", kv });
  const response = await worker.fetch(buildRequest({ secretHeader: null }), env);
  assert.equal(response.status, 403);
  assert.equal(kv.putCalls.length, 0);
});

test("telegram webhook rejects wrong secret header", async () => {
  const worker = await loadWorker();
  const kv = new MockKV(seedSession(Date.now()));
  const env = buildEnv({ secret: "topsecret", kv });
  const response = await worker.fetch(buildRequest({ secretHeader: "wrong" }), env);
  assert.equal(response.status, 403);
  assert.equal(kv.putCalls.length, 0);
});

test("telegram webhook accepts correct secret header and writes KV", async () => {
  const worker = await loadWorker();
  const kv = new MockKV(seedSession(Date.now()));
  const env = buildEnv({ secret: "topsecret", kv });
  const response = await worker.fetch(
    buildRequest({ secretHeader: "topsecret" }),
    env
  );
  assert.equal(response.status, 200);
  assert.equal(kv.putCalls.length, 1);
  assert.ok(kv.store.has("feedback:run123:job1:42"));
});
