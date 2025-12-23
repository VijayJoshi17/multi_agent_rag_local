import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio
# We mock these imports so tests can runs even if dependencies are installing
# But for real test they need to exist.
import sys
from typing import Any

# Mocking ollama and sentence_transformers for testing flow logic
sys.modules['ollama'] = MagicMock()
sys.modules['sentence_transformers'] = MagicMock()

# Now we can import the app modules
from app.models.schemas import AgentState, DocumentChunk
from app.agents.supervisor import SupervisorAgent

class TestFreeAgentFlow(unittest.TestCase):
    def setUp(self):
        # Mock VectorStore
        self.patcher_vs = patch('app.agents.retriever.VectorStore')
        self.mock_vs_cls = self.patcher_vs.start()
        self.mock_vs_instance = AsyncMock()
        self.mock_vs_cls.return_value = self.mock_vs_instance
        
        self.mock_vs_instance.search.return_value = [
            DocumentChunk(content="Free Version Context", metadata={"source": "test"})
        ]
        
        # Mock EmbeddingService
        self.patcher_emb = patch('app.agents.retriever.EmbeddingService')
        self.mock_emb_cls = self.patcher_emb.start()
        self.mock_emb = MagicMock()
        self.mock_emb_cls.return_value = self.mock_emb
        self.mock_emb.get_embedding = AsyncMock(return_value=[0.1]*384)

        # Mock Ollama call in BaseAgent
        self.patcher_llm = patch('app.agents.base.ollama.chat')
        self.mock_chat = self.patcher_llm.start()
        self.mock_chat.return_value = {
            'message': {'content': 'Mocked Llama Response'}
        }

    def tearDown(self):
        patch.stopall()

    def test_supervisor_flow(self):
        async def run_test():
            supervisor = SupervisorAgent()
            
            # Ensure verifier passes
            with patch.object(supervisor.verifier, 'run', new_callable=AsyncMock) as mock_verify:
                mock_verify.return_value = AgentState(
                    query="test",
                    retrieved_docs=[DocumentChunk(content="Mock", metadata={})],
                    summary="Mock Summary",
                    generated_answer="Mock Answer",
                    verification_status=True
                )
                
                response = await supervisor.run("Is this free?")
                
                self.assertIsNotNone(response)
                self.assertEqual(response.response, "Mocked Llama Response")
                # Check confidence score logic
                self.assertEqual(response.confidence_score, 1.0)
                print("\nFree Version Flow Test Passed!")

        asyncio.run(run_test())

if __name__ == '__main__':
    unittest.main()
