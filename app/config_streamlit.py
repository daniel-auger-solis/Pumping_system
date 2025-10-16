import streamlit as st

def configurar_app():
    # Configuración de la página
    st.set_page_config(
        page_title="Simulador Hidráulico",
        page_icon="💧",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Ocultar menú, header y footer
    hide_streamlit_style = """
        <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        </style>
    """
    st.markdown(hide_streamlit_style, unsafe_allow_html=True)
