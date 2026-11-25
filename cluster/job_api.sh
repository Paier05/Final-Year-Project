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

# One 6-hour part of the issue #15 run for ONE game: the issue's script A
# (the model is called over an API, so one job per game, side by side, and no
# GPU). Submit from the repo root on TC1:
#     mkdir -p logs
#     sbatch --export=ALL,GAME=ft09 --job-name=evo-ft09 cluster/job_api.sh
#     sbatch --export=ALL,GAME=vc33 --job-name=evo-vc33 cluster/job_api.sh
# 2 jobs x (10 CPUs, 30 GB, no GPU) = 20 CPUs, 60 GB: within MaxTRESPU.
# The same script runs every part: --resume starts the run if it is new and
# continues it otherwise. Nothing is resubmitted automatically. Each game has
# its own run directory, run_state.json, lock, checkpoints and log.
#
# Baseline B (#14's best ls20 harness, baselines/issue14_v4, seeds 1-3, no
# evolution) runs first in the same job while runs/<game>_baseline_b has no
# summary.json; the run's time guard is then told the minutes it used.
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
CONFIG=config_evolve_15.yaml

echo "=== node $(hostname), job $SLURM_JOB_ID, game $GAME, start $(date +%FT%T) ==="
PID=""
# SLURM sends USR1 to this shell 15 minutes before the limit; pass it on.
trap '[ -n "$PID" ] && kill -USR1 $PID' USR1

if [ ! -f "runs/${GAME}_baseline_b/summary.json" ]; then
  echo "=== baseline B ==="
  python evolve_run.py --config $CONFIG --game "$GAME" --stage baseline --harness baselines/issue14_v4 \
    --run-dir "runs/${GAME}_baseline_b" &
  PID=$!
  wait $PID; RC=$?
  if [ $RC -gt 128 ]; then wait $PID; RC=$?; fi
  if [ $RC -ne 0 ]; then
    echo "=== baseline B exit code $RC: the run is not started in this job ===" >&2
    exit $RC
  fi
fi

ELAPSED=$(( (SECONDS + 59) / 60 ))
echo "=== run, $ELAPSED min of the job used before it ==="
python evolve_run.py --config $CONFIG --game "$GAME" --run-dir "runs/$GAME" --resume --elapsed-min $ELAPSED &
PID=$!
wait $PID; RC=$?
if [ $RC -gt 128 ]; then wait $PID; RC=$?; fi
echo "=== end $(date +%FT%T), exit code $RC ==="
exit $RC
