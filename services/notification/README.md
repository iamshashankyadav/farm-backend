# notification service

**Owner:** Team 1 · Slot M3 · Sprint 2 (Issue #14)

Push and in-app notifications driven by domain events across the platform.

| | |
| --- | --- |
| Python package | `notification_service` |
| Local dev port | 8008 |
| Database schema | `notification` |
| Route prefix | `/api/v1/notification` |

---

## Features & Architecture

### 1. In-App Inbox & Device Tokens
- **Device Tokens (`POST /notifications/devices`, `DELETE /notifications/devices/{token}`)**:
  - Registers Expo push tokens (`ExponentPushToken[...]`) and FCM tokens for iOS, Android, and Web platforms.
  - Automatically associates tokens with the authenticated `user_id`.
- **In-App Inbox (`GET /notifications`)**:
  - Paginated list of notifications with cursor support and `unreadOnly` filter.
  - Returns `unreadCount` and full payload data.
- **Unread Count (`GET /notifications/unread-count`)**:
  - Fast unread counter for app badges and tab bar notifications.
- **Read Status (`POST /notifications/{id}/read`, `POST /notifications/read-all`)**:
  - Marks individual notifications or all user notifications as read.

### 2. Event Consumers (`consumers.py`)
Listens on the RabbitMQ `farm.events` topic exchange and maps domain events into user notifications:
- `order.placed`: `"Order Placed Successfully"`
- `order.confirmed`: `"Order Confirmed"`
- `order.packed`: `"Order Packed"`
- `order.ready_for_dispatch`: `"Order Ready for Dispatch"`
- `order.in_transit`: `"Order Out for Delivery"`
- `order.delivered` / `delivery.completed`: `"Order Delivered"`
- `order.completed`: `"Order Completed"`
- `order.cancelled`: `"Order Cancelled"`
- `payment.succeeded`: `"Payment Succeeded"`
- `reservation.accepted`: `"Plot Reservation Accepted"`
- `harvest.ready`: `"Crop Ready for Harvest"`
- `quality.graded`: `"Quality Inspection Passed"` / `"Harvest Inspection Graded"`
- `pool.assigned`: `"Delivery Route Assigned"`

### 3. Push Delivery (`push.py`)
- Dispatches push notifications via the Expo Push API (which proxies to Firebase Cloud Messaging for Android and APNs for iOS).
- Handled asynchronously outside the database transaction with graceful failure handling.

---

## Local Development & Testing

```bash
# Start API locally
uv run --package farm-notification uvicorn notification_service.main:app --reload --port 8008

# Run migrations (requires DATABASE_URL)
cd services/notification && uv run alembic upgrade head

# Run tests
uv run pytest services/notification
```
