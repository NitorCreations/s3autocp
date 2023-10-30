# s3autocp

`s3autocp` is a Python script designed to automate the process of copying local directories to Amazon S3 with appropriate Content-Type headers and optional compression. This script is especially useful for deploying static assets, applying suitable MIME types, and ensuring efficient transfer and storage with Brotli and Gzip compression.

## Features

- **Content-Type Guessing:** Automatically determines the Content-Type for files based on their extensions.
- **Compression:** Compresses eligible files using Brotli and Gzip for optimized storage and transfer.
- **S3 Upload:** Efficiently uploads files to a specified S3 bucket, setting appropriate headers like Cache-Control.
- **Command-Line Interface:** Easy-to-use CLI for specifying source directory and destination S3 URL.

## Requirements

- Python 3.9
- `boto3` library
- `brotli` library
- AWS credentials configured (typically via environment variables or AWS CLI)

## Installation

Make sure you have Python 3 installed. Then, install the required dependencies:

```bash
pip install s3autocp
```

## Development

```bash
pip install boto3 brotli
```

## Usage

```s3autocp [-c/--compress] <source_directory> <destination_s3_url>```

- `-c/--compress`: Enable compression for appropriate file types
- `<source_directory>`: The local directory you wish to copy to S3.
- `<destination_s3_url>`: The S3 URL where files will be uploaded, in the format `s3://bucket-name/path`.

## Example

```s3autocp ./my-local-dir s3://my-bucket/my-path```

This command will copy all files from `./my-local-dir` to the S3 bucket `my-bucket` under the `my-path` directory.

## How It Works

1. The script scans the source directory recursively for files.
2. Determines the MIME type for each file.
3. If you are using the `-c/--compress`-flag, compresses eligible files using Brotli and Gzip.
4. Uploads files to the specified S3 bucket with appropriate Content-Type and Cache-Control headers.

## Contributing

Contributions, issues, and feature requests are welcome. Feel free to check [issues page](https://github.com/NitorCreations/s3autocp/issues) if you want to contribute.

## License

Distributed under the Apache License. See `LICENSE` for more information.
