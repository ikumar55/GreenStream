import logging
import json
import os
from typing import Dict, List, Optional
from datetime import datetime, timezone
import httpx

logger = logging.getLogger(__name__)

CARBON_API_URL = "http://localhost:8001/carbon"
LATENCY_API_URL = "http://localhost:8002/latency"

class Router:
    def __init__(self):
        self.cdn_pops = {
            "us-east": "https://cdn-us-east.example.com"
        }
        # Set up logging directory
        self.log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
        os.makedirs(self.log_dir, exist_ok=True)
        # Try to load optimized weights from file
        weights_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ml", "optimized_weights.json")
        try:
            with open(weights_path, "r") as f:
                weights = json.load(f)
                self.alpha = float(weights.get("alpha", 0.5))
                self.beta = float(weights.get("beta", 0.5))
                logger.info(f"Loaded optimized weights: alpha={self.alpha}, beta={self.beta}")
        except Exception as e:
            self.alpha = float(os.getenv("ROUTING_ALPHA", "0.5"))
            self.beta = float(os.getenv("ROUTING_BETA", "0.5"))
            logger.info(f"Using default/env weights: alpha={self.alpha}, beta={self.beta} (reason: {e})")
        # Add weights, configurable via env vars
        # self.alpha = float(os.getenv("ROUTING_ALPHA", "0.5"))
        # self.beta = float(os.getenv("ROUTING_BETA", "0.5"))
        logger.info(f"Initialized Router with alpha={self.alpha}, beta={self.beta}")

    def _log_routing_decision(self, decision: Dict, log_suffix: str = ""):
        date_str = datetime.now(timezone.utc).strftime('%Y%m%d')
        if log_suffix is not None and log_suffix != "":
            log_file = os.path.join(self.log_dir, f"routing_{date_str}_{log_suffix}.jsonl")
        else:
            log_file = os.path.join(self.log_dir, f"routing_{date_str}.jsonl")
        try:
            with open(log_file, "a") as f:
                f.write(json.dumps(decision) + "\n")
        except Exception as e:
            logger.error(f"Failed to log routing decision: {str(e)}")

    def _compute_weighted_score(self, pop, carbon_intensities, latencies, norm_carbon, norm_latency):
        return self.alpha * norm_carbon[pop] + self.beta * norm_latency[pop]

    async def fetch_carbon_intensity(self, pop: str) -> float:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(CARBON_API_URL, params={"zone": pop}, timeout=3)
                if resp.status_code == 200:
                    data = resp.json()
                    return float(data.get("carbon_intensity", 500.0))
        except Exception as e:
            logger.warning(f"Failed to fetch carbon for {pop}: {e}")
        return 500.0  # fallback

    async def fetch_latency(self, pop: str) -> float:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(LATENCY_API_URL, params={"pop": pop}, timeout=3)
                if resp.status_code == 200:
                    data = resp.json()
                    return float(data.get("latency_ms", 1000.0))
                else:
                    body = await resp.text()
                    logger.warning(f"Latency API non-200 for {pop}: status={resp.status_code}, body={body}")
        except Exception as e:
            logger.warning(f"Failed to fetch latency for {pop}: {e}")
        return 1000.0  # fallback

    async def get_all_carbon_intensities(self) -> Dict[str, float]:
        results = {}
        for pop in self.cdn_pops.keys():
            results[pop] = await self.fetch_carbon_intensity(pop)
        return results

    async def get_all_latencies(self) -> Dict[str, float]:
        results = {}
        for pop in self.cdn_pops.keys():
            results[pop] = await self.fetch_latency(pop)
        return results

    async def get_best_pop(self, policy="weighted"):
        """
        Get the best CDN POP.
        policy: "weighted" (use alpha/beta), "carbon" (lowest carbon), or "latency" (lowest latency)
        """
        carbon_intensities = await self.get_all_carbon_intensities()
        latencies = await self.get_all_latencies()
        acceptable_pops = [pop for pop in self.cdn_pops.keys() if latencies[pop] < 1000.0]

        fallback_reason = None
        if not acceptable_pops:
            logger.warning("No POPs meet latency SLO, defaulting to eu-west")
            acceptable_pops = ["eu-west"]
            fallback_reason = "no_acceptable_latency"

        if policy == "latency":
            best_pop = min(acceptable_pops, key=lambda pop: latencies[pop])
            policy_used = "latency"
        elif policy == "carbon":
            best_pop = min(acceptable_pops, key=lambda pop: carbon_intensities[pop])
            policy_used = "carbon"
        else:
            cvals = [carbon_intensities[pop] for pop in acceptable_pops]
            lvals = [latencies[pop] for pop in acceptable_pops]
            min_c, max_c = min(cvals), max(cvals)
            min_l, max_l = min(lvals), max(lvals)
            norm_carbon = {pop: (carbon_intensities[pop] - min_c) / (max_c - min_c) if max_c > min_c else 0.0 for pop in acceptable_pops}
            norm_latency = {pop: (latencies[pop] - min_l) / (max_l - min_l) if max_l > min_l else 0.0 for pop in acceptable_pops}
            best_pop = min(acceptable_pops, key=lambda pop: self._compute_weighted_score(pop, carbon_intensities, latencies, norm_carbon, norm_latency))
            policy_used = "weighted"

        return best_pop, carbon_intensities, latencies, policy_used, fallback_reason

    async def route_video(self, video_id: str, policy="weighted", log_suffix: str = None):
        """
        Route a video request to the best CDN POP.
        policy: "weighted", "carbon", or "latency"
        log_suffix: optional string to append to log file name
        """
        best_pop, carbon_intensities, latencies, policy_used, fallback_reason = await self.get_best_pop(policy=policy)
        baseline_pop = min(latencies.items(), key=lambda x: x[1])[0]
        carbon_saved = carbon_intensities[baseline_pop] - carbon_intensities[best_pop]
        timestamp = datetime.now(timezone.utc)
        decision = {
            "video_id": video_id,
            "selected_pop": best_pop,
            "baseline_pop": baseline_pop,
            "timestamp": timestamp.isoformat(),
            "carbon_intensities": carbon_intensities,
            "latencies": latencies,
            "metadata": {
                "carbon_intensity": carbon_intensities[best_pop],
                "latency": latencies[best_pop],
                "alpha": self.alpha,
                "beta": self.beta,
                "fallback_reason": fallback_reason,
                "carbon_saved": carbon_saved
            },
            "policy_used": policy_used
        }
        self._log_routing_decision(decision, log_suffix=log_suffix if log_suffix is not None else "")
        return decision

# Initialize the router
router = Router() 