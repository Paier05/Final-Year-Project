"""Regenerate the three required figures from ``results/*.json``.

Plots are built from the saved logs only -- nothing here retrains anything, so
the figures can be restyled without spending the compute again.

    python plots.py
"""

from __future__ import annotations

import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

import domain as D  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")

MODE_STYLE = {
    "rzero": ("#2563eb", "R-Zero (trained Challenger)"),
    "uniform": ("#f59e0b", "uniform curriculum"),
    "hardest": ("#dc2626", "hardest bucket only"),
    "oracle": ("#16a34a", "oracle (true labels, ceiling)"),
}


def load(tag):
    path = os.path.join(RESULTS, "%s.json" % tag)
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return json.load(fh)


def _finish(fig, name):
    fig.tight_layout()
    out = os.path.join(RESULTS, name)
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print("wrote %s" % os.path.relpath(out, HERE))


# ---------------------------------------------------------------------------


def plot_accuracy(tags=("rzero", "uniform", "hardest", "oracle")):
    """Plot 1: held-out accuracy vs iteration, mean +- std over seeds."""
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    for tag in tags:
        data = load(tag)
        if data is None:
            continue
        mean = 100 * np.array(data["accuracy_mean"])
        std = 100 * np.array(data["accuracy_std"])
        it = np.arange(len(mean))
        color, label = MODE_STYLE.get(tag, ("#666666", tag))
        ax.plot(it, mean, color=color, lw=2, label="%s (n=%d)" % (label, data["seeds"]))
        ax.fill_between(it, mean - std, mean + std, color=color, alpha=0.15, lw=0)
    ax.axvline(0, color="#999999", ls=":", lw=1)
    ax.annotate(
        "iteration 0 = after the seed phase\n(the last time a true label was used)",
        xy=(0, ax.get_ylim()[0]), xytext=(0.6, 0.06), textcoords="axes fraction",
        fontsize=8, color="#555555",
    )
    ax.set_xlabel("co-evolution iteration")
    ax.set_ylabel("held-out exact-match accuracy (%)")
    ax.set_title("Solver accuracy vs iteration (mean $\\pm$ std over seeds)")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, fontsize=9)
    _finish(fig, "plot1_accuracy.png")


def plot_curriculum(tag="rzero", seed_idx=0):
    """Plot 2: the Challenger's difficulty distribution over iterations."""
    data = load(tag)
    if data is None:
        print("no %s.json; skipping curriculum plot" % tag)
        return
    run = data["runs"][seed_idx]
    iters = run["iterations"]
    probs = np.array([it["bucket_probs"] for it in iters])  # (iters, buckets)

    # 36 stacked buckets is unreadable; group them by depth, which is the axis
    # the curriculum actually has to climb.
    depth_of = np.array([D.BUCKETS[b][0] for b in range(D.NUM_BUCKETS)])
    by_depth = np.stack(
        [probs[:, depth_of == d].sum(axis=1) for d in D.DEPTHS]
    )  # (depths, iters)

    fig, (ax, ax2) = plt.subplots(
        2, 1, figsize=(7.5, 6.2), sharex=True, gridspec_kw={"height_ratios": [2, 1]}
    )
    x = np.arange(probs.shape[0])
    colors = ["#dbeafe", "#93c5fd", "#3b82f6", "#1e3a8a"]
    ax.stackplot(
        x, 100 * by_depth, labels=["depth %d" % d for d in D.DEPTHS], colors=colors
    )
    ax.set_ylabel("share of the Challenger's mass (%)")
    ax.set_ylim(0, 100)
    ax.set_title("Challenger curriculum, %s (seed %d)" % (tag, run["seed"]))
    ax.legend(loc="upper left", frameon=False, fontsize=8, ncol=4)

    diff = [it.get("policy_mean_difficulty", it.get("mean_difficulty")) for it in iters]
    ax2.plot(x, diff, color="#1e3a8a", lw=2, marker="o", ms=3)
    ax2.axhline(
        float(D.DIFFICULTY.mean()), color="#999999", ls="--", lw=1,
        label="uniform policy (%.3f)" % D.DIFFICULTY.mean(),
    )
    ax2.set_xlabel("co-evolution iteration")
    ax2.set_ylabel("mean difficulty")
    ax2.grid(alpha=0.25)
    ax2.legend(frameon=False, fontsize=8)
    _finish(fig, "plot2_curriculum.png")


def plot_pseudo_labels(tag="rzero"):
    """Plot 3: pseudo-label accuracy and kept fraction, with the peak marked."""
    data = load(tag)
    if data is None:
        print("no %s.json; skipping pseudo-label plot" % tag)
        return
    runs = data["runs"]
    n_it = len(runs[0]["iterations"])
    pl = np.array(
        [[it.get("pseudo_label_accuracy", np.nan) for it in r["iterations"]] for r in runs]
    )
    kept = np.array(
        [[it.get("kept_fraction", np.nan) for it in r["iterations"]] for r in runs]
    )
    acc = np.array([[it["accuracy"] for it in r["iterations"]] for r in runs])
    x = np.arange(n_it)

    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    for arr, color, label in (
        (pl, "#7c3aed", "pseudo-label accuracy"),
        (kept, "#0891b2", "kept fraction"),
        (acc, "#2563eb", "held-out accuracy"),
    ):
        mean = 100 * np.nanmean(arr, axis=0)
        std = 100 * np.nanstd(arr, axis=0)
        ax.plot(x, mean, color=color, lw=2, label=label)
        ax.fill_between(x, mean - std, mean + std, color=color, alpha=0.15, lw=0)

    peak = int(np.nanargmax(np.nanmean(acc, axis=0)))
    ax.axvline(peak, color="#dc2626", ls="--", lw=1.5)
    ax.annotate(
        "accuracy peaks at iteration %d,\nthen stops improving" % peak,
        xy=(peak, 100 * np.nanmean(acc, axis=0)[peak]),
        xytext=(6, 12), textcoords="offset points", fontsize=8, color="#dc2626",
    )
    ax.set_xlabel("co-evolution iteration")
    ax.set_ylabel("percent")
    ax.set_title("Pseudo-label quality decays while the loop keeps training (%s)" % tag)
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, fontsize=9)
    _finish(fig, "plot3_pseudo_labels.png")


def main():
    plot_accuracy()
    plot_curriculum()
    plot_pseudo_labels()


if __name__ == "__main__":
    main()
