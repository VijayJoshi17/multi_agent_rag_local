# Larkspur Fleet API v2 — Reference

The Fleet API lets customers and integrators monitor robots, assign missions and read telemetry. The base URL is `https://fleet.larkspur.example/v2`.

## Authentication

Every request must include an API token in the `X-Fleet-Token` header. Tokens are created per site in the Fleet Console and can be scoped to read-only or read-write. Tokens do not expire automatically but can be revoked at any time.

## Rate limits

Each token may make up to 600 requests per minute. Telemetry streaming over WebSocket does not count towards this limit. When the limit is exceeded the API returns HTTP 429 with a `Retry-After` header in seconds.

## Pagination

List endpoints return at most 100 items per page. To fetch the next page, pass the `next_cursor` value from the previous response as the `cursor` query parameter.

## Core endpoints

- `GET /robots` — list robots at a site, with battery level and state.
- `GET /robots/{robot_id}` — details for one robot.
- `POST /robots/{robot_id}/missions` — assign a mission (a sequence of waypoints and actions).
- `DELETE /missions/{mission_id}` — cancel a mission that has not started.
- `GET /sites/{site_id}/heatmap` — congestion heatmap for the last 24 hours.

## Error codes

- `E1001` — invalid or revoked token.
- `E2040` — robot is offline.
- `E3007` — mission rejected because the robot's battery is below 15%.
- `E4031` — mission rejected because a waypoint lies outside the site's geofence.
- `E5000` — internal error; retry with exponential backoff.

## Webhooks

Integrators can subscribe to `mission.completed`, `mission.failed` and `robot.protective_stop` events. Webhook payloads are signed with HMAC-SHA256 using the site's webhook secret, sent in the `X-Fleet-Signature` header.
