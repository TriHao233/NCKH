class AppException(Exception):
    """Exception nghiệp vụ cơ sở, mang theo status_code HTTP tương ứng."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppException):
    def __init__(self, message: str = "Không tìm thấy tài nguyên"):
        super().__init__(message, status_code=404)


class UnauthorizedError(AppException):
    def __init__(self, message: str = "Không có quyền truy cập"):
        super().__init__(message, status_code=401)
