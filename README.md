# SWARM-DMAS-wrench

**SWARM-DMAS-wrench** is a simulation framework built on top of WRENCH for evaluating decentralized meta-scheduling algorithms in distributed computing environments.

---

## 📁 Codebase Organization

```text
SWARM-DMAS-wrench/ 
 ├── include/
 ├── src/
 │ ├── agents/       # Custom WRENCH agents (e.g., job scheduling,  workload submission)
 │ ├── info/         # Data structures (Job and system descriptions, system status, job lifecycle)
 │ ├── policies/     # Scheduling policies (e.g., Local, Random, External Python Scripts)
 │ ├── utils/        # Utility functions
 ├── data_generation/
 │ ├── data/ # Workload traces and input datasets 
 │ └── scripts/ # Scripts to generate synthetic workloads 
 ├── hardware_failure_profiles/ 
 │ └── 
 ├── experiments/ 
 │ └── 
 ├── platforms/ 
 │ └── AmSC.xml # Platform description (resources, links, latencies)
 ├── python_scripts/ 
 │ └──  
 └── swar_dmas.cpp # Entry point for simulation
 
```

 ---

## 🛠️ Installation

### Prerequisites

- C++17 compiler (e.g., `g++`, `clang++`)
- WRENCH installed and configured
- CMake ≥ 3.10
- Boost libraries

### Build Instructions

```bash
git clone https://github.com/frs69wq/SWARM-DMAS-wrench.git
cd SWARM-DMAS-wrench
mkdir build && cd build
cmake ..
make -j
cd ..
```

## 🚀 Running the Simulation

To run the simulation:

```bash
cd build
./swarm_dmas experiments/scenario.json
```
A JSOn file describing an experimental scenario is structured as follows:

```json
{
    "workload": "workloads/heterogeneous_mix_10.json",
    "platform": "platforms/AmSC.xml",
    "policy": "PythonBidding",
    "bidder": "python_scripts/random_bidder.py"
}
```

## 🧠 Agent Roles (in src/agents/)
Each agent extends WRENCH's simulation API to implement custom behaviors.

TBD


## 📊 Policy Roles (in src/policies/)
Policies define the decision-making logic used by the meta-scheduler or local schedulers.

 - PureLocal: Jobs are scheduled only on the system where they were submitted (baseline).
 - RandomBidding: Jobs are randomly assigned to another system.
 - PythonBidding:
    - ``llm_claude_bidder.py``
