.PHONY: all build push

NAME     := rosscdh/infra-provisioner
REGISTRY := 'hub.docker.com'
TAG      := $$(git log -1 --pretty=%h)
VERSION  := ${NAME}:${TAG}
LATEST   := ${NAME}:latest

BUILD_REPO_ORIGIN=$$(git config --get remote.origin.url)
BUILD_COMMIT_SHA1:=$$(git rev-parse --short HEAD)
BUILD_COMMIT_DATE:=$$(git log -1 --date=short --pretty=format:%ct)
BUILD_BRANCH:=$$(git symbolic-ref --short HEAD)
BUILD_DATE:=$$(date -u +"%Y-%m-%dT%H:%M:%SZ")


all: build


build:
	docker build -t ${LATEST} -t ${REGISTRY}/${LATEST} \
		--build-arg BUILD_COMMIT_SHA1=${BUILD_COMMIT_SHA1} \
		--build-arg BUILD_COMMIT_DATE=${BUILD_COMMIT_DATE} \
		--build-arg BUILD_BRANCH=${BUILD_BRANCH} \
		--build-arg BUILD_DATE=${BUILD_DATE} \
		--build-arg BUILD_REPO_ORIGIN=${BUILD_REPO_ORIGIN} \
		.
push:
	docker push ${REGISTRY}/${LATEST}
	docker rmi ${REGISTRY}/${LATEST}
