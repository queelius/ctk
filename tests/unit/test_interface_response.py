"""
Tests for InterfaceResponse and ResponseStatus helpers from ctk.interfaces.base.
"""

from ctk.interfaces.base import InterfaceResponse, ResponseStatus


class TestInterfaceResponse:
    """Tests for InterfaceResponse helper methods"""

    def test_success_response(self):
        """Test creating a success response"""
        response = InterfaceResponse.success(data={"key": "value"}, message="Success!")

        assert response.status == ResponseStatus.SUCCESS
        assert response.data == {"key": "value"}
        assert response.message == "Success!"

    def test_error_response(self):
        """Test creating an error response"""
        response = InterfaceResponse.error(
            message="Something went wrong", errors=["Error 1"]
        )

        assert response.status == ResponseStatus.ERROR
        assert response.message == "Something went wrong"
        assert "Error 1" in response.errors

    def test_to_dict(self):
        """Test converting response to dictionary"""
        response = InterfaceResponse.success(data={"id": 1}, message="OK")
        result = response.to_dict()

        assert result["status"] == "success"
        assert result["data"] == {"id": 1}
        assert result["message"] == "OK"
