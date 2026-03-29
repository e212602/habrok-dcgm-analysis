# habrok-dcgm-analysis

Project for analyzing jobs submitted to Habrok GPU Nodes.
## Project structure

- `data/hardware_reports/`: JSON files containing DCGM reports.
- `habrok_script_and_metadata.zip`: Contains jobs metadata and artificial SLURM script per job. (Large file, hence not pushed to github, but shared on Google Drive)
- `utils/`: Utility scripts.
- `analysis.ipynb`: Example showing how to interact with the data.

## Requirements

- Python 3
- pandas
- matplotlib
- numpy
- Jupyter Notebook

## DCGM Raw Reports
- DCGM reports are collected from ("/scratch/public/DCGM_output/"), a directory which can be accessed using one of the Habrok interactive nodes.
- Current Data contain reports collected from June 2025 up to March 2026.

## SLURM Scripts
- Due to privacy restrictions, extracting submitted SLURM scripts is infeasible. Thus, we use sacct to extract metadata and use it to artificially generate SLURM scripts per job. (utils/python/generate_slurm_script.py)

## TODO

- Analyze metadata or SLURM script features correlated with hardware metrics.
- Build an estimation engine for estimating runtime performance of a submitted job.

