import argparse
import brotli
import gzip
import json
import multiprocessing
import os
import re
from collections.abc import Callable
from glob import iglob
from typing import Iterator, Tuple


import boto3

DEFAULT_CONTENT_TYPE = "binary/octet-stream"
HASH_IN_FILENAME_REGEX = re.compile(r".*[\.\-][0-9a-fA-F]+[\..*]+")

s3_client = boto3.client("s3")

MIME_TYPES = {
    "aac": "audio/aac",
    "abw": "application/x-abiword",
    "arc": "application/x-freearc",
    "avif": "image/avif",
    "avi": "video/x-msvideo",
    "azw": "application/vnd.amazon.ebook",
    "bin": "application/octet-stream",
    "bmp": "image/bmp",
    "br": "application/x-br",
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
    "md": "text/markdown",
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
    "yaml": "application/yaml",
    "yml": "application/yaml",
    "zip": "application/zip",
    "3gp": "video/3gpp",
    "3g2": "video/3gpp2",
    "7z": "application/x-7z-compressed",
}

# as per https://developers.cloudflare.com/speed/optimization/content/brotli/content-compression/#compression-between-cloudflare-and-website-visitors
MIME_TYPES_TO_COMPRESS = set(
    [
        "text/html",
        "text/richtext",
        "text/plain",
        "text/css",
        "text/x-script",
        "text/x-component",
        "text/x-java-source",
        "text/x-markdown",
        "application/javascript",
        "application/x-javascript",
        "text/javascript",
        "text/js",
        "image/x-icon",
        "image/vnd.microsoft.icon",
        "application/x-perl",
        "application/x-httpd-cgi",
        "text/xml",
        "application/xml",
        "application/rss+xml",
        "application/vnd.api+json",
        "application/x-protobuf",
        "application/json",
        "multipart/bag",
        "multipart/mixed",
        "application/xhtml+xml",
        "font/ttf",
        "font/otf",
        "font/x-woff",
        "image/svg+xml",
        "application/vnd.ms-fontobject",
        "application/ttf",
        "application/x-ttf",
        "application/otf",
        "application/x-otf",
        "application/truetype",
        "application/opentype",
        "application/x-opentype",
        "application/font-woff",
        "application/eot",
        "application/font",
        "application/font-sfnt",
        "application/wasm",
        "application/javascript-binast",
        "application/manifest+json",
        "application/ld+json",
        "application/graphql+json",
        "application/geo+json",
    ]
)


def _get_mime_type(filename: str) -> str:
    parts = filename.split(".")
    extension = parts[-1]
    if extension in ("gz", "br") and parts[-2] in MIME_TYPES:
        extension = parts[-2]
    return MIME_TYPES.get(extension, DEFAULT_CONTENT_TYPE)


def _should_compress(filename: str) -> bool:
    mime_type = _get_mime_type(filename)
    non_text_compressibles = ["json", "map", "svg", "ico", "yaml", "yml", "xml"]
    compressibles = [
        key for key, value in MIME_TYPES.items() if value.startswith("text")
    ] + non_text_compressibles
    file_ext = filename.split(".")[-1]
    return file_ext in compressibles or (
        mime_type in MIME_TYPES_TO_COMPRESS and file_ext not in ["gz", "br"]
    )


def _get_args() -> Tuple[str, str]:
    parser = argparse.ArgumentParser(
        description="Copy a local directory to S3 with guessed Content-Types"
    )
    parser.add_argument(
        "-c",
        "--compress",
        action="store_true",
        default=False,
        help="compress compressable files using brotli and gzip",
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
    compress = args.compress
    source = args.source[0]
    if source.endswith("/"):
        source = source[:-1]
    destination = args.destination[0]
    if destination.endswith("/"):
        destination = destination[:-1]
    return compress, source, destination


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
    # cache image/video and audio files for half an hour
    elif (
        content_type.startswith("image/")
        or content_type.startswith("video/")
        or content_type.startswith("audio/")
    ):
        return "max-age=1800"
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
    print(
        f"upload: {filename} s3://{bucket}/{key}, Content-Type={content_type}, Cache-Control={cache_control}"
    )
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


def _compress_file(filename: str) -> list[str]:
    if _should_compress(filename):
        with open(filename, "rb") as f_input:
            data = f_input.read()
        brotli_data = brotli.compress(data, quality=11)
        gzip_data = gzip.compress(data, compresslevel=9)
        with open(f"{filename}.br", "wb") as f_output:
            f_output.write(brotli_data)
        with open(f"{filename}.gz", "wb") as f_output:
            f_output.write(gzip_data)
        return filename
    else:
        return None


def _upload(filename: str, bucket: str, path: str, source_dir: str) -> None:
    key = f'{path}{filename.replace(source_dir, "").replace("//", "/")}'
    # a hack to fix uploads going  "/" folder instead of root folder
    if key.startswith("/"):
        key = key[1:]
    _copy(filename=filename, bucket=bucket, key=key)


def s3autocp():
    compress, source, destination = _get_args()
    bucket_name, path = _get_bucket_name_and_path(
        destination=destination, source=source
    )
    # sort filenames so that files matching index.htm are last.
    # This ensures that new index.html pointing to new hashed files is not served prior to hashed files being uploaded
    filenames = sorted(
        _get_filenames(source_dir=source),
        key=lambda filename: "index.htm" in filename,
    )
    if compress:
        print("compressing files...", end="")
        pool = multiprocessing.Pool()
        compressed_files = pool.map(_compress_file, filenames)
        pool.close()
        pool.join()
        print("done!")
        for filename in compressed_files:
            if filename:
                filenames += [f"{filename}.br", f"{filename}.gz"]
    filenames = set(filenames)
    for filename in sorted(filenames):
        _upload(filename=filename, bucket=bucket_name, path=path, source_dir=source)


if __name__ == "__main__":
    s3autocp()
