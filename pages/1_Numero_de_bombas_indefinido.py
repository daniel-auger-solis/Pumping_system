import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import os
import json
from src.fluido import generar_perfil_con_bombas_automaticas
from app.config_streamlit import configurar_app

CP = None
COOLPROP_OK = False
COOLPROP_ERROR = ""
try:
    import CoolProp.CoolProp as CP
    COOLPROP_OK = True
except Exception as _e:
    COOLPROP_ERROR = str(_e)

configurar_app()

BASE_DIR        = os.path.dirname(os.path.dirname(__file__))
PATH_GEOGRAFICO = os.path.join(BASE_DIR, "data", "geografico")
PATH_MATERIALES = os.path.join(BASE_DIR, "data", "material")
PATH_FLUIDOS    = os.path.join(BASE_DIR, "data", "fluidos.json")

os.makedirs(PATH_GEOGRAFICO, exist_ok=True)
os.makedirs(PATH_MATERIALES, exist_ok=True)

ACERO_NOMBRE     = "Acero al Carbono ANSI B36.10 / B36.19"
DN_DEFAULT_ACERO = 150
DN_DEFAULT_HDPE  = 140
OPCION_CUSTOM    = "— Fluido personalizado —"
FLUIDO_DEFAULT   = "Agua"
P_ATM_BAR        = 1.01325
T_DEFAULT_C      = 25.0


# ── Funciones auxiliares ──────────────────────────────────────────────────────
def listar_materiales():
    archivos = [f for f in os.listdir(PATH_MATERIALES) if f.endswith(".json")]
    resultado = {}
    for arc in archivos:
        with open(os.path.join(PATH_MATERIALES, arc), "r", encoding="utf-8") as f:
            datos = json.load(f)
            resultado[datos["material"]] = datos
    return resultado


def detectar_tipo_material(modelos: list) -> str:
    return "pn" if (modelos and "pn" in modelos[0]) else "schedule"


def cargar_fluidos() -> dict:
    """Devuelve {nombre_es: nombre_en} para CoolProp."""
    if not os.path.exists(PATH_FLUIDOS):
        return {"Agua": "Water"}
    with open(PATH_FLUIDOS, "r", encoding="utf-8") as f:
        lista = json.load(f)
    return {item["name_es"]: item["name_en"] for item in lista}


def propiedades_coolprop(nombre_en: str, T_C: float, P_bar: float):
    """Retorna (densidad kg/m³, viscosidad Pa·s, error_str) o (None, None, msg) si falla."""
    if not COOLPROP_OK:
        msg = f"CoolProp no disponible: {COOLPROP_ERROR}" if COOLPROP_ERROR else "CoolProp no instalado."
        return None, None, msg
    try:
        T_K  = T_C + 273.15
        P_Pa = P_bar * 1e5
        rho  = CP.PropsSI("D", "T", T_K, "P", P_Pa, nombre_en)
        mu   = CP.PropsSI("V", "T", T_K, "P", P_Pa, nombre_en)
        return rho, mu, None
    except Exception as e:
        return None, None, str(e)


# ── Datos globales ────────────────────────────────────────────────────────────
materiales_disponibles = listar_materiales()
fluidos_dict           = cargar_fluidos()           # {es: en}
nombres_fluidos_es     = sorted(fluidos_dict.keys())

# ── Inicializar session_state ─────────────────────────────────────────────────
for key, val in [
    ("resultado_perfil_bombas_indefinido", None),
    ("params_ultimo_calculo",              None),
    ("mostrar_aviso_desactualizado",       False),
    ("singularidades",                     []),
    ("modal_singularidades",               False),
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

    diametro        = 0.1
    rugosidad       = 0.0002
    pn_seleccionado = None
    tipo_mat        = "pn"
    nombre_mat      = ""

    if materiales_disponibles:
        nombres_materiales = list(materiales_disponibles.keys())
        nombre_mat = st.selectbox("Material:", nombres_materiales)

        info_mat = materiales_disponibles[nombre_mat]
        modelos  = info_mat["modelos_cañerias"]
        tipo_mat = detectar_tipo_material(modelos)

        diametros_unicos = sorted(set(m["dn_mm"] for m in modelos))
        dn_def = DN_DEFAULT_ACERO if nombre_mat == ACERO_NOMBRE else DN_DEFAULT_HDPE
        indice_default = diametros_unicos.index(dn_def) if dn_def in diametros_unicos else 0

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
            schedules_disponibles = [s for s in orden_sch if any(m["schedule"] == s for m in modelos_dn)]
            schedule_seleccionado = st.selectbox("Schedule:", schedules_disponibles)
            modelo_final    = next(m for m in modelos_dn if m["schedule"] == schedule_seleccionado)
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

    # --- Checkbox fluido personalizado ---
    es_custom = st.checkbox("Fluido personalizado")

    # --- Selector de fluido (bloqueado si es custom) ---
    idx_default   = nombres_fluidos_es.index(FLUIDO_DEFAULT) if FLUIDO_DEFAULT in nombres_fluidos_es else 0
    fluido_sel_es = st.selectbox("Fluido:", nombres_fluidos_es, index=idx_default, disabled=es_custom)

    # --- Temperatura y Presión (siempre visibles) ---
    T_fluido = st.number_input("Temperatura [°C]", value=T_DEFAULT_C, step=1.0, format="%.1f")
    P_fluido = st.number_input("Presión [bar]", value=P_ATM_BAR, step=0.01, format="%.4f")
    st.caption(f"≡ {P_fluido * 100:.2f} kPa  |  {P_fluido * 14.5038:.3f} psi")

    if not es_custom:
        # --- Propiedades calculadas con CoolProp ---
        nombre_en = fluidos_dict[fluido_sel_es]
        rho, mu, cp_error = propiedades_coolprop(nombre_en, T_fluido, P_fluido)

        if rho is not None:
            densidad   = rho
            viscosidad = mu
            st.text_input("Densidad [kg/m³]",  value=f"{densidad:.4f}",   disabled=True)
            st.text_input("Viscosidad [Pa·s]", value=f"{viscosidad:.6f}", disabled=True)
        else:
            st.warning(f"⚠️ {cp_error} — Ingresa las propiedades manualmente.")
            densidad   = st.number_input("Densidad [kg/m³]",  value=1000.0, format="%.4f")
            viscosidad = st.number_input("Viscosidad [Pa·s]", value=0.001,  format="%.6f")
    else:
        # --- Fluido personalizado: densidad y viscosidad editables ---
        densidad   = st.number_input("Densidad [kg/m³]",  value=1000.0, format="%.4f")
        viscosidad = st.number_input("Viscosidad [Pa·s]", value=0.001,  format="%.6f")

    # --- Caudal y velocidad (comunes) ---
    st.divider()
    caudal = st.number_input("Caudal [m³/s]", value=0.015, format="%.4f")
    st.caption(f"≈ {caudal * 3600:.2f} m³/h")

    area      = np.pi * (diametro ** 2) / 4
    velocidad = caudal / area if diametro > 0 else 0.0
    st.text_input("Velocidad Resultante [m/s]", value=f"{velocidad:.3f}", disabled=True)


# ── Columna 4: condiciones iniciales ─────────────────────────────────────────
with col4:
    st.subheader("Condiciones iniciales")
    presion_inicial_m = st.number_input("Presión inicial [m]",         value=10.0, step=1.0)
    altura_seguridad  = st.number_input("Altura de seguridad [m]",      value=3.0,  step=1.0)
    head_bomba        = st.number_input("Head de bomba [m]",            value=5.0,  step=1.0)
    num_puntos_extra  = st.number_input("Puntos extra (interpolación)", min_value=0, value=0)

    st.write("")
    n_sing    = len(st.session_state.singularidades)
    label_btn = f"⚙️ Singularidades ({n_sing})" if n_sing > 0 else "⚙️ Agregar singularidades"
    if st.button(label_btn, use_container_width=True):
        st.session_state.modal_singularidades = True
        st.rerun()


# ── Modal de singularidades ───────────────────────────────────────────────────
@st.dialog("⚙️ Singularidades del sistema")
def abrir_modal_singularidades():
    st.caption("Ingresá cada singularidad con su posición en el eje X del perfil y su coeficiente K.")

    with st.form("form_singularidad", clear_on_submit=True):
        c1, c2    = st.columns(2)
        x_sing    = c1.number_input("Posición X [m]",   min_value=0.0, step=1.0,  format="%.1f")
        k_sing    = c2.number_input("Coeficiente K [-]", min_value=0.0, step=0.1, format="%.2f")
        desc_sing = st.text_input("Descripción (opcional)", placeholder="Ej: Válvula de compuerta")
        agregar   = st.form_submit_button("➕ Agregar", use_container_width=True)

    if agregar:
        st.session_state.singularidades.append({
            "x_m": x_sing, "k": k_sing,
            "descripcion": desc_sing.strip() or "—",
        })
        st.rerun()

    if st.session_state.singularidades:
        st.divider()
        st.markdown("**Singularidades cargadas:**")
        for i, s in enumerate(st.session_state.singularidades):
            col_info, col_del = st.columns([5, 1])
            col_info.markdown(
                f"**#{i+1}** &nbsp; X = `{s['x_m']} m` &nbsp;|&nbsp; K = `{s['k']}` &nbsp;|&nbsp; {s['descripcion']}"
            )
            if col_del.button("🗑️", key=f"del_sing_{i}"):
                st.session_state.singularidades.pop(i)
                st.rerun()
    else:
        st.info("No hay singularidades cargadas.")

if st.session_state.modal_singularidades:
    st.session_state.modal_singularidades = False
    abrir_modal_singularidades()


# ── Snapshot de parámetros actuales ──────────────────────────────────────────
params_actuales = {
    "archivo":           P_geo_csv,
    "densidad":          densidad,
    "viscosidad":        viscosidad,
    "caudal":            caudal,
    "diametro":          diametro,
    "rugosidad":         rugosidad,
    "presion_inicial_m": presion_inicial_m,
    "altura_seguridad":  altura_seguridad,
    "head_bomba":        head_bomba,
    "num_puntos_extra":  num_puntos_extra,
}

hay_resultado = st.session_state.resultado_perfil_bombas_indefinido is not None
if (
    hay_resultado
    and st.session_state.params_ultimo_calculo is not None
    and st.session_state.params_ultimo_calculo != params_actuales
):
    st.session_state.mostrar_aviso_desactualizado = True

if st.session_state.mostrar_aviso_desactualizado:
    st.info("🔄 Los parámetros han cambiado. Presiona **Calcular perfil hidráulico** para actualizar los resultados.")

# ── Botón de cálculo ──────────────────────────────────────────────────────────
boton_presionado = st.button("🚀 Calcular perfil hidráulico")

if boton_presionado:
    if not P_geo_csv:
        st.warning("⚠️ Debes seleccionar o subir un perfil geográfico CSV antes de calcular.")
    else:
        fluido_calc  = {"densidad": densidad, "viscosidad": viscosidad, "velocidad": velocidad}
        tuberia_calc = {"diametro": diametro, "rugosidad": rugosidad}

        x_final, h_final, bombas = generar_perfil_con_bombas_automaticas(
            P_geo_csv, fluido_calc, tuberia_calc,
            presion_inicial_m, altura_seguridad, head_bomba,
            num_puntos_extra=num_puntos_extra if num_puntos_extra > 0 else None,
            singularidades=st.session_state.singularidades,
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
                "x_final":        x_final,
                "h_final":        h_final,
                "bombas":         bombas,
                "singularidades": list(st.session_state.singularidades),
                "archivo":        P_geo_csv,
                "pn_bar":         pn_seleccionado,
                "material":       nombre_mat,
                "tipo_mat":       tipo_mat,
            }
            st.session_state.params_ultimo_calculo        = params_actuales.copy()
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

        if st.session_state.mostrar_aviso_desactualizado:
            st.warning("🔄 Estás viendo resultados desactualizados — presiona **Calcular perfil hidráulico** para actualizar.")

        df_terr = pd.read_csv(res["archivo"], header=None)
        df_terr.columns = ["x", "z"]

        tiene_pn = res["tipo_mat"] == "pn" and res["pn_bar"] is not None

        # ── Capas del gráfico con leyenda ─────────────────────────────────────
        # Terreno: área + línea (sin leyenda, es el fondo visual)
        terreno_area = alt.Chart(df_terr).mark_area(
            color="saddlebrown", opacity=0.25
        ).encode(
            x=alt.X("x", title="Distancia Horizontal [m]"),
            y=alt.Y("z", title="Elevación [msnm]", scale=alt.Scale(zero=False)),
        )
        df_terr_leg = df_terr.copy()
        df_terr_leg["serie"] = "Terreno"
        terreno_linea = alt.Chart(df_terr_leg).mark_line(size=2).encode(
            x="x",
            y=alt.Y("z", scale=alt.Scale(zero=False)),
            color=alt.Color(
                "serie:N",
                scale=alt.Scale(
                    domain=["Terreno"],
                    range=["saddlebrown"],
                ),
                legend=alt.Legend(title="Referencias"),
            ),
        )

        capas = [terreno_area, terreno_linea]

        # MOP (si aplica)
        if tiene_pn:
            mca_max = res["pn_bar"] * 10.197
            df_terr["mop"] = df_terr["z"] + mca_max
            df_mop = df_terr[["x", "mop"]].copy()
            df_mop["serie"] = f"MOP ({res['pn_bar']} bar)"
            linea_mop = alt.Chart(df_mop).mark_line(
                strokeDash=[6, 4], size=2
            ).encode(
                x="x",
                y=alt.Y("mop:Q", scale=alt.Scale(zero=False)),
                color=alt.Color(
                    "serie:N",
                    scale=alt.Scale(
                        domain=[f"MOP ({res['pn_bar']} bar)"],
                        range=["crimson"],
                    ),
                    legend=alt.Legend(title=None),
                ),
            )
            capas.append(linea_mop)

        # Línea de presión hidráulica
        df_p = pd.DataFrame({"x": res["x_final"], "h": res["h_final"], "serie": "Línea piezométrica"})
        linea_p = alt.Chart(df_p).mark_line(size=2.5).encode(
            x="x",
            y=alt.Y("h:Q", scale=alt.Scale(zero=False)),
            color=alt.Color(
                "serie:N",
                scale=alt.Scale(
                    domain=["Línea piezométrica"],
                    range=["dodgerblue"],
                ),
                legend=alt.Legend(title=None),
            ),
        )
        capas.append(linea_p)

        # ── Singularidades: segmentos verticales hacia abajo ──────────────────
        sings_res = res.get("singularidades", [])
        if sings_res:
            x_arr  = res["x_final"]
            h_arr  = res["h_final"]
            seg_id = 0
            seg_rows = []

            # Recorrer pares consecutivos buscando caídas en el mismo X
            # fluido.py inserta [x_i, h_antes] → [x_i, h_tras] con h_tras < h_antes
            for j in range(len(x_arr) - 1):
                if abs(x_arr[j] - x_arr[j + 1]) < 1e-9:   # mismo X
                    h_a, h_b = h_arr[j], h_arr[j + 1]
                    if h_b < h_a:                           # caída → es singularidad
                        seg_rows.append({"x": x_arr[j], "h": h_a, "seg": seg_id})
                        seg_rows.append({"x": x_arr[j], "h": h_b, "seg": seg_id})
                        seg_id += 1

            if seg_rows:
                df_sing = pd.DataFrame(seg_rows)
                df_sing["serie"] = "Singularidad"
                linea_sing = alt.Chart(df_sing).mark_line(size=2.5).encode(
                    x=alt.X("x:Q"),
                    y=alt.Y("h:Q", scale=alt.Scale(zero=False)),
                    detail="seg:N",          # un trazo por cada segmento
                    color=alt.Color(
                        "serie:N",
                        scale=alt.Scale(domain=["Singularidad"], range=["darkorange"]),
                        legend=alt.Legend(title=None),
                    ),
                )
                capas.append(linea_sing)

        grafico = alt.layer(*capas).resolve_scale(color="independent").properties(height=400)
        st.altair_chart(grafico, use_container_width=True)

        # ── Validación MOP ────────────────────────────────────────────────────
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
