"""Development-only helpers. Every endpoint here answers 404 unless the mock video provider is active."""

from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.api.deps import VideoProviderDep
from app.core.errors import api_error
from app.services.video import MockVideoProvider

router = APIRouter(prefix="/dev", tags=["dev (mock mode only)"], include_in_schema=False)

# Mock uploads are thrown away anyway; this only stops someone filling the disk/RAM of a dev box
_MAX_MOCK_UPLOAD_BYTES = 2 * 1024**3


@router.post("/mock-video-upload/{video_id}", status_code=201)
async def mock_video_upload(
    video_id: str, request: Request, provider: VideoProviderDep, token: Annotated[str, Query(min_length=10)]
):
    """Stands in for VdoCipher's upload URL: the browser POSTs the multipart form here.

    The body is streamed and discarded (nothing is stored). The one-time `token` in the
    URL plays the role of the signed upload policy of the real provider.
    """
    if not isinstance(provider, MockVideoProvider) or not provider.upload_base_url:
        raise api_error(404, "not_found", "Topilmadi")
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > _MAX_MOCK_UPLOAD_BYTES:
            raise api_error(413, "file_too_large", "Fayl juda katta")
    if not provider.accept_upload(video_id, token):
        raise api_error(403, "invalid_upload_token", "Yuklash havolasi yaroqsiz yoki ishlatilgan")
    return {"status": "uploaded", "bytes": received}
