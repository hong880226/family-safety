"""Device schemas."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    family_id: int
    member_id: int | None
    name: str
    device_type: str
    device_id: str
    computer_model: str | None
    last_username: str | None
    last_seen: datetime | None
    online: bool
    created_at: datetime
