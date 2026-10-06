# syntax=docker/dockerfile:1
ARG COMPOSER_IMAGE
ARG PHP_IMAGE

FROM ${COMPOSER_IMAGE} AS composer
FROM ${PHP_IMAGE}

RUN apk add --no-cache bash git unzip openssh-client libzip \
    && apk add --no-cache --virtual .build-deps $PHPIZE_DEPS libzip-dev \
    && docker-php-ext-install -j"$(nproc)" zip \
    && apk del .build-deps

COPY --from=composer /usr/bin/composer /usr/local/bin/composer

ENV COMPOSER_HOME=/tmp/composer \
    COMPOSER_CACHE_DIR=/tmp/composer/cache \
    PATH=/tmp/composer/vendor/bin:$PATH

WORKDIR /app
ENTRYPOINT ["docker-php-entrypoint", "composer"]
CMD ["--help"]