# 🛰️ GreenStream - Carbon-Aware Edge CDN

GreenStream is a smart edge CDN routing layer that reduces carbon emissions by dynamically steering video traffic toward regions with lower grid CO₂ intensity, without breaking latency SLAs.

## 🌟 Features

- Real-time carbon intensity data integration via Electricity Maps API
- Dynamic latency probing to CDN POPs
- Smart routing based on carbon intensity and latency constraints
- Latency SLO: ≤ 80ms
- Carbon-aware routing decisions
- Logging and metrics for ML training
- (Future) ML-powered adaptive routing

## 🚀 Getting Started

### Prerequisites

- Python 3.8+
- Docker and Docker Compose
- Electricity Maps API key

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/greenstream.git
cd greenstream
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your Electricity Maps API key
```

5. Start the services:
```bash
docker-compose up -d
```

6. Run the application:
```bash
uvicorn api.main:app --reload
```

## 📁 Project Structure

```
greenstream/
├── api/                    # FastAPI reverse proxy
│   ├── main.py            # /video/{id} route, routing logic
│   ├── carbon.py          # Electricity Maps client + cache
│   ├── latency.py         # Async RTT probes
│   ├── routing.py         # Decision logic (carbon + latency)
│   └── log_utils.py       # Log requests, decisions, and metrics
├── data/                  # Stores logs or cached files
├── tests/                 # Pytest test cases
├── docker-compose.yml     # Redis, Prometheus (optional)
└── README.md
```

## 🧪 Testing

Run the test suite:
```bash
pytest
```

## 📊 Monitoring

- Prometheus metrics available at `/metrics`
- Grafana dashboard (optional)

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.