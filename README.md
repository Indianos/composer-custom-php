# Composer with a chosen PHP runtime

Publish Composer CLI images to one Docker Hub repository, with independent PHP
and Composer major.minor selection. PHP runs on the official CLI Alpine image;
the Composer binary comes from the official Composer image.

## Tags

With the supplied configuration, `indianos/composer` gets:

| Tag | PHP | Composer |
| --- | --- | --- |
| `latest` | Highest configured PHP minor, latest resolved patch | Highest configured Composer minor, latest resolved patch |
| `phpX.Y` | Latest resolved patch in PHP X.Y | Configured default Composer line |
| `phpX.Y-composerA.B` | Latest resolved patch in PHP X.Y | Latest resolved patch in Composer A.B |

The short PHP tags are generated for every configured PHP line. There are no
PHP patch tags or Composer patch tags. `latest` always points to the highest
configured PHP and Composer minor lines. Minor tags are mutable; pin the
published image digest when you need an immutable deployment.

```sh
docker run --rm -it -v "$PWD:/app" indianos/composer install
docker run --rm --entrypoint php indianos/composer --version
```

Images include Git, SSH client, Bash, unzip, and the PHP zip extension. Other
PHP extensions required by your application must be added in a derived image.
This is a build/dependency-management image, not a production PHP server.

## GitHub and Docker Hub setup

1. Create a Docker Hub repository, such as `indianos/composer`.
2. Set `repository` in [versions.json](versions.json) to your namespace/repository.
3. Add GitHub Actions repository secrets:
   - `DOCKERHUB_USERNAME`: Docker Hub login with access to that repository.
   - `DOCKERHUB_TOKEN`: Docker Hub access token with read/write permission.
4. Push this project to GitHub with `main` or `master` as its default branch.
5. Open **Actions > Composer images > Run workflow** to publish immediately.

The workflow needs no GitHub write permission and does not commit generated
changes. Fork pull requests build and test without access to publishing secrets.
Keep publishing secrets restricted to trusted repository contributors.

## Automatic and manual updates

- **Daily, 04:17 UTC:** resolve the latest official upstream images within every
  configured minor line, test, and publish. Daily rebuilds also refresh Alpine
  packages. GitHub schedules can be delayed; scheduled workflows in inactive
  public repositories may be disabled by GitHub after 60 days.
- **Push to the default `main`/`master` branch:** publish relevant project changes
  using the committed digest lock.
- **Pull request:** validate and smoke-test all combinations, without publishing.
- **Manual:** `refresh=true` fetches new upstream digests; `publish=false` tests
  without pushing. `refresh=false` reproduces the committed upstream inputs.
  Publication is restricted to the default branch, including manual runs.

Every run stores the actual `versions.lock.json` as the `resolved-versions`
artifact for 30 days. Scheduled/manual refreshes update that file in the runner,
not in Git. Download and commit the artifact, or run the refresh command below,
to update the repository's baseline. Digest locks pin upstream PHP and Composer
images, not Alpine packages installed during the build.

New **patch releases** and rebuilt upstream images are picked up automatically.
New **minor/major lines** require an explicit edit to [versions.json](versions.json),
so a PHP or Composer compatibility change is never silently introduced.
Removed lines stop receiving updates; existing Docker Hub tags are not deleted.

## Version files

[versions.json](versions.json) is the source of truth:

- `php`: PHP major.minor lines to track.
- `composer`: Composer major.minor lines to track.
- `default_composer`: line used by the short `phpX.Y` aliases.
- `repository`: destination Docker Hub namespace/repository.
- `platforms`: `linux/amd64`, `linux/arm64`, or both.

[versions.lock.json](versions.lock.json) stores resolved official-image manifest
digests. All PHP/Composer combinations are built. Only one combination per PHP
line owns the short alias. Invalid versions, stale locks, duplicate lines, or
unsupported upstream architectures fail before publishing.

After editing version lines, refresh and commit both files:

```sh
python3 scripts/versions.py refresh
python3 scripts/versions.py validate
python3 scripts/versions.py matrix
python3 -m unittest discover -s tests -v
```

Python 3.9+ is sufficient; the tooling has no third-party dependencies. Refresh
requires network access to Docker Hub. Registry outages, unavailable minor tags,
and rate limits fail the run rather than falling back to unverified images.

## Local build

With Docker running, build one locked combination from the project root:

```bash
read -r PHP_MINOR COMPOSER_MINOR PHP_IMAGE COMPOSER_IMAGE <<< "$(python3 -c '
import json
key = lambda version: tuple(map(int, version.split(".")))
config = json.load(open("versions.json"))
lock = json.load(open("versions.lock.json"))
php = max(config["php"], key=key)
composer = max(config["composer"], key=key)
print(php, composer, lock["php"][php], lock["composer"][composer])
')"
IMAGE="composer-custom:php${PHP_MINOR}-composer${COMPOSER_MINOR}"
docker build --build-arg PHP_IMAGE="$PHP_IMAGE" \
  --build-arg COMPOSER_IMAGE="$COMPOSER_IMAGE" -t "$IMAGE" .
bash tests/smoke.sh "$IMAGE" "$PHP_MINOR" "$COMPOSER_MINOR" linux/amd64
```

Use `--platform linux/arm64` in the build and the smoke test on an ARM64 host.
CI uses QEMU to smoke-test each configured architecture before pushing a
multi-platform manifest. Tests check actual PHP/Composer minor versions,
required extensions, the default entrypoint, and an offline Composer install.

Containers run as root by default. To avoid root-owned files on Linux:

```sh
docker run --rm -it --user "$(id -u):$(id -g)" \
  -v "$PWD:/app" indianos/composer install
```

Allowing Composer plugins as root requires explicitly setting
`COMPOSER_ALLOW_SUPERUSER=1`; only do this for trusted dependencies. Mount
credentials or an SSH agent when accessing private repositories. Do not bake
credentials into the image.