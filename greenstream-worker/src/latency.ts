import type { Env } from "./index";

export interface LatencyRecord {
  ms: number;
  ts: number;
}

export async function probeLatency(pop: string, assetUrl?: string): Promise<number> {
  const t0 = Date.now();
  try {
    // Use a small static asset or /cdn-cgi/trace for minimal payload
    const url = assetUrl || `https://${pop}.example-asset.txt`;
    await fetch(url, { method: "HEAD", cf: { cacheEverything: true }});
    return Date.now() - t0;
  } catch (e) {
    console.error("probeLatency error for pop", pop, e);
    return 1000; // fallback
  }
}

export async function getLatency(pop: string, env: Env, assetUrl?: string): Promise<LatencyRecord> {
  const key = `LAT:${pop}`;
  const cached = await env.ECO_CONFIG.get(key, "json") as LatencyRecord | null;
  if (cached && Date.now() - cached.ts < 55_000) return cached;

  const ms = await probeLatency(pop, assetUrl);
  const rec = { ms, ts: Date.now() };
  await env.ECO_CONFIG.put(key, JSON.stringify(rec), { expirationTtl: 120 });
  return rec;
} 