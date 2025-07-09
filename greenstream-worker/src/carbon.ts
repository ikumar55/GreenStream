import type { Env } from "./index";

export interface CarbonRecord {
  gco2: number;
  ts: number;
}

export async function getCarbon(zone: string, env: Env): Promise<CarbonRecord> {
  const key = `CO2:${zone}`;
  const cached = await env.ECO_CONFIG.get(key, "json") as CarbonRecord | null;
  if (cached && Date.now() - cached.ts < 55_000) return cached;  // 55 s safety

  const url = `https://api.electricitymap.org/v3/carbon-intensity/latest?zone=${zone}`;
  try {
    const res = await fetch(url, { headers: { "auth-token": env.EM_API_KEY }});
    if (!res.ok) throw new Error(`EM ${res.status}`);
    const data = await res.json() as any;
    const rec = { gco2: data.carbonIntensity, ts: Date.now() };
    await env.ECO_CONFIG.put(key, JSON.stringify(rec), { expirationTtl: 120 });
    return rec;
  } catch (e) {
    console.error("getCarbon error for zone", zone, e);
    // Fallback: static value
    const rec = { gco2: 500, ts: Date.now() };
    await env.ECO_CONFIG.put(key, JSON.stringify(rec), { expirationTtl: 120 });
    return rec;
  }
} 