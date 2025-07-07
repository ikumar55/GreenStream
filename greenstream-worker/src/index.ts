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

interface Env {
	ECO_CONFIG: KVNamespace;
}

const POPS = ["us-east", "eu-west", "ap-southeast"];
const LATENCY_SLO = 80; // ms

// Mock data for demo (replace with real fetches later)
const mockCarbon: Record<string, number> = {
	"us-east": 243,
	"eu-west": 300,
	"ap-southeast": 450,
};
const mockLatency: Record<string, number> = {
	"us-east": 83.7,
	"eu-west": 98.8,
	"ap-southeast": 63.9,
};

function selectPOP(
	pops: string[],
	carbon: Record<string, number>,
	latency: Record<string, number>,
	alpha: number,
	beta: number,
	maxLatency: number
): { pop: string; reason: string } {
	// Filter by latency SLO
	const acceptable = pops.filter((pop) => latency[pop] <= maxLatency);
	if (acceptable.length === 0) return { pop: "eu-west", reason: "fallback" };

	// Normalize
	const minC = Math.min(...acceptable.map((p) => carbon[p]));
	const maxC = Math.max(...acceptable.map((p) => carbon[p]));
	const minL = Math.min(...acceptable.map((p) => latency[p]));
	const maxL = Math.max(...acceptable.map((p) => latency[p]));
	const normC = (pop: string) => (maxC > minC ? (carbon[pop] - minC) / (maxC - minC) : 0);
	const normL = (pop: string) => (maxL > minL ? (latency[pop] - minL) / (maxL - minL) : 0);

	let best = acceptable[0];
	let bestScore = alpha * normC(best) + beta * normL(best);
	for (const pop of acceptable) {
		const score = alpha * normC(pop) + beta * normL(pop);
		if (score < bestScore) {
			best = pop;
			bestScore = score;
		}
	}
	return { pop: best, reason: "weighted" };
}

export default {
	async fetch(request: Request, env: Env): Promise<Response> {
		// Read alpha/beta from KV (default to 0.9/0.1 if not set)
		const alphaStr = await env.ECO_CONFIG.get("alpha");
		const betaStr = await env.ECO_CONFIG.get("beta");
		const alpha = alphaStr ? parseFloat(alphaStr) : 0.9;
		const beta = betaStr ? parseFloat(betaStr) : 0.1;

		// Use mock data for now
		const result = selectPOP(POPS, mockCarbon, mockLatency, alpha, beta, LATENCY_SLO);

		const response = {
			selected_pop: result.pop,
			reason: result.reason,
			alpha,
			beta,
			carbon: mockCarbon,
			latency: mockLatency,
			timestamp: new Date().toISOString(),
		};
		return new Response(JSON.stringify(response, null, 2), {
			headers: { "content-type": "application/json" },
		});
	},
};
