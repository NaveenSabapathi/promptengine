from flask import jsonify


class APIError(Exception):
    def __init__(self, code, message, status=400):
        self.code, self.message, self.status = code, message, status


def error_response(code, message, status):
    return jsonify(error={"code": code, "message": message}), status
