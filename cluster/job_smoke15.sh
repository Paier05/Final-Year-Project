#!/bin/bash
#SBATCH --partition=UGGPU-TC1
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --cpus-per-task=10
#SBATCH --mem=30G
#SBATCH --time=15
#SBATCH --output=logs/output_%x_%j.out
#SBATCH --error=logs/error_%x_%j.err

# Smoke check for issue #15, in the setup of the real run (script A: one job
# per game, both at once). Submit from the repo root on TC1:
#     mkdir -p logs
#     sbatch --export=ALL,GAME=ft09 --job-name=smoke-ft09 cluster/job_smoke15.sh
#     sbatch --export=ALL,GAME=vc33 --job-name=smoke-vc33 cluster/job_smoke15.sh
# Each job: the test suite, then the preflight (evolve/smoke.py: the game
# steps, the model endpoint answers from this node, one short episode runs,
# a checkpoint is written, --resume picks it up), in its own run directory
# runs/smoke_<game>_<job>. If either step fails the job exits non-zero: do
# not start the real run.

if [ -z "$GAME" ]; then
  echo "GAME is not set: sbatch --export=ALL,GAME=ft09 ..." >&2
  exit 2
fi

module load anaconda
source activate evo-harness
set -a; source ~/.evo_harness_env; set +a
export OPERATION_MODE=offline
export PYTHONUNBUFFERED=1

echo "=== node $(hostname), job $SLURM_JOB_ID, game $GAME, start $(date +%FT%T), $(python --version) ==="
echo "=== 1/2 test suite ==="
python -m evolve.selftest
TESTS=$?
echo "=== test suite exit code: $TESTS ==="
if [ $TESTS -ne 0 ]; then exit $TESTS; fi

echo "=== 2/2 preflight ==="
python evolve_run.py --config config_evolve_15.yaml --game "$GAME" --stage smoke --run-dir "runs/smoke_${GAME}_$SLURM_JOB_ID"
SMOKE=$?
echo "=== preflight exit code: $SMOKE, end $(date +%FT%T) ==="
exit $SMOKE
