import logging
import json
import os
from typing import Dict, List, Optional
from datetime import datetime, timezone
from .carbon import get_carbon_client
from .latency import latency_prober

logger = logging.getLogger(__name__)

class Router:
    def __init__(self):
        self.cdn_pops = {
            "us-east": "https://cdn-us-east.example.com",
            "eu-west": "https://cdn-eu-west.example.com",
            "ap-southeast": "https://cdn-ap-southeast.example.com"
        }
        # Set up logging directory
        self.log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
        os.makedirs(self.log_dir, exist_ok=True)
        # Add weights, configurable via env vars
        self.alpha = float(os.getenv("ROUTING_ALPHA", "0.5"))
        self.beta = float(os.getenv("ROUTING_BETA", "0.5"))
        logger.info(f"Initialized Router with alpha={self.alpha}, beta={self.beta}")

    def _log_routing_decision(self, decision: Dict, log_suffix: str = None):
        date_str = datetime.now(timezone.utc).strftime('%Y%m%d')
        if log_suffix:
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

    async def get_best_pop(self, policy="weighted"):
        """
        Get the best CDN POP.
        policy: "weighted" (use alpha/beta), "carbon" (lowest carbon), or "latency" (lowest latency)
        """
        carbon_client = get_carbon_client()
        carbon_intensities = await carbon_client.get_all_intensities()
        latencies = await latency_prober.probe_all_pops()
        acceptable_pops = await latency_prober.get_acceptable_pops()

        if not acceptable_pops:
            logger.warning("No POPs meet latency SLO, defaulting to eu-west")
            return "eu-west", carbon_intensities, latencies, "fallback"

        if policy == "latency":
            best_pop = min(acceptable_pops, key=lambda pop: latencies[pop])
            return best_pop, carbon_intensities, latencies, "latency"
        elif policy == "carbon":
            best_pop = min(acceptable_pops, key=lambda pop: carbon_intensities[pop])
            return best_pop, carbon_intensities, latencies, "carbon"
        else:
            cvals = [carbon_intensities[pop] for pop in acceptable_pops]
            lvals = [latencies[pop] for pop in acceptable_pops]
            min_c, max_c = min(cvals), max(cvals)
            min_l, max_l = min(lvals), max(lvals)
            norm_carbon = {pop: (carbon_intensities[pop] - min_c) / (max_c - min_c) if max_c > min_c else 0.0 for pop in acceptable_pops}
            norm_latency = {pop: (latencies[pop] - min_l) / (max_l - min_l) if max_l > min_l else 0.0 for pop in acceptable_pops}
            best_pop = min(acceptable_pops, key=lambda pop: self._compute_weighted_score(pop, carbon_intensities, latencies, norm_carbon, norm_latency))
            return best_pop, carbon_intensities, latencies, "weighted"

    async def route_video(self, video_id: str, policy="weighted", log_suffix: str = None):
        """
        Route a video request to the best CDN POP.
        policy: "weighted", "carbon", or "latency"
        log_suffix: optional string to append to log file name
        """
        best_pop, carbon_intensities, latencies, policy_used = await self.get_best_pop(policy=policy)
        baseline_pop = min(latencies.items(), key=lambda x: x[1])[0]
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
                "latency": latencies[best_pop]
            },
            "policy_used": policy_used
        }
        self._log_routing_decision(decision, log_suffix=log_suffix)
        return decision

# Initialize the router
router = Router() 