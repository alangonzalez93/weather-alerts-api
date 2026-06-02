import uuid
from datetime import date, timedelta

VALID_ALERT = {
    "field_id": str(uuid.uuid4()),
    "zone": "Mendoza",
    "event_type": "frost",
    "threshold": 0.5,
    "notification_channel": "email",
    "contact": "farmer@example.com",
}


async def _create_alert(client, overrides: dict | None = None) -> dict:
    payload = {**VALID_ALERT, "field_id": str(uuid.uuid4()), **(overrides or {})}
    resp = await client.post("/api/v1/alerts/", json=payload)
    assert resp.status_code == 201
    return resp.json()


async def _add_notification(db_session, alert_id, *, status="sent", days_offset=0):
    from app.models.notification import Notification

    notif = Notification(
        alert_id=uuid.UUID(alert_id),
        target_date=date.today() + timedelta(days=days_offset),
        probability=0.8,
        status=status,
    )
    db_session.add(notif)
    await db_session.flush()
    await db_session.refresh(notif)
    return notif


async def test_list_notifications_returns_404_for_missing_alert(client):
    resp = await client.get(f"/api/v1/alerts/{uuid.uuid4()}/notifications")
    assert resp.status_code == 404


async def test_list_notifications_ordered_by_triggered_at(client, db_session):
    alert = await _create_alert(client)
    await _add_notification(db_session, alert["id"], days_offset=0)
    await _add_notification(db_session, alert["id"], days_offset=1)
    await _add_notification(db_session, alert["id"], days_offset=2)

    resp = await client.get(f"/api/v1/alerts/{alert['id']}/notifications")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    triggered_ats = [item["triggered_at"] for item in body["items"]]
    assert triggered_ats == sorted(triggered_ats, reverse=True)


async def test_list_notifications_filtered_by_status(client, db_session):
    alert = await _create_alert(client)
    await _add_notification(db_session, alert["id"], status="sent")
    await _add_notification(db_session, alert["id"], status="failed")
    await _add_notification(db_session, alert["id"], status="pending")

    resp = await client.get(f"/api/v1/alerts/{alert['id']}/notifications?status=sent")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "sent"


async def test_list_notifications_pagination(client, db_session):
    alert = await _create_alert(client)
    for i in range(5):
        await _add_notification(db_session, alert["id"], days_offset=i)

    resp = await client.get(
        f"/api/v1/alerts/{alert['id']}/notifications?limit=2&offset=0"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["items"]) == 2

    resp2 = await client.get(
        f"/api/v1/alerts/{alert['id']}/notifications?limit=2&offset=2"
    )
    body2 = resp2.json()
    ids_page1 = {n["id"] for n in body["items"]}
    ids_page2 = {n["id"] for n in body2["items"]}
    assert ids_page1.isdisjoint(ids_page2)
