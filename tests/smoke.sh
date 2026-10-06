#!/usr/bin/env bash
set -euo pipefail

image=${1:?Usage: bash tests/smoke.sh IMAGE PHP_MINOR COMPOSER_MINOR PLATFORM}
php_version=${2:?PHP major.minor is required}
composer_version=${3:?Composer major.minor is required}
platform=${4:?Platform is required}
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

docker run --rm --platform "$platform" --entrypoint php "$image" -r '
    if (PHP_MAJOR_VERSION . "." . PHP_MINOR_VERSION !== $argv[1]) {
        fwrite(STDERR, "Unexpected PHP version: " . PHP_VERSION . "\n");
        exit(1);
    }
    foreach (["zip", "openssl", "Phar", "iconv", "zlib"] as $extension) {
        if (!extension_loaded($extension)) {
            fwrite(STDERR, "Missing extension: " . $extension . "\n");
            exit(1);
        }
    }
    echo "PHP " . PHP_VERSION . " verified\n";
' "$php_version"

output=$(docker run --rm --platform "$platform" "$image" --version --no-ansi)
printf '%s\n' "$output"
case "$output" in
    "Composer version ${composer_version}."*) ;;
    *) printf 'Unexpected Composer version; expected %s.x\n' "$composer_version" >&2; exit 1 ;;
esac

docker run --rm --platform "$platform" \
    --env COMPOSER_ALLOW_SUPERUSER=1 \
    --volume "$root/tests/fixtures:/fixture:ro" \
    --entrypoint sh "$image" -ec '
        cp /fixture/composer.json /app/composer.json
        composer install --no-interaction --no-progress
        composer validate --strict --no-interaction
        php -r '\''require "/app/vendor/autoload.php"; echo "Autoloader verified\n";'\''
    '