"""
IOTBSM Simulation Engine
Based on: Hexmoor, Wilson & Bhattaram (2006),
"A Theoretical Inter-organizational Trust-based Security Model,"
The Knowledge Engineering Review Vol. 21 No. 2, pp. 127-161 (Cambridge University Press).

Maps the formal IOTBSM definitions to agentic AI enterprise context:
  - Organization     -> Enterprise AI deployment
  - Agent            -> Internal AI agent
  - Boundary Spanner -> Orchestrator AI agent (cross-org representative)
  - Fact             -> Data/information asset
  - Fact Pedigree    -> Provenance log
"""

import random
import math
import uuid
import json
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict


# ─────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────

@dataclass
class Fact:
    """Definition 6: A datum produced and shared by agents."""
    id: str
    content: str
    initiator_id: str
    org_id: str
    cycle_created: int
    expiration_interval: int
    pedigree: list = field(default_factory=list)          # Definition 19
    intended_receivers: list = field(default_factory=list)
    unintended_receivers: list = field(default_factory=list)

    def is_expired(self, current_cycle: int) -> bool:
        return (current_cycle - self.cycle_created) >= self.expiration_interval

    def sign(self, entity_id: str, cycle: int):
        """Definition 18: Entity signs the fact pedigree."""
        self.pedigree.append({"entity": entity_id, "cycle": cycle})


@dataclass
class Agent:
    """Definition 4: Autonomous agent, member of an organization."""
    id: str
    org_id: str
    required_fact_content: str
    is_boundary_spanner: bool = False
    reliability: float = 0.5
    trust_relations: dict = field(default_factory=dict)   # entity_id -> float [0,1]
    satisfied: bool = False
    accessible_facts: list = field(default_factory=list)


@dataclass
class Organization:
    """Definition 3: A known organization in the inter-org network."""
    id: str
    name: str
    agents: dict = field(default_factory=dict)            # agent_id -> Agent
    boundary_spanners: dict = field(default_factory=dict) # bs_id -> Agent
    fact_request_repository: list = field(default_factory=list)  # Definition 7
    inter_org_trust: dict = field(default_factory=dict)   # org_id -> float
    initial_trust: dict = field(default_factory=dict)     # org_id -> tau_0
    interaction_count: dict = field(default_factory=dict) # org_id -> int (i)


# ─────────────────────────────────────────────
# Trust calculus (Equations 5 & 6)
# ─────────────────────────────────────────────

def logistic_trust(tau_0: float, r: float, i: int) -> float:
    """
    Equation 5: Logistic (Verhulst) growth function for inter-org trust.
    τ_i(om, on, r) = τ_0 / (τ_0 + (1 - τ_0) * e^(-r*i))
    Trust builds exponentially toward 1.0 from initial τ_0.
    """
    if i == 0:
        return tau_0
    denom = tau_0 + (1.0 - tau_0) * math.exp(-r * i)
    return tau_0 / denom if denom != 0 else tau_0


def compute_rate(bs_trust_values: list, x: int) -> float:
    """
    Equation 6: Rate r = average of BS trust relations, scaled by x^(-x).
    r_i^mn = (sum of BS trust values) / (xy)^x
    Scaled down further by 0.01 to produce realistic logistic growth over 100+ cycles.
    """
    if not bs_trust_values or x == 0:
        return 0.0
    total = sum(bs_trust_values)
    xy = len(bs_trust_values)
    denominator = (xy ** max(x, 1)) if xy > 0 else 1
    raw = total / denominator
    return raw * 0.005   # Scale so trust grows gradually over 100+ cycles


def instantaneous_bs_trust(io_trust: float, prev_bs_trust: float, alpha: float = 0.6) -> float:
    """
    Equation 7: Instantaneous inter-boundary-spanner trust.
    τ_i(bj_m, bk_n) = τ_i(om,on) * α + τ_{i-1}(bj_m,bk_n) * (1-α)
    α > 0.5 ensures inter-org trust dominates (as per paper).
    """
    return io_trust * alpha + prev_bs_trust * (1.0 - alpha)


# ─────────────────────────────────────────────
# Trust Policy Models (TPM1, TPM2, TPM3)
# ─────────────────────────────────────────────

def apply_tpm1(fact: Fact, trust_relations: dict, decrement: float = 0.1):
    """
    TPM1 (Definition 24): Exponential trust reduction along fact path,
    proportional to depth/degree of responsibility.
    """
    path = fact.pedigree
    depth = len(path)
    for k, entry in enumerate(path):
        eid = entry["entity"]
        if k > 0:
            prev_eid = path[k-1]["entity"]
            degree_resp = k + 1
            degree_unrec = depth
            update_val = decrement ** (degree_unrec - degree_resp + 1)
            key = (prev_eid, eid)
            if key in trust_relations:
                trust_relations[key] = max(0.0, trust_relations[key] - update_val)


def apply_tpm2(fact: Fact, trust_relations: dict, decrement: float = 0.1):
    """
    TPM2: Uniform trust decrement across all edges in the fact path.
    More restrictive than TPM1.
    """
    path = fact.pedigree
    for k in range(1, len(path)):
        prev_eid = path[k-1]["entity"]
        eid = path[k]["entity"]
        key = (prev_eid, eid)
        if key in trust_relations:
            trust_relations[key] = max(0.0, trust_relations[key] - decrement)


def apply_tpm3(fact: Fact, trust_relations: dict, decrement: float = 0.1):
    """
    TPM3: Initiator reduces trust in all entities in the fact path.
    Most restrictive — cuts off the first transmission step.
    """
    if not fact.pedigree:
        return
    initiator = fact.initiator_id
    for entry in fact.pedigree[1:]:
        eid = entry["entity"]
        key = (initiator, eid)
        if key in trust_relations:
            trust_relations[key] = max(0.0, trust_relations[key] - decrement)


# ─────────────────────────────────────────────
# Reliability metric (Boundary Spanner selection)
# ─────────────────────────────────────────────

def compute_reliability(agent: Agent, all_agents: dict) -> float:
    """
    Section 4.7: Reliability = weighted average of incoming trust relations.
    Direct relations weighted more than indirect.
    """
    incoming_direct = []
    incoming_indirect = []

    for other_id, other_agent in all_agents.items():
        if other_id == agent.id:
            continue
        if agent.id in other_agent.trust_relations:
            trust_val = other_agent.trust_relations[agent.id]
            incoming_direct.append(trust_val)
        else:
            # Indirect: find max path through intermediaries
            best = 0.0
            for mid_id, mid_agent in all_agents.items():
                if mid_id in (agent.id, other_id):
                    continue
                if (agent.id in mid_agent.trust_relations and
                        mid_id in other_agent.trust_relations):
                    path_val = min(
                        mid_agent.trust_relations[agent.id],
                        other_agent.trust_relations[mid_id]
                    )
                    best = max(best, path_val)
            if best > 0:
                incoming_indirect.append(best)

    total = incoming_direct + incoming_indirect
    if not total:
        return 0.0
    avg = sum(total) / len(total)
    direct_count = len(incoming_direct)
    return avg * (direct_count / max(len(total), 1))


# ─────────────────────────────────────────────
# Main Simulation
# ─────────────────────────────────────────────

class IOTBSMSimulation:
    """
    Full inter-organizational trust-based security model simulation.
    Supports 6+ organizations with agents, boundary spanners,
    trust calculus, TPMs, and fact pedigree tracking.
    """

    FACT_TOPICS = [
        "market_intelligence", "threat_data", "regulatory_update",
        "supply_chain_risk", "customer_insight", "technical_standard",
        "compliance_report", "vulnerability_advisory", "benchmark_data",
        "merger_signal", "pricing_model", "workforce_trend"
    ]

    def __init__(self,
                 num_orgs: int = 6,
                 agents_per_org: int = 5,
                 bs_fraction: float = 0.2,
                 trust_threshold: float = 0.4,
                 expiration_interval: int = 5,
                 bs_regulatory_rate: int = 10,
                 tpm_mode: int = 2,
                 decrement: float = 0.08,
                 alpha: float = 0.65):

        self.num_orgs = num_orgs
        self.agents_per_org = agents_per_org
        self.bs_fraction = bs_fraction
        self.trust_threshold = trust_threshold
        self.expiration_interval = expiration_interval
        self.bs_regulatory_rate = bs_regulatory_rate
        self.tpm_mode = tpm_mode
        self.decrement = decrement
        self.alpha = alpha

        self.organizations: dict[str, Organization] = {}
        self.global_trust_relations: dict[tuple, float] = {}
        self.active_facts: list[Fact] = []
        self.cycle = 0

        # Metrics history
        self.history = {
            "cycle": [],
            "ia_pct": [],
            "sm_pct": [],
            "total_facts_shared": [],
            "inter_org_trust": defaultdict(list),   # (om,on) -> [trust over time]
            "security_breaches": [],
            "bs_count": [],
            "active_facts_count": [],
        }

        self._build_network()

    def _org_name(self, i: int) -> str:
        names = ["Acme Corp", "Nexus Labs", "Sentinel AI", "Vertex Systems",
                 "Orionis Data", "Caldwell Group", "Meridian Tech", "Apex Analytics",
                 "Vanguard AI", "Stratos Intelligence"]
        return names[i % len(names)]

    def _build_network(self):
        """Initialize organizations, agents, trust relations, and boundary spanners."""
        fact_pool = self.FACT_TOPICS * 3

        for i in range(self.num_orgs):
            org_id = f"org_{i}"
            org = Organization(id=org_id, name=self._org_name(i))
            self.organizations[org_id] = org

            # Create agents
            for j in range(self.agents_per_org):
                agent_id = f"a_{i}_{j}"
                required = random.choice(fact_pool)
                agent = Agent(id=agent_id, org_id=org_id, required_fact_content=required)
                org.agents[agent_id] = agent

        # Establish intra-org trust relations
        for org in self.organizations.values():
            all_ids = list(org.agents.keys())
            for aid in all_ids:
                for bid in all_ids:
                    if aid != bid:
                        tv = random.uniform(0.2, 1.0)
                        org.agents[aid].trust_relations[bid] = tv
                        self.global_trust_relations[(aid, bid)] = tv

        # Initialize inter-org trust (τ_0)
        org_ids = list(self.organizations.keys())
        for i, om_id in enumerate(org_ids):
            om = self.organizations[om_id]
            for on_id in org_ids:
                if om_id != on_id:
                    tau0 = random.uniform(0.1, 0.5)
                    om.initial_trust[on_id] = tau0
                    om.inter_org_trust[on_id] = tau0
                    om.interaction_count[on_id] = 0

        # Elect initial boundary spanners
        for org in self.organizations.values():
            self._elect_boundary_spanners(org)

        # Establish inter-BS trust relations
        self._establish_inter_bs_relations()

    def _elect_boundary_spanners(self, org: Organization):
        """Section 4.7: Elect top-x agents as boundary spanners by reliability."""
        all_agents = {**org.agents, **org.boundary_spanners}

        # Demote existing BSs back to agents
        for bs_id, bs in list(org.boundary_spanners.items()):
            bs.is_boundary_spanner = False
            org.agents[bs_id] = bs
        org.boundary_spanners.clear()

        # Compute reliability for all
        for agent in org.agents.values():
            agent.reliability = compute_reliability(agent, org.agents)

        # Elect top bs_fraction
        sorted_agents = sorted(org.agents.values(), key=lambda a: a.reliability, reverse=True)
        num_bs = max(1, int(len(sorted_agents) * self.bs_fraction))

        for agent in sorted_agents[:num_bs]:
            agent.is_boundary_spanner = True
            org.boundary_spanners[agent.id] = agent
            del org.agents[agent.id]
            # BS adopts all fact requests
            org.fact_request_repository = list(set(
                [a.required_fact_content for a in org.agents.values()]
            ))

    def _establish_inter_bs_relations(self):
        """Ensure every BS has at least one relation to a BS in every other org."""
        org_ids = list(self.organizations.keys())
        for om_id in org_ids:
            om = self.organizations[om_id]
            for on_id in org_ids:
                if om_id == on_id:
                    continue
                on = self.organizations[on_id]
                if not om.boundary_spanners or not on.boundary_spanners:
                    continue
                # Guarantee at least one connection
                bs_m = random.choice(list(om.boundary_spanners.values()))
                bs_n = random.choice(list(on.boundary_spanners.values()))
                tv = random.uniform(0.2, 0.7)
                bs_m.trust_relations[bs_n.id] = tv
                self.global_trust_relations[(bs_m.id, bs_n.id)] = tv

    def _get_all_agents(self, org: Organization) -> dict:
        return {**org.agents, **org.boundary_spanners}

    def _update_inter_org_trust(self):
        """Equations 5 & 6: Update inter-organizational trust each cycle."""
        org_ids = list(self.organizations.keys())
        for om_id in org_ids:
            om = self.organizations[om_id]
            for on_id in org_ids:
                if om_id == on_id:
                    continue
                on = self.organizations[on_id]

                # Gather BS trust values (Eq 6)
                bs_trust_vals = []
                for bs_m in om.boundary_spanners.values():
                    for bs_n_id, tv in bs_m.trust_relations.items():
                        if bs_n_id in on.boundary_spanners:
                            bs_trust_vals.append(tv)

                x = len(om.boundary_spanners)
                r = compute_rate(bs_trust_vals, x)
                i = om.interaction_count.get(on_id, 0)
                tau0 = om.initial_trust.get(on_id, 0.3)

                new_trust = logistic_trust(tau0, r, i)
                om.inter_org_trust[on_id] = new_trust

                # Update instantaneous BS trust (Eq 7)
                for bs_m in om.boundary_spanners.values():
                    for bs_n_id in list(bs_m.trust_relations.keys()):
                        if bs_n_id in on.boundary_spanners:
                            prev = bs_m.trust_relations[bs_n_id]
                            new_bs_trust = instantaneous_bs_trust(new_trust, prev, self.alpha)
                            bs_m.trust_relations[bs_n_id] = new_bs_trust
                            self.global_trust_relations[(bs_m.id, bs_n_id)] = new_bs_trust

    def _can_share(self, sender_id: str, receiver_id: str,
                   sender_org_id: str, receiver_org_id: str) -> bool:
        """
        ISP1-ISP4: Trust threshold checks for information sharing.
        Cross-org exchange also checks inter-org trust (Definition 14).
        """
        sender_agent = None
        for org in self.organizations.values():
            all_a = self._get_all_agents(org)
            if sender_id in all_a:
                sender_agent = all_a[sender_id]
                break
        if sender_agent is None:
            return False

        trust_val = sender_agent.trust_relations.get(receiver_id, 0.0)
        if trust_val < self.trust_threshold:
            return False

        # Cross-org: also check inter-org trust (ISP3/ISP4)
        if sender_org_id != receiver_org_id:
            om = self.organizations[sender_org_id]
            io_trust = om.inter_org_trust.get(receiver_org_id, 0.0)
            if io_trust < self.trust_threshold:
                return False

        return True

    def _apply_tpm(self, fact: Fact):
        """Apply selected trust policy model on security breach."""
        if self.tpm_mode == 1:
            apply_tpm1(fact, self.global_trust_relations, self.decrement)
        elif self.tpm_mode == 2:
            apply_tpm2(fact, self.global_trust_relations, self.decrement)
        elif self.tpm_mode == 3:
            apply_tpm3(fact, self.global_trust_relations, self.decrement)

    def step(self):
        """Execute one simulation cycle (Figure 5 algorithm)."""
        self.cycle += 1

        # Step 3: Boundary spanner regulatory process
        if self.cycle % self.bs_regulatory_rate == 0:
            for org in self.organizations.values():
                self._elect_boundary_spanners(org)
            self._establish_inter_bs_relations()

        # Step 5: Every agent generates a fact and posts requirement
        new_facts = []
        for org in self.organizations.values():
            org.fact_request_repository = list(set(
                [a.required_fact_content for a in org.agents.values()]
            ))
            for agent in org.agents.values():
                agent.satisfied = False
                agent.accessible_facts = []
                topic = random.choice(self.FACT_TOPICS)
                fact = Fact(
                    id=str(uuid.uuid4())[:8],
                    content=topic,
                    initiator_id=agent.id,
                    org_id=org.id,
                    cycle_created=self.cycle,
                    expiration_interval=self.expiration_interval
                )
                fact.sign(agent.id, self.cycle)
                new_facts.append(fact)
                agent.accessible_facts.append(fact)

        self.active_facts.extend(new_facts)

        # Step 6-11: Information sharing within and across orgs
        intended_count = 0
        unintended_count = 0
        breaches = 0

        for fact in list(self.active_facts):
            if fact.is_expired(self.cycle):
                continue

            initiator_org = self.organizations.get(fact.org_id)
            if not initiator_org:
                continue

            # Share within org first
            initiator_agent = self._get_all_agents(initiator_org).get(fact.initiator_id)
            if not initiator_agent:
                continue

            for agent in initiator_org.agents.values():
                if agent.id == fact.initiator_id:
                    continue
                if not agent.satisfied and fact.content == agent.required_fact_content:
                    if self._can_share(fact.initiator_id, agent.id, fact.org_id, fact.org_id):
                        fact.sign(agent.id, self.cycle)
                        agent.satisfied = True
                        fact.intended_receivers.append(agent.id)
                        intended_count += 1
                    else:
                        fact.unintended_receivers.append(agent.id)
                        unintended_count += 1
                        breaches += 1

            # Cross-org sharing via boundary spanners
            for bs_m in initiator_org.boundary_spanners.values():
                for on_id, on in self.organizations.items():
                    if on_id == fact.org_id:
                        continue

                    for bs_n in on.boundary_spanners.values():
                        if bs_n.id not in bs_m.trust_relations:
                            continue

                        initiator_org.interaction_count[on_id] = \
                            initiator_org.interaction_count.get(on_id, 0) + 1

                        can = self._can_share(bs_m.id, bs_n.id, fact.org_id, on_id)
                        if can:
                            fact.sign(bs_n.id, self.cycle)
                            # Deliver to agents in on that need this fact
                            for agent in on.agents.values():
                                if (not agent.satisfied and
                                        fact.content == agent.required_fact_content):
                                    # Check agent-level trust from bs_n
                                    if bs_n.trust_relations.get(agent.id, 0) >= self.trust_threshold:
                                        fact.sign(agent.id, self.cycle)
                                        agent.satisfied = True
                                        fact.intended_receivers.append(agent.id)
                                        intended_count += 1
                        else:
                            # Only record breach if fact was actually requested
                            requesting = [a for a in on.agents.values()
                                          if fact.content == a.required_fact_content
                                          and not a.satisfied]
                            if requesting:
                                fact.unintended_receivers.append(bs_n.id)
                                unintended_count += 1
                                breaches += 1

        # Apply TPM on breaches
        for fact in self.active_facts:
            if fact.unintended_receivers:
                self._apply_tpm(fact)

        # Update inter-org trust
        self._update_inter_org_trust()

        # Expire old facts
        self.active_facts = [f for f in self.active_facts
                             if not f.is_expired(self.cycle)]

        # Compute metrics (Definitions 26-30)
        total_shared = intended_count + unintended_count
        ia_pct = (intended_count / total_shared * 100) if total_shared > 0 else 100.0
        sm_pct = (unintended_count / total_shared * 100) if total_shared > 0 else 0.0

        bs_count = sum(len(o.boundary_spanners) for o in self.organizations.values())

        # Record history
        self.history["cycle"].append(self.cycle)
        self.history["ia_pct"].append(ia_pct)
        self.history["sm_pct"].append(sm_pct)
        self.history["total_facts_shared"].append(total_shared)
        self.history["security_breaches"].append(breaches)
        self.history["bs_count"].append(bs_count)
        self.history["active_facts_count"].append(len(self.active_facts))

        for om_id, om in self.organizations.items():
            for on_id, trust_val in om.inter_org_trust.items():
                key = f"{om.name[:6]}→{self.organizations[on_id].name[:6]}"
                self.history["inter_org_trust"][key].append(trust_val)

        return {
            "cycle": self.cycle,
            "ia_pct": ia_pct,
            "sm_pct": sm_pct,
            "total_shared": total_shared,
            "breaches": breaches,
            "bs_count": bs_count
        }

    def run(self, num_cycles: int = 100):
        """Run the full simulation."""
        for _ in range(num_cycles):
            self.step()

    def get_org_trust_matrix(self) -> dict:
        """Return current inter-org trust matrix for heatmap."""
        orgs = list(self.organizations.values())
        matrix = []
        labels = [o.name[:8] for o in orgs]
        for om in orgs:
            row = []
            for on in orgs:
                if om.id == on.id:
                    row.append(1.0)
                else:
                    row.append(round(om.inter_org_trust.get(on.id, 0.0), 3))
            matrix.append(row)
        return {"labels": labels, "matrix": matrix}

    def get_network_graph(self) -> dict:
        """Return BS network graph data for visualization."""
        nodes = []
        edges = []
        for org in self.organizations.values():
            # Org node
            nodes.append({
                "id": org.id,
                "label": org.name[:10],
                "type": "org",
                "agent_count": len(org.agents),
                "bs_count": len(org.boundary_spanners)
            })
            for bs in org.boundary_spanners.values():
                for other_id, tv in bs.trust_relations.items():
                    for other_org in self.organizations.values():
                        if other_id in other_org.boundary_spanners and other_org.id != org.id:
                            edges.append({
                                "source": org.id,
                                "target": other_org.id,
                                "trust": round(tv, 3)
                            })
        return {"nodes": nodes, "edges": edges}

    def get_provenance_sample(self, n: int = 5) -> list:
        """Return sample fact pedigrees for provenance display."""
        sample = []
        facts_with_path = [f for f in self.active_facts if len(f.pedigree) > 1]
        for fact in facts_with_path[:n]:
            sample.append({
                "fact_id": fact.id,
                "content": fact.content,
                "org": self.organizations[fact.org_id].name,
                "pedigree_length": len(fact.pedigree),
                "intended": len(fact.intended_receivers),
                "unintended": len(fact.unintended_receivers),
                "pedigree": fact.pedigree[:8]
            })
        return sample
