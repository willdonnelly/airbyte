# build
DOCKER_BUILD_PLATFORM=linux/amd64 ALPINE_IMAGE=amd64/alpine:3.14 DOCKER_BUILD_ARCH=amd64 ./gradlew :airbyte-integrations:connectors:$1:build

# publish to :dev tag
# docker tag docker.io/airbyte/$1:dev ghcr.io/estuary/airbyte-$1:dev && docker push ghcr.io/estuary/airbyte-$1:dev
