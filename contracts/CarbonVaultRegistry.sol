// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract CarbonVaultRegistry {
    struct Record {
        string projectId;
        bytes32 dataHash;
        uint256 timestamp;
        address recorder;
    }

    mapping(string => Record) public records;

    event EvidenceRecorded(
        string indexed projectId,
        bytes32 indexed dataHash,
        uint256 timestamp,
        address indexed recorder
    );

    function recordEvidence(string calldata projectId, bytes32 dataHash) external {
        require(bytes(projectId).length > 0, "project id required");
        require(records[projectId].timestamp == 0, "project already recorded");

        records[projectId] = Record({
            projectId: projectId,
            dataHash: dataHash,
            timestamp: block.timestamp,
            recorder: msg.sender
        });

        emit EvidenceRecorded(projectId, dataHash, block.timestamp, msg.sender);
    }
}
