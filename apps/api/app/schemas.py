from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str
    password: str = Field(min_length=8, max_length=200)


class LoginIn(BaseModel):
    email: str
    password: str


class PlanIn(BaseModel):
    plan: str


class IpfsIn(BaseModel):
    pinata_jwt: str = ""


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    project_type: str = "generative"
    canvas_width: int = 1024
    canvas_height: int = 1024
    license: str = "custom"
    ai_disclosure: str = ""


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    project_type: str | None = None
    canvas_width: int | None = None
    canvas_height: int | None = None
    license: str | None = None
    ai_disclosure: str | None = None


class MemberIn(BaseModel):
    email: str
    role: str = "editor"


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    item_id: str | None = None


class DecisionIn(BaseModel):
    status: str


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    optional: bool = False
    none_weight: float = 1


class CategoryUpdate(BaseModel):
    name: str | None = None
    optional: bool | None = None
    none_weight: float | None = None
    z_index: int | None = None


class OrderIn(BaseModel):
    ids: list[str]


class TraitUpdate(BaseModel):
    name: str | None = None
    weight: float | None = None
    exact_count: int | None = None
    clear_exact_count: bool = False
    always_include: bool | None = None
    rarity_label: str | None = None


class RuleIn(BaseModel):
    rule_type: str
    trait_a_id: str
    trait_b_id: str


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class PreviewIn(BaseModel):
    trait_ids: list[str] = []


class CollectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    supply: int = 10
    seed: int = 1
    mode: str = "weighted"
    description_template: str = "{collection} #{token_id} — {trait_list}"
    image_base_uri: str = ""
    external_url: str = ""
    symbol: str = ""
    metadata_schema: str = "erc721"
    marketplace_profile: str = "opensea"


class EditorIn(BaseModel):
    operations: list[dict] = []
    layers: list[dict] = []


class VariationIn(BaseModel):
    count: int = 4
    seed: int = 1


class WorkflowIn(BaseModel):
    name: str
    description: str = ""
    operations: list[dict] = []


class RunIn(BaseModel):
    asset_ids: list[str]
    seed: int = 1
    dry_run: bool = False


class RemoveBgIn(BaseModel):
    tolerance: int = 32
    mode: str = "corner"
    replacement_color: str | None = None


class EnhanceIn(BaseModel):
    scale: int = 2


class InpaintIn(BaseModel):
    x: int
    y: int
    width: int
    height: int


class AiBatchIn(BaseModel):
    asset_ids: list[str]
    operation: str
    params: dict = {}
