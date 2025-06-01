import asyncio
import random
import httpx
import json
from datetime import datetime, timedelta, timezone
import os
import sys
from typing import Dict, List, Optional
import logging
import argparse

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml.replay import LogReplayer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TrafficSimulator:
    def __init__(self, base_url: str, num_requests: int = 100, log_suffix: Optional[str] = None):
        self.base_url = base_url
        self.num_requests = num_requests
        self.log_suffix = log_suffix
        self.http_client = httpx.AsyncClient(timeout=10.0)
        
    async def _make_request(self, video_id: str) -> Dict:
        """
        Make a single video request.
        
        Args:
            video_id: The video ID to request
            
        Returns:
            Dict: Request metadata
        """
        try:
            start_time = datetime.now(timezone.utc)
            # Build query string
            query_params = []
            if self.log_suffix:
                query_params.append(f"log_suffix={self.log_suffix}")
            # Always use weighted policy for experiments
            query_params.append("policy=weighted")
            query_str = "&".join(query_params)
            url = f"{self.base_url}/video/{video_id}"
            if query_str:
                url = f"{url}?{query_str}"
            response = await self.http_client.get(url)
            end_time = datetime.now(timezone.utc)
            
            return {
                "video_id": video_id,
                "status_code": response.status_code,
                "latency_ms": (end_time - start_time).total_seconds() * 1000,
                "timestamp": end_time.isoformat()
            }
        except httpx.ConnectError as e:
            logger.error(f"Connection error for video {video_id}: {str(e)}")
            return {
                "video_id": video_id,
                "status_code": 503,
                "error": "Connection failed",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            logger.error(f"Request failed for video {video_id}: {str(e)}")
            return {
                "video_id": video_id,
                "status_code": 500,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
    async def run_simulation(self, batch_size: int = 50, delay_range: tuple = (1, 5)) -> List[Dict]:
        """
        Run the traffic simulation with controlled batching and delays.
        
        Args:
            batch_size: Number of requests to send in each batch
            delay_range: Tuple of (min_delay, max_delay) in seconds between batches
            
        Returns:
            List[Dict]: List of request results
        """
        results = []
        num_batches = (self.num_requests + batch_size - 1) // batch_size
        
        for batch in range(num_batches):
            # Calculate requests for this batch
            start_idx = batch * batch_size
            end_idx = min(start_idx + batch_size, self.num_requests)
            batch_size_actual = end_idx - start_idx
            
            # Generate video IDs for this batch
            video_ids = [f"video_{i:04d}" for i in range(start_idx, end_idx)]
            
            # Make requests concurrently
            tasks = [self._make_request(video_id) for video_id in video_ids]
            batch_results = await asyncio.gather(*tasks)
            results.extend(batch_results)
            
            logger.info(f"Completed batch {batch + 1}/{num_batches} ({batch_size_actual} requests)")
            
            # Add delay between batches if not the last batch
            if batch < num_batches - 1:
                delay = random.uniform(*delay_range)
                logger.info(f"Waiting {delay:.1f}s before next batch...")
                await asyncio.sleep(delay)
        
        return results

    async def generate_test_data(self, duration_minutes: int = 10, requests_per_minute: int = 10) -> None:
        """
        Generate test data over a specified duration with controlled request rate.
        
        Args:
            duration_minutes: Duration in minutes to run the simulation
            requests_per_minute: Target number of requests per minute
        """
        end_time = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
        request_count = 0
        successful_requests = 0
        
        while datetime.now(timezone.utc) < end_time and request_count < self.num_requests:
            # Calculate delay to maintain request rate
            target_interval = 60.0 / requests_per_minute
            jitter = random.uniform(-0.1, 0.1) * target_interval
            delay = max(0.1, target_interval + jitter)
            
            # Generate a random video ID
            video_id = f"video_{random.randint(0, 9999):04d}"
            
            # Make request
            result = await self._make_request(video_id)
            request_count += 1
            
            if result["status_code"] == 200:
                successful_requests += 1
                logger.info(f"Successfully processed video {video_id}")
            else:
                logger.warning(f"Failed to process video {video_id}: {result.get('error', 'Unknown error')}")
            
            # Wait before next request
            await asyncio.sleep(delay)
            
        logger.info(f"Generated {request_count} test requests ({successful_requests} successful) over {duration_minutes} minutes")
        
    async def close(self):
        """Clean up resources."""
        await self.http_client.aclose()

def analyze_simulation_results(results: List[Dict], log_dir: str, log_suffix: Optional[str] = None):
    """
    Analyze simulation results and compare with baseline.
    
    Args:
        results: List of request results
        log_dir: Directory containing routing logs
        log_suffix: Optional suffix for log file
    """
    # Load routing decisions from logs
    replayer = LogReplayer(log_dir)
    decisions = replayer.load_logs(log_suffix)
    
    if not decisions:
        logger.warning("No routing logs found for analysis")
        return
        
    # Calculate success rate
    success_rate = sum(1 for r in results if r["status_code"] == 200) / len(results)
    
    # Calculate average latency
    latencies = [r["latency_ms"] for r in results if r["status_code"] == 200]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    
    # Calculate carbon savings
    carbon_savings = replayer.calculate_carbon_savings(decisions)
    
    print("\nSimulation Results")
    print("=" * 50)
    print(f"Total requests: {len(results)}")
    print(f"Success rate: {success_rate:.2%}")
    print(f"Average latency: {avg_latency:.2f}ms")
    print(f"Carbon savings vs baseline: {carbon_savings:.2f}%")

async def main():
    parser = argparse.ArgumentParser(description="GreenStream Traffic Simulation")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Simulation command
    sim_parser = subparsers.add_parser("simulate", help="Run a quick simulation")
    sim_parser.add_argument("--base-url", default="http://localhost:8000", help="Base URL of GreenStream API")
    sim_parser.add_argument("--num-requests", type=int, default=100, help="Number of requests to simulate")
    sim_parser.add_argument("--log-dir", default="logs", help="Directory containing routing logs")
    sim_parser.add_argument("--log-suffix", help="Optional suffix for log file (e.g., 'batch1')")
    sim_parser.add_argument("--batch-size", type=int, default=50, help="Number of requests per batch")
    sim_parser.add_argument("--min-delay", type=float, default=1.0, help="Minimum delay between batches (seconds)")
    sim_parser.add_argument("--max-delay", type=float, default=5.0, help="Maximum delay between batches (seconds)")
    
    # Test data generation command
    test_parser = subparsers.add_parser("generate-test-data", help="Generate test data over time")
    test_parser.add_argument("--base-url", default="http://localhost:8000", help="Base URL of GreenStream API")
    test_parser.add_argument("--duration", type=int, default=10, help="Duration in minutes")
    test_parser.add_argument("--num-requests", type=int, default=100, help="Maximum number of requests")
    test_parser.add_argument("--requests-per-minute", type=int, default=10, help="Target requests per minute")
    
    args = parser.parse_args()
    
    if args.command == "simulate":
        simulator = TrafficSimulator(args.base_url, args.num_requests, args.log_suffix)
        try:
            results = await simulator.run_simulation(
                batch_size=args.batch_size,
                delay_range=(args.min_delay, args.max_delay)
            )
            analyze_simulation_results(results, args.log_dir, args.log_suffix)
        finally:
            await simulator.close()
            
    elif args.command == "generate-test-data":
        simulator = TrafficSimulator(args.base_url, args.num_requests)
        try:
            await simulator.generate_test_data(args.duration, args.requests_per_minute)
        finally:
            await simulator.close()
            
    else:
        parser.print_help()

if __name__ == "__main__":
    asyncio.run(main()) 