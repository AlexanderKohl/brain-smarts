"""Google Drive search/read/export/download and explicit write helpers."""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path
from typing import Any

from _cli_common import add_account_arg, print_json
from google_oauth import GoogleConnection, GoogleOAuthError


EXPORT_MIME = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ),
    "application/vnd.google-apps.drawing": "image/png",
}


def _service(account: str | None) -> Any:
    return GoogleConnection.from_environment(account).build_service("drive", "v3")


def cmd_search(args: argparse.Namespace) -> int:
    service = _service(args.account)
    response = (
        service.files()
        .list(
            q=args.query,
            pageSize=args.max,
            fields="files(id,name,mimeType,modifiedTime,owners,webViewLink,size)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    print_json(response)
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    service = _service(args.account)
    meta = (
        service.files()
        .get(
            fileId=args.file_id,
            fields="id,name,mimeType,modifiedTime,owners,webViewLink,size,parents",
            supportsAllDrives=True,
        )
        .execute()
    )
    print_json(meta)
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    from googleapiclient.http import MediaIoBaseDownload

    service = _service(args.account)
    meta = (
        service.files()
        .get(fileId=args.file_id, fields="id,name,mimeType", supportsAllDrives=True)
        .execute()
    )
    output = Path(args.output)
    if output.exists() and not args.force:
        print(f"Refusing to overwrite {output}", file=sys.stderr)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    mime = meta.get("mimeType", "")
    fh = io.BytesIO()
    if mime.startswith("application/vnd.google-apps."):
        export_mime = args.export_mime or EXPORT_MIME.get(mime)
        if not export_mime:
            print(
                f"No default export MIME for {mime}; pass --export-mime.",
                file=sys.stderr,
            )
            return 2
        request = service.files().export_media(fileId=args.file_id, mimeType=export_mime)
    else:
        request = service.files().get_media(fileId=args.file_id, supportsAllDrives=True)
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    output.write_bytes(fh.getvalue())
    print_json(
        {
            "action": "download",
            "file_id": args.file_id,
            "name": meta.get("name"),
            "mimeType": mime,
            "output": str(output),
            "bytes": output.stat().st_size,
        }
    )
    return 0


def cmd_upload(args: argparse.Namespace) -> int:
    if not args.i_approve_write:
        print(
            "Refusing Drive write without --i-approve-write.",
            file=sys.stderr,
        )
        return 3
    from googleapiclient.http import MediaFileUpload

    service = _service(args.account)
    path = Path(args.path)
    if not path.is_file():
        print(f"File not found: {path}", file=sys.stderr)
        return 2
    metadata: dict[str, Any] = {"name": args.name or path.name}
    if args.parent_id:
        metadata["parents"] = [args.parent_id]
    media = MediaFileUpload(str(path), mimetype=args.mime_type, resumable=True)
    created = (
        service.files()
        .create(body=metadata, media_body=media, fields="id,name,mimeType,webViewLink")
        .execute()
    )
    print_json({"action": "upload", "file": created})
    return 0


def cmd_update_content(args: argparse.Namespace) -> int:
    if not args.i_approve_write:
        print(
            "Refusing Drive write without --i-approve-write.",
            file=sys.stderr,
        )
        return 3
    from googleapiclient.http import MediaFileUpload

    service = _service(args.account)
    path = Path(args.path)
    if not path.is_file():
        print(f"File not found: {path}", file=sys.stderr)
        return 2
    media = MediaFileUpload(str(path), mimetype=args.mime_type, resumable=True)
    updated = (
        service.files()
        .update(
            fileId=args.file_id,
            media_body=media,
            fields="id,name,mimeType,modifiedTime,webViewLink",
            supportsAllDrives=True,
        )
        .execute()
    )
    print_json({"action": "update_content", "file": updated})
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="Drive files.list query")
    add_account_arg(search)
    search.add_argument(
        "--query",
        required=True,
        help='Drive query, e.g. "name contains \'brief\' and trashed=false"',
    )
    search.add_argument("--max", type=int, default=20)
    search.set_defaults(func=cmd_search)

    get_meta = sub.add_parser("get", help="Get file metadata")
    add_account_arg(get_meta)
    get_meta.add_argument("--file-id", required=True)
    get_meta.set_defaults(func=cmd_get)

    download = sub.add_parser("download", help="Download or export a file")
    add_account_arg(download)
    download.add_argument("--file-id", required=True)
    download.add_argument("--output", required=True)
    download.add_argument("--export-mime")
    download.add_argument("--force", action="store_true")
    download.set_defaults(func=cmd_download)

    upload = sub.add_parser(
        "upload",
        help="Upload a new file (drive.file scope; explicit approval required)",
    )
    add_account_arg(upload)
    upload.add_argument("--path", required=True)
    upload.add_argument("--name")
    upload.add_argument("--parent-id")
    upload.add_argument("--mime-type", default="application/octet-stream")
    upload.add_argument("--i-approve-write", action="store_true")
    upload.set_defaults(func=cmd_upload)

    update = sub.add_parser(
        "update-content",
        help="Replace file content (explicit approval; preferably app-created files)",
    )
    add_account_arg(update)
    update.add_argument("--file-id", required=True)
    update.add_argument("--path", required=True)
    update.add_argument("--mime-type", default="application/octet-stream")
    update.add_argument("--i-approve-write", action="store_true")
    update.set_defaults(func=cmd_update_content)

    args = parser.parse_args()
    try:
        return args.func(args)
    except GoogleOAuthError as exc:
        print(f"Drive error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
