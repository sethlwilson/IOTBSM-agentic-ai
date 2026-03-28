"""
IOTBSM Proof of Concept — Main Runner
Runs the simulation and generates the interactive HTML dashboard.

Usage:
    python3 run.py [--orgs N] [--agents N] [--cycles N] [--tpm 1|2|3]

Based on: Hexmoor, Wilson & Bhattaram (2006)
The Knowledge Engineering Review, 21(2), 127-161.
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(__file__))

from simulation import IOTBSMSimulation
from dashboard import generate_dashboard


def parse_args():
    parser = argparse.ArgumentParser(description="IOTBSM Simulation")
    parser.add_argument("--orgs", type=int, default=8, help="Number of organizations (default: 8)")
    parser.add_argument("--agents", type=int, default=6, help="Agents per org (default: 6)")
    parser.add_argument("--cycles", type=int, default=120, help="Simulation cycles (default: 120)")
    parser.add_argument("--tpm", type=int, default=2, choices=[1,2,3], help="Trust policy model (default: 2)")
    parser.add_argument("--threshold", type=float, default=0.35, help="Trust threshold (default: 0.35)")
    parser.add_argument("--decrement", type=float, default=0.08, help="Trust decrement on breach (default: 0.08)")
    parser.add_argument("--alpha", type=float, default=0.65, help="Inter-org trust weight α (default: 0.65)")
    parser.add_argument("--output", type=str, default="./dashboard.html")
    return parser.parse_args()


def print_summary(sim: IOTBSMSimulation):
    print("\n" + "="*60)
    print("  IOTBSM SIMULATION SUMMARY")
    print("="*60)
    print(f"  Organizations   : {sim.num_orgs}")
    print(f"  Agents/Org      : {sim.agents_per_org}")
    print(f"  Total Agents    : {sim.num_orgs * sim.agents_per_org}")
    print(f"  Cycles Run      : {sim.cycle}")
    print(f"  TPM Mode        : TPM{sim.tpm_mode}")
    print(f"  Trust Threshold : {sim.trust_threshold}")
    print(f"  Alpha (α)       : {sim.alpha}")
    print("-"*60)

    ia_final = sim.history["ia_pct"][-1] if sim.history["ia_pct"] else 0
    sm_final = sim.history["sm_pct"][-1] if sim.history["sm_pct"] else 0
    total_b  = sum(sim.history["security_breaches"])
    bs_final = sim.history["bs_count"][-1] if sim.history["bs_count"] else 0

    print(f"  Final IA%       : {ia_final:.1f}%  (target: 100%)")
    print(f"  Final SM%       : {sm_final:.1f}%  (target: 0%)")
    print(f"  Total Breaches  : {total_b}")
    print(f"  Active BS Agents: {bs_final}")
    print("-"*60)

    print("\n  Inter-Org Trust Matrix (final):")
    orgs = list(sim.organizations.values())
    header = "         " + "  ".join(f"{o.name[:6]:>7}" for o in orgs)
    print(f"  {header}")
    for om in orgs:
        row = f"  {om.name[:8]:10}"
        for on in orgs:
            if om.id == on.id:
                val = "  1.000"
            else:
                val = f"  {om.inter_org_trust.get(on.id, 0):.3f}"
            row += val
        print(row)
    print("="*60 + "\n")


def main():
    args = parse_args()

    print(f"\n🔵 Initializing IOTBSM simulation...")
    print(f"   {args.orgs} organizations × {args.agents} agents × {args.cycles} cycles")
    print(f"   TPM{args.tpm} | threshold={args.threshold} | α={args.alpha}\n")

    sim = IOTBSMSimulation(
        num_orgs=args.orgs,
        agents_per_org=args.agents,
        bs_fraction=0.2,
        trust_threshold=args.threshold,
        expiration_interval=6,
        bs_regulatory_rate=15,
        tpm_mode=args.tpm,
        decrement=args.decrement,
        alpha=args.alpha
    )

    print("🔄 Running simulation cycles...")
    for i in range(args.cycles):
        result = sim.step()
        if (i + 1) % 20 == 0:
            print(f"   Cycle {result['cycle']:3d} | "
                  f"IA: {result['ia_pct']:5.1f}% | "
                  f"SM: {result['sm_pct']:5.1f}% | "
                  f"Breaches: {result['breaches']:3d} | "
                  f"BS: {result['bs_count']}")

    print_summary(sim)

    print(f"📊 Generating dashboard → {args.output}")
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    generate_dashboard(sim, args.output)
    print("✅ Done.\n")


if __name__ == "__main__":
    main()
