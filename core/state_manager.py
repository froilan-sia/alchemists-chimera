"""
Session state management for Streamlit application.
"""
import streamlit as st
from typing import Any, Optional

class StateManager:
    """Manages session state for the Streamlit application."""

    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        """Get value from session state with default."""
        if key not in st.session_state:
            st.session_state[key] = default
        return st.session_state[key]

    @staticmethod
    def set(key: str, value: Any) -> None:
        """Set value in session state."""
        st.session_state[key] = value

    @staticmethod
    def clear(key: Optional[str] = None) -> None:
        """Clear session state or specific key."""
        if key:
            if key in st.session_state:
                del st.session_state[key]
        else:
            for key in list(st.session_state.keys()):
                del st.session_state[key]

    @staticmethod
    def get_role() -> str:
        """Get current user role."""
        return StateManager.get('role', 'Compliance Officer (Demo)')
