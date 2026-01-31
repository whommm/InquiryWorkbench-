from pydantic import BaseModel, field_validator
from typing import Optional, Any, List, Union

class ChatHistoryMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    current_sheet_data: Optional[List[List[Any]]] = None
    chat_history: Optional[List[ChatHistoryMessage]] = None

class UpdateAction(BaseModel):
    target_row: int
    price: float
    tax: bool = False
    shipping: Optional[Union[bool, str]] = False
    delivery_time: str
    offer_brand: Optional[str] = None
    supplier: Optional[str] = None
    remarks: Optional[str] = None
    quoted_model: Optional[str] = None
    quoted_spec: Optional[str] = None
    lookup_supplier: Optional[str] = None
    lookup_item: Optional[str] = None
    lookup_brand: Optional[str] = None
    lookup_model: Optional[str] = None

    @field_validator("tax", mode="before")
    @classmethod
    def _coerce_bool_zh(cls, v):
        if isinstance(v, bool):
            return v
        if v is None:
            return v
        if isinstance(v, (int, float)):
            return bool(v)
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("true", "t", "yes", "y", "1", "是", "含税", "含运", "含税运", "含运费", "含税含运", "含税/含运"):
                return True
            if s in ("false", "f", "no", "n", "0", "否", "不含税", "不含运", "不含税不含运", "不含税/不含运"):
                return False
        return v

    @field_validator("shipping", mode="before")
    @classmethod
    def _coerce_shipping_zh(cls, v):
        if isinstance(v, bool):
            return v
        if v is None:
            return v
        if isinstance(v, (int, float)):
            return bool(v)
        if isinstance(v, str):
            s = v.strip()
            sl = s.lower()
            if sl in ("true", "t", "yes", "y", "1", "是", "含运", "含运费", "包邮", "含税运", "含税/含运"):
                return True
            if sl in ("false", "f", "no", "n", "0", "否", "不含运", "不含运费"):
                return False
            if s:
                return s
        return v

class ChatResponse(BaseModel):
    action: str  # "ASK" or "WRITE"
    content: Optional[str] = None
    data: Optional[Any] = None
    updated_sheet: Optional[List[List[Any]]] = None
