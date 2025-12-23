from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from app.rag.ingestion import IngestionPipeline
from app.utils.logger import setup_logger
import shutil
import os
import uuid

router = APIRouter()
logger = setup_logger(__name__)

# Single instance of pipeline to reuse components
# Note: pipeline creates generic EmbeddingService/VectorStore.
# VectorStore now uses singleton client, so it's safe.
ingestion_pipeline = IngestionPipeline()

UPLOAD_DIR = "data/uploaded_docs"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    Upload a file (TXT, MD, PDF, DOCX, PPTX, ZIP, CSV, XLSX).
    - Text-based docs are ingested into Vector Store.
    - Data files (CSV/XLSX) are saved for Data Analyst.
    - ZIP files are extracted and processed.
    """
    logger.info(f"Received file upload: {file.filename}")
    
    allowed_extensions = [".txt", ".md", ".pdf", ".docx", ".pptx", ".zip", ".csv", ".xlsx"]
    ext = os.path.splitext(file.filename)[1].lower()
    
    if ext not in allowed_extensions:
         raise HTTPException(status_code=400, detail=f"Supported formats: {allowed_extensions}")
         
    filename = os.path.basename(file.filename)
    file_path = os.path.join(UPLOAD_DIR, filename)
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        logger.info(f"File saved to {file_path}.")
        
        # Branch Logic
        if ext in [".csv", ".xlsx"]:
            logger.info("Saved Data File for Data Analyst.")
            return {"status": "success", "message": f"Uploaded {filename} for Data Analysis"}
            
        elif ext == ".zip":
            # Handle ZIP Extraction
            import zipfile
            extract_dir = os.path.join(UPLOAD_DIR, f"extracted_{uuid.uuid4()}")
            os.makedirs(extract_dir, exist_ok=True)
            
            logger.info(f"Extracting ZIP to {extract_dir}...")
            
            extracted_files = []
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
                
            # Recursively find all supported files
            for root, dirs, files in os.walk(extract_dir):
                for f in files:
                    if f.lower().endswith((".txt", ".md", ".pdf", ".docx", ".pptx")):
                        extracted_files.append(os.path.join(root, f))
            
            if extracted_files:
                logger.info(f"Found {len(extracted_files)} documents in ZIP. Starting ingestion...")
                await ingestion_pipeline.ingest_files(extracted_files)
                msg = f"Successfully processed ZIP. Ingested {len(extracted_files)} documents."
            else:
                msg = "Uploaded ZIP but found no supported documents inside."
                
            return {"status": "success", "message": msg}
            
        else:
            # Single Document Ingestion
            logger.info(f"Starting ingestion for {ext} file...")
            await ingestion_pipeline.ingest_files([file_path])
            return {"status": "success", "message": f"Successfully ingested {filename}"}
        
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

@router.delete("/reset")
async def reset_knowledge_base():
    """
    Clear all documents from the Vector Store AND in-memory BM25 index.
    Also clears physical uploaded files.
    """
    try:
        # 1. Clear Vector Store (Qdrant)
        success_vs = await ingestion_pipeline.vector_store.clear()
        
        # 2. Clear BM25
        from app.rag.bm25_retriever import get_bm25_retriever
        bm25 = get_bm25_retriever()
        bm25.clear()
        
        # 3. Clear Upload Directory
        if os.path.exists(UPLOAD_DIR):
            for filename in os.listdir(UPLOAD_DIR):
                file_path = os.path.join(UPLOAD_DIR, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    logger.warning(f"Failed to delete {file_path}: {e}")

        if success_vs:
            logger.info("Knowledge Base (Vector+BM25+Files) cleared successfully.")
            return {"status": "success", "message": "Knowledge Base Completely Cleared"}
        else:
            raise HTTPException(status_code=500, detail="Failed to clear Vector Store")
    except Exception as e:
        logger.error(f"Reset failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
