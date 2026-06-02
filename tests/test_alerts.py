import uuid

VALID_ALERT = {
    "field_id": str(uuid.uuid4()),
    "zone": "Buenos Aires",
    "event_type": "frost",
    "threshold": 0.7,
    "notification_channel": "whatsapp",
    "contact": "+5491112345678",
}


# ── helpers ───────────────────────────────────────────────────────────────────


async def _create_alert(client, overrides: dict | None = None) -> dict:
    payload = {**VALID_ALERT, **(overrides or {})}
    resp = await client.post("/api/v1/alerts/", json=payload)
    assert resp.status_code == 201
    return resp.json()


# ── POST /api/v1/alerts/ ──────────────────────────────────────────────────────


async def test_create_alert(client):
    resp = await client.post("/api/v1/alerts/", json=VALID_ALERT)
    assert resp.status_code == 201
    body = resp.json()
    assert body["zone"] == "Buenos Aires"
    assert body["event_type"] == "frost"
    assert body["threshold"] == 0.7
    assert body["is_active"] is True
    assert body["notification_channel"] == "whatsapp"
    assert body["contact"] == "+5491112345678"
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


async def test_create_alert_invalid_threshold(client):
    resp = await client.post("/api/v1/alerts/", json={**VALID_ALERT, "threshold": 1.5})
    assert resp.status_code == 422


async def test_create_alert_invalid_event_type(client):
    resp = await client.post("/api/v1/alerts/", json={**VALID_ALERT, "event_type": "volcano"})
    assert resp.status_code == 422


async def test_create_alert_whatsapp_invalid_phone(client):
    resp = await client.post(
        "/api/v1/alerts/",
        json={**VALID_ALERT, "notification_channel": "whatsapp", "contact": "not-a-phone"},
    )
    assert resp.status_code == 422


async def test_create_alert_email_invalid_format(client):
    resp = await client.post(
        "/api/v1/alerts/",
        json={
            **VALID_ALERT,
            "notification_channel": "email",
            "contact": "not-an-email",
        },
    )
    assert resp.status_code == 422


# ── GET /api/v1/alerts/{id} ───────────────────────────────────────────────────


async def test_get_alert_not_found(client):
    resp = await client.get(f"/api/v1/alerts/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_deleted_alert_returns_404(client):
    alert = await _create_alert(client)
    await client.delete(f"/api/v1/alerts/{alert['id']}")
    resp = await client.get(f"/api/v1/alerts/{alert['id']}")
    assert resp.status_code == 404


# ── GET /api/v1/alerts/ ───────────────────────────────────────────────────────


async def test_list_alerts_requires_field_id(client):
    resp = await client.get("/api/v1/alerts/")
    assert resp.status_code == 422


async def test_list_alerts_filtered_by_field_id(client):
    field_a = str(uuid.uuid4())
    field_b = str(uuid.uuid4())
    await _create_alert(client, {"field_id": field_a})
    await _create_alert(client, {"field_id": field_a})
    await _create_alert(client, {"field_id": field_b})

    resp = await client.get(f"/api/v1/alerts/?field_id={field_a}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert all(a["field_id"] == field_a for a in body["items"])


async def test_list_alerts_filtered_by_is_active(client):
    field_id = str(uuid.uuid4())
    alert = await _create_alert(client, {"field_id": field_id})
    await client.patch(
        f"/api/v1/alerts/{alert['id']}", json={"is_active": False}
    )

    resp = await client.get(f"/api/v1/alerts/?field_id={field_id}&is_active=true")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0

    resp = await client.get(f"/api/v1/alerts/?field_id={field_id}&is_active=false")
    body = resp.json()
    assert body["total"] == 1


async def test_list_alerts_pagination(client):
    field_id = str(uuid.uuid4())
    for _ in range(5):
        await _create_alert(client, {"field_id": field_id})

    resp = await client.get(f"/api/v1/alerts/?field_id={field_id}&limit=2&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["items"]) == 2

    resp2 = await client.get(f"/api/v1/alerts/?field_id={field_id}&limit=2&offset=2")
    body2 = resp2.json()
    assert len(body2["items"]) == 2
    # items must not overlap
    ids_page1 = {a["id"] for a in body["items"]}
    ids_page2 = {a["id"] for a in body2["items"]}
    assert ids_page1.isdisjoint(ids_page2)


async def test_list_alerts_limit_exceeds_max(client):
    field_id = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/alerts/?field_id={field_id}&limit=201")
    assert resp.status_code == 422


# ── PATCH /api/v1/alerts/{id} ─────────────────────────────────────────────────


async def test_update_alert(client):
    alert = await _create_alert(client)
    resp = await client.patch(
        f"/api/v1/alerts/{alert['id']}",
        json={"threshold": 0.9, "is_active": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["threshold"] == 0.9
    assert body["is_active"] is False
    assert body["zone"] == alert["zone"]  # unchanged


async def test_update_alert_contact_requires_channel(client):
    alert = await _create_alert(client)
    resp = await client.patch(
        f"/api/v1/alerts/{alert['id']}",
        json={"contact": "+5491199999999"},  # missing notification_channel
    )
    assert resp.status_code == 422


# ── DELETE /api/v1/alerts/{id} ────────────────────────────────────────────────


async def test_delete_alert_soft_deletes_pending_notifications(client, db_session):
    from datetime import date

    from app.models.enums import NotificationStatus
    from app.models.notification import Notification

    alert = await _create_alert(client)
    alert_id = uuid.UUID(alert["id"])

    # Manually insert one pending and one sent notification
    pending_notif = Notification(
        alert_id=alert_id,
        target_date=date.today(),
        probability=0.8,
        status=NotificationStatus.pending,
    )
    sent_notif = Notification(
        alert_id=alert_id,
        target_date=date.today(),
        probability=0.75,
        status=NotificationStatus.sent,
    )
    db_session.add(pending_notif)
    db_session.add(sent_notif)
    await db_session.flush()

    resp = await client.delete(f"/api/v1/alerts/{alert['id']}")
    assert resp.status_code == 204

    await db_session.refresh(pending_notif)
    await db_session.refresh(sent_notif)

    assert pending_notif.deleted is True
    assert sent_notif.deleted is False  # sent records are preserved
