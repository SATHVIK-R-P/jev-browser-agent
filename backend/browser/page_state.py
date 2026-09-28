from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field

class InteractiveElement(BaseModel):
    id: str  # e.g. "element_1"
    tag_name: str
    role: str
    name: str  # accessible name, aria-label, or text
    text: str
    selector: str
    attributes: Dict[str, Any] = Field(default_factory=dict)
    bounding_box: Optional[Dict[str, float]] = None  # {x, y, width, height}
    is_visible: bool = True
    is_enabled: bool = True

    def to_summary(self) -> str:
        parts = [f"[{self.id}]", f"<{self.tag_name}>", f"role='{self.role}'"]
        if self.name:
            clean_name = self.name.replace("\n", " ").strip()
            parts.append(f"name='{clean_name[:40]}'")
        if self.text and self.text != self.name:
            clean_text = self.text.replace("\n", " ").strip()
            parts.append(f"text='{clean_text[:40]}'")
        if "placeholder" in self.attributes:
            parts.append(f"placeholder='{self.attributes['placeholder']}'")
        if "href" in self.attributes:
            parts.append(f"href='{self.attributes['href'][:40]}'")
        return " ".join(parts)

class PageState(BaseModel):
    url: str
    title: str
    elements: List[InteractiveElement] = Field(default_factory=list)
    text_summary: str = ""
    screenshot_base64: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def get_element_by_id(self, elem_id: str) -> Optional[InteractiveElement]:
        for el in self.elements:
            if el.id == elem_id:
                return el
        return None

    def get_interactive_elements_summary(self, max_items: int = 25) -> str:
        lines = []
        for el in self.elements[:max_items]:
            lines.append(el.to_summary())
        if len(self.elements) > max_items:
            lines.append(f"... and {len(self.elements) - max_items} more elements.")
        return "\n".join(lines)
