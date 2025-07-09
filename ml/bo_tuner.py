import json
import glob
import os
from typing import Dict, List, Tuple
import numpy as np
from datetime import datetime, timedelta
import logging
from ml.replay import LogReplayer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WeightTuner:
    def __init__(self, log_dir: str):
        self.log_dir = log_dir
        self.replayer = LogReplayer(log_dir)
        
    def _evaluate_weights(self, alpha: float, beta: float, decisions: List[Dict]) -> float:
        """
        Evaluate a set of weights on historical decisions.
        
        Args:
            alpha: Weight for latency
            beta: Weight for carbon
            decisions: List of routing decisions
            
        Returns:
            float: Average reward
        """
        rewards = [self.replayer.calculate_reward(d, alpha, beta) for d in decisions]
        return np.mean(rewards)
        
    def _grid_search(self, decisions: List[Dict], num_points: int = 10) -> Tuple[float, float]:
        """
        Perform grid search to find optimal weights.
        
        Args:
            decisions: List of routing decisions
            num_points: Number of points to try in each dimension
            
        Returns:
            Tuple[float, float]: Optimal alpha and beta
        """
        best_reward = float('-inf')
        best_weights = (0.5, 0.5)
        
        # Generate grid points
        alphas = np.linspace(0.1, 0.9, num_points)
        betas = np.linspace(0.1, 0.9, num_points)
        
        for alpha in alphas:
            for beta in betas:
                if abs(alpha + beta - 1.0) > 0.01:  # Ensure weights sum to ~1
                    continue
                    
                reward = self._evaluate_weights(alpha, beta, decisions)
                if reward > best_reward:
                    best_reward = reward
                    best_weights = (alpha, beta)
                    
        return best_weights
        
    def tune_weights(self, date: str = None) -> Dict:
        """
        Tune alpha and beta weights using historical data.
        
        Args:
            date: Optional date string in YYYYMMDD format
            
        Returns:
            Dict: Tuning results
        """
        decisions = self.replayer.load_logs(date)
        if not decisions:
            return {
                "error": "No logs found for the specified date"
            }
            
        # Find optimal weights
        alpha, beta = self._grid_search(decisions)
        
        # Calculate metrics with optimal weights
        carbon_savings = self.replayer.calculate_carbon_savings(decisions)
        avg_reward = self._evaluate_weights(alpha, beta, decisions)
        
        return {
            "date": date or "all",
            "num_decisions": len(decisions),
            "optimal_alpha": alpha,
            "optimal_beta": beta,
            "carbon_savings_percent": carbon_savings,
            "average_reward": avg_reward
        }

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Tune GreenStream routing weights")
    parser.add_argument("--log-dir", default="data/logs", help="Directory containing routing logs")
    parser.add_argument("--date", help="Date to analyze (YYYYMMDD format)")
    parser.add_argument("--output", default="ml/optimized_weights.json", help="Where to write optimal weights")
    args = parser.parse_args()
    
    tuner = WeightTuner(args.log_dir)
    results = tuner.tune_weights(args.date)
    
    print("\nGreenStream Weight Tuning Results")
    print("=" * 50)
    print(f"Date: {results['date']}")
    print(f"Number of decisions: {results['num_decisions']}")
    print(f"Optimal alpha (latency weight): {results['optimal_alpha']:.3f}")
    print(f"Optimal beta (carbon weight): {results['optimal_beta']:.3f}")
    print(f"Carbon savings: {results['carbon_savings_percent']:.2f}%")
    print(f"Average reward: {results['average_reward']:.4f}")

    # Write optimal weights to file for router to use
    if "optimal_alpha" in results and "optimal_beta" in results:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w") as f:
            json.dump({"alpha": results["optimal_alpha"], "beta": results["optimal_beta"]}, f)
        print(f"\nOptimal weights written to {args.output}")

if __name__ == "__main__":
    main() 