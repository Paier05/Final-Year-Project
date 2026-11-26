#!/bin/bash
#SBATCH --partition=UGGPU-TC1
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --cpus-per-task=10
#SBATCH --mem=30G
#SBATCH --time=360
#SBATCH --signal=B:USR1@900
#SBATCH --output=logs/output_%x_%j.out
#SBATCH --error=logs/error_%x_%j.err

# One 6-hour part of the issue #16 run for ONE game: the issue's script A
# (the model is called over an API, so one job per game, side by side, and no
# GPU), as in #15. Submit from the repo root on TC1 (~/evo-harness-16):
#     mkdir -p logs
#     sbatch --export=ALL,GAME=ft09 --job-name=evo-ft09-v4 cluster/job_api16.sh
#     sbatch --export=ALL,GAME=vc33 --job-name=evo-vc33-v4 cluster/job_api16.sh
# 2 jobs x (10 CPUs, 30 GB, no GPU) = 20 CPUs, 60 GB: within MaxTRESPU.
# The same script runs every part: --resume starts the run if it is new and
# continues it otherwise. Nothing is resubmitted automatically. Each game has
# its own run directory (runs/<game>-v4), run_state.json, lock, checkpoints,
# rejected-edit store and log; #15's runs/<game> are not used.
#
# Secrets come from ~/.evo_harness_env (chmod 600), never from this file.

if [ -z "$GAME" ]; then
  echo "GAME is not set: sbatch --export=ALL,GAME=ft09 ..." >&2
  exit 2
fi

module load anaconda
source activate evo-harness
set -a; source ~/.evo_harness_env; set +a
# The game runs from environment_files/; no ARC API call is needed.
export OPERATION_MODE=offline
export PYTHONUNBUFFERED=1

echo "=== node $(hostname), job $SLURM_JOB_ID, game $GAME, commit $(cat COMMIT), start $(date +%FT%T) ==="
python evolve_run.py --config config_evolve_16.yaml --game "$GAME" --run-dir "runs/${GAME}-v4" --resume &
PID=$!
# SLURM sends USR1 to this shell 15 minutes before the limit; pass it on.
trap 'kill -USR1 $PID' USR1
wait $PID; RC=$?
if [ $RC -gt 128 ]; then wait $PID; RC=$?; fi
echo "=== end $(date +%FT%T), exit code $RC ==="
exit $RC
