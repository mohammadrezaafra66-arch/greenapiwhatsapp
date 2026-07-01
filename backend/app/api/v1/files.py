"""
File upload endpoint: upload a file to Green API storage, get back a URL.
The URL can then be used in sendFileByUrl campaigns.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.account import Account, AccountStatus
from app.models.inbox import UploadedFile
from app.services.green_api import GreenAPIClient

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload/{account_id}")
async def upload_file(
    account_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """Upload file to Green API storage. Returns a URL usable in campaigns as image_url."""
    account = await db.get(Account, uuid.UUID(account_id))
    if not account or account.status != AccountStatus.active:
        raise HTTPException(400, "Account not found or not active")

    client = GreenAPIClient(account.instance_id, account.api_token)
    content = await file.read()
    green_url = await client.upload_file(content, file.filename)

    if not green_url:
        raise HTTPException(500, "Upload failed — Green API returned no URL")

    record = UploadedFile(
        account_id=uuid.UUID(account_id),
        original_filename=file.filename,
        green_api_url=green_url
    )
    db.add(record)
    await db.commit()

    return {"url": green_url, "filename": file.filename}


@router.get("/list/{account_id}")
async def list_uploaded_files(account_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(UploadedFile)
        .where(UploadedFile.account_id == uuid.UUID(account_id))
        .order_by(UploadedFile.uploaded_at.desc())
        .limit(50)
    )
    files = result.scalars().all()
    return [
        {"id": str(f.id), "filename": f.original_filename, "url": f.green_api_url, "uploaded_at": str(f.uploaded_at)}
        for f in files
    ]
