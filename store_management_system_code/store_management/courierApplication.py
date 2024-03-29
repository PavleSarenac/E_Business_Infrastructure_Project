from flask import Flask, request, jsonify, Response
from configuration import Configuration, web3, abi, ownerEthereumAddress
from models import database, Order
from flask_jwt_extended import JWTManager, jwt_required
from decorators import roleCheck
from web3.exceptions import ContractLogicError

COURIER_ROLE_ID_STRING = "3"

application = Flask(__name__)
application.config.from_object(Configuration)

jwt = JWTManager(application)


@application.route("/orders_to_deliver", methods=["GET"])
@jwt_required()
@roleCheck(COURIER_ROLE_ID_STRING)
def orders_to_deliver():
    return jsonify(getUndeliveredOrders()), 200


@application.route("/pick_up_order", methods=["POST"])
@jwt_required()
@roleCheck(COURIER_ROLE_ID_STRING)
def pick_up_order():
    errorMessage, errorCode, orderForPickUp = validatePickUpOrderRequest()
    if len(errorMessage) > 0:
        return jsonify(message=errorMessage), errorCode

    confirmOrderPickUp(orderForPickUp)

    return Response(status=200)


def getUndeliveredOrders():
    undeliveredOrders = {"orders": []}
    for order in Order.query.filter(Order.orderStatus == "CREATED").all():
        undeliveredOrders["orders"].append({
            "id": order.id,
            "email": order.buyerEmail
        })
    return undeliveredOrders


def validatePickUpOrderRequest():
    orderId = request.json.get("id", None)
    if orderId is None:
        return "Missing order id.", 400, None
    if type(orderId) is not int or orderId <= 0:
        return "Invalid order id.", 400, None
    orderForPickUp = Order.query.filter(Order.id == orderId).first()
    if not orderForPickUp:
        return "Invalid order id.", 400, None
    if orderForPickUp.orderStatus == "PENDING" or orderForPickUp.orderStatus == "COMPLETE":
        return "Invalid order id.", 400, None
    ethereumCourierAddress = request.json.get("address", None)
    if ethereumCourierAddress is None or ethereumCourierAddress == "":
        return "Missing address.", 400, None
    if not web3.is_address(ethereumCourierAddress):
        return "Invalid address.", 400, None

    ethereumContractDeployed = web3.eth.contract(address=orderForPickUp.ethereumContractAddress, abi=abi)
    try:
        transactionHash = ethereumContractDeployed.functions.courierPickUpOrder(
            ethereumCourierAddress, orderId
        ).transact({
            "from": ownerEthereumAddress  # receno u tekstu da vlasnik snosi troskove vezivanja kurira za ugovor
        })
        web3.eth.wait_for_transaction_receipt(transactionHash)
    except ContractLogicError as contractLogicError:
        contractLogicErrorString = str(contractLogicError)
        return contractLogicErrorString[contractLogicErrorString.find("revert ") + 7:], 400, None

    return "", 0, orderForPickUp


def confirmOrderPickUp(orderForPickUp):
    orderForPickUp.orderStatus = "PENDING"
    database.session.commit()


if __name__ == "__main__":
    database.init_app(application)
    application.run(debug=True, host=Configuration.HOST, port=Configuration.COURIER_APPLICATION_PORT)
