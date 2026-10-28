"""Small, testable Streamlit rendering primitives."""


def render_labeled_value(container, label: str, value) -> None:
    """Render a label/value pair without passing multiple objects to st.write."""
    container.markdown(f"**{label}**")
    container.write(value)
