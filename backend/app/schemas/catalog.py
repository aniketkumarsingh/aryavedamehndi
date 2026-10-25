import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# Allowed design filter values - labels live in frontend/src/lib/designs.js.
DesignStyle = Literal["rajasthani", "indian", "arabic", "indo-arabic", "jaal", "mandala", "jewellery", "floral", "minimal", "moroccan"]
DesignCoverage = Literal["fingers", "palm", "back", "forearm", "elbow", "toes", "foot"]
# Occasions first, then festivals - labels in frontend/src/lib/designs.js.
DesignOccasion = Literal[
    "wedding", "engagement", "roka", "sangeet", "haldi", "nikah", "godh-bharai", "anniversary", "birthday", "party", "everyday",
    "karwa-chauth", "teej", "eid", "eid-ul-adha", "raksha-bandhan", "diwali", "navratri", "gangaur", "ganesh-chaturthi", "lohri", "makar-sankranti",
    "holi", "bhai-dooj", "chhath", "durga-puja", "janmashtami", "onam", "pongal", "christmas",
    "baisakhi", "gurpurab", "new-year", "bihu", "valentines",
    "housewarming", "kitty-party", "bridal-shower", "mayra", "tilak",
]


class DesignIn(BaseModel):
    package_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    price_min: float = Field(..., gt=0, le=1_000_000)
    price_max: float = Field(..., gt=0, le=1_000_000)
    duration_minutes: int = Field(default=60, ge=10, le=720)
    sort_order: int = 0
    is_active: bool = True
    style: DesignStyle | None = None
    coverage: DesignCoverage | None = None
    occasions: list[DesignOccasion] = Field(default_factory=list, max_length=10)
    photo_needed: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def check_price_range(self):
        if self.price_max < self.price_min:
            raise ValueError("price_max must be at least price_min")
        return self


class DesignOut(BaseModel):
    id: uuid.UUID
    package_id: uuid.UUID
    category: str | None
    name: str
    description: str | None
    image_url: str | None
    # Full-resolution copy for zooming (null when image_url is already full size).
    image_hd_url: str | None = None
    # "photo" or "illustration" (an AI illustration, shown labelled as such)
    image_kind: str = "photo"
    # Licence credit to show with the main image, or null.
    image_credit: dict | None = None
    price_min: float
    price_max: float
    duration_minutes: int
    sort_order: int
    is_active: bool
    style: str | None = None
    coverage: str | None = None
    occasions: list[str] = []
    # Why the design is hidden: the photo it still needs (admin view).
    photo_needed: str | None = None
    # Main photo + gallery views (not counting 360 frames).
    image_count: int = 0
    # Frames in the 360-degree turntable view; 0 = no 360 view yet.
    spin_frame_count: int = 0
    # Bookable artists with an approved photo of this design.
    artist_count: int = 0

    class Config:
        from_attributes = True


class DesignImageOut(BaseModel):
    id: uuid.UUID
    url: str
    hd_url: str | None = None
    label: str | None
    # "photo" | "angle" | "detail" | "illustration" | "ai_photo" | "spin"
    kind: str
    sort_order: int
    credit: dict | None = None

    class Config:
        from_attributes = True


class DesignArtistOut(BaseModel):
    """An artist offering a design, as shown on the design's page - their
    own (admin-approved) photo of this design is the verification."""

    artist_id: uuid.UUID
    name: str | None
    gender: str | None
    profile_photo_url: str | None
    rating_avg: float
    rating_count: int
    proof_image_url: str
    distance_km: float | None = None
    eta_minutes: int | None = None


class DesignDetailOut(DesignOut):
    # Extra gallery views, in order (the main photo is image_url).
    images: list[DesignImageOut]
    # 360-degree turntable frames, in rotation order.
    spin_frames: list[DesignImageOut] = []
    artists: list[DesignArtistOut]


class DesignImageIn(BaseModel):
    label: str | None = Field(default=None, max_length=80)
    kind: Literal["photo", "angle", "detail", "illustration", "ai_photo", "spin"] = "photo"


class ArtistDesignOut(BaseModel):
    id: uuid.UUID
    design: DesignOut
    proof_image_url: str
    # "pending" | "approved" | "rejected"
    status: str
    catalog_consent: bool = False
    rejection_reason: str | None
    created_at: datetime
    reviewed_at: datetime | None

    class Config:
        from_attributes = True


class DesignPhotoReviewOut(ArtistDesignOut):
    """Admin review queue row - who submitted it."""

    artist_id: uuid.UUID
    artist_name: str | None
    artist_phone: str


class DesignPhotoRejectIn(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)
