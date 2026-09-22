// Copyright (c) 2015-present The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <arith_uint256.h>
#include <chain.h>
#include <chainparams.h>
#include <chainparamsbase.h>
#include <common/args.h>
#include <pow.h>
#include <test/data/asert_test_vectors.raw.h>
#include <test/util/random.h>
#include <test/util/common.h>
#include <test/util/setup_common.h>
#include <util/chaintype.h>

#include <util/strencodings.h>

#include <boost/test/unit_test.hpp>

#include <optional>
#include <string>
#include <string_view>
#include <vector>

BOOST_FIXTURE_TEST_SUITE(pow_tests, BasicTestingSetup)

/* Test calculation of next difficulty target with no constraints applying */
BOOST_AUTO_TEST_CASE(get_next_work)
{
    const auto chainParams = CreateChainParams(*m_node.args, ChainType::MAIN);
    int64_t nLastRetargetTime = 1261130161; // Block #30240
    CBlockIndex pindexLast;
    pindexLast.nHeight = 32255;
    pindexLast.nTime = 1262152739;  // Block #32255
    pindexLast.nBits = 0x1d00ffff;

    // Here (and below): expected_nbits is calculated in
    // CalculateNextWorkRequired(); redoing the calculation here would be just
    // reimplementing the same code that is written in pow.cpp. Rather than
    // copy that code, we just hardcode the expected result.
    unsigned int expected_nbits = 0x1d00d86aU;
    BOOST_CHECK_EQUAL(CalculateNextWorkRequired(&pindexLast, nLastRetargetTime, chainParams->GetConsensus()), expected_nbits);
    BOOST_CHECK(PermittedDifficultyTransition(chainParams->GetConsensus(), pindexLast.nHeight+1, pindexLast.nBits, expected_nbits));
}

/* Test the constraint on the upper bound for next work */
BOOST_AUTO_TEST_CASE(get_next_work_pow_limit)
{
    const auto chainParams = CreateChainParams(*m_node.args, ChainType::MAIN);
    int64_t nLastRetargetTime = 1231006505; // Block #0
    CBlockIndex pindexLast;
    pindexLast.nHeight = 2015;
    pindexLast.nTime = 1233061996;  // Block #2015
    pindexLast.nBits = 0x1d00ffff;
    unsigned int expected_nbits = 0x1d00ffffU;
    BOOST_CHECK_EQUAL(CalculateNextWorkRequired(&pindexLast, nLastRetargetTime, chainParams->GetConsensus()), expected_nbits);
    BOOST_CHECK(PermittedDifficultyTransition(chainParams->GetConsensus(), pindexLast.nHeight+1, pindexLast.nBits, expected_nbits));
}

/* Test the constraint on the lower bound for actual time taken */
BOOST_AUTO_TEST_CASE(get_next_work_lower_limit_actual)
{
    const auto chainParams = CreateChainParams(*m_node.args, ChainType::MAIN);
    int64_t nLastRetargetTime = 1279008237; // Block #66528
    CBlockIndex pindexLast;
    pindexLast.nHeight = 68543;
    pindexLast.nTime = 1279297671;  // Block #68543
    pindexLast.nBits = 0x1c05a3f4;
    unsigned int expected_nbits = 0x1c0168fdU;
    BOOST_CHECK_EQUAL(CalculateNextWorkRequired(&pindexLast, nLastRetargetTime, chainParams->GetConsensus()), expected_nbits);
    BOOST_CHECK(PermittedDifficultyTransition(chainParams->GetConsensus(), pindexLast.nHeight+1, pindexLast.nBits, expected_nbits));
    // Test that reducing nbits further would not be a PermittedDifficultyTransition.
    unsigned int invalid_nbits = expected_nbits-1;
    BOOST_CHECK(!PermittedDifficultyTransition(chainParams->GetConsensus(), pindexLast.nHeight+1, pindexLast.nBits, invalid_nbits));
}

/* Test the constraint on the upper bound for actual time taken */
BOOST_AUTO_TEST_CASE(get_next_work_upper_limit_actual)
{
    const auto chainParams = CreateChainParams(*m_node.args, ChainType::MAIN);
    int64_t nLastRetargetTime = 1263163443; // NOTE: Not an actual block time
    CBlockIndex pindexLast;
    pindexLast.nHeight = 46367;
    pindexLast.nTime = 1269211443;  // Block #46367
    pindexLast.nBits = 0x1c387f6f;
    unsigned int expected_nbits = 0x1d00e1fdU;
    BOOST_CHECK_EQUAL(CalculateNextWorkRequired(&pindexLast, nLastRetargetTime, chainParams->GetConsensus()), expected_nbits);
    BOOST_CHECK(PermittedDifficultyTransition(chainParams->GetConsensus(), pindexLast.nHeight+1, pindexLast.nBits, expected_nbits));
    // Test that increasing nbits further would not be a PermittedDifficultyTransition.
    unsigned int invalid_nbits = expected_nbits+1;
    BOOST_CHECK(!PermittedDifficultyTransition(chainParams->GetConsensus(), pindexLast.nHeight+1, pindexLast.nBits, invalid_nbits));
}

BOOST_AUTO_TEST_CASE(CheckProofOfWork_test_negative_target)
{
    const auto consensus = CreateChainParams(*m_node.args, ChainType::MAIN)->GetConsensus();
    uint256 hash;
    unsigned int nBits;
    nBits = UintToArith256(consensus.powLimit).GetCompact(true);
    hash = uint256{1};
    BOOST_CHECK(!CheckProofOfWork(hash, nBits, consensus));
}

BOOST_AUTO_TEST_CASE(CheckProofOfWork_test_overflow_target)
{
    const auto consensus = CreateChainParams(*m_node.args, ChainType::MAIN)->GetConsensus();
    uint256 hash;
    unsigned int nBits{~0x00800000U};
    hash = uint256{1};
    BOOST_CHECK(!CheckProofOfWork(hash, nBits, consensus));
}

BOOST_AUTO_TEST_CASE(CheckProofOfWork_test_too_easy_target)
{
    const auto consensus = CreateChainParams(*m_node.args, ChainType::MAIN)->GetConsensus();
    uint256 hash;
    unsigned int nBits;
    arith_uint256 nBits_arith = UintToArith256(consensus.powLimit);
    nBits_arith *= 2;
    nBits = nBits_arith.GetCompact();
    hash = uint256{1};
    BOOST_CHECK(!CheckProofOfWork(hash, nBits, consensus));
}

BOOST_AUTO_TEST_CASE(CheckProofOfWork_test_biger_hash_than_target)
{
    const auto consensus = CreateChainParams(*m_node.args, ChainType::MAIN)->GetConsensus();
    uint256 hash;
    unsigned int nBits;
    arith_uint256 hash_arith = UintToArith256(consensus.powLimit);
    nBits = hash_arith.GetCompact();
    hash_arith *= 2; // hash > nBits
    hash = ArithToUint256(hash_arith);
    BOOST_CHECK(!CheckProofOfWork(hash, nBits, consensus));
}

BOOST_AUTO_TEST_CASE(CheckProofOfWork_test_zero_target)
{
    const auto consensus = CreateChainParams(*m_node.args, ChainType::MAIN)->GetConsensus();
    uint256 hash;
    unsigned int nBits;
    arith_uint256 hash_arith{0};
    nBits = hash_arith.GetCompact();
    hash = ArithToUint256(hash_arith);
    BOOST_CHECK(!CheckProofOfWork(hash, nBits, consensus));
}

BOOST_AUTO_TEST_CASE(GetBlockProofEquivalentTime_test)
{
    const auto chainParams = CreateChainParams(*m_node.args, ChainType::MAIN);
    std::vector<CBlockIndex> blocks(10000);
    for (int i = 0; i < 10000; i++) {
        blocks[i].pprev = i ? &blocks[i - 1] : nullptr;
        blocks[i].nHeight = i;
        blocks[i].nTime = 1269211443 + i * chainParams->GetConsensus().nPowTargetSpacing;
        blocks[i].nBits = 0x207fffff; /* target 0x7fffff000... */
        blocks[i].nChainWork = i ? blocks[i - 1].nChainWork + GetBlockProof(blocks[i - 1]) : arith_uint256(0);
    }

    for (int j = 0; j < 1000; j++) {
        CBlockIndex *p1 = &blocks[m_rng.randrange(10000)];
        CBlockIndex *p2 = &blocks[m_rng.randrange(10000)];
        CBlockIndex *p3 = &blocks[m_rng.randrange(10000)];

        int64_t tdiff = GetBlockProofEquivalentTime(*p1, *p2, *p3, chainParams->GetConsensus());
        BOOST_CHECK_EQUAL(tdiff, p1->GetBlockTime() - p2->GetBlockTime());
    }
}

// ---- ASERT (aserti3-2d) ----------------------------------------------------

static constexpr uint32_t ASERT_REF_BITS{0x19044b7e}; // ECX beta fork bits, difficulty ~1e9
// A deliberately non-default half-life for the synthetic chains below, so they also prove
// the parameter is honoured rather than a constant being read somewhere. The value mainnet
// carries is ASERT_SPEC_HALF_LIFE, which the published vectors and ChainParams_MAIN_sanity use.
static constexpr int64_t ASERT_TEST_HALF_LIFE{24 * 60 * 60};
static constexpr int64_t ASERT_SPEC_HALF_LIFE{2 * 24 * 60 * 60};

BOOST_AUTO_TEST_CASE(asert_published_vectors)
{
    // The aserti3-2d reference vectors, run01..run12, verbatim as published with the
    // specification (src/test/data/asert_test_vectors.raw). 14,000 rows over the spec's
    // parameters: half-life two days, spacing 600 s, powLimit compact 0x1d00ffff, anchors
    // from the pow limit down to 0x01010000, heights across the signed 32- and 64-bit
    // boundaries, and runs whose solve times are negative throughout.
    //
    // This is what makes "bit-for-bit compatible with the spec" a checked claim rather
    // than an inferred one: the spec's 2^x is a cubic approximation, so an implementation
    // can be accurate against true 2^x and still disagree with the reference on most
    // inputs. Only the reference's own outputs settle it.
    const auto consensus = CreateChainParams(*m_node.args, ChainType::MAIN)->GetConsensus();
    // The vectors are defined against the spec's own pow limit, compact 0x1d00ffff, which is
    // where the saturating runs are expected to stop. This tree's MAIN powLimit is the wider
    // 00000000ffff..ff rather than Bitcoin's 00000000ffff0000..00; both encode to 0x1d00ffff,
    // but the vectors pin the limit they were generated with rather than borrowing ours.
    arith_uint256 pow_limit;
    pow_limit.SetCompact(0x1d00ffff);
    BOOST_REQUIRE(pow_limit <= UintToArith256(consensus.powLimit));

    const std::string_view data{reinterpret_cast<const char*>(test::data::asert_test_vectors.data()),
                                test::data::asert_test_vectors.size()};

    auto field_after = [](std::string_view line, std::string_view key) -> std::optional<std::string_view> {
        const auto pos = line.find(key);
        if (pos == std::string_view::npos) return std::nullopt;
        std::string_view rest = line.substr(pos + key.size());
        while (!rest.empty() && (rest.front() == ' ' || rest.front() == '\t')) rest.remove_prefix(1);
        while (!rest.empty() && (rest.back() == ' ' || rest.back() == '\t' || rest.back() == '\r')) rest.remove_suffix(1);
        return rest;
    };

    // run10's heights run past INT64_MAX on purpose, so they are parsed unsigned and only
    // the height difference — small in every run — is handed to the algorithm.
    uint64_t anchor_height{0};
    int64_t anchor_parent_time{0};
    arith_uint256 anchor_target;
    bool anchor_ready{false};
    int runs{0};
    int rows{0};

    size_t line_start{0};
    while (line_start < data.size()) {
        size_t line_end = data.find('\n', line_start);
        if (line_end == std::string_view::npos) line_end = data.size();
        std::string_view line = data.substr(line_start, line_end - line_start);
        line_start = line_end + 1;
        while (!line.empty() && (line.back() == '\r' || line.back() == ' ')) line.remove_suffix(1);
        if (line.empty()) continue;

        if (line.starts_with("##")) {
            if (line.find("description:") != std::string_view::npos) {
                ++runs;
                anchor_ready = false;
            } else if (const auto v = field_after(line, "anchor height:")) {
                const auto parsed = ToIntegral<uint64_t>(*v);
                BOOST_REQUIRE(parsed.has_value());
                anchor_height = *parsed;
            } else if (const auto v = field_after(line, "anchor parent time:")) {
                const auto parsed = ToIntegral<int64_t>(*v);
                BOOST_REQUIRE(parsed.has_value());
                anchor_parent_time = *parsed;
            } else if (const auto v = field_after(line, "anchor nBits:")) {
                BOOST_REQUIRE(v->starts_with("0x"));
                const auto parsed = ToIntegral<uint32_t>(v->substr(2), 16);
                BOOST_REQUIRE(parsed.has_value());
                const uint32_t compact{*parsed};
                bool negative{true}, overflow{true};
                anchor_target.SetCompact(compact, &negative, &overflow);
                BOOST_REQUIRE(!negative && !overflow && anchor_target > 0);
                anchor_ready = true;
            }
            continue;
        }
        if (line.starts_with("#")) continue;

        // "iteration height time target"
        std::vector<std::string> fields;
        for (size_t i = 0; i < line.size();) {
            while (i < line.size() && line[i] == ' ') ++i;
            const size_t word = i;
            while (i < line.size() && line[i] != ' ') ++i;
            if (i > word) fields.emplace_back(line.substr(word, i - word));
        }
        BOOST_REQUIRE_EQUAL(fields.size(), 4U);
        BOOST_REQUIRE(anchor_ready);

        const auto height = ToIntegral<uint64_t>(fields[1]);
        const auto time = ToIntegral<int64_t>(fields[2]);
        BOOST_REQUIRE(height.has_value() && time.has_value());
        BOOST_REQUIRE(fields[3].starts_with("0x"));
        const auto expected_bits = ToIntegral<uint32_t>(std::string_view{fields[3]}.substr(2), 16);
        BOOST_REQUIRE(expected_bits.has_value());

        const arith_uint256 got = CalculateASERT(anchor_target, consensus.nPowTargetSpacing,
                                                 *time - anchor_parent_time,
                                                 static_cast<int64_t>(*height - anchor_height),
                                                 pow_limit, ASERT_SPEC_HALF_LIFE);
        BOOST_CHECK_EQUAL(got.GetCompact(), *expected_bits);
        ++rows;
    }

    BOOST_CHECK_EQUAL(runs, 12);
    BOOST_CHECK_EQUAL(rows, 14000);
}

BOOST_AUTO_TEST_CASE(asert_invariants)
{
    const auto consensus = CreateChainParams(*m_node.args, ChainType::MAIN)->GetConsensus();
    const arith_uint256 pow_limit = UintToArith256(consensus.powLimit);
    const int64_t spacing = consensus.nPowTargetSpacing;
    arith_uint256 ref;
    ref.SetCompact(ASERT_REF_BITS);

    // Exactly on schedule: the anchor target comes back untouched, at any height.
    for (int64_t h : {0, 1, 2015, 2016, 100000, 1000000}) {
        BOOST_CHECK(CalculateASERT(ref, spacing, spacing * (h + 1), h, pow_limit, ASERT_TEST_HALF_LIFE) == ref);
    }
    // One half-life behind schedule doubles the target; one ahead halves it.
    BOOST_CHECK(CalculateASERT(ref, spacing, spacing * 100 + ASERT_TEST_HALF_LIFE, 99, pow_limit, ASERT_TEST_HALF_LIFE) == ref << 1);
    BOOST_CHECK(CalculateASERT(ref, spacing, spacing * 100 - ASERT_TEST_HALF_LIFE, 99, pow_limit, ASERT_TEST_HALF_LIFE) == ref >> 1);
    // Monotone in time: a later timestamp never gives a harder target.
    arith_uint256 prev = CalculateASERT(ref, spacing, -ASERT_TEST_HALF_LIFE * 3, 0, pow_limit, ASERT_TEST_HALF_LIFE);
    for (int64_t t = -ASERT_TEST_HALF_LIFE * 3; t <= ASERT_TEST_HALF_LIFE * 3; t += 977) {
        const arith_uint256 cur = CalculateASERT(ref, spacing, t, 0, pow_limit, ASERT_TEST_HALF_LIFE);
        BOOST_CHECK(cur >= prev);
        prev = cur;
    }
    // Far behind schedule saturates at the limit; far ahead floors at 1. Both paths are
    // exercised: shifts below 256 (overflow caught by the round-trip check) and at or above it.
    BOOST_CHECK(CalculateASERT(ref, spacing, ASERT_TEST_HALF_LIFE * 40, 0, pow_limit, ASERT_TEST_HALF_LIFE) == pow_limit);
    BOOST_CHECK(CalculateASERT(ref, spacing, ASERT_TEST_HALF_LIFE * 300, 0, pow_limit, ASERT_TEST_HALF_LIFE) == pow_limit);
    BOOST_CHECK(CalculateASERT(ref, spacing, int64_t{1} << 50, 0, pow_limit, ASERT_TEST_HALF_LIFE) == pow_limit);
    BOOST_CHECK(CalculateASERT(ref, spacing, -ASERT_TEST_HALF_LIFE * 200, 0, pow_limit, ASERT_TEST_HALF_LIFE) == arith_uint256{1});
    BOOST_CHECK(CalculateASERT(ref, spacing, -ASERT_TEST_HALF_LIFE * 300, 0, pow_limit, ASERT_TEST_HALF_LIFE) == arith_uint256{1});
    BOOST_CHECK(CalculateASERT(ref, spacing, -(int64_t{1} << 50), 0, pow_limit, ASERT_TEST_HALF_LIFE) == arith_uint256{1});
    // Starting at the limit and falling behind stays at the limit.
    BOOST_CHECK(CalculateASERT(pow_limit, spacing, spacing * 10 + ASERT_TEST_HALF_LIFE, 9, pow_limit, ASERT_TEST_HALF_LIFE) == pow_limit);
}

BOOST_AUTO_TEST_CASE(asert_chain)
{
    // A synthetic chain: 2016-block rule up to the anchor, ASERT above it. Checkpoints come
    // from the Python model of the same chain (asert_ref.py chain_sim).
    Consensus::Params params = CreateChainParams(*m_node.args, ChainType::MAIN)->GetConsensus();
    constexpr int ANCHOR{100};
    params.EcashAsertAnchorHeight = ANCHOR;
    params.EcashAsertHalfLife = ASERT_TEST_HALF_LIFE;
    const int64_t spacing = params.nPowTargetSpacing;

    struct Phase { int64_t gap; int count; };
    static const Phase plan[] = {{600, 50}, {10, 200}, {6000, 100}};
    int total = ANCHOR + 1;
    for (const auto& ph : plan) total += ph.count;

    std::vector<CBlockIndex> blocks(total);
    for (int h = 0; h <= ANCHOR; ++h) {
        blocks[h].pprev = h ? &blocks[h - 1] : nullptr;
        blocks[h].nHeight = h;
        blocks[h].nTime = 1600000000 + spacing * h;
        blocks[h].nBits = ASERT_REF_BITS;
        blocks[h].BuildSkip();
    }
    // Below and at the anchor the old rule answers: no ASERT, no change off a boundary.
    BOOST_CHECK(!IsAsertHeight(params, ANCHOR));
    BOOST_CHECK(IsAsertHeight(params, ANCHOR + 1));
    {
        CBlockHeader hdr;
        hdr.nTime = blocks[ANCHOR - 1].nTime + spacing;
        BOOST_CHECK_EQUAL(GetNextWorkRequired(&blocks[ANCHOR - 1], &hdr, params), ASERT_REF_BITS);
    }

    int h = ANCHOR;
    for (const auto& ph : plan) {
        for (int i = 0; i < ph.count; ++i) {
            CBlockHeader hdr;
            hdr.nTime = blocks[h].nTime + ph.gap;
            const uint32_t bits = GetNextWorkRequired(&blocks[h], &hdr, params);
            // Every step must pass the headers-sync guard.
            BOOST_CHECK(PermittedDifficultyTransition(params, h + 1, blocks[h].nBits, bits));
            ++h;
            blocks[h].pprev = &blocks[h - 1];
            blocks[h].nHeight = h;
            blocks[h].nTime = hdr.nTime;
            blocks[h].nBits = bits;
            blocks[h].BuildSkip();
        }
    }
    BOOST_CHECK_EQUAL(h, total - 1);

    struct Checkpoint { int height; uint32_t bits; };
    static const Checkpoint checkpoints[] = {
    {101, 0x19044b7e},
    {150, 0x19044b7e},
    {151, 0x19044b7e},
    {200, 0x190367e9},
    {350, 0x1901aca9},
    {351, 0x1901aaa3},
    {400, 0x190dec52},
    {450, 0x197979b2},
    };
    for (const auto& c : checkpoints) {
        BOOST_CHECK_EQUAL(blocks[c.height].nBits, c.bits);
    }

    // Shape: flat while on schedule, harder through the burst, easier through the stall.
    auto target = [&](int height) { arith_uint256 t; t.SetCompact(blocks[height].nBits); return t; };
    BOOST_CHECK(target(ANCHOR + 50) == target(ANCHOR));
    for (int i = ANCHOR + 52; i <= ANCHOR + 251; ++i) BOOST_CHECK(target(i) < target(i - 1));
    for (int i = ANCHOR + 252; i <= ANCHOR + 350; ++i) BOOST_CHECK(target(i) > target(i - 1));
    // The 6000 s stall is still far from the limit: recovery is exponential in time, not a reset.
    BOOST_CHECK(target(total - 1) < UintToArith256(params.powLimit));

    // The target depends on the previous block's time only, never on the new header's.
    {
        CBlockHeader early, late;
        early.nTime = blocks[h].nTime + 1;
        late.nTime = blocks[h].nTime + 100000;
        BOOST_CHECK_EQUAL(GetNextWorkRequired(&blocks[h], &early, params), GetNextWorkRequired(&blocks[h], &late, params));
    }
}

BOOST_AUTO_TEST_CASE(asert_mainnet_shape)
{
    // The shape mainnet would use: the anchor IS the fork block. Its target comes from the
    // EcashForkBits reset inside the 2016-block rule, and the first ASERT block measures the
    // anchor's solve time against the anchor's parent (a pre-fork block).
    Consensus::Params params = CreateChainParams(*m_node.args, ChainType::MAIN)->GetConsensus();
    constexpr int FORK{2016};
    params.EcashHeight = FORK;
    params.EcashForkBits = ASERT_REF_BITS;
    params.EcashAsertAnchorHeight = FORK;
    params.EcashAsertHalfLife = ASERT_TEST_HALF_LIFE;
    const int64_t spacing = params.nPowTargetSpacing;
    constexpr uint32_t PRE_FORK_BITS{0x1703a30c}; // a Bitcoin-mainnet-like target

    std::vector<CBlockIndex> blocks(FORK + 2);
    for (int h = 0; h < FORK; ++h) {
        blocks[h].pprev = h ? &blocks[h - 1] : nullptr;
        blocks[h].nHeight = h;
        blocks[h].nTime = 1600000000 + spacing * h;
        blocks[h].nBits = PRE_FORK_BITS;
        blocks[h].BuildSkip();
    }
    // 2015 -> 2016: the boundary retarget is overridden by the fork reset, not by ASERT.
    CBlockHeader fork_hdr;
    fork_hdr.nTime = blocks[FORK - 1].nTime + 3 * spacing; // the fork block took 30 minutes
    BOOST_CHECK(!IsAsertHeight(params, FORK));
    BOOST_CHECK_EQUAL(GetNextWorkRequired(&blocks[FORK - 1], &fork_hdr, params), ASERT_REF_BITS);
    blocks[FORK].pprev = &blocks[FORK - 1];
    blocks[FORK].nHeight = FORK;
    blocks[FORK].nTime = fork_hdr.nTime;
    blocks[FORK].nBits = ASERT_REF_BITS;
    blocks[FORK].BuildSkip();

    // 2016 -> 2017: ASERT, anchored on the fork block, clock started at the fork block's parent.
    CBlockHeader next_hdr;
    next_hdr.nTime = blocks[FORK].nTime + spacing;
    BOOST_CHECK(IsAsertHeight(params, FORK + 1));
    arith_uint256 ref;
    ref.SetCompact(ASERT_REF_BITS);
    const arith_uint256 expected = CalculateASERT(ref, spacing, blocks[FORK].nTime - blocks[FORK - 1].nTime, 0, UintToArith256(params.powLimit), ASERT_TEST_HALF_LIFE);
    BOOST_CHECK_EQUAL(GetNextWorkRequired(&blocks[FORK], &next_hdr, params), expected.GetCompact());
    // The fork block was 20 minutes late, so the first ASERT target is easier than the anchor's.
    BOOST_CHECK(expected > ref);
    BOOST_CHECK(PermittedDifficultyTransition(params, FORK + 1, ASERT_REF_BITS, expected.GetCompact()));

    // A chain that never retargets ignores the anchor entirely.
    params.fPowNoRetargeting = true;
    BOOST_CHECK_EQUAL(GetNextWorkRequired(&blocks[FORK], &next_hdr, params), ASERT_REF_BITS);
}

BOOST_AUTO_TEST_CASE(asert_permitted_difficulty_transition)
{
    Consensus::Params params = CreateChainParams(*m_node.args, ChainType::MAIN)->GetConsensus();
    params.EcashAsertAnchorHeight = 1000;
    params.EcashAsertHalfLife = ASERT_TEST_HALF_LIFE;
    const int64_t height = 1001; // first ASERT block, not a 2016 boundary

    arith_uint256 old_target;
    old_target.SetCompact(ASERT_REF_BITS);
    const auto bits = [](const arith_uint256& t) { return t.GetCompact(); };

    // At ASERT heights only the limit is enforced: any harder, any easier, up to powLimit.
    BOOST_CHECK(PermittedDifficultyTransition(params, height, ASERT_REF_BITS, ASERT_REF_BITS));
    BOOST_CHECK(PermittedDifficultyTransition(params, height, ASERT_REF_BITS, bits(old_target >> 2)));
    BOOST_CHECK(PermittedDifficultyTransition(params, height, ASERT_REF_BITS, bits(old_target >> 40)));
    BOOST_CHECK(PermittedDifficultyTransition(params, height, ASERT_REF_BITS, bits(old_target << 10)));
    BOOST_CHECK(PermittedDifficultyTransition(params, height, ASERT_REF_BITS, bits(UintToArith256(params.powLimit))));
    BOOST_CHECK(!PermittedDifficultyTransition(params, height, ASERT_REF_BITS, 0x1e00ffff));             // above powLimit
    // Below the anchor the old rule is untouched: off a boundary the bits must not move at all.
    BOOST_CHECK(!PermittedDifficultyTransition(params, 999, ASERT_REF_BITS, bits(old_target >> 2)));
    BOOST_CHECK(PermittedDifficultyTransition(params, 999, ASERT_REF_BITS, ASERT_REF_BITS));
}

BOOST_AUTO_TEST_CASE(asert_wide_powlimit_is_total)
{
    // With a powLimit at 2^255 (regtest's) the 256-bit multiply can drop its carry. The
    // round-trip check must turn that into the limit, never a tiny target.
    const arith_uint256 wide_limit = UintToArith256(uint256{"7fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"});
    const arith_uint256 t = CalculateASERT(wide_limit, 600, 600 * 10 + ASERT_TEST_HALF_LIFE, 9, wide_limit, ASERT_TEST_HALF_LIFE);
    BOOST_CHECK(t == wide_limit);
    BOOST_CHECK(CalculateASERT(wide_limit, 600, 600 * 10, 9, wide_limit, ASERT_TEST_HALF_LIFE) == wide_limit);
}

void sanity_check_chainparams(const ArgsManager& args, ChainType chain_type)
{
    const auto chainParams = CreateChainParams(args, chain_type);
    const auto consensus = chainParams->GetConsensus();

    // hash genesis is correct
    BOOST_CHECK_EQUAL(consensus.hashGenesisBlock, chainParams->GenesisBlock().GetHash());

    // target timespan is an even multiple of spacing
    BOOST_CHECK_EQUAL(consensus.nPowTargetTimespan % consensus.nPowTargetSpacing, 0);

    // genesis nBits is positive, doesn't overflow and is lower than powLimit
    arith_uint256 pow_compact;
    bool neg, over;
    pow_compact.SetCompact(chainParams->GenesisBlock().nBits, &neg, &over);
    BOOST_CHECK(!neg && pow_compact != 0);
    BOOST_CHECK(!over);
    BOOST_CHECK(UintToArith256(consensus.powLimit) >= pow_compact);

    // an ASERT anchor needs a parent block, a positive half-life, no min-difficulty blocks, and a
    // powLimit below 2^239 so refTarget * factor (< 2^17) fits -- see pow.cpp:CalculateASERT()
    if (consensus.EcashAsertAnchorHeight != 0) {
        BOOST_CHECK(consensus.EcashAsertAnchorHeight >= 1);
        BOOST_CHECK(consensus.EcashAsertHalfLife > 0);
        BOOST_CHECK(!consensus.fPowAllowMinDifficultyBlocks);
        BOOST_CHECK((UintToArith256(consensus.powLimit) >> 239) == 0);
    }

    // check max target * 4*nPowTargetTimespan doesn't overflow -- see pow.cpp:CalculateNextWorkRequired()
    if (!consensus.fPowNoRetargeting) {
        arith_uint256 targ_max{UintToArith256(uint256{"ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"})};
        targ_max /= consensus.nPowTargetTimespan*4;
        BOOST_CHECK(UintToArith256(consensus.powLimit) < targ_max);
    }
}

BOOST_AUTO_TEST_CASE(ChainParams_MAIN_sanity)
{
    sanity_check_chainparams(*m_node.args, ChainType::MAIN);
    // aserti3-2d: the "2d" is the half-life. Changing it forfeits the published vectors
    // above and BCH's production history as evidence for this configuration.
    BOOST_CHECK_EQUAL(CreateChainParams(*m_node.args, ChainType::MAIN)->GetConsensus().EcashAsertHalfLife, ASERT_SPEC_HALF_LIFE);
}

BOOST_AUTO_TEST_CASE(ChainParams_REGTEST_sanity)
{
    sanity_check_chainparams(*m_node.args, ChainType::REGTEST);
}

BOOST_AUTO_TEST_CASE(ChainParams_REGTEST_ASERT_sanity)
{
    // -testasertanchor changes four consensus values at once, and the bounds they have to
    // respect are checked nowhere else: the regtest built without the flag is a different
    // chain. In particular, turning retargeting back on makes CalculateNextWorkRequired
    // reachable, and sanity_check_chainparams is what pins powLimit under both
    // 2^239 (CalculateASERT) and (2^256-1)/(4*nPowTargetTimespan) (the 2016-block rule).
    ArgsManager args;
    SetupChainParamsBaseOptions(args);
    args.ForceSetArg("-testasertanchor", "200");
    sanity_check_chainparams(args, ChainType::REGTEST);

    const auto consensus = CreateChainParams(args, ChainType::REGTEST)->GetConsensus();
    BOOST_CHECK_EQUAL(consensus.EcashAsertAnchorHeight, 200);
    BOOST_CHECK_EQUAL(consensus.EcashAsertHalfLife, ASERT_SPEC_HALF_LIFE);
    BOOST_CHECK(!consensus.fPowNoRetargeting);
    BOOST_CHECK(!consensus.fPowAllowMinDifficultyBlocks);

    // 0 disables rather than raising, so that -notestasertanchor behaves like a negation.
    ArgsManager off;
    SetupChainParamsBaseOptions(off);
    off.ForceSetArg("-testasertanchor", "0");
    BOOST_CHECK_EQUAL(CreateChainParams(off, ChainType::REGTEST)->GetConsensus().EcashAsertAnchorHeight, 0);
}

BOOST_AUTO_TEST_CASE(ChainParams_TESTNET_sanity)
{
    sanity_check_chainparams(*m_node.args, ChainType::TESTNET);
}

BOOST_AUTO_TEST_CASE(ChainParams_TESTNET4_sanity)
{
    sanity_check_chainparams(*m_node.args, ChainType::TESTNET4);
}

BOOST_AUTO_TEST_CASE(ChainParams_SIGNET_sanity)
{
    sanity_check_chainparams(*m_node.args, ChainType::SIGNET);
}

BOOST_AUTO_TEST_SUITE_END()
