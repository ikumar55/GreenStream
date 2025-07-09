/// <reference types="@cloudflare/workers-types" />
/**
 * Welcome to Cloudflare Workers! This is your first worker.
 *
 * - Run `npm run dev` in your terminal to start a development server
 * - Open a browser tab at http://localhost:8787/ to see your worker in action
 * - Run `npm run deploy` to publish your worker
 *
 * Bind resources to your worker in `wrangler.jsonc`. After adding bindings, a type definition for the
 * `Env` object can be regenerated with `npm run cf-typegen`.
 *
 * Learn more at https://developers.cloudflare.com/workers/
 */

// Cloudflare Worker: GreenStream Edge Router
// - Reads alpha/beta weights from KV
// - Uses mock carbon/latency data for 3 POPs
// - Selects best POP using weighted score
// - Responds with selected POP and metadata

import { getCarbon } from "./carbon";
import { getLatency } from "./latency";

export interface Env {
	ECO_CONFIG: KVNamespace;
	EM_API_KEY: string;
}

const POPS = ["us-east", "eu-west", "ap-southeast"];
const POP_TO_ZONE: Record<string, string> = {
	"us-east": "US-NY-NYIS"
	// Only us-east is supported for live carbon; others will fallback
};

function popZone(pop: string): string {
	return POP_TO_ZONE[pop] || "FALLBACK";
}

function selectPOP(
	metrics: { pop: string; latency: number; carbon: number }[],
	alpha: number,
	beta: number
): { pop: string; score: number } {
	// Normalize
	const minC = Math.min(...metrics.map(m => m.carbon));
	const maxC = Math.max(...metrics.map(m => m.carbon));
	const minL = Math.min(...metrics.map(m => m.latency));
	const maxL = Math.max(...metrics.map(m => m.latency));
	const norm = (val: number, min: number, max: number) => max > min ? (val - min) / (max - min) : 0;
	const scored = metrics.map(m => ({
		...m,
		score: alpha * norm(m.carbon, minC, maxC) + beta * norm(m.latency, minL, maxL)
	}));
	scored.sort((a, b) => a.score - b.score);
	return { pop: scored[0].pop, score: scored[0].score };
}

const POP_TO_ASSET: Record<string, string> = {
	"us-east": "https://www.google.com/robots.txt",
	"eu-west": "https://www.google.com/robots.txt",
	"ap-southeast": "https://www.google.com/robots.txt"
};

export default {
	async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
		// Read alpha/beta from KV (default to 0.5/0.5 if not set)
		const weights = JSON.parse(await env.ECO_CONFIG.get("weights") || '{"alpha":0.5,"beta":0.5}');
		const alpha = weights.alpha;
		const beta = weights.beta;

		// Gather metrics for each POP
		const metrics = await Promise.all(
			POPS.map(async pop => {
				// Use real latency probe to Google robots.txt for all POPs
				const latencyRec = await getLatency(pop, env, POP_TO_ASSET[pop]);
				// Only fetch live carbon for us-east, fallback for others
				let carbonRec;
				if (pop === "us-east") {
					carbonRec = await getCarbon("US-NY-NYIS", env);
				} else {
					carbonRec = { gco2: 500, ts: Date.now() };
				}
				return {
					pop,
					latency: latencyRec.ms,
					carbon: carbonRec.gco2
				};
			})
		);

		// Compute best POP
		const best = selectPOP(metrics, alpha, beta);

		// Build response (for now, JSON; can add redirect/logging later)
		return new Response(JSON.stringify({
			selected_pop: best.pop,
			metrics,
			alpha,
			beta,
			timestamp: new Date().toISOString()
		}, null, 2), {
			headers: { "content-type": "application/json" }
		});
	}
};
