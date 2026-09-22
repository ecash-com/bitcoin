#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test the ASERT (aserti3-2d) difficulty rule on a running node.

The unit tests in pow_tests exercise the formula. The formula is not where the bug
goes: it goes in the activation transition, where an anchor that cannot be found
leaves the first ASERT block at minimum difficulty and resets the curve, while every
unit test still passes. So this test drives a real node across the anchor and checks
the node's own answers block by block.

-testasertanchor=<height> is a regtest-only switch: it sets the anchor and, because
none of them can coexist with a per-block difficulty rule, also turns off
no-retargeting and min-difficulty blocks and lowers powLimit (which re-grinds the
regtest genesis block).
"""

from test_framework.messages import uint256_from_compact
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import assert_equal, assert_greater_than

ANCHOR_HEIGHT = 20
HALF_LIFE = 2 * 24 * 60 * 60
SPACING = 600
POW_LIMIT_BITS = 0x1e1fffff

RBITS = 16
RADIX = 1 << RBITS


def compact_from_uint256(value):
    """The inverse of uint256_from_compact: arith_uint256::GetCompact()."""
    size = (value.bit_length() + 7) // 8
    if size <= 3:
        compact = value << (8 * (3 - size))
    else:
        compact = value >> (8 * (size - 3))
    if compact & 0x00800000:
        compact >>= 8
        size += 1
    return compact | (size << 24)


def calculate_asert(ref_target, time_diff, height_diff, pow_limit, half_life):
    """An independent transcription of the aserti3-2d spec, mirroring src/pow.cpp.

    Kept deliberately literal, including the truncating division and the 256-bit
    saturation, so that agreement with the node means agreement on the arithmetic
    and not just on the shape of the curve.
    """
    schedule = SPACING * min(height_diff + 1, 1 << 32)
    drift = max(-(1 << 44), min(1 << 44, time_diff - schedule))

    # C++ integer division truncates toward zero; Python's // floors.
    magnitude = (abs(drift) * RADIX) // half_life
    exponent = -magnitude if drift < 0 else magnitude

    shifts = exponent >> RBITS  # arithmetic shift in both languages
    frac = exponent - shifts * RADIX
    assert 0 <= frac < RADIX

    factor = 65536 + ((195766423245049 * frac
                       + 971821376 * frac * frac
                       + 5127 * frac * frac * frac
                       + (1 << 47)) >> 48)
    next_target = ref_target * factor
    if next_target >> 256:
        return pow_limit

    shifts -= RBITS
    if shifts >= 256:
        return pow_limit
    if shifts <= -256:
        return 1
    if shifts <= 0:
        next_target >>= -shifts
    else:
        next_target <<= shifts
        if next_target >> 256:
            return pow_limit

    if next_target == 0:
        return 1
    return min(next_target, pow_limit)


class AsertTest(BitcoinTestFramework):
    def set_test_params(self):
        self.num_nodes = 1
        self.setup_clean_chain = True
        self.extra_args = [[f"-testasertanchor={ANCHOR_HEIGHT}"]]

    def block_time(self, height):
        return self.nodes[0].getblockheader(self.nodes[0].getblockhash(height))["time"]

    def block_bits(self, height):
        return int(self.nodes[0].getblockheader(self.nodes[0].getblockhash(height))["bits"], 16)

    def mine_at(self, timestamp):
        """Mine one block whose timestamp is exactly `timestamp`."""
        node = self.nodes[0]
        node.setmocktime(timestamp)
        height = node.getblockcount() + 1
        # The lowered powLimit means roughly 2^19 hashes per block, and the timestamp is
        # pinned, so the miner only has the nonce to work with: give it enough tries that
        # a miss is a real failure rather than bad luck.
        self.generate(node, 1, maxtries=100_000_000, sync_fun=self.no_op)
        assert_equal(node.getblockcount(), height)
        assert_equal(self.block_time(height), timestamp)
        return height

    def expected_bits(self, height):
        """What the node should have put in the block at `height`."""
        assert height > ANCHOR_HEIGHT
        ref_target = uint256_from_compact(self.block_bits(ANCHOR_HEIGHT))
        time_diff = self.block_time(height - 1) - self.block_time(ANCHOR_HEIGHT - 1)
        height_diff = (height - 1) - ANCHOR_HEIGHT
        target = calculate_asert(ref_target, time_diff, height_diff,
                                 uint256_from_compact(POW_LIMIT_BITS), HALF_LIFE)
        return compact_from_uint256(target)

    def run_test(self):
        node = self.nodes[0]
        pow_limit_target = uint256_from_compact(POW_LIMIT_BITS)

        self.log.info("The genesis block sits at the lowered powLimit")
        assert_equal(self.block_bits(0), POW_LIMIT_BITS)

        self.log.info("Below and at the anchor, the 2016-block rule is unchanged")
        # Every block on schedule except the anchor itself, which is solved in 10 s. A block's
        # target is computed from its PARENT's timestamp, so it is the anchor's own solve
        # time -- not the activation block's -- that moves the first ASERT target.
        start = 1_600_000_000
        for height in range(1, ANCHOR_HEIGHT):
            self.mine_at(start + SPACING * height)
            assert_equal(self.block_bits(height), POW_LIMIT_BITS)
        self.mine_at(self.block_time(ANCHOR_HEIGHT - 1) + 10)
        assert_equal(self.block_bits(ANCHOR_HEIGHT), POW_LIMIT_BITS)

        self.log.info("The activation block does not fall through to minimum difficulty")
        # The anchor was solved in 10 s against a 600 s schedule, so ASERT's answer for the
        # block above it is strictly harder than the limit. An anchor that could not be
        # found would instead leave this block at exactly the limit -- the bug this test
        # exists for, and the one every unit test passes straight through.
        self.mine_at(self.block_time(ANCHOR_HEIGHT) + 10)
        activation_bits = self.block_bits(ANCHOR_HEIGHT + 1)
        assert activation_bits != POW_LIMIT_BITS, "activation block took minimum difficulty"
        assert_greater_than(pow_limit_target, uint256_from_compact(activation_bits))

        self.log.info("The first ASERT block measures against the anchor's parent")
        # expected_bits() spans time from block ANCHOR-1. Measuring from the anchor itself
        # would be one solve time short, which this equality rejects.
        assert_equal(activation_bits, self.expected_bits(ANCHOR_HEIGHT + 1))

        self.log.info("Fast blocks make the target harder, monotonically")
        height = ANCHOR_HEIGHT + 1
        previous = uint256_from_compact(activation_bits)
        for _ in range(30):
            height = self.mine_at(self.block_time(height) + 10)
            bits = self.block_bits(height)
            assert_equal(bits, self.expected_bits(height))
            target = uint256_from_compact(bits)
            assert_greater_than(previous, target)
            previous = target

        self.log.info("The target does not depend on the new block's own timestamp")
        # Mine the same height twice from the same parent, 5000 s apart, and require the
        # same nBits. Checked here, while the target is off the limit; at the limit it
        # would hold trivially. (getblocktemplate is not available on this fork -- it
        # refuses and points at bip300301_enforcer -- so this goes through the chain.)
        parent_height = height
        parent_time = self.block_time(parent_height)
        first = self.mine_at(parent_time + 10)
        first_bits = self.block_bits(first)
        assert first_bits != POW_LIMIT_BITS
        node.invalidateblock(node.getblockhash(first))
        assert_equal(node.getblockcount(), parent_height)
        height = self.mine_at(parent_time + 5_000)
        assert_equal(self.block_bits(height), first_bits)

        self.log.info("A stall makes it easier again, and saturates at powLimit")
        # The first block of the stall still carries a target computed from the last fast
        # block, so the recovery only shows from the second one on.
        height = self.mine_at(self.block_time(height) + 40_000)
        assert_equal(self.block_bits(height), self.expected_bits(height))
        previous = uint256_from_compact(self.block_bits(height))
        rose = False
        for _ in range(29):
            height = self.mine_at(self.block_time(height) + 40_000)
            bits = self.block_bits(height)
            assert_equal(bits, self.expected_bits(height))
            target = uint256_from_compact(bits)
            # Strictly easier until it reaches the limit, and pinned there afterwards.
            if previous < pow_limit_target:
                assert_greater_than(target, previous)
                rose = True
            else:
                assert_equal(target, pow_limit_target)
            previous = target
        assert rose, "the stall never moved the target"
        assert_equal(self.block_bits(height), POW_LIMIT_BITS)

        self.log.info("The chain revalidates from disk across a restart with -reindex")
        tip = node.getbestblockhash()
        self.restart_node(0, extra_args=[f"-testasertanchor={ANCHOR_HEIGHT}", "-reindex"])
        assert_equal(node.getbestblockhash(), tip)
        assert_equal(node.getblockcount(), height)


if __name__ == '__main__':
    AsertTest(__file__).main()
