"""Dependencies for the VM management service"""
from fastapi import Request


def get_transaction_id(request: Request) -> str:
    """Get the transaction ID from the request state"""
    return request.state.tx_id
