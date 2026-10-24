// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title CoolRoofEscrow
/// @notice Funds measured cooling outcomes using thresholds fixed by the sponsor.
contract CoolRoofEscrow is Ownable, ReentrancyGuard {
    enum Tranche { QUALITY, DURABILITY, FORCE_MAJEURE_RESERVE }
    struct MeasurementProof { bytes32 id; uint256 measuredAt; }

    struct Project {
        string roofId;
        address sponsor;
        address contractor;
        uint256 totalAmount;
        // Solidity has no decimals: Celsius deltas are multiplied by ten (-80 = -8.0 C).
        int256 minNormalizedDeltaCx10;
        uint256 minCoveragePct;
        uint256 createdAt;
        bool exists;
        // The durability clock starts when the coating is verified, not when funds are
        // locked. Appended last so clients decoding the older struct still read every field.
        uint256 qualityReleasedAt;
    }

    uint256 public constant PERCENT_BASE = 100;
    uint256 public constant QUALITY_PERCENT = 60;
    uint256 public constant DURABILITY_PERCENT = 30;
    uint256 public constant RESERVE_PERCENT = 10;
    uint256 public constant DURABILITY_DELAY = 180 days;
    uint256 public constant RECLAIM_DELAY = 365 days;
    uint256 public constant DURABILITY_CLAIM_WINDOW = 30 days;
    uint8 public constant APPROVED_STATUS = 0;
    uint8 public constant FORCE_MAJEURE_STATUS = 3;
    // schema/thresholds.json default weather limits, expressed in tenths.
    uint256 public constant FORCE_MAJEURE_GUST_MS_X10 = 200;
    uint256 public constant FORCE_MAJEURE_PRECIP_MM_X10 = 500;
    uint256 private constant MINIMUM_DEPOSIT = PERCENT_BASE / RESERVE_PERCENT;

    address public oracle;
    mapping(string => Project) private projects;
    mapping(string => mapping(Tranche => bool)) private released;
    mapping(string => bool) private durabilitySuspended;
    mapping(string => bool) private reclaimed;
    mapping(string => MeasurementProof) private qualityProofs;

    error UnauthorizedOracle(address caller);
    error InvalidAddress();
    error InvalidRoofId();
    error InvalidDeposit();
    error InvalidThresholds();
    error ProjectAlreadyExists(string roofId);
    error ProjectNotFound(string roofId);
    error InvalidPhase(uint8 phase);
    error InvalidCoverage(uint256 coveragePct);
    error InvalidForceMajeurePhase();
    error PhaseAlreadySettled(string roofId, Tranche tranche);
    error PaymentFailed(address recipient, uint256 amount);
    error NotProjectSponsor(address caller);
    error ReclaimNotYetAvailable(uint256 availableAt);
    error ProjectClosed(string roofId);

    event ProjectCreated(string roofId, address indexed sponsor, address indexed contractor, uint256 totalAmount);
    event VerificationSubmitted(string roofId, uint8 status, int256 normalizedDeltaCx10, bytes32 evidenceHash);
    event VerificationEvidence(string roofId, uint8 phase, uint256 coveragePct, bool forceMajeure, bytes deviceSignature);
    event TrancheReleased(string roofId, Tranche tranche, uint256 amount, address indexed to);
    event PaymentHeld(string roofId, Tranche tranche, string reason);
    event ForceMajeureApplied(string roofId, uint256 maxGustMsX10, uint256 precipMmX10);
    event UnreleasedReclaimed(string roofId, address indexed sponsor, uint256 amount);
    event OracleUpdated(address indexed previousOracle, address indexed newOracle);

    modifier onlyOracle() {
        if (msg.sender != oracle) revert UnauthorizedOracle(msg.sender);
        _;
    }

    /// @notice The deployer controls oracle rotation, never project thresholds or balances.
    constructor(address initialOracle) Ownable(msg.sender) {
        _setOracle(initialOracle);
    }

    /// @notice Fixes sponsor-approved thresholds before any measurements arrive.
    function createProject(
        string calldata roofId,
        address contractor,
        int256 minNormalizedDeltaCx10,
        uint256 minCoveragePct
    ) external payable nonReentrant {
        if (bytes(roofId).length == 0) revert InvalidRoofId();
        if (projects[roofId].exists) revert ProjectAlreadyExists(roofId);
        if (contractor == address(0) || contractor == address(this)) revert InvalidAddress();
        if (msg.value < MINIMUM_DEPOSIT) revert InvalidDeposit();
        if (minNormalizedDeltaCx10 >= 0 || minCoveragePct == 0 || minCoveragePct > PERCENT_BASE) {
            revert InvalidThresholds();
        }
        projects[roofId] = Project({
            roofId: roofId, sponsor: msg.sender, contractor: contractor,
            totalAmount: msg.value, minNormalizedDeltaCx10: minNormalizedDeltaCx10,
            minCoveragePct: minCoveragePct, createdAt: block.timestamp, exists: true,
            qualityReleasedAt: 0
        });
        emit ProjectCreated(roofId, msg.sender, contractor, msg.value);
    }

    /// @notice Only approved evidence or a checked weather exception may release funds.
    /// @dev Device signatures are retained as evidence, not authenticated without a device registry/protocol.
    /// @param coveragePct Whole percent: the escrow compares it with an integer threshold.
    /// @param maxGustMsX10 Peak wind gust in m/s multiplied by ten (Solidity has no decimals).
    /// @param precipMmX10 Precipitation in mm multiplied by ten; both are reported only with force majeure.
    function submitVerification(
        string calldata roofId,
        uint8 status,
        int256 normalizedDeltaCx10,
        uint256 coveragePct,
        bool forceMajeure,
        uint8 phase,
        bytes32 evidenceHash,
        bytes calldata deviceSignature,
        uint256 maxGustMsX10,
        uint256 precipMmX10,
        bytes32 measurementId,
        uint256 measuredAt
    ) external onlyOracle nonReentrant {
        Project storage project = _getProject(roofId);
        if (phase > uint8(Tranche.DURABILITY)) revert InvalidPhase(phase);
        if (coveragePct > PERCENT_BASE) revert InvalidCoverage(coveragePct);
        Tranche tranche = Tranche(phase);
        _checkPhase(project.roofId, tranche, forceMajeure);
        emit VerificationSubmitted(roofId, status, normalizedDeltaCx10, evidenceHash);
        emit VerificationEvidence(roofId, phase, coveragePct, forceMajeure, deviceSignature);
        MeasurementProof memory proof = MeasurementProof(measurementId, measuredAt);
        if (!_acceptMeasurement(project, tranche, forceMajeure, proof)) return;
        bool meetsThresholds = normalizedDeltaCx10 <= project.minNormalizedDeltaCx10
            && coveragePct >= project.minCoveragePct;
        if (forceMajeure) {
            _processForceMajeure(project, status, maxGustMsX10, precipMmX10);
            return;
        }
        if (status != APPROVED_STATUS) {
            emit PaymentHeld(roofId, tranche, "Verification not approved");
            return;
        }
        if (tranche == Tranche.QUALITY) qualityProofs[roofId] = proof;
        _processVerification(project, tranche, meetsThresholds);
    }

    /// @notice Reclaims after one year and, if quality was paid, after the durability
    /// eligibility date plus a protected 30-day contractor claim window.
    function reclaimUnreleased(string calldata roofId) external nonReentrant {
        Project storage project = _getProject(roofId);
        if (msg.sender != project.sponsor) revert NotProjectSponsor(msg.sender);
        uint256 availableAt = project.createdAt + RECLAIM_DELAY;
        uint256 durabilityEndsAt = project.qualityReleasedAt + DURABILITY_DELAY + DURABILITY_CLAIM_WINDOW;
        if (project.qualityReleasedAt != 0 && durabilityEndsAt > availableAt) {
            availableAt = durabilityEndsAt;
        }
        if (block.timestamp < availableAt) revert ReclaimNotYetAvailable(availableAt);
        if (reclaimed[roofId]) revert ProjectClosed(roofId);
        // Never zero: the reserve is only paid on force majeure, which suspends durability.
        uint256 amount = _unreleasedAmount(project);
        reclaimed[roofId] = true;
        emit UnreleasedReclaimed(roofId, project.sponsor, amount);
        (bool success,) = payable(project.sponsor).call{value: amount}("");
        if (!success) revert PaymentFailed(project.sponsor, amount);
    }

    /// @notice Allows operational oracle rotation without changing existing project terms.
    function setOracle(address newOracle) external onlyOwner {
        _setOracle(newOracle);
    }

    /// @notice Exposes the original terms so clients can audit payment decisions.
    function getProject(string calldata roofId) external view returns (Project memory) {
        return _getProject(roofId);
    }

    /// @notice Distinguishes paid tranches from funds still held in escrow.
    function getTrancheStatus(string calldata roofId, Tranche tranche) external view returns (bool) {
        _getProject(roofId);
        return released[roofId][tranche];
    }

    /// @notice A suspended durability tranche remains unpaid after a reserve payout.
    function isDurabilitySuspended(string calldata roofId) external view returns (bool) {
        _getProject(roofId);
        return durabilitySuspended[roofId];
    }

    /// @notice A reclaimed project accepts no further verifications.
    function isReclaimed(string calldata roofId) external view returns (bool) {
        _getProject(roofId);
        return reclaimed[roofId];
    }

    function _setOracle(address newOracle) private {
        if (newOracle == address(0) || newOracle == address(this)) revert InvalidAddress();
        emit OracleUpdated(oracle, newOracle);
        oracle = newOracle;
    }

    function _acceptMeasurement(Project storage project, Tranche tranche, bool storm, MeasurementProof memory proof)
        private returns (bool)
    {
        string memory roofId = project.roofId;
        if (proof.id == bytes32(0) || proof.measuredAt == 0 || proof.measuredAt > block.timestamp) {
            emit PaymentHeld(roofId, tranche, "Invalid measurement identity or time");
            return false;
        }
        if (tranche == Tranche.QUALITY || !released[roofId][Tranche.QUALITY]) return true;
        MeasurementProof storage quality = qualityProofs[roofId];
        if (proof.id == quality.id || proof.measuredAt <= quality.measuredAt) {
            emit PaymentHeld(roofId, tranche, "A new durability measurement is required");
            return false;
        }
        uint256 eligibleAt = project.qualityReleasedAt + DURABILITY_DELAY;
        if (!storm && block.timestamp >= eligibleAt && proof.measuredAt < eligibleAt) {
            emit PaymentHeld(roofId, tranche, "Durability measurement predates eligibility");
            return false;
        }
        return true;
    }

    function _getProject(string memory roofId) private view returns (Project storage project) {
        project = projects[roofId];
        if (!project.exists) revert ProjectNotFound(roofId);
    }

    function _checkPhase(string memory roofId, Tranche tranche, bool forceMajeure) private view {
        if (reclaimed[roofId]) revert ProjectClosed(roofId);
        if (forceMajeure && tranche == Tranche.QUALITY) revert InvalidForceMajeurePhase();
        if (released[roofId][tranche] || durabilitySuspended[roofId]) {
            revert PhaseAlreadySettled(roofId, tranche);
        }
    }

    function _processVerification(Project storage project, Tranche tranche, bool meetsThresholds) private {
        string memory roofId = project.roofId;
        if (tranche == Tranche.DURABILITY) {
            if (!released[roofId][Tranche.QUALITY]) {
                emit PaymentHeld(roofId, tranche, "Quality tranche not released");
                return;
            }
            if (block.timestamp < project.qualityReleasedAt + DURABILITY_DELAY) {
                emit PaymentHeld(roofId, tranche, "Durability period not elapsed");
                return;
            }
        }
        if (!meetsThresholds) {
            emit PaymentHeld(roofId, tranche, "Measurement thresholds not met");
            return;
        }
        _releaseTranche(project, tranche);
    }

    function _applyForceMajeure(Project storage project, uint256 maxGustMsX10, uint256 precipMmX10) private {
        durabilitySuspended[project.roofId] = true;
        emit ForceMajeureApplied(project.roofId, maxGustMsX10, precipMmX10);
        emit PaymentHeld(project.roofId, Tranche.DURABILITY, "Durability suspended by force majeure");
        _releaseTranche(project, Tranche.FORCE_MAJEURE_RESERVE);
    }

    function _processForceMajeure(Project storage project, uint8 status, uint256 gustX10, uint256 rainX10) private {
        bool extremeWeather = gustX10 > FORCE_MAJEURE_GUST_MS_X10 || rainX10 > FORCE_MAJEURE_PRECIP_MM_X10;
        if (status != FORCE_MAJEURE_STATUS || !extremeWeather) {
            emit PaymentHeld(project.roofId, Tranche.DURABILITY, "Force majeure evidence not accepted");
            return;
        }
        if (!released[project.roofId][Tranche.QUALITY]) {
            emit PaymentHeld(project.roofId, Tranche.DURABILITY, "Quality tranche not released");
            return;
        }
        _applyForceMajeure(project, gustX10, rainX10);
    }

    function _trancheAmount(Project storage project, Tranche tranche) private view returns (uint256) {
        uint256 qualityAmount = project.totalAmount * QUALITY_PERCENT / PERCENT_BASE;
        uint256 durabilityAmount = project.totalAmount * DURABILITY_PERCENT / PERCENT_BASE;
        // Assign rounding dust to the reserve so project allocations sum to the deposit.
        if (tranche == Tranche.QUALITY) return qualityAmount;
        if (tranche == Tranche.DURABILITY) return durabilityAmount;
        return project.totalAmount - qualityAmount - durabilityAmount;
    }

    function _unreleasedAmount(Project storage project) private view returns (uint256 amount) {
        for (uint8 index = 0; index <= uint8(Tranche.FORCE_MAJEURE_RESERVE); index++) {
            Tranche tranche = Tranche(index);
            if (!released[project.roofId][tranche]) amount += _trancheAmount(project, tranche);
        }
    }

    function _releaseTranche(Project storage project, Tranche tranche) private {
        if (released[project.roofId][tranche]) revert PhaseAlreadySettled(project.roofId, tranche);
        uint256 amount = _trancheAmount(project, tranche);
        released[project.roofId][tranche] = true;
        if (tranche == Tranche.QUALITY) project.qualityReleasedAt = block.timestamp;
        emit TrancheReleased(project.roofId, tranche, amount, project.contractor);
        (bool success,) = payable(project.contractor).call{value: amount}("");
        if (!success) revert PaymentFailed(project.contractor, amount);
    }
}
