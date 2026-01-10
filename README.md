# Hard Nanos - HardHaQ '25 Ion Trap Challenge

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Overview

This repository contains the **Team Hard Nanos** submission for the **HardHaQ '25 Trapped Ion Problem Set**. The project focuses on optimizing an RF Paul trap design to effectively confine a single Yb⁺ (Ytterbium) ion using a combination of oscillating and static electric fields within a vacuum environment.

**Team Members:** Nikhil, Rebanta, Lucas

## Project Description

The Ion Trap Challenge required us to modify an RF Paul trap to achieve stable ion confinement through:

- **RF rods** for radial confinement using oscillating radiofrequency voltage
- **DC endcaps** for axial stability with static electric fields
- **Vacuum environment** to minimize ion collisions with background gas

Our approach combines:
1. **COMSOL Multiphysics simulations** for electromagnetic modeling
2. **Python-based optimization** to systematically explore the parameter space
3. **Streamlit web application** for interactive data visualization and analysis

## Repository Structure

```
.
├── Comsol_Optimization/     # COMSOL optimization scripts
│   ├── Hardhaq_Optimization_Easy.py
│   ├── Comsol_Optimize.py
│   └── Comsol_SchizoTest/
├── Website/                 # Streamlit visualization app
│   ├── streamlit_app.py
│   ├── requirements.txt
│   └── README.md
├── PDF/                     # Submission documentation
│   ├── HardHaq_Submission.pdf
│   ├── HardHaq_Submission.tex
│   └── PDF_Visuals/
└── README.md               # This file
```

## Features

### 1. COMSOL Optimization

The optimization scripts in `Comsol_Optimization/` provide automated parameter tuning for the ion trap design:

- **Multi-parameter optimization**: Optimizes 10+ parameters including V_rf, V_dc, V_endcap, electrode geometry, and frequency
- **Objective function**: Balances trap depth (>5 eV), offset minimization (~0 mm), and power efficiency (~1000 mW)
- **Nelder-Mead algorithm**: Robust optimization method with configurable bounds and weights
- **CSV logging**: Tracks all trials for post-analysis

**Key Parameters:**
- RF voltage (V_rf): 0-1000 V
- DC voltage (V_dc): 0-500 V
- Endcap voltage (V_endcap): 0-500 V
- Electrode geometry: spacing, amplitude, radius
- Frequency (f): 1-100 MHz

### 2. Interactive Web Application

The Streamlit app in `Website/` provides powerful tools for analyzing parameter sweep results:

**Features:**
- **Parameter-file discovery**: Automatically finds and groups files matching `<param>_<value>.txt` pattern
- **Numeric table extraction**: Parses simulation results from text files
- **Multi-file comparison**: Compare results across different parameter values
- **Interactive plotting**: Visualize how metrics change with parameters
- **Best-fit analysis**: Linear regression with Pearson correlation for each column
- **Live file watching**: Auto-refresh when new simulation results are added
- **Customizable themes**: Dark/Light/Custom color schemes

### 3. Submission Documentation

The `PDF/` folder contains:
- Complete submission report (`HardHaq_Submission.pdf`)
- LaTeX source with figures (`HardHaq_Submission.tex`)
- Supporting visuals and diagrams

## Getting Started

### Prerequisites

- Python 3.8+
- COMSOL Multiphysics 6.3 (for optimization scripts)
- Virtual environment (recommended)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/Nikhil-Marella/Hard_Nanos_HardHaq.git
cd Hard_Nanos_HardHaq
```

2. Set up the Streamlit web application:
```bash
cd Website
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

3. Run the Streamlit app:
```bash
streamlit run streamlit_app.py
```

4. Open your browser to `http://localhost:8501`

### Using the COMSOL Optimization Scripts

**Note:** Requires COMSOL Multiphysics and the MPh Python interface.

```bash
cd Comsol_Optimization
python Hardhaq_Optimization_Easy.py
```

The script will:
1. Load the COMSOL model (`.mph` file)
2. Run optimization iterations using the Nelder-Mead algorithm
3. Save results to `optimization_log.csv`
4. Output the best parameter configuration

## Usage

### Analyzing Simulation Results

The Streamlit app is designed to work with text files following the naming pattern:
```
<parameter>_<value>.txt
```

Examples:
- `V_rf_300.txt` - Results for V_rf = 300V
- `f_10000000.txt` - Results for f = 10 MHz

Place your simulation output files in a folder and point the app to it via the sidebar.

### Understanding the Output

The optimization targets three key metrics:

1. **Trap Depth (depth_eV)**: Energy barrier preventing ion escape (target: ≥5 eV)
2. **Offset (offset_mm)**: Displacement from trap center (target: ~0 mm)
3. **Power Estimate (P_est_mW)**: RF power consumption (target: ~1000 mW)

## Physics Background

### RF Paul Trap Principles

The RF Paul trap uses an oscillating quadrupole electric field to confine charged particles. Unlike static fields (which violate Earnshaw's theorem), the time-varying RF field creates an effective "pseudo-potential" that provides 3D confinement.

**Key concepts:**
- **Radial confinement**: RF rods generate dynamic stability through alternating focusing/defocusing
- **Axial confinement**: DC endcaps provide static trapping along the z-axis
- **Pseudo-potential**: Time-averaged effective potential proportional to V²/Ω²

The effective harmonic potential strength scales as:
```
Ψ(r) ∝ (Q²V²)/(m·Ω²·r₀²) · r²
```

Where:
- Q = ion charge
- V = RF amplitude
- m = ion mass
- Ω = RF angular frequency
- r₀ = characteristic electrode spacing

## Technical Details

### Optimization Approach

The optimization script uses:
- **Normalized parameter space**: Maps physical bounds to [0,1] for better convergence
- **Weighted multi-objective function**: Combines depth, offset, and power metrics
- **Penalty constraints**: Rejects unphysical solutions (e.g., depth < 0.00001 eV)
- **Incremental logging**: Saves each trial to CSV for analysis

### Web App Architecture

- **Backend**: Python with Pandas, NumPy, Matplotlib
- **Frontend**: Streamlit for interactive UI
- **File monitoring**: Watchdog library for live updates
- **Table parsing**: Heuristic detection of numeric data blocks

## Contributing

This is a submission repository for the HardHaQ '25 challenge. For questions or collaboration:

- Open an issue on GitHub
- Contact the team members

## Citation

If you use this work in your research, please cite:

```
Hard Nanos Team (2025). HardHaQ '25 Trapped Ion Problem Set Submission.
GitHub repository: https://github.com/Nikhil-Marella/Hard_Nanos_HardHaq
```

## Acknowledgments

- HardHaQ '25 organizers for hosting the Ion Trap Challenge
- COMSOL Multiphysics for electromagnetic simulation capabilities
- The trapped ion physics community for foundational research

## License

This project is open source and available under the MIT License.

---

**Note**: The `.mph` COMSOL model files are excluded from version control (see `.gitignore`). Contact the team if you need access to the complete COMSOL models.
