// Copyright (c) 2009-2010 Satoshi Nakamoto
// Copyright (c) 2009-present The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <pow.h>

#include <arith_uint256.h>
#include <chain.h>
#include <primitives/block.h>
#include <uint256.h>
#include <util/check.h>

#include <algorithm>

unsigned int GetNextWorkRequired(const CBlockIndex* pindexLast, const CBlockHeader *pblock, const Consensus::Params& params)
{
    assert(pindexLast != nullptr);

    // ASERT takes over for every block above the anchor. Chains that never retarget keep
    // not retargeting; the anchor is only meaningful on chains without min-difficulty
    // blocks (enforced by the chainparams sanity test).
    if (!params.fPowNoRetargeting && IsAsertHeight(params, pindexLast->nHeight + 1)) {
        const CBlockIndex* pindexAnchor = pindexLast->GetAncestor(params.EcashAsertAnchorHeight);
        assert(pindexAnchor != nullptr);
        return GetNextASERTWorkRequired(pindexLast, pindexAnchor, params);
    }

    unsigned int nProofOfWorkLimit = UintToArith256(params.powLimit).GetCompact();

    // Only change once per difficulty adjustment interval
    if ((pindexLast->nHeight+1) % params.DifficultyAdjustmentInterval() != 0)
    {
        if (params.fPowAllowMinDifficultyBlocks)
        {
            // Special difficulty rule for testnet:
            // If the new block's timestamp is more than 2* 10 minutes
            // then it MUST be a min-difficulty block.
            if (pblock->GetBlockTime() > pindexLast->GetBlockTime() + params.nPowTargetSpacing*2)
                return nProofOfWorkLimit;
            else
            {
                // Return the last non-special-min-difficulty-rules-block
                const CBlockIndex* pindex = pindexLast;
                while (pindex->pprev && pindex->nHeight % params.DifficultyAdjustmentInterval() != 0 && pindex->nBits == nProofOfWorkLimit)
                    pindex = pindex->pprev;
                return pindex->nBits;
            }
        }
        return pindexLast->nBits;
    }

    // Go back by what we want to be 14 days worth of blocks
    int nHeightFirst = pindexLast->nHeight - (params.DifficultyAdjustmentInterval()-1);
    assert(nHeightFirst >= 0);
    const CBlockIndex* pindexFirst = pindexLast->GetAncestor(nHeightFirst);
    assert(pindexFirst);

    return CalculateNextWorkRequired(pindexLast, pindexFirst->GetBlockTime(), params);
}

unsigned int CalculateNextWorkRequired(const CBlockIndex* pindexLast, int64_t nFirstBlockTime, const Consensus::Params& params)
{
    if (params.fPowNoRetargeting)
        return pindexLast->nBits;

    // Limit adjustment step
    int64_t nActualTimespan = pindexLast->GetBlockTime() - nFirstBlockTime;
    if (nActualTimespan < params.nPowTargetTimespan/4)
        nActualTimespan = params.nPowTargetTimespan/4;
    if (nActualTimespan > params.nPowTargetTimespan*4)
        nActualTimespan = params.nPowTargetTimespan*4;

    // Retarget
    const arith_uint256 bnPowLimit = UintToArith256(params.powLimit);
    arith_uint256 bnNew;

    // Special difficulty rule for Testnet4
    if (params.enforce_BIP94) {
        // Here we use the first block of the difficulty period. This way
        // the real difficulty is always preserved in the first block as
        // it is not allowed to use the min-difficulty exception.
        int nHeightFirst = pindexLast->nHeight - (params.DifficultyAdjustmentInterval()-1);
        const CBlockIndex* pindexFirst = pindexLast->GetAncestor(nHeightFirst);
        bnNew.SetCompact(pindexFirst->nBits);
    } else {
        bnNew.SetCompact(pindexLast->nBits);
    }

    bnNew *= nActualTimespan;
    bnNew /= params.nPowTargetTimespan;

    // eCash fork activation difficulty reset
    if (pindexLast->nHeight + 1 == params.EcashHeight)
        bnNew.SetCompact(params.EcashForkBits);

    if (bnNew > bnPowLimit)
        bnNew = bnPowLimit;

    return bnNew.GetCompact();
}

bool IsAsertHeight(const Consensus::Params& params, int64_t height)
{
    return params.EcashAsertAnchorHeight > 0 && height > params.EcashAsertAnchorHeight;
}

unsigned int GetNextASERTWorkRequired(const CBlockIndex* pindexPrev, const CBlockIndex* pindexAnchorBlock, const Consensus::Params& params)
{
    assert(pindexPrev != nullptr);
    assert(pindexAnchorBlock != nullptr);
    // The anchor's own solve time counts, so the clock starts at its parent.
    assert(pindexAnchorBlock->pprev != nullptr);
    assert(pindexPrev->nHeight >= pindexAnchorBlock->nHeight);

    const arith_uint256 powLimit = UintToArith256(params.powLimit);
    arith_uint256 refTarget;
    refTarget.SetCompact(pindexAnchorBlock->nBits);

    const int64_t nTimeDiff = pindexPrev->GetBlockTime() - pindexAnchorBlock->pprev->GetBlockTime();
    const int64_t nHeightDiff = pindexPrev->nHeight - pindexAnchorBlock->nHeight;

    const arith_uint256 nextTarget = CalculateASERT(refTarget, params.nPowTargetSpacing, nTimeDiff, nHeightDiff, powLimit, params.EcashAsertHalfLife);

    return nextTarget.GetCompact();
}

// aserti3-2d, as specified and deployed by Bitcoin Cash (Nov 2020). Kept
// bit-for-bit compatible with that spec so its published test vectors apply.
arith_uint256 CalculateASERT(const arith_uint256& refTarget, const int64_t nPowTargetSpacing, const int64_t nTimeDiff, const int64_t nHeightDiff, const arith_uint256& powLimit, const int64_t nHalfLife) noexcept
{
    // Fixed-point radix for the exponent: 16 fractional bits.
    static constexpr int64_t rbits = 16;
    static constexpr int64_t radix = 1 << rbits;

    assert(refTarget > 0 && refTarget <= powLimit);
    assert(nHalfLife > 0);
    assert(nHeightDiff >= 0);

    // How far the chain has drifted from its schedule, in seconds. Block timestamps are 32-bit
    // and heights fit in 31, so in consensus |drift| is far below 2^44; the clamps only keep
    // the arithmetic total on inputs outside that domain. A clamped drift saturates the
    // result to the limit or to 1 for any real half-life, so the answer is unchanged.
    static constexpr int64_t max_drift = int64_t{1} << 44;
    const int64_t schedule = nPowTargetSpacing * std::min(nHeightDiff + 1, int64_t{1} << 32);
    const int64_t drift = std::clamp(nTimeDiff - schedule, -max_drift, max_drift);

    // The drift in units of half-lives, 16.16 fixed point.
    const int64_t exponent = (drift * radix) / nHalfLife;

    // Split into integer shifts and a fractional part. Arithmetic right shift floors negative values.
    int64_t shifts = exponent >> rbits;
    const uint64_t frac = uint64_t(exponent - shifts * radix);
    assert(frac < uint64_t(radix));

    // 2^(frac/65536) ~ 1 + 0.695502*x + 0.226698*x^2 + 0.077800*x^3, as a 16.16 factor.
    // The polynomial's coefficients carry 48 fractional bits; max error ~1.3e-4, well under
    // one compact-encoding step. factor is in [65536, 131072), so it fits the 32-bit multiply.
    const uint64_t factor = 65536 + ((195766423245049ULL * frac + 971821376ULL * frac * frac + 5127ULL * frac * frac * frac + (1ULL << 47)) >> 48);
    assert(factor >= 65536 && factor < 131072);
    arith_uint256 nextTarget = refTarget * uint32_t(factor);
    // The 256-bit multiply drops its carry. It cannot overflow while powLimit < 2^239 (every
    // network that may set an anchor; see the chainparams sanity test), but keep the function
    // total: a product that does not round-trip has run past the limit.
    if (nextTarget / factor != refTarget) {
        return powLimit;
    }

    // Undo the factor's radix together with the integer shifts. Anything of 256 bits or
    // more is decided here, before the shift count is narrowed for the shift operators.
    shifts -= rbits;
    if (shifts >= 256) {
        return powLimit;
    }
    if (shifts <= -256) {
        return arith_uint256(1);
    }
    if (shifts <= 0) {
        nextTarget >>= static_cast<unsigned int>(-shifts);
    } else {
        // A left shift that does not round-trip has overflowed 256 bits: the target has run
        // past the limit. Shifts of 256 or more zero the value and are caught the same way.
        const arith_uint256 nextTargetCopy = nextTarget;
        nextTarget <<= static_cast<unsigned int>(shifts);
        if ((nextTarget >> static_cast<unsigned int>(shifts)) != nextTargetCopy) {
            return powLimit;
        }
    }

    if (nextTarget == 0) {
        return arith_uint256(1);
    }
    if (nextTarget > powLimit) {
        return powLimit;
    }
    return nextTarget;
}

// Check that on difficulty adjustments, the new difficulty does not increase
// or decrease beyond the permitted limits.
bool PermittedDifficultyTransition(const Consensus::Params& params, int64_t height, uint32_t old_nbits, uint32_t new_nbits)
{
    if (params.fPowAllowMinDifficultyBlocks) return true;

    if (!params.fPowNoRetargeting && IsAsertHeight(params, height)) {
        // Under ASERT the target moves every block by 2^((solve_time - spacing) / half_life),
        // and a valid chain puts no fixed bound on that: the only floor on a timestamp is the
        // median of the previous 11, which can sit days behind the tip after a slow stretch,
        // so a single MTP+1 timestamp can make the next block many times harder. Any constant
        // limit here would reject such a chain during headers sync. Headers sync therefore
        // relies on what it already has at these heights: real proof of work on every header
        // (HasValidProofOfWork) and the minimum-chain-work gate. Only the limit is enforced.
        //
        // In the other direction — a cheap header chain built by claiming to be far behind
        // schedule — timestamps are bounded above by real time plus MAX_FUTURE_BLOCK_TIME,
        // so how far behind schedule a header may claim to be is bounded by elapsed
        // wall-clock time rather than by anything an attacker picks. Note the limit of that:
        // the schedule is measured from the anchor's parent, not from pindexPrev, so the
        // bound is on time since the anchor. Once the anchor is many half-lives in the past,
        // a fork off it can reach powLimit cheaply, and what carries the weight there is the
        // minimum-chain-work gate and the proof of work on each header, not this function.
        const arith_uint256 pow_limit = UintToArith256(params.powLimit);
        arith_uint256 observed_new_target;
        observed_new_target.SetCompact(new_nbits);
        return observed_new_target <= pow_limit;
    }

    if (height % params.DifficultyAdjustmentInterval() == 0) {
        int64_t smallest_timespan = params.nPowTargetTimespan/4;
        int64_t largest_timespan = params.nPowTargetTimespan*4;

        const arith_uint256 pow_limit = UintToArith256(params.powLimit);
        arith_uint256 observed_new_target;
        observed_new_target.SetCompact(new_nbits);

        // Calculate the largest difficulty value possible:
        arith_uint256 largest_difficulty_target;
        largest_difficulty_target.SetCompact(old_nbits);
        largest_difficulty_target *= largest_timespan;
        largest_difficulty_target /= params.nPowTargetTimespan;

        if (largest_difficulty_target > pow_limit) {
            largest_difficulty_target = pow_limit;
        }

        // Round and then compare this new calculated value to what is
        // observed.
        arith_uint256 maximum_new_target;
        maximum_new_target.SetCompact(largest_difficulty_target.GetCompact());
        if (maximum_new_target < observed_new_target) return false;

        // Calculate the smallest difficulty value possible:
        arith_uint256 smallest_difficulty_target;
        smallest_difficulty_target.SetCompact(old_nbits);
        smallest_difficulty_target *= smallest_timespan;
        smallest_difficulty_target /= params.nPowTargetTimespan;

        if (smallest_difficulty_target > pow_limit) {
            smallest_difficulty_target = pow_limit;
        }

        // Round and then compare this new calculated value to what is
        // observed.
        arith_uint256 minimum_new_target;
        minimum_new_target.SetCompact(smallest_difficulty_target.GetCompact());
        if (minimum_new_target > observed_new_target) return false;
    } else if (old_nbits != new_nbits) {
        return false;
    }
    return true;
}

// Bypasses the actual proof of work check during fuzz testing with a simplified validation checking whether
// the most significant bit of the last byte of the hash is set.
bool CheckProofOfWork(uint256 hash, unsigned int nBits, const Consensus::Params& params)
{
    if (EnableFuzzDeterminism()) return (hash.data()[31] & 0x80) == 0;
    return CheckProofOfWorkImpl(hash, nBits, params);
}

std::optional<arith_uint256> DeriveTarget(unsigned int nBits, const uint256 pow_limit)
{
    bool fNegative;
    bool fOverflow;
    arith_uint256 bnTarget;

    bnTarget.SetCompact(nBits, &fNegative, &fOverflow);

    // Check range
    if (fNegative || bnTarget == 0 || fOverflow || bnTarget > UintToArith256(pow_limit))
        return {};

    return bnTarget;
}

bool CheckProofOfWorkImpl(uint256 hash, unsigned int nBits, const Consensus::Params& params)
{
    auto bnTarget{DeriveTarget(nBits, params.powLimit)};
    if (!bnTarget) return false;

    // Check proof of work matches claimed amount
    if (UintToArith256(hash) > bnTarget)
        return false;

    return true;
}
