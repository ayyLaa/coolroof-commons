// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {CoolRoofEscrow} from "../CoolRoofEscrow.sol";

/// @notice Exercises callbacks from a contractor that is also the configured oracle.
contract PaymentReceiver {
    CoolRoofEscrow private immutable escrow;
    // Passing values the test takes from schema/thresholds.json; Solidity cannot read JSON.
    int256 private immutable normalizedDeltaCx10;
    uint256 private immutable coveragePct;
    bool private rejectPayment;
    bool public reentrySucceeded;
    bytes4 public reentryError;
    error PaymentRejected();

    /// @notice Keeps callback tests isolated to a single escrow instance.
    constructor(CoolRoofEscrow target, int256 deltaCx10, uint256 coverage) {
        escrow = target;
        normalizedDeltaCx10 = deltaCx10;
        coveragePct = coverage;
    }

    /// @notice Lets tests prove that failed native-currency calls roll back settlement.
    function setRejectPayment(bool value) external { rejectPayment = value; }

    /// @notice Acts as the oracle to reach the guarded payment callback.
    function verify() external {
        escrow.submitVerification("callback", 0, normalizedDeltaCx10, coveragePct, false, 0, bytes32(0), "", 0, 0, keccak256("callback-proof"), block.timestamp);
    }

    /// @notice Attempts reentry even with oracle privileges to test the guard itself.
    receive() external payable {
        if (rejectPayment) revert PaymentRejected();
        bytes memory result;
        (reentrySucceeded, result) = address(escrow).call(abi.encodeCall(
            escrow.submitVerification, ("callback", 0, normalizedDeltaCx10, coveragePct, false, 0, bytes32(0), bytes(""), 0, 0, keccak256("callback-proof"), block.timestamp)
        ));
        if (result.length >= 4) reentryError = bytes4(result);
    }
}
