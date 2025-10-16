import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import altair as alt
import os
from src.fluido import generar_perfil_con_bombas_automaticas
from app.config_streamlit import configurar_app

# Configurar Streamlit
configurar_app()

st.title("📈 Número de bombas indefinido")
st.write("""
Este módulo permite generar el **perfil hidráulico** correspondiente al transporte de un fluido a lo largo del **perfil geográfico** que se adjunta en formato CSV.  
A partir de los datos del terreno y los parámetros hidráulicos definidos, el sistema calcula las **pérdidas de carga** y determina la ubicación de cada **bomba** necesaria para mantener la presión adecuada en todo el trayecto.  

El usuario puede definir la **presión inicial**, la **altura de seguridad** y el **head de las bombas**, visualizando finalmente la **línea de presión** superpuesta al perfil del terreno.
""")

st.header("Parámetros")

# Columnas para organizar la entrada de datos
col1, col2, col3, col4 = st.columns(4, border=True)

# Columna 1: selección del archivo
with col1:
    st.subheader("Archivo CSV del perfil")
    carpeta_data = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    archivos_disponibles = [f for f in os.listdir(carpeta_data) if f.endswith(".csv")]

    opcion_origen = st.radio(
        "¿Cómo quieres ingresar el archivo?",
        ("📂 Elegir desde carpeta /data", "⬆️ Subir archivo CSV manualmente")
    )

    P_geo_csv = None  # Variable para almacenar la ruta del archivo

    if opcion_origen == "📂 Elegir desde carpeta /data":
        opciones_archivos = ["Selecciona archivo"] + archivos_disponibles
        archivo_seleccionado = st.selectbox("Selecciona un archivo existente:", opciones_archivos, index=0)
        if archivo_seleccionado != "Selecciona archivo":
            P_geo_csv = os.path.join(carpeta_data, archivo_seleccionado)
            st.success(f"Archivo seleccionado: {archivo_seleccionado}")

    else:
        archivo = st.file_uploader("Sube el archivo CSV del perfil geográfico", type=["csv"])
        if archivo is not None:
            temp_path = os.path.join(carpeta_data, archivo.name)
            with open(temp_path, "wb") as f:
                f.write(archivo.getbuffer())
            P_geo_csv = temp_path
            st.success(f"Archivo subido correctamente: {archivo.name}")


# Columna 2: parámetros del fluido
with col2:
    st.subheader("Parámetros del fluido")
    densidad = st.number_input("Densidad [kg/m³]", value=1000.0, step=10.0)
    viscosidad = st.number_input("Viscosidad [Pa·s]", value=0.001, step=0.001, format="%.3f")
    velocidad = st.number_input("Velocidad [m/s]", value=1.5)

# Columna 3: parámetros de la tubería
with col3:
    st.subheader("Parámetros de la tubería")
    diametro = st.number_input("Diámetro [m]", value=0.1)
    rugosidad = st.number_input("Rugosidad [m]", value=0.0002, step=0.0001, format="%.4f")

# Columna 4: condiciones iniciales
with col4:
    st.subheader("Condiciones iniciales")
    presion_inicial_m = st.number_input("Presión inicial [m]", value=10.0, step=1.0)
    altura_seguridad = st.number_input("Altura de seguridad [m]", value=3.0, step=1.0)
    head_bomba = st.number_input("Head de bomba [m]", value=5.0, step=1.0)
    num_puntos_extra = st.number_input("Puntos extra (interpolación)", min_value=0, value=0)

# Crear clave en session_state si no existe
if "resultado_perfil_bombas_indefinido" not in st.session_state:
    st.session_state.resultado_perfil_bombas_indefinido = None

# Botón para ejecutar el cálculo
if st.button("🚀 Calcular perfil hidráulico") and P_geo_csv:
    fluido = {'densidad': densidad, 'viscosidad': viscosidad, 'velocidad': velocidad}
    tuberia = {'diametro': diametro, 'rugosidad': rugosidad}

    x_final, h_final, bombas = generar_perfil_con_bombas_automaticas(
        P_geo_csv,
        fluido,
        tuberia,
        presion_inicial_m,
        altura_seguridad,
        head_bomba,
        num_puntos_extra=num_puntos_extra if num_puntos_extra > 0 else None
    )

    # Guardar resultados en session_state
    st.session_state.resultado_perfil_bombas_indefinido = {
        "x_final": x_final,
        "h_final": h_final,
        "bombas": bombas,
        "archivo": P_geo_csv
    }

    st.success(f"✅ Cálculo completado. Se agregaron {len(bombas)} bombas.")

# Mostrar resultados si existen en session_state
if st.session_state.resultado_perfil_bombas_indefinido:
    resultado = st.session_state.resultado_perfil_bombas_indefinido
    bombas = resultado["bombas"]

    # Crear columnas para tabla y gráfico
    col1, col2 = st.columns(2)

    # Columna 1: tabla de bombas
    with col1:
        st.subheader("📋 Tabla de bombas")
        if bombas:
            df_bombas = pd.DataFrame(bombas, index=range(1, len(bombas)+1))
            df_bombas = df_bombas.rename(columns={"x": "Distancia [m]", "head": "Energía entregada [m]"})
            st.dataframe(df_bombas)
        else:
            st.write("No se agregaron bombas.")

    # Columna 2: gráfico
    with col2:
        st.subheader("📈 Gráfico del perfil hidráulico")

        # Leer perfil geográfico
        df_csv = pd.read_csv(resultado["archivo"], header=None)
        df_csv.columns = ["x", "z"]

        # Terreno
        terreno = alt.Chart(df_csv).mark_area(
            color='saddlebrown', opacity=0.4
        ).encode(
            x=alt.X('x', axis=alt.Axis(title='Distancia [m]')),
            y=alt.Y('z', axis=alt.Axis(title='Altura [m]'))
        ) + alt.Chart(df_csv).mark_line(
            color='saddlebrown'
        ).encode(
            x='x',
            y='z'
        )

        # Línea de presión
        df_presion = pd.DataFrame({"x": resultado["x_final"], "Altura": resultado["h_final"]})
        linea_presion = alt.Chart(df_presion).mark_line(color='deepskyblue').encode(
            x=alt.X('x', axis=alt.Axis(title='Distancia [m]')),
            y=alt.Y('Altura', axis=alt.Axis(title='Altura [m]'))
        )

        grafico = terreno + linea_presion
        st.altair_chart(grafico, use_container_width=True)