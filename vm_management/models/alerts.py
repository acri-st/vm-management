"""Models for alerts"""

from pydantic import BaseModel


class AlertLabels(BaseModel):
    """Labels for the alert"""

    instance_id: str
    instance: str
    alertname: str
    severity: str | None = None


class Alert(BaseModel):
    """Alert model"""

    status: str
    labels: AlertLabels


class AlertWebhookPayload(BaseModel):
    """Payload for the alert webhook"""

    receiver: str
    status: str
    alerts: list[Alert]
