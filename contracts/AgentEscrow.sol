// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title AgentEscrow — holds native XPL in escrow for marketplace jobs.
contract AgentEscrow {
    enum Status { None, Held, Released, Refunded }

    struct Escrow {
        address client;
        address provider;
        uint256 amount;
        Status status;
    }

    address public judge;
    mapping(bytes32 => Escrow) public escrows;

    event Deposited(bytes32 indexed escrowId, address indexed client, address indexed provider, uint256 amount);
    event Released(bytes32 indexed escrowId, address indexed provider, uint256 amount);
    event Refunded(bytes32 indexed escrowId, address indexed client, uint256 amount);

    modifier onlyJudge() {
        require(msg.sender == judge, "only judge");
        _;
    }

    constructor(address _judge) {
        judge = _judge;
    }

    /// @notice Client deposits XPL into escrow.
    function deposit(bytes32 escrowId, address provider) external payable {
        require(msg.value > 0, "no value");
        require(escrows[escrowId].status == Status.None, "already exists");
        require(provider != address(0), "zero provider");

        escrows[escrowId] = Escrow({
            client: msg.sender,
            provider: provider,
            amount: msg.value,
            status: Status.Held
        });

        emit Deposited(escrowId, msg.sender, provider, msg.value);
    }

    /// @notice Judge releases escrowed funds to the provider.
    function release(bytes32 escrowId) external onlyJudge {
        Escrow storage e = escrows[escrowId];
        require(e.status == Status.Held, "not held");

        e.status = Status.Released;
        uint256 amt = e.amount;

        (bool ok, ) = e.provider.call{value: amt}("");
        require(ok, "transfer failed");

        emit Released(escrowId, e.provider, amt);
    }

    /// @notice Judge refunds escrowed funds to the client.
    function refund(bytes32 escrowId) external onlyJudge {
        Escrow storage e = escrows[escrowId];
        require(e.status == Status.Held, "not held");

        e.status = Status.Refunded;
        uint256 amt = e.amount;

        (bool ok, ) = e.client.call{value: amt}("");
        require(ok, "transfer failed");

        emit Refunded(escrowId, e.client, amt);
    }

    /// @notice View an escrow's details.
    function getEscrow(bytes32 escrowId)
        external
        view
        returns (address client, address provider, uint256 amount, Status status)
    {
        Escrow storage e = escrows[escrowId];
        return (e.client, e.provider, e.amount, e.status);
    }
}
