"""final .mp4 + thumbnail -> uploaded (default: private) YouTube video, via Data API v3."""
import google.oauth2.credentials
import googleapiclient.discovery
import googleapiclient.errors
import googleapiclient.http

import config

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _get_service():
    creds = google.oauth2.credentials.Credentials(
        token=None,
        refresh_token=config.YT_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.YT_CLIENT_ID,
        client_secret=config.YT_CLIENT_SECRET,
        scopes=SCOPES,
    )
    return googleapiclient.discovery.build("youtube", "v3", credentials=creds)


def upload_video(video_path: str, title: str, description: str, tags, thumbnail_path: str = None,
                  privacy: str = None):
    """Uploads video_path with the given metadata. Returns the new video's id."""
    youtube = _get_service()
    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags,
            "categoryId": config.DEFAULT_CATEGORY_ID,
        },
        "status": {
            "privacyStatus": privacy or config.DEFAULT_PRIVACY,
            "selfDeclaredMadeForKids": config.MADE_FOR_KIDS,
        },
    }
    media = googleapiclient.http.MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _, response = request.next_chunk()
    video_id = response["id"]

    if thumbnail_path:
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=googleapiclient.http.MediaFileUpload(thumbnail_path),
            ).execute()
        except googleapiclient.errors.HttpError as e:
            # Custom thumbnails require the channel to have completed phone verification.
            # Don't let a thumbnail failure throw away an otherwise-successful upload.
            print(f"  (warning: could not set custom thumbnail, video still uploaded: {e})")

    return video_id
