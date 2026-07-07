# TODO: Validate
"""Minimal GAPIClient example.

Run directly:

    uv run python examples/user_client.py
"""

from user_model import UserModel

from good_ass_pydantic_integrator import GAPIClient


class UserClient(GAPIClient[UserModel]):
    """Auto-updating client for ``UserModel``."""

    _response_model = UserModel


if __name__ == "__main__":
    response: dict[str, str | int] = {"id": 1, "name": "Ada", "status": "active"}
    user = UserClient.parse(response)
