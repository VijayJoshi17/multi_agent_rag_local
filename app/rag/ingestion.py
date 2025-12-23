import os
from typing import List
from app.rag.embeddings import EmbeddingService
from app.rag.vector_store import VectorStore
from app.models.schemas import DocumentChunk
from langchain_text_splitters import RecursiveCharacterTextSplitter

class IngestionPipeline:
    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.vector_store = VectorStore()
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            # transformers tokenizer typically matches sentence structure better, 
            # but character splitting is fine for general purpose
            length_function=len,
        )

    async def ingest_files(self, file_paths: List[str]):
        """Ingest specific list of files"""
        documents = []
        
        for file_path in file_paths:
            if not os.path.exists(file_path):
                print(f"File {file_path} not found.")
                continue
                
            try:
                text = ""
                ext = os.path.splitext(file_path)[1].lower()
                
                if ext in [".txt", ".md"]:
                    with open(file_path, "r", encoding="utf-8") as f:
                        text = f.read()
                elif ext == ".pdf":
                    text = self._parse_pdf(file_path)
                elif ext == ".docx":
                    text = self._parse_docx(file_path)
                elif ext == ".pptx":
                    text = self._parse_pptx(file_path)
                else:
                    print(f"Unsupported file type: {ext}")
                    continue
                
                if not text:
                    print(f"No text extracted from {file_path}")
                    continue

                chunks = self.text_splitter.split_text(text)
                for chunk in chunks:
                    documents.append(DocumentChunk(
                        content=chunk,
                        metadata={"source": os.path.basename(file_path)}
                    ))
            except Exception as e:
                print(f"Error processing {file_path}: {e}")
        
        if not documents:
            print("No documents generated from files.")
            return

        print(f"Generated {len(documents)} chunks. Generatings embeddings...")
        texts = [doc.content for doc in documents]
        embeddings = await self.embedding_service.get_embeddings(texts)

        print("Upserting to Vector Store...")
        await self.vector_store.upsert_documents(documents, embeddings)
        print("Ingestion complete.")

    def _parse_pdf(self, file_path: str) -> str:
        import pypdf
        text = ""
        with open(file_path, 'rb') as f:
            reader = pypdf.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        return text

    def _parse_docx(self, file_path: str) -> str:
        import docx
        doc = docx.Document(file_path)
        return "\n".join([para.text for para in doc.paragraphs])

    def _parse_pptx(self, file_path: str) -> str:
        from pptx import Presentation
        prs = Presentation(file_path)
        text = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    text.append(shape.text)
        return "\n".join(text)

    async def run(self, data_dir: str = "data/sample_docs"):
        """Run ingestion on a directory"""
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
            print(f"Directory {data_dir} created. Please add documents.")
            return

        file_paths = []
        for filename in os.listdir(data_dir):
            if filename.lower().endswith((".txt", ".md", ".pdf", ".docx", ".pptx")):
                file_paths.append(os.path.join(data_dir, filename))
        
        if not file_paths:
            print("No supported files found in directory.")
            return
            
        await self.ingest_files(file_paths)
        
    if __name__ == "__main__":
        import asyncio
        pipeline = IngestionPipeline()
        asyncio.run(pipeline.run())
