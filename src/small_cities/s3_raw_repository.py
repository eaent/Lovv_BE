import json
import os

from small_cities.mapper import build_city_api_record, is_usable_image_url, read_number


DEFAULT_BUCKET = "lovv-data-pipeline-dev-925273580929"
DEFAULT_PREFIX = "raw/KR/details/20260609/"
NOT_FOUND_ERROR_CODES = {"NoSuchKey", "NoSuchBucket", "NotFound", "404"}
UPSTREAM_ERROR_CODES = {"AccessDenied", "SlowDown", "Throttling", "ThrottlingException", "RequestTimeout", "ServiceUnavailable", "InternalError"}


class CityDataRepositoryError(Exception):
    def __init__(self, code, message, status_code):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class CityDataNotFoundError(CityDataRepositoryError):
    def __init__(self):
        super().__init__("NOT_FOUND", "Small city was not found.", 404)


class CityDataUpstreamError(CityDataRepositoryError):
    def __init__(self):
        super().__init__("UPSTREAM_UNAVAILABLE", "Small-city source data is unavailable.", 502)


class CityDataInvalidError(CityDataRepositoryError):
    def __init__(self):
        super().__init__("INTERNAL_ERROR", "Small-city source data is invalid.", 500)


class S3RawCityRepository:
    def __init__(self, bucket, prefix, s3_client=None):
        self.bucket = bucket
        self.prefix = _normalize_prefix(prefix)
        self.s3 = s3_client or _s3_client()
        self._city_records = None

    @classmethod
    def from_env(cls):
        return cls(
            bucket=os.environ.get("MAP_CITY_S3_BUCKET", DEFAULT_BUCKET),
            prefix=os.environ.get("MAP_CITY_S3_PREFIX", DEFAULT_PREFIX),
        )

    def list_city_records(self):
        if self._city_records is not None:
            return list(self._city_records)

        records = []
        for key in self._list_city_keys():
            try:
                records.append(self._build_city_record_from_document(self._read_document(key), key))
            except (CityDataInvalidError, KeyError, TypeError, ValueError):
                continue

        self._city_records = records
        return list(records)

    def get_city_record(self, city_id):
        key = self._city_key(city_id)
        try:
            return self._build_city_record_from_document(self._read_document(key), key)
        except CityDataNotFoundError:
            return None
        except (KeyError, TypeError, ValueError) as error:
            raise CityDataInvalidError() from error

    def get_city_places(self, city_id):
        key = self._city_key(city_id)
        try:
            document = self._read_document(key)
        except CityDataNotFoundError:
            return None
        except (KeyError, TypeError, ValueError) as error:
            raise CityDataInvalidError() from error

        try:
            city_record = document.get("city_record") or {}
            records = document.get("records") or []
            attractions = [_place_from_item(item, "attraction") for item in records if item.get("entity_type") == "attraction"]
            festivals = [_place_from_item(item, "festival") for item in records if item.get("entity_type") == "festival"]
            attractions = [place for place in attractions if place is not None]
            festivals = [place for place in festivals if place is not None]
        except (AttributeError, TypeError, ValueError) as error:
            raise CityDataInvalidError() from error

        return {
            "cityId": document.get("city_id") or city_record.get("city_id") or city_id,
            "cityName": _display_city_name(city_record),
            "summary": _summary(city_record, records),
            "attractions": attractions,
            "festivals": festivals,
        }

    def _build_city_record_from_document(self, document, key):
        city_record = document.get("city_record") or {}
        items = document.get("records") or []
        record = build_city_api_record(city_record, items, source="S3RawCityDetails", source_key=key)
        record["detail_summary"] = _summary(city_record, items)
        return record

    def _list_city_keys(self):
        keys = []
        request = {"Bucket": self.bucket, "Prefix": self.prefix}
        while True:
            try:
                response = self.s3.list_objects_v2(**request)
            except Exception as error:
                raise _repository_error_from_client_error(error) from error
            for item in response.get("Contents") or []:
                key = item.get("Key")
                if key and key.endswith(".json"):
                    keys.append(key)
            token = response.get("NextContinuationToken")
            if not token:
                break
            request["ContinuationToken"] = token
        return keys

    def _read_document(self, key):
        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=key)
        except Exception as error:
            raise _repository_error_from_client_error(error) from error
        try:
            payload = response["Body"].read().decode("utf-8")
            parsed = json.loads(payload)
        except (KeyError, AttributeError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CityDataInvalidError() from error
        if not isinstance(parsed, dict):
            raise CityDataInvalidError()
        return parsed

    def _city_key(self, city_id):
        city_name_en = city_id_to_file_stem(city_id)
        return f"{self.prefix}{city_name_en}.json"


def city_id_to_file_stem(city_id):
    if not isinstance(city_id, str) or "-" not in city_id:
        return ""
    return city_id.split("-", 1)[1]


def _place_from_item(item, place_type):
    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        return None

    image_url = item.get("image_url")
    return {
        "placeId": item.get("entity_id") or f"{place_type.upper()}-{item.get('content_id', '')}",
        "type": place_type,
        "contentId": item.get("content_id"),
        "title": title.strip(),
        "description": _short_text(item.get("description")),
        "address": item.get("address"),
        "phone": item.get("phone"),
        "imageUrl": image_url.strip() if is_usable_image_url(image_url) else None,
        "latitude": read_number(item.get("latitude")),
        "longitude": read_number(item.get("longitude")),
        "theme": item.get("theme"),
        "themeTags": item.get("theme_tags") if isinstance(item.get("theme_tags"), list) else [],
        "startDate": item.get("eventstartdate") or None,
        "endDate": item.get("eventenddate") or None,
        "visitMonths": item.get("visit_months") if isinstance(item.get("visit_months"), list) else [],
    }


def _summary(city_record, records):
    return {
        "attractionCount": _count_or_field(city_record, records, "attraction_count", "attraction"),
        "festivalCount": _count_or_field(city_record, records, "festival_count", "festival"),
        "visitorStatisticsCount": _count_or_field(city_record, records, "visitor_statistics_count", "visitor_statistics"),
    }


def _count_or_field(city_record, records, field, entity_type):
    value = city_record.get(field)
    if isinstance(value, int):
        return value
    return sum(1 for item in records if item.get("entity_type") == entity_type)


def _display_city_name(city_record):
    name = city_record.get("city_name_ko")
    if isinstance(name, str):
        trimmed = name.strip()
        for suffix in ("시", "군"):
            if trimmed.endswith(suffix) and len(trimmed) > len(suffix):
                return trimmed[: -len(suffix)]
        return trimmed
    return city_record.get("city_name_en")


def _short_text(value, limit=280):
    if not isinstance(value, str):
        return None
    trimmed = " ".join(value.split())
    if len(trimmed) <= limit:
        return trimmed
    return trimmed[: limit - 3] + "..."


def _normalize_prefix(prefix):
    prefix = prefix or DEFAULT_PREFIX
    return prefix if prefix.endswith("/") else f"{prefix}/"


def _repository_error_from_client_error(error):
    code = _client_error_code(error)
    if code in NOT_FOUND_ERROR_CODES:
        return CityDataNotFoundError()
    if code in UPSTREAM_ERROR_CODES:
        return CityDataUpstreamError()
    return CityDataUpstreamError()


def _client_error_code(error):
    response = getattr(error, "response", None)
    if isinstance(response, dict):
        error_body = response.get("Error")
        if isinstance(error_body, dict):
            code = error_body.get("Code")
            if code is not None:
                return str(code)
        status_code = (response.get("ResponseMetadata") or {}).get("HTTPStatusCode")
        if status_code is not None:
            return str(status_code)
    return error.__class__.__name__


def _s3_client():
    try:
        import boto3
    except ImportError as error:
        raise RuntimeError("boto3 is required in the Lambda runtime.") from error
    return boto3.client("s3")
