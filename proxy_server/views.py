import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


@csrf_exempt
def proxy_to_ngrok(request, target_path=""):
    base_url = getattr(settings, "NGROK_API_BASE", "http://127.0.0.1:4040/api").rstrip("/")
    timeout = getattr(settings, "PROXY_TIMEOUT_SECONDS", 30)

    target_url = f"{base_url}/{target_path.lstrip('/')}"
    query_string = request.META.get("QUERY_STRING", "")
    if query_string:
        target_url = f"{target_url}?{query_string}"

    forward_headers = {}
    for header, value in request.headers.items():
        lowered = header.lower()
        if lowered in HOP_BY_HOP_HEADERS or lowered in {"host", "content-length", "accept-encoding"}:
            continue
        forward_headers[header] = value

    body = request.body if request.body else None
    upstream_request = Request(
        target_url,
        data=body,
        headers=forward_headers,
        method=request.method,
    )

    try:
        with urlopen(upstream_request, timeout=timeout) as upstream_response:
            response_body = upstream_response.read()
            response = HttpResponse(response_body, status=upstream_response.status)
            for header, value in upstream_response.headers.items():
                if header.lower() not in HOP_BY_HOP_HEADERS:
                    response[header] = value
            return response
    except HTTPError as exc:
        response_body = exc.read()
        response = HttpResponse(response_body, status=exc.code)
        for header, value in exc.headers.items():
            if header.lower() not in HOP_BY_HOP_HEADERS:
                response[header] = value
        return response
    except URLError as exc:
        return JsonResponse(
            {
                "error": "Failed to reach upstream ngrok API",
                "details": str(exc.reason),
            },
            status=502,
        )


def health(_request):
    return JsonResponse(
        {
            "service": "django-proxy",
            "upstream": getattr(settings, "NGROK_API_BASE", "http://127.0.0.1:4040/api"),
            "usage": "Send requests to /proxy/<path> to forward to ngrok API",
        }
    )
