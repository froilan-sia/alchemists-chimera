"""
Sidebar component with role selector.
"""
import streamlit as st
import os

def render_sidebar() -> None:
    """Render the sidebar with role selector and navigation."""
    with st.sidebar:
        st.title("🧭 Navigation")

        # Role selector with key="role" for persistence
        # Streamlit automatically manages st.session_state.role when key="role" is used
        st.selectbox(
            "Select Your Role",
            ["Compliance Officer (Demo)", "Risk Auditor", "Regulatory Analyst"],
            index=0,
            key="role",  # Key ensures persistence across reruns
            help="Select your role for audit trail attribution"
        )

        # Navigation
        st.divider()
        st.markdown("### Tabs")
        st.markdown("""
        - **Hybrid Chat**: Query the knowledge base
        - **Surgeon's Table**: Upload and approve PDFs
        - **KG Explorer**: Visualize the knowledge graph
        """)

        # Environment info
        st.divider()
        st.caption(f"Role: {st.session_state.get('role', 'Not set')}")

        # LLM mode info
        llm_mode = os.getenv("LLM_MODE", "local")
        mode_display = {
            "local": "Local Ollama",
            "mock": "Mock Mode (Demo)",
            "api": "External API"
        }.get(llm_mode, "Unknown")
        st.caption(f"LLM: {mode_display}")

        # Quick actions
        st.divider()
        st.markdown("### Quick Actions")
        if st.button("Clear Session Cache", use_container_width=True):
            st.cache_resource.clear()
            st.cache_data.clear()
            st.success("Cache cleared!")

        if st.button("Reset Session", use_container_width=True):
            # Clear all session state except role
            current_role = st.session_state.get('role')
            for key in list(st.session_state.keys()):
                if key != "role":  # Keep role selection
                    del st.session_state[key]
            if current_role:
                st.session_state.role = current_role  # Restore role
            st.rerun()
