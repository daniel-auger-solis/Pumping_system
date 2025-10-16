import streamlit as st
from app.config_streamlit import configurar_app

# Configurar Streamlit
st.set_page_config(page_title="Portada", layout="wide")
configurar_app()

# Título principal
st.title("💧 Simulador de Pérdida de Carga con Bombas Hidráulicas")

# Texto explicativo de la aplicación
st.write("""
Bienvenido al **Simulador de Pérdida de Carga con Bombas Hidráulicas**.  

Esta aplicación permite calcular el **perfil hidráulico** de un sistema de transporte de fluido a lo largo de un **perfil geográfico** que se proporciona en formato CSV.  

Con esta herramienta podrás:

- Visualizar el **perfil del terreno** y la **línea de presión** del fluido.
- Determinar la ubicación y el **head de las bombas** necesarias para mantener la presión adecuada.
- Realizar cálculos tanto **desde la presión inicial** como **desde la presión final deseada**, según la página multipágina que selecciones.
- Obtener tablas y gráficos interactivos que muestran los resultados del cálculo.

📌 Para comenzar, selecciona la página correspondiente en la barra lateral:

- **Número de bombas indefinido**: Calcula el perfil hidráulico definiendo la presión inicial y la altura de seguridad, dejando que el sistema determine cuántas bombas agregar.
- **Cálculo con Presión Final Definida**: Calcula el perfil hidráulico partiendo de una presión final conocida, pudiendo agregar bombas intermedias para mantener la presión objetivo.
""")
