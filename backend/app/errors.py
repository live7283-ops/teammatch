"""공통 예외 처리 — 일관된 에러 응답 형식 (백엔드1 8번).

FastAPI 기본 에러는 엔드포인트마다 형식이 조금씩 다르다
(HTTPException 은 {"detail": ...}, 검증 오류는 {"detail": [...]}).
프론트가 에러를 일관되게 다룰 수 있도록 아래 한 가지 형식으로 통일한다:

    {
      "error": {
        "code": <HTTP 상태코드>,
        "message": <사람이 읽을 메시지>,
        "detail": <검증 오류 등 추가 정보, 없으면 null>,
        "path": <요청 경로>
      }
    }
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("teammatch")


def _body(code: int, message: str, path: str, detail=None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "detail": detail,
            "path": path,
        }
    }


def register_error_handlers(app: FastAPI) -> None:
    """앱에 공통 예외 핸들러들을 등록한다."""

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(request: Request, exc: StarletteHTTPException):
        # HTTPException(raise 한 404/409/422 등)을 통일 형식으로 감싼다.
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(exc.status_code, str(exc.detail), request.url.path),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(request: Request, exc: RequestValidationError):
        # 요청 본문/파라미터 검증 실패(422). 어떤 필드가 틀렸는지 detail에 담는다.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_body(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "요청 형식이 올바르지 않습니다.",
                request.url.path,
                detail=exc.errors(),
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled_exc(request: Request, exc: Exception):
        # 예상 못 한 서버 오류(500). 내부 스택은 로그로만 남기고,
        # 응답에는 민감 정보를 노출하지 않는다.
        logger.exception("Unhandled error on %s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_body(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "서버 내부 오류가 발생했습니다.",
                request.url.path,
            ),
        )
