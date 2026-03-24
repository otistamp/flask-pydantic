import json

from flask import Blueprint, current_app, make_response

from .openapi import generate_openapi_spec

try:
    import yaml
except ImportError:
    yaml = None


def create_docs_blueprint(app) -> Blueprint:
    bp = Blueprint("flask_pydantic", __name__)
    _cached_spec = {}

    def _get_spec() -> dict:
        if not _cached_spec:
            _cached_spec["spec"] = generate_openapi_spec(current_app._get_current_object())
        return _cached_spec["spec"]

    openapi_url = app.config.get("FLASK_PYDANTIC_OPENAPI_URL", "/openapi.json")
    if openapi_url:
        @bp.route(openapi_url)
        def openapi_json():
            spec = _get_spec()
            resp = make_response(json.dumps(spec, indent=2))
            resp.mimetype = "application/json"
            return resp

    yaml_url = app.config.get("FLASK_PYDANTIC_OPENAPI_YAML_URL", "/openapi.yaml")
    if yaml_url and yaml is not None:
        @bp.route(yaml_url)
        def openapi_yaml():
            spec = _get_spec()
            resp = make_response(yaml.dump(spec, default_flow_style=False, sort_keys=False))
            resp.mimetype = "text/yaml"
            return resp

    docs_url = app.config.get("FLASK_PYDANTIC_DOCS_URL", "/docs")
    cdn_url = app.config.get("FLASK_PYDANTIC_CDN_URL", "https://unpkg.com")
    if docs_url:
        @bp.route(docs_url)
        def swagger_ui():
            spec_url = app.config.get("FLASK_PYDANTIC_OPENAPI_URL", "/openapi.json")
            html = f"""<!DOCTYPE html>
<html>
<head>
    <title>{current_app.name} - Swagger UI</title>
    <link rel="stylesheet" href="{cdn_url}/swagger-ui-dist/swagger-ui.css">
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="{cdn_url}/swagger-ui-dist/swagger-ui-bundle.js"></script>
    <script>
        SwaggerUIBundle({{
            url: "{spec_url}",
            dom_id: '#swagger-ui',
            presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
            layout: "BaseLayout"
        }});
    </script>
</body>
</html>"""
            return make_response(html)

    redoc_url = app.config.get("FLASK_PYDANTIC_REDOC_URL", "/redoc")
    if redoc_url:
        @bp.route(redoc_url)
        def redoc():
            spec_url = app.config.get("FLASK_PYDANTIC_OPENAPI_URL", "/openapi.json")
            html = f"""<!DOCTYPE html>
<html>
<head>
    <title>{current_app.name} - ReDoc</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>body {{ margin: 0; padding: 0; }}</style>
</head>
<body>
    <redoc spec-url="{spec_url}"></redoc>
    <script src="{cdn_url}/redoc/bundles/redoc.standalone.js"></script>
</body>
</html>"""
            return make_response(html)

    return bp
