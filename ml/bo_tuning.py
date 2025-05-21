import json
import numpy as np
import matplotlib.pyplot as plt
from skopt import gp_minimize
from skopt.space import Real
from skopt.plots import plot_convergence
from pathlib import Path
import glob
import nbformat
from nbformat import v4 as nbf

# Define the notebook cells
notebook_cells = [
    nbf.new_markdown_cell("# GreenStream Bayesian Optimization Tuning\nThis notebook loads routing logs, defines the reward function, and performs Bayesian Optimization to tune the routing weights (alpha for carbon, beta for latency)."),
    nbf.new_code_cell("""import json
import numpy as np
import matplotlib.pyplot as plt
from skopt import gp_minimize
from skopt.space import Real
from skopt.plots import plot_convergence
from pathlib import Path
import glob

def load_logs(log_dir='logs', date='20250521'):
    decisions = []
    pattern = f"{log_dir}/routing_{date}.jsonl"
    for log_file in glob.glob(pattern):
        with open(log_file, 'r') as f:
            for line in f:
                try:
                    decision = json.loads(line.strip())
                    decisions.append(decision)
                except json.JSONDecodeError:
                    continue
    print(f"Loaded {len(decisions)} routing decisions")
    return decisions

decisions = load_logs()"""),
    nbf.new_code_cell("""def calculate_reward(decision, alpha=0.5, beta=0.5):
    selected_pop = decision['selected_pop']
    baseline_pop = decision['baseline_pop']
    carbon_intensities = decision['carbon_intensities']
    latencies = decision['latencies']

    carbon_selected = carbon_intensities[selected_pop]
    carbon_baseline = carbon_intensities[baseline_pop]
    latency_selected = latencies[selected_pop]
    latency_baseline = latencies[baseline_pop]

    carbon_savings = (carbon_baseline - carbon_selected) / carbon_baseline * 100 if carbon_baseline else 0
    latency_increase = latency_selected - latency_baseline

    norm_carbon = carbon_savings / 100
    norm_latency = -latency_increase / 100

    reward = alpha * norm_carbon + beta * norm_latency
    return reward

def objective(params):
    alpha = params[0]
    beta = 1 - alpha
    rewards = [calculate_reward(d, alpha, beta) for d in decisions]
    return -np.mean(rewards)"""),
    nbf.new_code_cell("""space = [Real(0.1, 0.9, name='alpha')]
result = gp_minimize(objective, space, n_calls=20, random_state=42)
best_alpha = result.x[0]
best_beta = 1 - best_alpha
best_reward = -result.fun
print(f"Best alpha: {best_alpha:.3f}")
print(f"Best beta: {best_beta:.3f}")
print(f"Best reward: {best_reward:.3f}")"""),
    nbf.new_code_cell("""plot_convergence(result)
plt.title('Optimization Convergence')
plt.show()

alphas = np.linspace(0.1, 0.9, 50)
rewards = [-objective([alpha]) for alpha in alphas]
plt.plot(alphas, rewards)
plt.scatter([best_alpha], [best_reward], color='red', label='Best Point')
plt.xlabel('Alpha (Carbon Weight)')
plt.ylabel('Average Reward')
plt.title('Reward vs Alpha')
plt.legend()
plt.grid(True)
plt.show()"""),
    nbf.new_code_cell("""def analyze_weights(alpha, beta):
    rewards = [calculate_reward(d, alpha, beta) for d in decisions]
    carbon_savings = []
    latency_increases = []
    for d in decisions:
        selected_pop = d['selected_pop']
        baseline_pop = d['baseline_pop']
        cs = (d['carbon_intensities'][baseline_pop] - d['carbon_intensities'][selected_pop]) / d['carbon_intensities'][baseline_pop] * 100
        li = d['latencies'][selected_pop] - d['latencies'][baseline_pop]
        carbon_savings.append(cs)
        latency_increases.append(li)
    print(f"Alpha: {alpha:.3f}, Beta: {beta:.3f}")
    print(f"Average Reward: {np.mean(rewards):.3f}")
    print(f"Average Carbon Savings: {np.mean(carbon_savings):.2f}%")
    print(f"Average Latency Increase: {np.mean(latency_increases):.2f}ms")
    print(f"95th Percentile Latency Increase: {np.percentile(latency_increases, 95):.2f}ms")

print("Default weights (alpha=0.5, beta=0.5):")
analyze_weights(0.5, 0.5)
print("\\nOptimized weights:")
analyze_weights(best_alpha, best_beta)""")
]

# Build and write the notebook
notebook = nbf.new_notebook()
notebook.cells = notebook_cells

with open("bo_tuning.ipynb", "w") as f:
    nbformat.write(notebook, f)

print("✅ Notebook 'bo_tuning.ipynb' created successfully.")
