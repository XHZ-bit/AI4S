import pymupdf
from fastapi import APIRouter, HTTPException, UploadFile, Response
from fastapi.responses import FileResponse

from app import preferences
from app.tenancy import data_dir

router = APIRouter(prefix="/api/preferences", tags=["preferences"])


@router.get("")
def get_preferences(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return preferences.public()


@router.put("")
def update_preferences(req: preferences.Preferences):
    try:
        return preferences.save(req)
    except ValueError as exc:
        raise HTTPException(409 if "其他页面" in str(exc) else 422, str(exc)) from None


@router.post("/avatar")
async def upload_avatar(file: UploadFile):
    raw = await file.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(413, "头像不能超过 2MB")
    # Decode then rasterize; never serve user supplied SVG/HTML or original metadata.
    if not raw.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"RIFF")):
        raise HTTPException(422, "请选择 PNG、JPEG 或 WebP 图片")
    try:
        pix = pymupdf.Pixmap(raw)
        if pix.width * pix.height > 16_000_000:
            raise ValueError("too large")
        if pix.n - pix.alpha > 3:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        factor = min(1, 256 / max(pix.width, pix.height))
        if factor < 1:
            pix = pymupdf.Pixmap(pix, int(pix.width * factor), int(pix.height * factor))
        output = pix.tobytes("png")
    except Exception:
        raise HTTPException(422, "图片无法读取，或尺寸超过 1600 万像素") from None
    path = data_dir() / "avatar.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(output)
    return {"avatar_url": "/api/preferences/avatar"}


@router.get("/avatar")
def avatar():
    path = data_dir() / "avatar.png"
    if not path.is_file():
        raise HTTPException(404, "尚未上传头像")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.delete("/avatar")
def remove_avatar():
    (data_dir() / "avatar.png").unlink(missing_ok=True)
    return {"ok": True}


@router.post("/test-model")
def test_model():
    from app.tutoring import tutor_chat
    try:
        text, model = tutor_chat([{"role": "user", "content": "请只回复：连接成功"}], max_tokens=32)
    except Exception:
        raise HTTPException(502, "连接未通过，请检查已保存的地址、模型名称、密钥和提供商权限") from None
    return {"ok": True, "model": model, "message": text[:120]}
