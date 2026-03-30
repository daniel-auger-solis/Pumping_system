import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import altair as alt
import os
import json
from src.fluido import generar_perfil_con_bombas_automaticas
from app.config_streamlit import configurar_app

# Configurar Streamlit
configurar_app()

# --- Lógica de Rutas para Data ---
# Obtenemos la raíz del proyecto (un nivel arriba de /pages o /app)
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
PATH_GEOGRAFICO = os.path.join(BASE_DIR, "data", "geografico")
PATH_MATERIALES = os.path.join(BASE_DIR, "data", "material")

# Asegurar que las carpetas existan para evitar errores
os.makedirs(PATH_GEOGRAFICO, exist_ok=True)
os.makedirs(PATH_MATERIALES, exist_ok=True)

# --- Funciones de carga de Materiales ---
def listar_materiales():
    archivos = [f for f in os.listdir(PATH_MATERIALES) if f.endswith(".json")]
    materiales_dict = {}
    for arc in archivos:
        with open(os.path.join(PATH_MATERIALES, arc), "r", encoding="utf-8") as f:
            datos = json.load(f)
            materiales_dict[datos["material"]] = datos
    return materiales_dict

materiales_disponibles = listar_materiales()

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
    archivos_disponibles = [f for f in os.listdir(PATH_GEOGRAFICO) if f.endswith(".csv")]

    opcion_origen = st.radio(
        "¿Cómo quieres ingresar el archivo?",
        ("📂 Elegir desde carpeta /data", "⬆️ Subir archivo CSV manualmente")
    )

    P_geo_csv = None  # Variable para almacenar la ruta del archivo

    if opcion_origen == "📂 Elegir desde carpeta /data":
        archivo_sel = st.selectbox("Selecciona perfil:", ["Selecciona"] + archivos_disponibles)
        if archivo_sel != "Selecciona":
            P_geo_csv = os.path.join(PATH_GEOGRAFICO, archivo_sel)

    else:
        archivo = st.file_uploader("Sube el perfil geográfico", type=["csv"])
        if archivo:
            P_geo_csv = os.path.join(PATH_GEOGRAFICO, archivo.name)
            with open(P_geo_csv, "wb") as f:
                f.write(archivo.getbuffer())
            st.success("Cargado en /geografico")


# Columna 3: parámetros de la tubería (La movemos antes o calculamos primero el diámetro)
with col3:
    st.subheader("Tubería")
    
    if materiales_disponibles:
        # 1. Seleccionar Material
        nombre_mat = st.selectbox("Material:", list(materiales_disponibles.keys()))
        info_mat = materiales_disponibles[nombre_mat]
        modelos = info_mat["modelos_cañerias"]
        
        # 2. Seleccionar Diámetro (DN mm) - Eliminando duplicados
        diametros_unicos = sorted(list(set(m["dn_mm"] for m in modelos)))
        dn_seleccionado = st.selectbox("DN [mm]:", diametros_unicos)
        
        # 3. Seleccionar PN (Presión Nominal) según el diámetro elegido
        pns_disponibles = sorted([m["pn"] for m in modelos if m["dn_mm"] == dn_seleccionado])
        pn_seleccionado = st.selectbox("PN [Bar]:", pns_disponibles)
        
        # 4. Obtener datos técnicos finales del modelo seleccionado
        modelo_final = next(m for m in modelos if m["dn_mm"] == dn_seleccionado and m["pn"] == pn_seleccionado)
        
        # El diámetro interno es el que se usa para el cálculo hidráulico (convertido a metros)
        diametro = modelo_final["diametro_interno_mm"] / 1000.0
        rugosidad = info_mat["rugosidad_m"]
        
        st.caption(f"Ø Interno: {modelo_final['diametro_interno_mm']} mm")
        st.write(f"**Rugosidad:** {rugosidad} m")
    else:
        st.error("No hay archivos de materiales en /data/materiales")
        diametro = 0.1
        rugosidad = 0.0002

# Columna 2: parámetros del fluido
with col2:
    st.subheader("Fluido")
    densidad = st.number_input("Densidad [kg/m³]", value=1000.0)
    viscosidad = st.number_input("Viscosidad [Pa·s]", value=0.001, format="%.3f")
    caudal = st.number_input("Caudal [m³/s]", value=0.015, format="%.4f")
    
    # Cálculo de velocidad usando el 'diametro' interno obtenido del JSON
    area = np.pi * (diametro ** 2) / 4
    velocidad = caudal / area if diametro > 0 else 0.0
    
    st.text_input("Velocidad Resultante [m/s]", value=f"{velocidad:.3f}", disabled=True)
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

# --- Ejecución del Cálculo ---
if st.button("🚀 Calcular perfil hidráulico") and P_geo_csv:
    # Usamos la 'velocidad' que ya calculamos reactivamente en la Columna 2
    fluido = {
        'densidad': densidad, 
        'viscosidad': viscosidad, 
        'velocidad': velocidad
    }
    
    # Usamos el 'diametro' interno y la 'rugosidad' obtenidos del JSON en la Columna 3
    tuberia = {
        'diametro': diametro, 
        'rugosidad': rugosidad
    }

    x_final, h_final, bombas = generar_perfil_con_bombas_automaticas(
        P_geo_csv,
        fluido,
        tuberia,
        presion_inicial_m,
        altura_seguridad,
        head_bomba,
        num_puntos_extra=num_puntos_extra if num_puntos_extra > 0 else None
    )

    # Guardar resultados y metadatos técnicos en session_state
    st.session_state.resultado_perfil_bombas_indefinido = {
        "x_final": x_final,
        "h_final": h_final,
        "bombas": bombas,
        "archivo": P_geo_csv,
        "pn_bar": pn_seleccionado,  # Guardamos el PN para el gráfico MOP
        "material": nombre_mat
    }

    st.success(f"✅ Cálculo completado. Se agregaron {len(bombas)} bombas.")

# --- Visualización de Resultados ---
if st.session_state.resultado_perfil_bombas_indefinido:
    res = st.session_state.resultado_perfil_bombas_indefinido
    
    col_tabla, col_graf = st.columns([1, 2]) # Le damos más ancho al gráfico

    with col_tabla:
        st.subheader("📋 Detalle de Instalación")
        if res["bombas"]:
            df_b = pd.DataFrame(res["bombas"])
            df_b.columns = ["Distancia [m]", "Head [m]"]
            st.dataframe(df_b, use_container_width=True)
        else:
            st.info("El sistema no requirió bombas adicionales.")

    with col_graf:
        st.subheader(f"📈 Perfil Hidráulico: {res['material']}")

        # 1. Preparar Datos del Terreno y MOP
        df_terr = pd.read_csv(res["archivo"], header=None)
        df_terr.columns = ["x", "z"]
        
        # Calcular MOP (Línea roja de rotura)
        mca_max = res["pn_bar"] * 10.197
        df_terr["mop"] = df_terr["z"] + mca_max

        # 2. Gráfico de Terreno (Área)
        terreno = alt.Chart(df_terr).mark_area(color='saddlebrown', opacity=0.3).encode(
            x='x', y='z'
        ) + alt.Chart(df_terr).mark_line(color='saddlebrown', size=2).encode(
            x='x', y='z'
        )

        # 3. Gráfico MOP (Línea discontinua roja)
        linea_mop = alt.Chart(df_terr).mark_line(
            strokeDash=[6, 4], color='red', opacity=0.6
        ).encode(x='x', y='mop')

        # 4. Línea de Presión (Azul)
        df_p = pd.DataFrame({"x": res["x_final"], "h": res["h_final"]})
        linea_p = alt.Chart(df_p).mark_line(color='dodgerblue', size=2.5).encode(
            x=alt.X('x', title='Distancia Horizontal [m]'),
            y=alt.Y('h', title='Elevación [msnm]', scale=alt.Scale(zero=False))
        )

        # 5. Combinar y mostrar
        grafico_final = (terreno + linea_mop + linea_p).properties(height=400)
        st.altair_chart(grafico_final, use_container_width=True)

        # --- Validación de Seguridad ---
        # Comprobamos si la presión máxima alcanzada supera el MOP
        presion_max = max(res["h_final"])
        cota_en_presion_max = df_terr.loc[(df_terr['x'] - res['x_final'][np.argmax(res['h_final'])]).abs().idxmin(), 'z']
        
        if (presion_max - cota_en_presion_max) > mca_max:
            st.error(f"⚠️ ¡ALERTA DE SOBREPRESIÓN! La línea de energía supera el MOP de {res['pn_bar']} Bar.")
        else:
            st.caption(f"🛡️ Presión dentro de los límites de operación para {res['material']} PN{res['pn_bar']}.")
