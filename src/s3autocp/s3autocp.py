import argparse
import json
import os
import re
from glob import iglob
from typing import Iterator, Tuple


import boto3

DEFAULT_CONTENT_TYPE = "binary/octet-stream"
HASH_IN_FILENAME_REGEX = re.compile(r".*[\.\-][0-9a-fA-F]+[\..*]+")

s3_client = boto3.client("s3")


def _get_mime_type(filename: str) -> str:
    mime_types = {
        "aac": "audio/aac",
        "abw": "application/x-abiword",
        "arc": "application/x-freearc",
        "avif": "image/avif",
        "avi": "video/x-msvideo",
        "azw": "application/vnd.amazon.ebook",
        "bin": "application/octet-stream",
        "bmp": "image/bmp",
        "bz": "application/x-bzip",
        "bz2": "application/x-bzip2",
        "cda": "application/x-cdf",
        "csh": "application/x-csh",
        "css": "text/css",
        "csv": "text/csv",
        "doc": "application/msword",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "eot": "application/vnd.ms-fontobject",
        "epub": "application/epub+zip",
        "gz": "application/gzip",
        "gif": "image/gif",
        "htm": "text/html",
        "html": "text/html",
        "ico": "image/vnd.microsoft.icon",
        "ics": "ext/calendar",
        "jar": "application/java-archive",
        "jpeg": "image/jpeg",
        "jpg": "image/jpeg",
        "js": "text/javascript",
        "json": "application/json",
        "jsonld": "application/ld+json",
        "map": "application/json",
        "mid": "audio/midi",
        "midi": "audio/midi",
        "mjs": "text/javascript",
        "mp3": "audio/mpeg",
        "mp4": "video/mp4",
        "mpeg": "video/mpeg",
        "mpkg": "application/vnd.apple.installer+xml",
        "odp": "application/vnd.oasis.opendocument.presentation",
        "ods": "application/vnd.oasis.opendocument.spreadsheet",
        "odt": "application/vnd.oasis.opendocument.text",
        "oga": "audio/ogg",
        "ogv": "video/ogg",
        "ogx": "application/ogg",
        "opus": "audio/opus",
        "otf": "font/otf",
        "png": "image/png",
        "pdf": "application/pdf",
        "php": "application/x-httpd-php",
        "ppt": "application/vnd.ms-powerpoint",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "rar": "application/vnd.rar",
        "rtf": "application/rtf",
        "sh": "application/x-sh",
        "svg": "image/svg+xml",
        "tar": "application/x-tar",
        "tif": "image/tiff",
        "tiff": "image/tiff",
        "ts": "video/mp2t",
        "ttf": "font/ttf",
        "txt": "text/plain",
        "vsd": "application/vnd.visio",
        "wav": "audio/wav",
        "weba": "audio/webm",
        "webm": "video/webm",
        "webp": "image/webp",
        "woff": "font/woff",
        "woff2": "font/woff2",
        "xhtml": "application/xhtml+xml",
        "xls": "application/vnd.ms-excel",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xml": "application/xml",
        "xul": "application/vnd.mozilla.xul+xml",
        "zip": "application/zip",
        "3gp": "video/3gpp",
        "3g2": "video/3gpp2",
        "7z": "application/x-7z-compressed",
    }
    parts = filename.split(".")
    extension = parts[-1]
    if extension in ("gz", "br") and parts[-2] in mime_types:
        extension = parts[-2]
    return mime_types.get(extension, DEFAULT_CONTENT_TYPE)


def _get_args() -> Tuple[str, str]:
    parser = argparse.ArgumentParser(
        description="Copy a local directory to S3 with guessed Content-Types"
    )
    parser.add_argument(
        "source", metavar="source", type=str, nargs=1, help="source directory"
    )
    parser.add_argument(
        "destination",
        metavar="destination",
        type=str,
        nargs=1,
        help="destination s3 url",
    )
    args = parser.parse_args()
    source = args.source[0]
    if source.endswith("/"):
        source = source[:-1]
    destination = args.destination[0]
    if destination.endswith("/"):
        destination = destination[:-1]
    return source, destination


def _get_filenames(source_dir: str) -> Iterator[str]:
    if source_dir[-1] != "/":
        source_dir += "/"
    path = source_dir + "/**/*"
    return (f for f in iglob(path, recursive=True) if not os.path.isdir(f))


def _filename_contains_hash(filename: str) -> bool:
    return bool(HASH_IN_FILENAME_REGEX.match(filename))


def _get_cache_control(filename: str, content_type: str) -> str:
    if _filename_contains_hash(filename=filename) or content_type.startswith("font/"):
        return "max-age=31536000, immutable"
    else:
        return "no-cache"


def _get_bucket_name_and_path(destination: str, source: str) -> Tuple[str, str]:
    if destination.startswith("s3://"):
        destination = destination[5:]
    parts = destination.split("/")
    bucket_name = parts[0]
    path = "/".join(parts[1:])
    return bucket_name, path


def _copy(filename: str, bucket: str, key: str) -> None:
    content_type = _get_mime_type(filename=filename)
    cache_control = _get_cache_control(filename=filename, content_type=content_type)
    res = s3_client.put_object(
        Body=open(filename, "rb"),
        Bucket=bucket,
        Key=key,
        CacheControl=cache_control,
        ContentType=content_type,
    )
    if res["ResponseMetadata"]["HTTPStatusCode"] != 200:
        raise RuntimeError(
            f"Unable to upload {filename}. Response:\n{json.dumps(res, indent=2, default=str)}"
        )


def s3autocp():
    source, destination = _get_args()
    bucket_name, path = _get_bucket_name_and_path(
        destination=destination, source=source
    )
    # sort filenames so that files matching index.htm are last.
    # This ensures that new index.html pointing to new hashed files is not served prior to hashed files being uploaded
    filenames = sorted(
        _get_filenames(source_dir=source),
        key=lambda filename: "index.htm" in filename,
    )
    for filename in filenames:
        key = f'{path}{filename.replace(source, "").replace("//", "/")}'
        if key.startswith("/"):
            key = key[1:]
        _copy(filename=filename, bucket=bucket_name, key=key)
        print(f"upload: {filename} s3://{bucket_name}/{key}")


if __name__ == "__main__":
    s3autocp()
