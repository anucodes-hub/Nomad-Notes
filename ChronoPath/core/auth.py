import os
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import firebase_admin
from firebase_admin import credentials, auth

# Initialize Firebase Admin
try:
    firebase_admin.get_app()
except ValueError:
    try:
        cred = credentials.Certificate("firebase-admin.json")
        firebase_admin.initialize_app(cred)
    except FileNotFoundError:
        print("Warning: firebase-admin.json not found. Firebase features may not work during testing.")

from config import get_settings
import logging

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> str:
    settings = get_settings()
    
    # Local development bypass
    if settings.environment.lower() == "development" and settings.local_auth_bypass:
        logger.warning("WARNING: Development authentication mode active; Firebase verification is bypassed.")
        print("WARNING: Development authentication mode active; Firebase verification is bypassed.")
        return "local-dev-user"

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
    try:
        # Verify the Firebase ID token
        decoded_token = auth.verify_id_token(token)
        uid = decoded_token.get("uid")
        if not uid:
            raise credentials_exception
        return uid
    except Exception as e:
        print(f"Firebase token verification failed: {e}")
        raise credentials_exception
