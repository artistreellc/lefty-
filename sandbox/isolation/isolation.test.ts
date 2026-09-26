// Proves the sandbox isolation lock holds. If any of these fail, the sandbox
// is NOT isolated — stop and bring it to Mike.
import { describe, expect, it } from 'vitest';
import http from 'node:http';
import https from 'node:https';
import { BLANKED_KEYS, SandboxNetworkError } from './lock.mjs';

describe('sandbox isolation lock', () => {
  it('data links are never live (cut under tests, sim when running) and every per-link switch is gone', () => {
    expect(process.env.ARBO_DATA_LINKS).toBeUndefined();
    expect(process.env.ARBO_SANDBOX).toBe('isolated');
    expect(Object.keys(process.env).filter((k) => k.startsWith('ARBO_LINK_'))).toEqual([]);
  });

  it('blanks every credential Arbo reads', () => {
    for (const key of BLANKED_KEYS) expect(process.env[key], key).toBe('');
  });

  it("Arbo's own env reports every integration unconfigured", async () => {
    const { integrationStatus } = await import('../src/env.js');
    expect(Object.values(integrationStatus()).every((v) => v === false)).toBe(true);
  });

  it("Arbo's DB door stays shut", async () => {
    const { hasDb, getDb, dataLinksLive } = await import('../src/db/client.js');
    expect(dataLinksLive()).toBe(false);
    expect(hasDb()).toBe(false);
    expect(() => getDb()).toThrow();
  });

  it('refuses outbound fetch to any live host', async () => {
    for (const url of [
      'https://wdpyysgxmwvvoyveihum.supabase.co/rest/v1/',
      'https://api.openphone.com/v1/calls',
      'https://gmail.googleapis.com/',
      'https://api.anthropic.com/v1/messages',
      'https://api.elevenlabs.io/',
      'https://api.x.ai/v1/chat/completions',
    ]) {
      await expect(fetch(url)).rejects.toBeInstanceOf(SandboxNetworkError);
    }
  });

  it('refuses outbound http/https requests and WebSockets', () => {
    expect(() => https.request('https://api.twilio.com/')).toThrow(SandboxNetworkError);
    expect(() => http.get({ hostname: 'example.com', path: '/' })).toThrow(SandboxNetworkError);
    expect(() => new globalThis.WebSocket('wss://wdpyysgxmwvvoyveihum.supabase.co/realtime/v1')).toThrow(SandboxNetworkError);
  });

  it('still allows loopback, so the sandbox app can be driven locally', async () => {
    const server = http.createServer((_req, res) => res.end('ok'));
    await new Promise<void>((r) => server.listen(0, '127.0.0.1', r));
    const { port } = server.address() as { port: number };
    const res = await fetch(`http://127.0.0.1:${port}/`);
    expect(await res.text()).toBe('ok');
    server.close();
  });
});
