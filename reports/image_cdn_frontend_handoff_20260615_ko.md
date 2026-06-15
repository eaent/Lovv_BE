# 이미지 CDN 프론트 인수인계

## 전달 목적

CloudFront 기반 이미지 CDN을 프론트에서 사용할 때 필요한 URL 규칙과 주의사항을 정리한다.

## 사용해야 하는 값

- CDN base URL: `/lovv/dev/cloudfront/image_base_url`
- 예: `https://dxxxxx.cloudfront.net`

## URL 조합 규칙

프론트는 S3 URL을 직접 사용하지 않는다.

```text
<image_base_url>/<s3-object-key>
```

## 예시

```text
https://dxxxxx.cloudfront.net/content/KR/city/KR-Gangneung/main.webp
https://dxxxxx.cloudfront.net/avatar/user-hash/profile.webp
```

## 프론트 사용 규칙

- 허용 메서드: `GET`, `HEAD`
- S3 bucket URL 직접 사용 금지
- backend/API/DB에서 받은 S3 object key를 CDN base URL과 조합
- `403` 또는 `404` 발생 시 fallback 이미지 사용
- 같은 key의 이미지가 바뀌면 CloudFront cache 때문에 즉시 반영되지 않을 수 있음

## 이미지 용량 기준

- 권장: `0.5MB 이하`
- 마지막 허용선: `1MB 미만`

## fallback

- fallback 이미지 key는 프론트/기획 합의 후 고정
- 예시: `common/fallback.webp`

## 주의

- 기존 S3 파일은 삭제하지 않는다.
- 기존 S3 파일은 덮어쓰지 않는다.
- 기존 S3 파일을 인플레이스 압축하지 않는다.
- 현재 CDN은 읽기 전용 전달 경로다.
- 이미지 리사이즈/압축 산출물 생성 파이프라인은 이번 범위가 아니다.
