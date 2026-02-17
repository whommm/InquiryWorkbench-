import io
import logging

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..auth.utils import get_current_user
from ..core.llm import call_llm
from ..models.database import User, get_db
from ..models.types import ChatRequest, ChatResponse
from ..services.agent_runtime import run_two_stage_agent
from ..services.chat import build_tool_registry, execute_write_action, parse_chat_intent
from ..services.sheet_schema import build_sheet_schema
from ..services.supplier_service import SupplierService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    del current_user
    intent = parse_chat_intent(request)
    if intent.ask_message:
        return ChatResponse(action="ASK", content=intent.ask_message)

    tools = build_tool_registry(
        db=db,
        sheet_data=intent.sheet_data,
        schema=intent.schema,
        enabled_tools=request.enabled_tools,
        logger=logger,
    )
    logger.debug("Registered tools: %s", [t["name"] for t in tools.describe()])
    logger.debug("User message: %s", request.message)

    agent_out = run_two_stage_agent(
        call_llm=call_llm,
        user_message=request.message,
        history_messages=intent.history_messages,
        context=intent.context,
        tools=tools,
        max_tool_steps=3,
    )

    if agent_out.get("action") == "ASK":
        return ChatResponse(
            action="ASK",
            content=agent_out.get("content") or "Please provide more details.",
        )

    if agent_out.get("action") == "WRITE":
        return execute_write_action(
            agent_out=agent_out,
            user_message=request.message,
            sheet_data=intent.sheet_data,
            required_fields=intent.required_fields,
            db=db,
            logger=logger,
        )

    return ChatResponse(action="ASK", content="未知指令")


MAX_UPLOAD_SIZE = 10 * 1024 * 1024
ALLOWED_MIME_TYPES = [
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
]


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    del current_user

    filename = file.filename or ""
    if not filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="仅支持 Excel 文件格式 (.xlsx, .xls)")

    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="文件类型不正确，请上传 Excel 文件")

    try:
        contents = await file.read()
        if len(contents) > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=400, detail="文件大小不能超过 10MB")

        df = pd.read_excel(io.BytesIO(contents)).fillna("")
        headers = df.columns.tolist()
        data = df.values.tolist()
        result_data = [headers] + data

        recommended_suppliers = []
        try:
            schema = build_sheet_schema(result_data)
            cols = schema.get("item_columns") or {}
            brand_col = cols.get("brand")

            brands = set()
            for row in result_data[1:]:
                if not isinstance(row, list):
                    continue
                if isinstance(brand_col, int) and brand_col < len(row):
                    brand = row[brand_col]
                    if brand and str(brand).strip() and str(brand).strip().lower() != "none":
                        brands.add(str(brand).strip())

            supplier_service = SupplierService(db)
            seen_suppliers = set()
            for brand in brands:
                results = supplier_service.search_suppliers(brand, limit=3)
                for supplier in results:
                    if supplier.id in seen_suppliers:
                        continue
                    seen_suppliers.add(supplier.id)
                    recommended_suppliers.append(
                        {
                            "company_name": supplier.company_name,
                            "contact_name": supplier.contact_name,
                            "contact_phone": supplier.contact_phone,
                            "match_reason": f"品牌匹配: {brand}",
                            "quote_count": supplier.quote_count,
                            "last_quote_date": supplier.last_quote_date.isoformat()
                            if supplier.last_quote_date
                            else None,
                        }
                    )

            recommended_suppliers = recommended_suppliers[:10]

        except Exception as exc:
            logger.warning("Failed to analyze suppliers from uploaded file", exc_info=exc)

        return {
            "data": result_data,
            "recommended_suppliers": recommended_suppliers,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(exc)}")
