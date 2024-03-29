from fastapi import (
    APIRouter,
    HTTPException,
    Depends,
    status,
    Security,
    Request,
    BackgroundTasks,
)
from fastapi.security import (
    OAuth2PasswordRequestForm,
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.connect import get_db
from src.schemas import UserSchema, UserResponseSchema, TokenModel, RequestEmail, ResetPasswordSchema
from src.repository import auth as repository_auth
from src.services.auth import auth_service
from src.services.email import send_email, send_reset_password_email
from src.conf import messages

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()


@router.post(
    "/signup", response_model=UserResponseSchema, status_code=status.HTTP_201_CREATED
)
async def signup(
    body: UserSchema,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user.

    Args:
        body (UserSchema): The user's registration details.
        background_tasks (BackgroundTasks): Background tasks to run asynchronously.
        request (Request): The HTTP request object.
        db (AsyncSession): The async database session.

    Returns:
        UserResponseSchema: The registered user's details.
    """
    print(f"[d] request={request}")
    exist_user = await repository_auth.get_user_by_email(body.email, db)
    if exist_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=messages.ACCOUNT_EXIST
        )
    body.password = auth_service.get_password_hash(body.password)
    new_user = await repository_auth.create_user(body, db)
    background_tasks.add_task(
        send_email, new_user.email, new_user.username, str(request.base_url)
    )
    return new_user


@router.post("/login", response_model=TokenModel)
async def login(
    body: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)
):
    """
    Log in a user.

    Args:
        body (OAuth2PasswordRequestForm): The login form data.
        db (AsyncSession): The async database session.

    Returns:
        TokenModel: Access and refresh tokens for the user.
    """
    user = await repository_auth.get_user_by_email(body.username, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=messages.INVALID_EMAIL
        )
    if not user.confirmed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=messages.EMAIL_NOT_CONFIRMED,
        )
    if not auth_service.verify_password(body.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=messages.BAD_PASSWORD
        )
    # Generate JWT
    access_token = await auth_service.create_access_token(data={"sub": user.email})
    refresh_token = await auth_service.create_refresh_token(data={"sub": user.email})
    await repository_auth.update_token(user, refresh_token, db)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.get("/refresh_token", response_model=TokenModel)
async def refresh_token(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = Depends(get_db),
):
    """
    Refresh the access token using a refresh token.

    Args:
        credentials (HTTPAuthorizationCredentials): The refresh token from
        the authorization header.
        db (AsyncSession): The async database session.

    Returns:
        TokenModel: New access and refresh tokens.
    """
    token = credentials.credentials
    email = await auth_service.decode_refresh_token(token)
    user = await repository_auth.get_user_by_email(email, db)
    if user.refresh_token != token:
        await repository_auth.update_token(user, None, db)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=messages.BAD_REFRESH_TOKEN
        )

    access_token = await auth_service.create_access_token(data={"sub": email})
    refresh_token = await auth_service.create_refresh_token(data={"sub": email})
    await repository_auth.update_token(user, refresh_token, db)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/request_email")
async def request_email(
    body: RequestEmail,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Request confirmation email for a registered user.

    Args:
        body (RequestEmail): The request body containing the user's email.
        background_tasks (BackgroundTasks): Background tasks to run asynchronously.
        request (Request): The HTTP request object.
        db (AsyncSession): The async database session.

    Returns:
        dict: A message indicating the action taken.
    """
    user = await repository_auth.get_user_by_email(body.email, db)

    if user.confirmed:
        return {"message": messages.EMAIL_ALREADY_CONFIRMED}
    if user:
        background_tasks.add_task(
            send_email, user.email, user.username, request.base_url
        )
    return {"message": messages.CHECK_EMAIL_CONFIRMED}


@router.get("/confirmed_email/{token}")
async def confirmed_email(token: str, db: AsyncSession = Depends(get_db)):
    """
    Confirm a user's email using a confirmation token.

    Args:
        token (str): The confirmation token sent to the user's email.
        db (AsyncSession): The async database session.

    Returns:
        dict: A message indicating the result of the email confirmation.
    """
    email = await auth_service.get_email_from_token(token)
    user = await repository_auth.get_user_by_email(email, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=messages.VERIFICATION_ERROR
        )
    if user.confirmed:
        return {"message": messages.EMAIL_ALREADY_CONFIRMED}
    await repository_auth.confirmed_email(email, db)
    return {"message": messages.EMAIL_CONFIRMED}


@router.post("/reset_password_email")
async def reset_password_email(
    body: RequestEmail,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Send a reset password email to the user's registered email address.

    Args:
        body (RequestEmail): The request body containing the user's email.
        background_tasks (BackgroundTasks): Background tasks to run asynchronously.
        request (Request): The HTTP request object.
        db (AsyncSession): The async database session.

    Returns:
        dict: A message indicating the success of the email sending.
    """
    user = await repository_auth.get_user_by_email(body.email, db)
    background_tasks.add_task(
        send_reset_password_email, user.email, user.username, request.base_url
    )
    return {"message": messages.PASSWORD_RESET_EMAIL_SUCCESS}


@router.post("/reset_password/{token}")
async def reset_password(
    token: str, body: ResetPasswordSchema, db: AsyncSession = Depends(get_db)
):
    """
    Reset the user's password using the provided reset token.

    Args:
        token (str): The reset token obtained from the email.
        body (ResetPasswordSchema): The request body containing the new password.
        db (AsyncSession): The async database session.

    Returns:
        dict: A message indicating the success of the password reset.
    """
    email = await auth_service.get_email_from_token(token)
    user = await repository_auth.get_user_by_email(email, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=messages.USER_NOT_FOUND
        )

    hashed_password = auth_service.get_password_hash(body.new_password)
    await repository_auth.update_user_password(user, hashed_password, db)

    return {"message": messages.PASSWORD_RESET_SUCCESS}
