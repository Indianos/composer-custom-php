# Composer with a chosen PHP runtime

Run Composer with a selectable PHP CLI version. This image combines the
official Composer binary with the official PHP CLI Alpine image and is intended
for dependency installation and development workflows, not as a production PHP
server.

## Choose an image

The image repository publishes these tag formats:

| Tag | PHP version | Composer version |
| --- | --- | --- |
| `latest` | Highest configured PHP minor line | Highest configured Composer minor line |
| `phpX.Y` | PHP X.Y | Default Composer line (currently 2.10) |
| `A.B-phpX.Y` | PHP X.Y | Composer A.B |

Examples:

- `indianos/composer:latest`
- `indianos/composer:php8.2`
- `indianos/composer:2.10-php8.2`
- `indianos/composer:2.2-php8.2`

Tags select major.minor lines, not patch versions. A tag such as
`2.10-php8.2` tracks the latest resolved patch releases in Composer 2.10 and
PHP 8.2. Tags can move as upstream images are refreshed. For a deployment that
must use an exact image, pull by digest rather than relying on a mutable tag.

## Run Composer

Run Composer in the current project directory by mounting it at `/app`:

```sh
docker run --rm -it \
  -v "$PWD:/app" \
  indianos/composer:2.10-php8.2 install
```

Run a different Composer command by replacing `install`, for example:

```sh
docker run --rm -it -v "$PWD:/app" \
  indianos/composer:2.10-php8.2 update
```

The image entrypoint runs Composer. To run PHP instead, override the
entrypoint:

```sh
docker run --rm --entrypoint php indianos/composer:2.10-php8.2 --version
```

## Included tools

The image includes Composer, PHP CLI, Git, OpenSSH client, Bash, unzip, and the
PHP zip extension. It is based on Alpine Linux and is published for `linux/amd64`
and `linux/arm64`. Add any application-specific PHP extensions in a derived
image; this image does not include a web server or application runtime setup.

## Working principles

- PHP and Composer versions are selected independently through the image tag.
- Tags identify configured minor lines. Patch updates are picked up when the
  upstream images are refreshed. Request additional PHP/Composer lines or
  contribute improvements through the [GitHub repository](https://github.com/Indianos/composer-custom-php)
  by opening an issue or pull request.
- `latest` follows the highest configured PHP and Composer lines. Use an
  explicit tag when you need to select a particular combination.
- Tags are convenient but mutable. Pin the image digest when repeatable pulls
  are more important than automatically receiving updates.
- The image runs as root by default. On Linux, use your host user and group to
  avoid creating root-owned files in a mounted project directory:

  ```sh
  docker run --rm -it --user "$(id -u):$(id -g)" \
    -v "$PWD:/app" indianos/composer:2.10-php8.2 install
  ```

- Composer plugins run as root only when explicitly allowed with
  `COMPOSER_ALLOW_SUPERUSER=1`. Set this only when you trust the dependencies.
- Do not bake credentials into an image. Provide private repository credentials
  or SSH access at runtime, and avoid exposing them to untrusted code.

Composer's home and cache are stored under `/tmp` in the container. They are
discarded when the container exits unless you explicitly mount persistent
storage.