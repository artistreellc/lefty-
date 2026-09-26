// SANDBOX ISOLATION LOCK
//
// This sandbox is a copy of Arbo that must never reach anything real: no
// Supabase, no Quo, no Gmail/Calendar/Drive, no Twilio, no ElevenLabs, no
// Anthropic, no Resend, no customer, no phone. Mike, 2026-09-26: "keep it
// isolated."
//
// This file is loaded BEFORE any Arbo code (node --import, and vitest
// setupFiles), so it holds no matter what the copied code does:
//
//   1. Every credential Arbo's src/env.ts reads is set to the EMPTY string.
//      env.ts treats '' as "not configured", and dotenv never overrides a
//      variable that already exists, so a stray .env cannot refill them.
//   2. The data-link switch can never be 'live'. Running the app forces
//      'sim' (Arbo's own in-memory fake data). Under the test runner it is
//      left CUT (unset) — Arbo's own default, which its tests assert on.
//      Every per-link ARBO_LINK_* switch is removed either way.
//   3. Outbound network is refused: fetch, WebSocket, and http/https
//      request/get only reach loopback (localhost, 127.0.0.1, ::1).
//   4. A deploy-carried config (private/deploy.config.json) refuses boot.
//
// Nothing here edits Arbo's own code. Removing this lock is a Mike decision.

import { existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import http from 'node:http';
import https from 'node:https';
import { syncBuiltinESMExports } from 'node:module';

const sandboxRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');

/** Every credential / live-switch key read by Arbo's src/env.ts (at 940caa9). */
export const BLANKED_KEYS = [
  'SUPABASE_URL', 'SUPABASE_ANON_KEY', 'SUPABASE_SERVICE_ROLE_KEY',
  'VAPI_API_KEY',
  'ELEVENLABS_API_KEY', 'ELEVENLABS_BRIDGE_SECRET', 'ELEVENLABS_POSTCALL_SECRET',
  'RESEND_API_KEY', 'RESEND_WEBHOOK_SECRET',
  'RAILWAY_WEBHOOK_KEY',
  'QUO_API_KEY',
  'ARBO_OUTREACH', 'ARBO_OUTREACH_CATCHUP',
  'TWILIO_SMS_WEBHOOK_KEY', 'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_PHONE_NUMBER',
  'ANTHROPIC_API_KEY',
  'APP_ACCESS_KEY',
  'GOOGLE_PROJECT_ID', 'GOOGLE_CLIENT_EMAIL', 'GOOGLE_PRIVATE_KEY', 'GOOGLE_MAPS_API_KEY',
  'ARBOR_DRIVE_ROOT_FOLDER_ID',
  'GMAIL_OAUTH_CLIENT_ID', 'GMAIL_OAUTH_CLIENT_SECRET', 'GMAIL_OAUTH_REFRESH_TOKEN',
  'OWNER_ALERT_PHONE', 'OWNER_HOME_ZIP',
  'RAILWAY_PUBLIC_DOMAIN',
];

const LOOPBACK = new Set(['localhost', '127.0.0.1', '::1', '[::1]']);

export class SandboxNetworkError extends Error {
  constructor(target) {
    super(`SANDBOX ISOLATION: outbound network to "${target}" is blocked. This sandbox never reaches a live service.`);
    this.name = 'SandboxNetworkError';
  }
}

function hostOf(input) {
  try {
    if (typeof input === 'string') return new URL(input).hostname;
    if (input instanceof URL) return input.hostname;
    if (input && typeof input.url === 'string') return new URL(input.url).hostname;
  } catch {
    // unparseable → treat as non-loopback
  }
  return String(input);
}

function isLoopback(host) {
  return LOOPBACK.has(String(host).toLowerCase());
}

// --- 4. Refuse a deploy-carried config --------------------------------------
if (existsSync(resolve(sandboxRoot, 'private', 'deploy.config.json'))) {
  throw new Error('SANDBOX ISOLATION: private/deploy.config.json exists. The sandbox refuses to boot with deploy-carried credentials.');
}

// --- 1 + 2. Blank credentials, force SIM ------------------------------------
for (const key of BLANKED_KEYS) process.env[key] = '';
for (const key of Object.keys(process.env)) {
  if (key.startsWith('ARBO_LINK_')) delete process.env[key];
}
if (process.env.VITEST) delete process.env.ARBO_DATA_LINKS;
else process.env.ARBO_DATA_LINKS = 'sim';
process.env.ARBO_SANDBOX = 'isolated';

// --- 3. Block outbound network ----------------------------------------------
const realFetch = globalThis.fetch;
globalThis.fetch = function sandboxFetch(input, init) {
  const host = hostOf(input);
  if (!isLoopback(host)) return Promise.reject(new SandboxNetworkError(host));
  return realFetch(input, init);
};

if (typeof globalThis.WebSocket === 'function') {
  const RealWebSocket = globalThis.WebSocket;
  globalThis.WebSocket = class SandboxWebSocket extends RealWebSocket {
    constructor(url, protocols) {
      const host = hostOf(url);
      if (!isLoopback(host)) throw new SandboxNetworkError(host);
      super(url, protocols);
    }
  };
}

function guardRequest(mod) {
  for (const name of ['request', 'get']) {
    const real = mod[name];
    mod[name] = function sandboxRequest(...args) {
      const [first] = args;
      const host = typeof first === 'string' || first instanceof URL
        ? hostOf(first)
        : (first?.hostname ?? first?.host ?? 'localhost');
      if (!isLoopback(String(host).replace(/:\d+$/, ''))) throw new SandboxNetworkError(host);
      return real.apply(this, args);
    };
  }
}
guardRequest(http);
guardRequest(https);
syncBuiltinESMExports();
