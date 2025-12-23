from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.models.schemas import QueryRequest, Answer
from app.agents.supervisor import SupervisorAgent
from app.utils.logger import setup_logger
import json

router = APIRouter()
logger = setup_logger(__name__)
supervisor = SupervisorAgent()

@router.post("/chat", response_model=Answer)
async def chat(request: QueryRequest):
    logger.info(f"Received query: {request.query}")
    try:
        response = await supervisor.run(request.query)
        return response
    except Exception as e:
        logger.error(f"Error processing query: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/chat/stream")
async def chat_stream(request: QueryRequest):
    logger.info(f"Received streaming query: {request.query}")
    
    async def event_generator():
        try:
            async for event in supervisor.stream_run(
                request.query, 
                chat_history=request.chat_history,
                run_verification=request.run_verification,
                mode=request.mode
            ):
                # Send as NDJSON line
                yield json.dumps(event) + "\n"
        except Exception as e:
            logger.error(f"Stream error: {str(e)}", exc_info=True)
            yield json.dumps({"type": "error", "error": str(e)}) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")
