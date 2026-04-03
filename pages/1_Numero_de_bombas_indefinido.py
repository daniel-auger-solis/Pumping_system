import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import os
import json
from src.fluido import generar_perfil_con_bombas_automaticas
from app.config_streamlit import configurar_app

configurar_app()

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
PATH_GEOGRAFICO = os.path.join(BASE_DIR, "data", "geografico")
PATH_MATERIALES = os.path.join(BASE_DIR, "data", "material")

os.makedirs(PATH_GEOGRAFICO, exist_ok=True)
os.makedirs(PATH_MATERIALES, exist_ok=True)

ACERO_NOMBRE = "Acero al Carbono ANSI B36.10 / B36.19"
DN_DEFAULT_ACERO = 150
DN_DEFAULT_HDPE  = 140

# --- Funciones auxiliares ---
def listar_materiales():
    archivos = [f for f in os.listdir(PATH_MATERIALES) if f.endswith(".json")]
    materiales_dict = {}
    for arc in archivos:
        with open(os.path.join(PATH_MATERIALES, arc), "r", encoding="utf-8") as f:
            datos = json.load(f)
            materiales_dict[datos["material"]] = datos
    return materiales_dict

def detectar_tipo_material(modelos: list) -> str:
    if modelos and "pn" in modelos[0]:
        return "pn"
    return "schedule"

materiales_disponibles = listar_materiales()

# --- Inicializar session_state ---
for key, val in [
    ("resultado_perfil_bombas_indefinido", None),
    ("params_ultimo_calculo",              None),
    ("mostrar_aviso_desactualizado",       False),
]:
    if key not in st.session_state:
        st.session_state[key] = val

# ── UI ────────────────────────────────────────────────────────────────────────
st.title("📈 Número de bombas indefinido")
st.write("""
Este módulo permite generar el **perfil hidráulico** correspondiente al transporte de un fluido
a lo largo del **perfil geográfico** que se adjunta en formato CSV.  
A partir de los datos del terreno y los parámetros hidráulicos definidos, el sistema calcula
las **pérdidas de carga** y determina la ubicación de cada **bomba** necesaria para mantener
la presión adecuada en todo el trayecto.
""")

st.header("Parámetros")
col1, col2, col3, col4 = st.columns(4, border=True)

# ── Columna 1: archivo CSV ────────────────────────────────────────────────────
with col1:
    st.subheader("Archivo CSV del perfil")
    archivos_disponibles = [f for f in os.listdir(PATH_GEOGRAFICO) if f.endswith(".csv")]
    opcion_origen = st.radio(
        "¿Cómo quieres ingresar el archivo?",
        ("📂 Elegir desde carpeta /data", "⬆️ Subir archivo CSV manualmente"),
    )
    P_geo_csv = None
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

# ── Columna 3: tubería ────────────────────────────────────────────────────────
with col3:
    st.subheader("Tubería")

    diametro    = 0.1
    rugosidad   = 0.0002
    pn_seleccionado = None
    tipo_mat    = "pn"
    nombre_mat  = ""

    if materiales_disponibles:
        nombres_materiales = list(materiales_disponibles.keys())
        nombre_mat = st.selectbox("Material:", nombres_materiales)

        info_mat = materiales_disponibles[nombre_mat]
        modelos  = info_mat["modelos_cañerias"]
        tipo_mat = detectar_tipo_material(modelos)

        diametros_unicos = sorted(set(m["dn_mm"] for m in modelos))

        # DN por defecto según material
        if nombre_mat == ACERO_NOMBRE:
            dn_def = DN_DEFAULT_ACERO
        else:
            dn_def = DN_DEFAULT_HDPE

        indice_default = (
            diametros_unicos.index(dn_def)
            if dn_def in diametros_unicos
            else 0
        )

        dn_seleccionado = st.selectbox("DN [mm]:", diametros_unicos, index=indice_default)
        modelos_dn = [m for m in modelos if m["dn_mm"] == dn_seleccionado]

        if tipo_mat == "pn":
            pns_disponibles = sorted(set(m["pn"] for m in modelos_dn))
            pn_seleccionado = st.selectbox("PN [Bar]:", pns_disponibles)
            modelo_final = next(m for m in modelos_dn if m["pn"] == pn_seleccionado)
        else:
            orden_sch = [
                "Sch 5s", "Sch 10s", "Sch 10", "Sch 20", "Sch 30",
                "Sch 40s", "STD", "Sch 40", "Sch 60",
                "Sch 80s", "XS", "Sch 80", "Sch 100",
                "Sch 120", "Sch 140", "Sch 160", "XXS",
            ]
            schedules_disponibles = [
                s for s in orden_sch if any(m["schedule"] == s for m in modelos_dn)
            ]
            schedule_seleccionado = st.selectbox("Schedule:", schedules_disponibles)
            modelo_final = next(m for m in modelos_dn if m["schedule"] == schedule_seleccionado)
            pn_seleccionado = None

        diametro  = modelo_final["diametro_interno_mm"] / 1000.0
        rugosidad = info_mat["rugosidad_m"]

        if tipo_mat == "schedule":
            st.caption(f"OD: {modelo_final['od_mm']} mm  |  ID: {modelo_final['diametro_interno_mm']} mm  |  e: {modelo_final['espesor_mm']} mm")
        else:
            st.caption(f"Ø Interno: {modelo_final['diametro_interno_mm']} mm")
        st.write(f"**Rugosidad:** {rugosidad} m")
    else:
        st.error("No hay archivos de materiales en /data/materiales")

# ── Columna 2: fluido ─────────────────────────────────────────────────────────
with col2:
    st.subheader("Fluido")
    densidad   = st.number_input("Densidad [kg/m³]", value=1000.0)
    viscosidad = st.number_input("Viscosidad [Pa·s]", value=0.001, format="%.3f")
    caudal     = st.number_input("Caudal [m³/s]", value=0.015, format="%.4f")
    st.caption(f"≈ {caudal * 3600:.2f} m³/h")

    area      = np.pi * (diametro ** 2) / 4
    velocidad = caudal / area if diametro > 0 else 0.0
    st.text_input("Velocidad Resultante [m/s]", value=f"{velocidad:.3f}", disabled=True)

# ── Columna 4: condiciones iniciales ─────────────────────────────────────────
with col4:
    st.subheader("Condiciones iniciales")
    presion_inicial_m = st.number_input("Presión inicial [m]",          value=10.0, step=1.0)
    altura_seguridad  = st.number_input("Altura de seguridad [m]",       value=3.0,  step=1.0)
    head_bomba        = st.number_input("Head de bomba [m]",             value=5.0,  step=1.0)
    num_puntos_extra  = st.number_input("Puntos extra (interpolación)",  min_value=0, value=0)

# ── Snapshot de parámetros actuales ──────────────────────────────────────────
params_actuales = {
    "archivo":          P_geo_csv,
    "densidad":         densidad,
    "viscosidad":       viscosidad,
    "caudal":           caudal,
    "diametro":         diametro,
    "rugosidad":        rugosidad,
    "presion_inicial_m": presion_inicial_m,
    "altura_seguridad": altura_seguridad,
    "head_bomba":       head_bomba,
    "num_puntos_extra": num_puntos_extra,
}

# Detectar cambio de parámetros y encender el flag (nunca apagarlo aquí)
hay_resultado = st.session_state.resultado_perfil_bombas_indefinido is not None
if (
    hay_resultado
    and st.session_state.params_ultimo_calculo is not None
    and st.session_state.params_ultimo_calculo != params_actuales
):
    st.session_state.mostrar_aviso_desactualizado = True

# ── Aviso de parámetros cambiados (antes del botón) ──────────────────────────
if st.session_state.mostrar_aviso_desactualizado:
    st.info("🔄 Los parámetros han cambiado. Presiona **Calcular perfil hidráulico** para actualizar los resultados.")

# ── Botón de cálculo ──────────────────────────────────────────────────────────
boton_presionado = st.button("🚀 Calcular perfil hidráulico")

if boton_presionado:
    if not P_geo_csv:
        st.warning("⚠️ Debes seleccionar o subir un perfil geográfico CSV antes de calcular.")
    else:
        fluido  = {"densidad": densidad, "viscosidad": viscosidad, "velocidad": velocidad}
        tuberia = {"diametro": diametro, "rugosidad": rugosidad}

        x_final, h_final, bombas = generar_perfil_con_bombas_automaticas(
            P_geo_csv, fluido, tuberia,
            presion_inicial_m, altura_seguridad, head_bomba,
            num_puntos_extra=num_puntos_extra if num_puntos_extra > 0 else None,
        )

        if len(bombas) > 20:
            st.session_state.resultado_perfil_bombas_indefinido = None
            st.session_state.params_ultimo_calculo              = None
            st.session_state.mostrar_aviso_desactualizado       = False
            st.error(
                f"🚫 El cálculo requiere **{len(bombas)} bombas**, lo que supera el límite permitido de 20. "
                "Considera aumentar el DN, reducir el caudal o incrementar el head de bomba."
            )
        else:
            st.session_state.resultado_perfil_bombas_indefinido = {
                "x_final":  x_final,
                "h_final":  h_final,
                "bombas":   bombas,
                "archivo":  P_geo_csv,
                "pn_bar":   pn_seleccionado,
                "material": nombre_mat,
                "tipo_mat": tipo_mat,
            }
            st.session_state.params_ultimo_calculo        = params_actuales.copy()
            # Apagar el aviso ahora que el cálculo está fresco
            st.session_state.mostrar_aviso_desactualizado = False
            st.success(f"✅ Cálculo completado. Se agregaron {len(bombas)} bombas.")

# ── Visualización de Resultados ───────────────────────────────────────────────
if st.session_state.resultado_perfil_bombas_indefinido:
    res = st.session_state.resultado_perfil_bombas_indefinido

    col_tabla, col_graf = st.columns([1, 2])

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

        # Aviso encima del gráfico (mismo flag)
        if st.session_state.mostrar_aviso_desactualizado:
            st.warning("🔄 Estás viendo resultados desactualizados — presiona **Calcular perfil hidráulico** para actualizar.")

        df_terr = pd.read_csv(res["archivo"], header=None)
        df_terr.columns = ["x", "z"]

        tiene_pn = res["tipo_mat"] == "pn" and res["pn_bar"] is not None

        terreno = (
            alt.Chart(df_terr).mark_area(color="saddlebrown", opacity=0.3).encode(x="x", y="z")
            + alt.Chart(df_terr).mark_line(color="saddlebrown", size=2).encode(x="x", y="z")
        )
        capas = [terreno]

        if tiene_pn:
            mca_max = res["pn_bar"] * 10.197
            df_terr["mop"] = df_terr["z"] + mca_max
            linea_mop = alt.Chart(df_terr).mark_line(
                strokeDash=[6, 4], color="red", opacity=0.6
            ).encode(x="x", y="mop")
            capas.append(linea_mop)

        df_p = pd.DataFrame({"x": res["x_final"], "h": res["h_final"]})
        linea_p = alt.Chart(df_p).mark_line(color="dodgerblue", size=2.5).encode(
            x=alt.X("x", title="Distancia Horizontal [m]"),
            y=alt.Y("h", title="Elevación [msnm]", scale=alt.Scale(zero=False)),
        )
        capas.append(linea_p)

        st.altair_chart(alt.layer(*capas).properties(height=400), use_container_width=True)

        if tiene_pn:
            presion_max = max(res["h_final"])
            idx_max     = np.argmax(res["h_final"])
            cota_max    = df_terr.loc[
                (df_terr["x"] - res["x_final"][idx_max]).abs().idxmin(), "z"
            ]
            if (presion_max - cota_max) > mca_max:
                st.error(f"⚠️ ¡ALERTA DE SOBREPRESIÓN! La línea de energía supera el MOP de {res['pn_bar']} Bar.")
            else:
                st.caption(f"🛡️ Presión dentro de los límites para {res['material']} PN{res['pn_bar']}.")
        else:
            st.caption(f"ℹ️ Validación MOP no disponible para {res['material']} (sin PN asignado).")
