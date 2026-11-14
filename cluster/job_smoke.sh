#!/bin/bash
#SBATCH --partition=UGGPU-TC1
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=15
#SBATCH --job-name=evo-smoke
#SBATCH --output=logs/output_%x_%j.out
#SBATCH --error=logs/error_%x_%j.err

# Smoke job for issue #14: the test suite, then the preflight check
# (evolve/smoke.py: the game steps, the model endpoint answers from this node,
# one short episode runs, a checkpoint is written, --resume picks it up).
# Submit from the repo root on TC1:
#     mkdir -p logs && sbatch cluster/job_smoke.sh
# If either step fails the job exits non-zero: do not start the real run.

module load anaconda
source activate evo-harness
set -a; source ~/.evo_harness_env; set +a
export OPERATION_MODE=offline
export PYTHONUNBUFFERED=1

echo "=== node $(hostname), job $SLURM_JOB_ID, $(python --version) ==="
echo "=== 1/2 test suite ==="
python -m evolve.selftest
TESTS=$?
echo "=== test suite exit code: $TESTS ==="
if [ $TESTS -ne 0 ]; then exit $TESTS; fi

echo "=== 2/2 preflight ==="
python evolve_run.py --config config_evolve.yaml --stage smoke --run-dir "runs/smoke_$SLURM_JOB_ID"
SMOKE=$?
echo "=== preflight exit code: $SMOKE ==="
exit $SMOKE
