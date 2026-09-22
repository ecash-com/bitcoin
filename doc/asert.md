# ASERT (aserti3-2d) difficulty adjustment

This document covers the parts of the ASERT rule that are decisions rather than code: how
the anchor is chosen and rolled out, and why the half-life is what it is. The algorithm
itself is in `src/pow.cpp` (`CalculateASERT`, `GetNextASERTWorkRequired`).

The rule is off unless `EcashAsertAnchorHeight` is non-zero. It is zero on every network.

## The anchor

`EcashAsertAnchorHeight` names the **last** block whose `nBits` come from the 2016-block
rule. Every block strictly above it takes its target from the anchor's `nBits` and the
clock:

    target(n) = anchor_target * 2^((time(n-1) - time(anchor-1) - 600 * (n - anchor)) / half_life)

Defining the anchor as the last block under the old rule, rather than the first block under
the new one, makes the anchor's existence a precondition of every ASERT evaluation. The
alternative — anchor at the activation height, found by walking back from `pindexPrev` —
cannot find it, because `pindexPrev` sits one block below; the activation block then falls
through to minimum difficulty and resets the curve.

### Setting it is a flag day

There is no signalling, no threshold and no grace period. A node whose build has a
different `EcashAsertAnchorHeight` computes a different target for the block above it and
follows a different chain from that block onward. A soft fork degrades to partial
participation; this degrades to a split.

The consequences of that are a rollout problem, not a code problem, so:

- **The mechanism merges disabled.** A height is argued separately, in its own change,
  once operators have demonstrably upgraded.
- **The height is published before the release that carries it**, with enough lead time
  that "has everyone upgraded" is an answerable question.
- **A node says so.** A build with a non-zero anchor logs it at startup, and warns on every
  new tip within 2016 blocks of the anchor. Discovering you are on the wrong build by
  forking off it is not acceptable as the only signal.

### Mainnet

`EcashAsertAnchorHeight = EcashHeight` is the natural choice. The fork block already
carries a fixed target (`EcashForkBits`) and its parent is the last Bitcoin block, so the
schedule starts exactly at the fork, from a deliberately chosen target. If that choice
turns out to be wrong, ASERT unwinds it over days rather than holding it for a full
2016-block epoch. That is the strongest case for the rule.

### Betanet, and how to read its first week

A chain already past its fork needs a later anchor, and there is a trap in picking one.
ASERT's whole schedule is relative to `nBits` at the anchor. A target that came off the
±4× retarget clamp is not a value the chain ever equilibrated at — anchor there and the
schedule is pinned to a target that was never right. The chain runs slow, accumulates
lateness, and ASERT walks the target back down.

That self-correction is the algorithm working, and it is faster than waiting 2016 blocks
for the same correction. But it means the days right after such an anchor measure
**convergence from a bad starting point**, not oscillation damping. Judging the rule by
that week answers a different question than the one being asked.

## The half-life

`EcashAsertHalfLife` is two days (172800 s) — the `2d` in `aserti3-2d`, and the value
Bitcoin Cash has run in production since November 2020. A shorter half-life gives faster
relief when hashrate leaves. It is not free.

**It is the safety argument.** BCH's production history is evidence for the two-day
variant and for nothing else. A one-day half-life is a different algorithm and has to be
argued on its own merits.

**It sets the leverage of the timestamp lever.** With a per-block difficulty rule,
timestamps become a lever on difficulty, bounded above by `MAX_FUTURE_BLOCK_TIME` (2 h).
Two hours of future-dating is worth `2^(7200/half_life)` easier for the next block:
about 6% at one day, about 3% at two, and repeatable. Halving the half-life doubles the
value of a lever that is being left at 2 h. The two decisions are coupled and should not be
made separately.

**It prices the cost of attacking a dormant chain.** A stalled chain falls behind schedule
at one second per second, so its target decays whether or not anyone is mining — that is
how the chain recovers, and under the 2016-block rule it does not happen at all. But the
decay is steep. Thirty days of silence is 30 half-lives at one day and 15 at two: a
difficulty of 1e9 lands near **1** in the first case and near **30,000** in the second.

That matters here more than it would in a chain without BIP300. Withdrawal-bundle approval
and used-slot replacement are counted in **blocks** — 13,150 of 26,300 — not in work. A
chain that has decayed to trivial difficulty is one where an attacker can buy an entire
voting window cheaply, and the 26,300-block delay meant to make that expensive is
denominated in the thing that just became free. The half-life is therefore not only a
liveness dial, and the longer value is the safer one.

A staged half-life — short while hashrate is unstable, transitioning to two days at a fixed
height, as bch2 launched — is a reasonable alternative that turns this into a parameter
rather than a judgement locked in now. It is not implemented here.

## Testing

`src/test/data/asert_test_vectors.raw` holds the aserti3-2d reference vectors, runs 1
through 12, verbatim as published with the specification: 14,000 rows checked by
`pow_tests/asert_published_vectors`.

This is deliberately not an accuracy test. The spec's `2^x` is a **cubic approximation**,
so an implementation can agree with exact arithmetic to within the documented error band
and still produce a different `nBits` on most inputs — two implementations that are both
accurate can still be two chains. Only the reference's own outputs settle compatibility.

`-testasertanchor=<height>` (regtest, debug-only) puts a regtest chain under ASERT. It also
disables no-retargeting and min-difficulty blocks and lowers `powLimit`, because none of
those can coexist with a per-block difficulty rule; lowering `powLimit` changes the regtest
genesis block, which the switch re-grinds. `test/functional/feature_asert.py` uses it to
exercise the activation transition on a real node — the place where the formula is not the
thing that breaks.
