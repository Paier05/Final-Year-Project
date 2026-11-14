#!/bin/bash
#SBATCH --partition=UGGPU-TC1
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=360
#SBATCH --signal=B:USR1@900
#SBATCH --job-name=evo-v3
#SBATCH --output=logs/output_%x_%j.out
#SBATCH --error=logs/error_%x_%j.err

# One 6-hour part of the issue #14 run. Submit from the repo root on TC1:
#     mkdir -p logs && sbatch cluster/job_part.sh
# The same script runs every part: --resume starts the run if it is new and
# continues it otherwise. Nothing is resubmitted automatically.
#
# No --gres=gpu line: the model is called over an API, the job uses no GPU.
# The 5 episodes of a round run in parallel inside this one job.
# Secrets come from ~/.evo_harness_env (chmod 600), never from this file.

module load anaconda
source activate evo-harness
set -a; source ~/.evo_harness_env; set +a
# The game runs from environment_files/; no ARC API call is needed.
export OPERATION_MODE=offline
export PYTHONUNBUFFERED=1

python evolve_run.py --config config_evolve.yaml --run-dir runs/v3 --resume &
PID=$!
# SLURM sends USR1 to this shell 15 minutes before the limit; pass it on.
trap 'kill -USR1 $PID' USR1
wait $PID; RC=$?
if [ $RC -gt 128 ]; then wait $PID; RC=$?; fi
exit $RC
