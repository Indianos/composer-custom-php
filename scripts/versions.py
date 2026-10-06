#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
SERIES = re.compile(r"[1-9][0-9]*\.[0-9]+")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
REPOSITORY = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*/[a-z0-9]+(?:[._-][a-z0-9]+)*")
MEDIA_TYPES = ", ".join([
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
])


def load_config(path):
    config = json.loads(Path(path).read_text())
    if not isinstance(config, dict):
        raise ValueError("Configuration must be an object")
    for technology in ("php", "composer"):
        versions = config.get(technology)
        if not isinstance(versions, list) or not versions:
            raise ValueError(f"{technology} must contain at least one major.minor version")
        if any(not isinstance(version, str) or not SERIES.fullmatch(version) for version in versions):
            raise ValueError(f"{technology} versions must be major.minor, without patch versions")
        if len(set(versions)) != len(versions):
            raise ValueError(f"Duplicate {technology} versions")
    if config.get("default_composer") not in config["composer"]:
        raise ValueError("default_composer must be a configured Composer version")
    if not isinstance(config.get("repository"), str) or not REPOSITORY.fullmatch(config["repository"]):
        raise ValueError("repository must be a lowercase Docker Hub namespace/name")
    platforms = config.get("platforms")
    if not isinstance(platforms, list) or not platforms or len(set(platforms)) != len(platforms):
        raise ValueError("platforms must be a nonempty list without duplicates")
    if any(platform not in ("linux/amd64", "linux/arm64") for platform in platforms):
        raise ValueError("Supported platforms are linux/amd64 and linux/arm64")
    return config


def source_tag(technology, version):
    suffix = "-cli-alpine" if technology == "php" else ""
    return f"{version}{suffix}"


def version_key(version):
    return tuple(int(part) for part in version.split("."))


def validate_lock(config, lock):
    if lock.get("schema") != 1:
        raise ValueError("Unsupported lock schema; run refresh")
    for technology in ("php", "composer"):
        images = lock.get(technology, {})
        if set(images) != set(config[technology]):
            raise ValueError(f"{technology} lock does not match configuration; run refresh")
        for version in config[technology]:
            prefix = f"docker.io/library/{technology}:{source_tag(technology, version)}@"
            image = images[version]
            if not isinstance(image, str) or not image.startswith(prefix) or not DIGEST.fullmatch(image[len(prefix):]):
                raise ValueError(f"Invalid locked image for {technology} {version}")


def build_matrix(config, lock):
    validate_lock(config, lock)
    include = []
    latest_php = max(config["php"], key=version_key)
    latest_composer = max(config["composer"], key=version_key)
    for php in config["php"]:
        for composer in config["composer"]:
            tags = [f"{config['repository']}:{composer}-php{php}"]
            if composer == config["default_composer"]:
                tags.append(f"{config['repository']}:php{php}")
            if php == latest_php and composer == latest_composer:
                tags.append(f"{config['repository']}:latest")
            include.append({
                "php": php,
                "composer": composer,
                "php_image": lock["php"][php],
                "composer_image": lock["composer"][composer],
                "platforms": ",".join(config["platforms"]),
                "tags": "\n".join(tags),
                "local_tag": f"composer-custom:{composer}-php{php}",
            })
    if len(include) > 256:
        raise ValueError("Configuration exceeds GitHub Actions' 256-job matrix limit")
    return {"include": include}


def request(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "composer-custom-php", **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read(), response.headers


def resolve_digest(technology, version, platforms, token):
    tag = source_tag(technology, version)
    payload, headers = request(
        f"https://registry-1.docker.io/v2/library/{technology}/manifests/{tag}",
        {"Authorization": f"Bearer {token}", "Accept": MEDIA_TYPES},
    )
    digest = headers.get("Docker-Content-Digest", "")
    if not DIGEST.fullmatch(digest) or digest != "sha256:" + hashlib.sha256(payload).hexdigest():
        raise ValueError(f"Invalid manifest digest for {technology}:{tag}")
    manifest = json.loads(payload)
    available = set()
    for entry in manifest.get("manifests", []):
        platform = entry.get("platform", {})
        available.add(f"{platform.get('os')}/{platform.get('architecture')}")
    if not set(platforms).issubset(available):
        raise ValueError(f"{technology}:{tag} does not support all configured platforms")
    return f"docker.io/library/{technology}:{tag}@{digest}"


def refresh(config, path):
    lock = {"schema": 1}
    for technology in ("php", "composer"):
        query = urllib.parse.urlencode({
            "service": "registry.docker.io",
            "scope": f"repository:library/{technology}:pull",
        })
        payload, _ = request(f"https://auth.docker.io/token?{query}")
        token = json.loads(payload)["token"]
        lock[technology] = {
            version: resolve_digest(technology, version, config["platforms"], token)
            for version in config[technology]
        }
    validate_lock(config, lock)
    content = json.dumps(lock, indent=2) + "\n"
    path = Path(path)
    changed = not path.exists() or path.read_text() != content
    if changed:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content)
        temporary.replace(path)
    return changed


def main():
    parser = argparse.ArgumentParser(description="Resolve upstream images and generate publication tags")
    parser.add_argument("command", choices=("validate", "refresh", "matrix"))
    parser.add_argument("--config", type=Path, default=ROOT / "versions.json")
    parser.add_argument("--lock", type=Path, default=ROOT / "versions.lock.json")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        if args.command == "refresh":
            changed = refresh(config, args.lock)
            print(f"changed={'true' if changed else 'false'}")
            output = os.environ.get("GITHUB_OUTPUT")
            if output:
                with open(output, "a") as stream:
                    stream.write(f"changed={'true' if changed else 'false'}\n")
        else:
            lock = json.loads(args.lock.read_text())
            matrix = build_matrix(config, lock)
            if args.command == "matrix":
                print(json.dumps(matrix, separators=(",", ":")))
            else:
                print(f"Validated {len(matrix['include'])} PHP/Composer combinations")
    except (ValueError, KeyError, TypeError, OSError, urllib.error.URLError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())