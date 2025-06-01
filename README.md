# GreenStream

GreenStream is a smart CDN control plane that routes user traffic across global edge nodes based on real-time carbon intensity and network latency. It dynamically selects the greenest performant path to deliver video and web content—reducing emissions by 8.2% with <30 ms added delay, on average.

What It Does:
- Live routing decisions using per-region carbon intensity and latency
- Bayesian optimization tunes global carbon vs performance tradeoff
- LSTM forecasting predicts traffic and carbon trends to plan routes ahead
- Reinforcement learning agent selects optimal CDN node per request
- Cloudflare Worker integration and DNS-based routing support
- Dashboard + replay tool to visualize carbon savings vs baseline

Tech Stack:
- FastAPI backend for routing engine + decision API
- PyTorch for ML models (LSTM + PPO agent)
- BayesOpt for tuning tradeoff parameters
- ElectricityMap / Octopus API for real-time carbon data
- Cloudflare Workers, mock POPs, simulated traffic logs
- Matplotlib / Plotly Dash for visualization + analysis

Note: Still in progress/optimizing
