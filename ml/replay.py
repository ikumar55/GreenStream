import json
import glob
import os
from typing import Dict, List, Tuple, Optional
import numpy as np
from datetime import datetime
import logging
import argparse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LogReplayer:
    def __init__(self, log_dir: str):
        self.log_dir = log_dir
        
    def load_logs(self, date: Optional[str] = None, suffix: Optional[str] = None, combine_all: bool = False) -> List[Dict]:
        """
        Load routing logs for a specific date or all dates.
        
        Args:
            date: Optional date string in YYYYMMDD format
            suffix: Optional suffix to match (e.g., 'batch1', 'morning')
            combine_all: If True, load all logs in the directory
            
        Returns:
            List[Dict]: List of routing decisions
        """
        if combine_all:
            pattern = "routing_*.jsonl"
        elif date and suffix:
            pattern = f"routing_{date}_{suffix}.jsonl"
        elif date:
            pattern = f"routing_{date}*.jsonl"  # Match all suffixes for the date
        else:
            pattern = "routing_*.jsonl"
            
        log_files = glob.glob(os.path.join(self.log_dir, pattern))
        
        if not log_files:
            logger.warning(f"No log files found matching pattern: {pattern}")
            return []
            
        logger.info(f"Found {len(log_files)} log files: {[os.path.basename(f) for f in log_files]}")
        
        decisions = []
        for log_file in log_files:
            try:
            with open(log_file) as f:
                for line in f:
                    decisions.append(json.loads(line))
                logger.info(f"Loaded {len(decisions)} decisions from {os.path.basename(log_file)}")
            except Exception as e:
                logger.error(f"Error loading {log_file}: {str(e)}")
                    
        return decisions
        
    def calculate_carbon_savings(self, decisions: List[Dict]) -> float:
        """
        Calculate percentage of carbon saved vs. latency-only baseline.
        
        Args:
            decisions: List of routing decisions
            
        Returns:
            float: Percentage of carbon saved
        """
        if not decisions:
            return 0.0
            
        total_carbon_green = 0
        total_carbon_baseline = 0
        
        for decision in decisions:
            # Carbon used by GreenStream's choice
            selected_pop = decision["selected_pop"]
            carbon_green = decision["carbon_intensities"][selected_pop]
            
            # Carbon that would have been used by baseline (lowest latency)
            baseline_pop = decision["baseline_pop"]
            carbon_baseline = decision["carbon_intensities"][baseline_pop]
                
            total_carbon_green += carbon_green
            total_carbon_baseline += carbon_baseline
            
        if total_carbon_baseline == 0:
            return 0.0
            
        return (1 - total_carbon_green / total_carbon_baseline) * 100
        
    def calculate_latency_impact(self, decisions: List[Dict]) -> Dict[str, float]:
        """
        Calculate latency impact compared to baseline.
        
        Args:
            decisions: List of routing decisions
            
        Returns:
            Dict[str, float]: Latency statistics
        """
        if not decisions:
            return {
                "mean_increase": 0.0,
                "max_increase": 0.0,
                "p95_increase": 0.0
            }
            
        latency_diffs = []
        for decision in decisions:
            selected_latency = decision["latencies"][decision["selected_pop"]]
            baseline_latency = decision["latencies"][decision["baseline_pop"]]
            latency_diffs.append(selected_latency - baseline_latency)
            
        return {
            "mean_increase": np.mean(latency_diffs),
            "max_increase": np.max(latency_diffs),
            "p95_increase": np.percentile(latency_diffs, 95)
        }
        
    def calculate_reward(self, decision: Dict, alpha: float = 0.5, beta: float = 0.5) -> float:
        """
        Calculate reward for a routing decision.
        
        Args:
            decision: Single routing decision
            alpha: Weight for latency (0-1)
            beta: Weight for carbon (0-1)
            
        Returns:
            float: Reward value
        """
        selected_pop = decision["selected_pop"]
        latency = decision["latencies"][selected_pop]
        carbon = decision["carbon_intensities"][selected_pop]
        
        # Normalize values
        max_latency = max(decision["latencies"].values())
        max_carbon = max(decision["carbon_intensities"].values())
        
        normalized_latency = latency / max_latency if max_latency > 0 else 0
        normalized_carbon = carbon / max_carbon if max_carbon > 0 else 0
        
        return -(alpha * normalized_latency + beta * normalized_carbon)
        
    def analyze_logs(self, date: Optional[str] = None, suffix: Optional[str] = None, combine_all: bool = False) -> Dict:
        """
        Analyze routing logs and return metrics.
        
        Args:
            date: Optional date string in YYYYMMDD format
            suffix: Optional suffix to match (e.g., 'batch1', 'morning')
            combine_all: If True, analyze all logs in the directory
            
        Returns:
            Dict: Analysis results
        """
        decisions = self.load_logs(date, suffix, combine_all)
        if not decisions:
            return {
                "error": "No logs found for the specified criteria"
            }
            
        carbon_savings = self.calculate_carbon_savings(decisions)
        latency_impact = self.calculate_latency_impact(decisions)
        
        # Calculate average reward with default weights
        rewards = [self.calculate_reward(d) for d in decisions]
        avg_reward = np.mean(rewards)
        
        # Calculate POP-level statistics
        pop_stats = {}
        for pop in decisions[0]["latencies"].keys():
            pop_decisions = [d for d in decisions if d["selected_pop"] == pop]
            if pop_decisions:
                pop_stats[pop] = {
                    "count": len(pop_decisions),
                    "percentage": len(pop_decisions) / len(decisions) * 100,
                    "avg_latency": np.mean([d["latencies"][pop] for d in pop_decisions]),
                    "avg_carbon": np.mean([d["carbon_intensities"][pop] for d in pop_decisions])
                }
        
        return {
            "date": date or "all",
            "suffix": suffix or "all",
            "num_decisions": len(decisions),
            "carbon_savings_percent": carbon_savings,
            "latency_impact": latency_impact,
            "average_reward": avg_reward,
            "pop_stats": pop_stats
        }

def print_report(results: Dict):
    """Print a formatted analysis report."""
    print("\nGreenStream Analysis Report")
    print("=" * 50)
    print(f"Date: {results['date']}")
    if results.get('suffix'):
        print(f"Suffix: {results['suffix']}")
    print(f"Number of decisions: {results['num_decisions']}")
    
    print("\nCarbon Impact")
    print("-" * 20)
    print(f"Carbon savings vs baseline: {results['carbon_savings_percent']:.2f}%")
    
    print("\nLatency Impact")
    print("-" * 20)
    latency_impact = results['latency_impact']
    print(f"Mean latency increase: {latency_impact['mean_increase']:.2f}ms")
    print(f"Max latency increase: {latency_impact['max_increase']:.2f}ms")
    print(f"95th percentile increase: {latency_impact['p95_increase']:.2f}ms")
    
    print("\nPOP Statistics")
    print("-" * 20)
    for pop, stats in results['pop_stats'].items():
        print(f"\n{pop}:")
        print(f"  Selected: {stats['count']} times ({stats['percentage']:.1f}%)")
        print(f"  Average latency: {stats['avg_latency']:.2f}ms")
        print(f"  Average carbon: {stats['avg_carbon']:.2f} gCO₂eq/kWh")
    
    print("\nOverall Performance")
    print("-" * 20)
    print(f"Average reward: {results['average_reward']:.4f}")

def main():
    parser = argparse.ArgumentParser(description="Analyze GreenStream routing logs")
    parser.add_argument("--log-dir", default="logs", help="Directory containing routing logs")
    parser.add_argument("--date", help="Date to analyze (YYYYMMDD format)")
    parser.add_argument("--suffix", help="Optional suffix to match (e.g., 'batch1', 'morning')")
    parser.add_argument("--combine-all", action="store_true", help="Analyze all logs in the directory")
    args = parser.parse_args()
    
    replayer = LogReplayer(args.log_dir)
    results = replayer.analyze_logs(args.date, args.suffix, args.combine_all)
    
    if "error" in results:
        print(f"Error: {results['error']}")
        return
        
    print_report(results)

if __name__ == "__main__":
    main() 