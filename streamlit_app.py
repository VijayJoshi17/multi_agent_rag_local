import streamlit as st
import requests
import json
import time

# Page Config
st.set_page_config(
    page_title="Multi-Agent RAG (Free)",
    page_icon="🤖",
    layout="wide"
)

# Constants
API_URL = "http://127.0.0.1:8000/api/v1/chat/stream"

# Title & Description
st.title("🤖 Multi-Agent RAG System (Local)")
st.markdown("""
This system uses a **Team of Agents** (Retriever, Summarizer, Reasoner, Verifier) 
driven by **Ollama (Phi-3 / Llama-3)** and **LangGraph** to answer your questions accurately.
""")

# Sidebar
with st.sidebar:
    st.header("System Status")
    try:
        # Simple health check (just checking if root returns 200)
        # Add timeout to prevent hanging if backend is down
        health = requests.get("http://127.0.0.1:8000/", timeout=5)
        if health.status_code == 200:
            st.success("Backend is Online ✅")
        else:
            st.error("Backend Error ❌")
    except Exception as e:
        st.error(f"Backend Offline ❌: {str(e)}")
        st.info("Run `uvicorn app.main:app --reload` in terminal")
    
    st.markdown("### ⚙️ Mode Selection")
    mode = st.radio("Choose Agent Mode", ["General Assistant", "Web Search Only", "Data Analyst"], help="General: RAG + Web. Web: Force Search. Data: Excel/CSV.")
    
    if mode == "Data Analyst":
        mode_key = "data_analyst"
    elif mode == "Web Search Only":
        mode_key = "web_search"
    else:
        mode_key = "general"

    st.markdown("### 📂 Document Upload")
    
    if mode == "Data Analyst":
        uploaded_file = st.file_uploader("Upload Data File", type=["csv", "xlsx"])
        if st.button("Upload Data", type="secondary"):
            if uploaded_file is not None:
                with st.spinner("Uploading Data..."):
                     # ... (Existing upload logic logic reused, but minimal change needed besides text)
                     try:
                        files = {"file": (uploaded_file.name, uploaded_file, "application/octet-stream")}
                        response = requests.post("http://127.0.0.1:8000/api/v1/upload", files=files)
                        if response.status_code == 200:
                            st.success("✅ Data Uploaded Successfully!")
                        else:
                            st.error(f"❌ Upload Failed: {response.text}")
                     except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
            else:
                st.warning("Please select a file.")
    else:
        # Knowledge Base Management
        st.sidebar.markdown("### 📚 Knowledge Base")
        
        col1, col2 = st.sidebar.columns([1,1])
        
        if col1.button("Reset KB", type="primary", help="Delete all documents"):
            try:
                resp = requests.delete("http://127.0.0.1:8000/api/v1/reset")
                if resp.status_code == 200:
                    st.sidebar.success("Cleared!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.sidebar.error(f"Failed: {resp.text}")
            except Exception as e:
                st.sidebar.error(f"Error: {str(e)}")

        uploaded_file = st.sidebar.file_uploader("Upload Document (PDF, Word, Text, Zip)", type=["txt", "pdf", "docx", "md", "pptx", "zip"])
        if st.button("Upload & Ingest", type="secondary"):
            if uploaded_file is not None:
                with st.spinner("Uploading & Ingesting..."):
                    try:
                        files = {"file": (uploaded_file.name, uploaded_file, "text/plain")}
                        response = requests.post("http://127.0.0.1:8000/api/v1/upload", files=files)
                        if response.status_code == 200:
                            st.success("✅ Ingested Successfully!")
                        else:
                            st.error(f"❌ Upload Failed: {response.text}")
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
            else:
                st.warning("Please select a file.")

    st.markdown("---")
    st.markdown("### Configuration")
    top_k = st.slider("Documents to Retrieve (Top-K)", 1, 10, 3)
    run_verification = st.checkbox("Enable Verifier Agent (Accurate, Slower)", value=True, help="Uncheck for faster answers (skips verification step)")

# Helper for Graph Visualization
def get_workflow_graph(active_node=None, visited_nodes=None):
    if visited_nodes is None:
        visited_nodes = set()
        
    # Colors
    inactive_color = "white"
    active_color = "#ffeb3b" # Yellow/Orange for active
    completed_color = "#a5d6a7" # Green for visited
    
    # Node Definitions
    nodes = {
        "start": "Start",
        "contextualize": "Contextualize",
        "router": "Router",
        "retrieve": "Retrieve (Docs)",
        "web_search": "Web Search",
        "data_analyst": "Data Analyst",
        "reason": "Reasoner",
        "verifier": "Verifier",
        "optimize": "Optimizer",
        "parser": "Parser",
        "end": "End"
    }
    
    dot = 'digraph G {\n'
    dot += '    rankdir=LR;\n'
    dot += '    node [shape=box, style="filled,rounded", fontname="Arial"];\n'
    
    # Define Nodes with formatting
    for key, label in nodes.items():
        color = inactive_color
        if key == active_node:
            color = active_color
        elif key in visited_nodes:
            color = completed_color
            
        # Bold the active node
        penwidth = "2.0" if key == active_node else "1.0"
        dot += f'    {key} [label="{label}", fillcolor="{color}", penwidth="{penwidth}"];\n'
    
    # Define Edges (Static Structure of Supervisor)
    dot += '    start -> contextualize;\n'
    dot += '    contextualize -> router [label="General"];\n'
    dot += '    contextualize -> data_analyst [label="Data Mode"];\n'
    dot += '    contextualize -> web_search [label="Web Mode"];\n'
    
    dot += '    router -> retrieve [label="Internal"];\n'
    dot += '    router -> web_search [label="External"];\n'
    
    dot += '    retrieve -> reason;\n'
    dot += '    web_search -> reason;\n'
    dot += '    data_analyst -> reason;\n'
    
    dot += '    reason -> verify [label="Verify=True"];\n'
    dot += '    reason -> optimize [label="Verify=False"];\n'
    dot += '    verify -> optimize;\n'
    dot += '    optimize -> parser;\n'
    dot += '    parser -> end;\n'
    
    dot += '}'
    
    return dot
    

# Main Chat Interface
# Session State for Chat History
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display Chat History
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Main Chat Input
if prompt := st.chat_input("Ask a question..."):
    # Add User Message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Agent Response
    with st.chat_message("assistant"):
        # Create Placeholders for Live Updates
        graph_placeholder = st.empty()
        status_container = st.status("🚀 Agents are thinking...", expanded=True)
        log_container = st.expander("📝 Live Execution Logs", expanded=True)
        response_placeholder = st.empty()
        
        # Initial Graph State
        visited_nodes = set()
        graph_placeholder.graphviz_chart(get_workflow_graph("start", visited_nodes))
        
        try:
            # Prepare Payload with History
            chat_history = [
                {"role": m["role"], "content": m["content"]} 
                for m in st.session_state.messages[:-1] 
            ]
            
            payload = {
                "query": prompt,
                "top_k": top_k,
                "run_verification": run_verification,
                "mode": mode_key,
                "chat_history": chat_history
            }
            
            # Streaming Request
            response = requests.post(API_URL, json=payload, stream=True)
            response.raise_for_status()
            
            final_data = None
            
            for line in response.iter_lines():
                if line:
                    event = json.loads(line.decode('utf-8'))
                    
                    if event["type"] == "start":
                        visited_nodes.add("start")
                        # Update to show start as visited? No, keep it yellow or green?
                        # When next node starts, start will be green.
                        
                    elif event["type"] == "status":
                        agent_name = event["agent"]
                        status_type = event.get("status", "complete")
                        details = event.get("details", "")
                        
                        # Update Graph!
                        if status_type == "starting":
                             graph_placeholder.graphviz_chart(get_workflow_graph(agent_name, visited_nodes))
                        elif status_type == "complete":
                             visited_nodes.add(agent_name)
                             graph_placeholder.graphviz_chart(get_workflow_graph(None, visited_nodes))
                             
                        icon = "🤖"
                        if agent_name == "contextualize": icon = "🔄"
                        elif agent_name == "router": icon = "🚥"
                        elif agent_name == "web_search": icon = "globe"
                        elif agent_name == "retrieve": icon = "🔍"
                        elif agent_name == "data_analyst": icon = "📊"
                        elif agent_name == "reason": icon = "🧠"
                        elif agent_name == "verify": icon = "✅"
                        elif agent_name == "optimize": icon = "⚙️"
                        elif agent_name == "parser": icon = "📝"
                        
                        if status_type == "starting":
                             status_container.markdown(f"**{icon} {agent_name.title()}**: {details}")
                        
                    elif event["type"] == "final":
                        final_data = event["data"]
                        status_container.update(label="✅ Answer Ready", state="complete", expanded=False)
                        graph_placeholder.graphviz_chart(get_workflow_graph("end"))
                    
                    elif event["type"] == "error":
                        status_container.update(label="❌ Error", state="error")
                        st.error(event["error"])
                        
                    # Update Logs
                    if "logs" in event:
                         with log_container.container():
                             for log_entry in event["logs"]:
                                 if not log_entry or not log_entry.strip():
                                     continue
                                     
                                 # Color code based on agent
                                 color = None
                                 if "[Retriever]" in log_entry: color = "blue"
                                 elif "[Router]" in log_entry: color = "orange"
                                 elif "[WebSearch]" in log_entry: color = "green"
                                 elif "[DataAnalyst]" in log_entry: color = "violet"
                                 elif "[Reasoner]" in log_entry: color = "violet"
                                 elif "[Parser]" in log_entry: color = "blue"
                                 
                                 if color:
                                     st.markdown(f":{color}[{log_entry}]")
                                 else:
                                     st.markdown(log_entry)
                        
            if final_data:
                # Display Final Answer
                response_placeholder.markdown(final_data["response"])
                
                # Append to History
                st.session_state.messages.append({"role": "assistant", "content": final_data["response"]})
                
                # Show Sources in Expander
                with st.expander("📚 Sources & Metadata", expanded=False):
                    st.caption(f"Trace ID: {final_data['trace_id']}")
                    st.caption(f"Confidence: {final_data['confidence_score']}")
                    
                    for idx, source in enumerate(final_data["sources"]):
                        st.markdown(f"**Source {idx+1}**")
                        # Check if it's a data analysis result
                        if source.get("metadata", {}).get("type") == "data_analysis":
                             st.markdown("📊 **Data Analysis Result**")
                             st.code(source["text"])
                        else:
                             # Regular text
                             st.info(source["text"][:500] + "...")
                        
                        # Metadata
                        meta = source.get("metadata", {})
                        st.caption(f"File: `{meta.get('source', 'unknown')}` | Type: `{meta.get('type', 'doc')}`")
                        st.divider()

        except Exception as e:
            st.error(f"Error: {str(e)}")

