// SPDX-License-Identifier: MIT
pragma solidity 0.8.19;
pragma experimental ABIEncoderV2;

import "@openzeppelin/contracts@4.9.3/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts@4.9.3/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts@4.9.3/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts@4.9.3/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/math/SafeMath.sol";

import "./Utils.sol";

interface IERC3156FlashLender {
    function maxFlashLoan(address token) external returns (uint256);
    function flashLoan(
        address receiver,
        address token,
        uint256 amount,
        bytes calldata data
    ) external returns (bool);
}

interface IERC3156FlashBorrower {
    function onFlashLoan(
        address initiator,
        address token,
        uint256 amount,
        uint256 fee,
        bytes calldata data
    ) external returns (bytes32);
}

interface IAugustusSwapper {
    function multiSwap(Utils.SellData calldata data)
        external
        payable
        returns (uint256);

    function megaSwap(Utils.MegaSwapSellData calldata data)
        external
        payable
        returns (uint256);
}

interface ITokenTransferProxy {
    function transferFrom(
        address token,
        address from,
        address to,
        uint256 amount
    ) external;
}

contract ParaSwapSwapper is IERC3156FlashBorrower {
    using SafeERC20 for IERC20;
    using SafeMath for uint256;

    address private owner;
    address private constant AUGUSTUS_SWAPPER_ADDRESS = 0xDEF171Fe48CF0115B1d80b88dc8eAB59176FEe57;
    address private constant TOKEN_TRANSFER_PROXY_ADDRESS = 0x216B4B4Ba9F3e719726886d34a177484278Bfcae;

    modifier onlyOwner() {
        require(msg.sender == owner, "Not the contract owner");
        _;
    }

    struct FlashCallbackData {
        address lender;
        uint256 loanAmount;
        address srcToken;
        address destToken;
        Utils.MegaSwapSellData path;
    }

    constructor() {
        owner = msg.sender;
    }

    function executeFlashArbitrage(
        address _lender,
        uint256 _loanAmount,
        address _srcToken,
        address _destToken,
        Utils.MegaSwapSellData calldata _path
    ) external onlyOwner {
        IERC3156FlashLender flashLender = IERC3156FlashLender(_lender);
        require(_loanAmount > 0, "Flash loan not available");

        uint256 _allowance = IERC20(_srcToken).allowance(address(this), _lender);
        approve(_srcToken, _lender, _allowance + _loanAmount);

        bytes memory data = abi.encode(
            FlashCallbackData({
                lender: _lender,
                loanAmount: _loanAmount,
                srcToken: _srcToken,
                destToken: _destToken,
                path: _path
            })
        );

        require(flashLender.flashLoan(address(this), _srcToken, _loanAmount, data), "Flash loan failed");
    }

    function onFlashLoan(
        address initiator,
        address token,
        uint256 amount,
        uint256 fee,
        bytes calldata data
    ) external override returns (bytes32) {
        require(initiator == address(this), "Invalid loan initiator");

        FlashCallbackData memory decoded = abi.decode(data, (FlashCallbackData));
        address lender = decoded.lender;
        uint256 acquiredAmount = decoded.loanAmount;
        address srcToken = decoded.srcToken;
        Utils.MegaSwapSellData memory path = decoded.path;

        require(token == srcToken, "Invalid token returned");
        require(amount == acquiredAmount, "Invalid loan amount returned");
        require(msg.sender == lender, "Unauthorized Lender");

        uint256 swappedAmount = megaSwap(srcToken, acquiredAmount, path);

        IERC20(srcToken).safeTransfer(owner, swappedAmount - acquiredAmount);
        return keccak256('ERC3156FlashBorrower.onFlashLoan');
    }

    function megaSwap(
        address _srcToken,
        uint256 _loanAmount,
        Utils.MegaSwapSellData memory _path
    ) internal returns (uint256) {
        // Approve TokenTransferProxy to spend fromToken
        approve(_srcToken, TOKEN_TRANSFER_PROXY_ADDRESS, _loanAmount);

        ITokenTransferProxy(TOKEN_TRANSFER_PROXY_ADDRESS).transferFrom(
            _srcToken,
            address(this),
            AUGUSTUS_SWAPPER_ADDRESS,
            _loanAmount
        );

        uint256 receivedAmount = IAugustusSwapper(AUGUSTUS_SWAPPER_ADDRESS).megaSwap(_path);

        return receivedAmount;
    }

    function approve(address token, address spender, uint256 amount) internal {
        IERC20(token).approve(spender, amount);
    }
}
