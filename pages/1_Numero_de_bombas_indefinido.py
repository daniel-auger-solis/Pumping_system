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
    ("editando_sing_idx",                  None),
    ("modal_fluido",                       False),
    ("fluido_es_custom",                   False),
    ("fluido_nombre_es",                   "Agua"),
    ("fluido_T",                           25.0),
    ("fluido_P",                           1.01325),
    ("fluido_densidad",                    1000.0),
    ("fluido_viscosidad",                  0.001),
]:
    if key not in st.session_state:
        st.session_state[key] = val

_sc_cond  = {}
_sc_flu   = {}


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

    # Leer propiedades del fluido guardadas en session_state
    es_custom     = st.session_state.fluido_es_custom
    fluido_sel_es = st.session_state.fluido_nombre_es
    T_fluido      = st.session_state.fluido_T
    P_fluido      = st.session_state.fluido_P
    densidad      = st.session_state.fluido_densidad
    viscosidad    = st.session_state.fluido_viscosidad

    # Resumen del fluido seleccionado
    if es_custom:
        resumen = f"Personalizado — ρ={densidad:.1f} kg/m³ | μ={viscosidad:.5f} Pa·s"
    else:
        resumen = f"{fluido_sel_es} — {T_fluido:.1f}°C | {P_fluido:.4f} bar"
    st.caption(resumen)

    # Botón para abrir el selector de fluido
    if st.button("🧪 Seleccionar fluido", use_container_width=True):
        st.session_state.modal_fluido = True
        st.rerun()

    # --- Caudal y velocidad ---
    caudal = st.number_input("Caudal [m³/s]", value=float(_sc_flu.get("caudal", 0.015)), format="%.4f")
    st.caption(f"≈ {caudal * 3600:.2f} m³/h")

    area      = np.pi * (diametro ** 2) / 4
    velocidad = caudal / area if diametro > 0 else 0.0
    st.text_input("Velocidad Resultante [m/s]", value=f"{velocidad:.3f}", disabled=True)


# ── Columna 4: condiciones iniciales ─────────────────────────────────────────
with col4:
    st.subheader("Condiciones iniciales")
    presion_inicial_m = st.number_input("Presión inicial [m]",         value=float(_sc_cond.get("presion_inicial_m", 10.0)), step=1.0)
    altura_seguridad  = st.number_input("Altura de seguridad [m]",      value=float(_sc_cond.get("altura_seguridad",  3.0)),  step=1.0)
    head_bomba        = st.number_input("Head de bomba [m]",            value=float(_sc_cond.get("head_bomba",        5.0)),  step=1.0)
    num_puntos_extra  = st.number_input("Puntos extra (interpolación)", min_value=0, value=int(_sc_cond.get("num_puntos_extra", 0)))

    st.write("")
    n_sing    = len(st.session_state.singularidades)
    label_btn = f"⚙️ Singularidades ({n_sing})" if n_sing > 0 else "⚙️ Agregar singularidades"
    if st.button(label_btn, use_container_width=True):
        st.session_state.modal_singularidades = True
        st.rerun()


# ── Modal de singularidades ───────────────────────────────────────────────────
@st.dialog("⚙️ Singularidades del sistema")
def abrir_modal_singularidades():
    # El índice de edición se lee en cada render del diálogo
    edit_idx = st.session_state.editando_sing_idx

    # ── Listado de singularidades (siempre visible arriba) ────────────────────
    if st.session_state.singularidades:
        st.markdown("**Singularidades cargadas:**")
        for i, s in enumerate(st.session_state.singularidades):
            col_info, col_edit, col_del = st.columns([5, 1, 1])
            etiqueta = f"**#{i+1}** {'✏️' if i == edit_idx else ''} &nbsp; X = `{s['x_m']} m` &nbsp;|&nbsp; K = `{s['k']}` &nbsp;|&nbsp; {s['descripcion']}"
            col_info.markdown(etiqueta)
            if col_edit.button("✏️", key=f"edit_sing_{i}", help="Editar"):
                st.session_state.editando_sing_idx = i
                st.session_state.modal_singularidades = True  # reabre el diálogo tras el rerun
                st.rerun()
            if col_del.button("🗑️", key=f"del_sing_{i}", help="Eliminar"):
                st.session_state.singularidades.pop(i)
                if st.session_state.editando_sing_idx == i:
                    st.session_state.editando_sing_idx = None
                st.session_state.mostrar_aviso_desactualizado = (
                    st.session_state.resultado_perfil_bombas_indefinido is not None
                )
                st.session_state.modal_singularidades = True  # reopen
                st.rerun()
    else:
        st.info("No hay singularidades cargadas.")

    st.divider()

    # ── Formulario: agregar o editar ──────────────────────────────────────────
    edit_idx = st.session_state.editando_sing_idx   # releer por si cambió arriba
    if edit_idx is None:
        st.caption("Ingresá la posición X y el coeficiente K de la singularidad.")
        form_label = "➕ Agregar"
        x_def, k_def, desc_def = 0.0, 0.0, ""
    else:
        s_edit = st.session_state.singularidades[edit_idx]
        st.info(f"✏️ Editando singularidad #{edit_idx + 1}")
        form_label = "💾 Guardar cambios"
        x_def  = float(s_edit["x_m"])
        k_def  = float(s_edit["k"])
        desc_def = s_edit["descripcion"] if s_edit["descripcion"] != "—" else ""

    with st.form("form_singularidad", clear_on_submit=True):
        c1, c2    = st.columns(2)
        x_sing    = c1.number_input("Posición X [m]",    min_value=0.0, step=1.0,  format="%.1f", value=x_def)
        k_sing    = c2.number_input("Coeficiente K [-]", min_value=0.0, step=0.1,  format="%.2f", value=k_def)
        desc_sing = st.text_input("Descripción (opcional)", value=desc_def,
                                  placeholder="Ej: Válvula de compuerta")
        col_btn1, col_btn2 = st.columns([3, 1])
        confirmar = col_btn1.form_submit_button(form_label, use_container_width=True)
        cancelar  = col_btn2.form_submit_button("✖️", use_container_width=True,
                                                 disabled=(edit_idx is None))

    if confirmar:
        entrada = {"x_m": x_sing, "k": k_sing, "descripcion": desc_sing.strip() or "—"}
        if edit_idx is None:
            st.session_state.singularidades.append(entrada)
        else:
            st.session_state.singularidades[edit_idx] = entrada
            st.session_state.editando_sing_idx = None
        st.session_state.mostrar_aviso_desactualizado = (
            st.session_state.resultado_perfil_bombas_indefinido is not None
        )
        st.session_state.modal_singularidades = True  # reopen after save
        st.rerun()

    if cancelar:
        st.session_state.editando_sing_idx = None
        st.session_state.modal_singularidades = True  # reopen
        st.rerun()

if st.session_state.modal_singularidades:
    st.session_state.modal_singularidades = False
    abrir_modal_singularidades()


# ── Modal de selección de fluido ──────────────────────────────────────────────
@st.dialog("🧪 Seleccionar fluido")
def abrir_modal_fluido():
    es_custom = st.checkbox("Fluido personalizado",
                            value=st.session_state.fluido_es_custom)

    if not es_custom:
        # Selector de fluido de la lista
        idx_actual = nombres_fluidos_es.index(st.session_state.fluido_nombre_es)                      if st.session_state.fluido_nombre_es in nombres_fluidos_es else 0
        fluido_sel = st.selectbox("Fluido:", nombres_fluidos_es, index=idx_actual)

        # Condiciones T y P
        c1, c2 = st.columns(2)
        T_val = c1.number_input("Temperatura [°C]",
                                value=float(st.session_state.fluido_T),
                                step=1.0, format="%.1f")
        P_val = c2.number_input("Presión [bar]",
                                value=float(st.session_state.fluido_P),
                                step=0.01, format="%.4f")
        st.caption(f"≡ {P_val * 100:.2f} kPa  |  {P_val * 14.5038:.3f} psi")

        # Calcular propiedades con CoolProp
        nombre_en = fluidos_dict[fluido_sel]
        rho, mu, cp_error = propiedades_coolprop(nombre_en, T_val, P_val)

        if rho is not None:
            st.text_input("Densidad [kg/m³]",  value=f"{rho:.4f}",  disabled=True)
            st.text_input("Viscosidad [Pa·s]", value=f"{mu:.6f}",   disabled=True)
        else:
            st.warning(f"⚠️ {cp_error} — las propiedades no pudieron calcularse.")
            rho = st.number_input("Densidad [kg/m³]",  value=float(st.session_state.fluido_densidad),  format="%.4f")
            mu  = st.number_input("Viscosidad [Pa·s]", value=float(st.session_state.fluido_viscosidad), format="%.6f")

        if st.button("✅ Confirmar", use_container_width=True, type="primary"):
            st.session_state.fluido_es_custom  = False
            st.session_state.fluido_nombre_es  = fluido_sel
            st.session_state.fluido_T          = T_val
            st.session_state.fluido_P          = P_val
            st.session_state.fluido_densidad   = rho
            st.session_state.fluido_viscosidad = mu
            st.session_state.mostrar_aviso_desactualizado = (
                st.session_state.resultado_perfil_bombas_indefinido is not None
            )
            st.rerun()

    else:
        # Fluido personalizado
        st.caption("Ingresa manualmente las propiedades del fluido.")
        c1, c2 = st.columns(2)
        T_val  = c1.number_input("Temperatura [°C]",  value=float(st.session_state.fluido_T),  step=1.0, format="%.1f")
        P_val  = c2.number_input("Presión [bar]",      value=float(st.session_state.fluido_P),  step=0.01, format="%.4f")
        st.caption(f"≡ {P_val * 100:.2f} kPa  |  {P_val * 14.5038:.3f} psi")
        rho    = st.number_input("Densidad [kg/m³]",   value=float(st.session_state.fluido_densidad),   format="%.4f")
        mu     = st.number_input("Viscosidad [Pa·s]",  value=float(st.session_state.fluido_viscosidad),  format="%.6f")

        if st.button("✅ Confirmar", use_container_width=True, type="primary"):
            st.session_state.fluido_es_custom  = True
            st.session_state.fluido_nombre_es  = OPCION_CUSTOM
            st.session_state.fluido_T          = T_val
            st.session_state.fluido_P          = P_val
            st.session_state.fluido_densidad   = rho
            st.session_state.fluido_viscosidad = mu
            st.session_state.mostrar_aviso_desactualizado = (
                st.session_state.resultado_perfil_bombas_indefinido is not None
            )
            st.rerun()

if st.session_state.modal_fluido:
    st.session_state.modal_fluido = False
    abrir_modal_fluido()


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
    "singularidades":    str(st.session_state.singularidades),
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

        # ── Singularidades: triángulo amarillo en h_antes (punto más alto) ────
        sings_res = res.get("singularidades", [])
        if sings_res:
            x_arr    = res["x_final"]
            h_arr    = res["h_final"]
            tri_rows = []

            for j in range(len(x_arr) - 1):
                if abs(x_arr[j] - x_arr[j + 1]) < 1e-9:   # mismo X
                    h_a, h_b = h_arr[j], h_arr[j + 1]
                    if h_b < h_a:                           # caída → singularidad
                        tri_rows.append({"x": x_arr[j], "h": h_a, "serie": "Singularidad"})

            if tri_rows:
                df_tri = pd.DataFrame(tri_rows)
                # yOffset in pixels: triangle-down size=200 → marker height ≈ 12px.
                # Altair supports yOffset directly on mark_point as a pixel shift.
                puntos_sing = alt.Chart(df_tri).mark_point(
                    shape="triangle-down",
                    size=200,
                    filled=True,
                    opacity=1.0,
                    yOffset=-8,   # shift up so tip of triangle touches the HGL line
                ).encode(
                    x=alt.X("x:Q"),
                    y=alt.Y("h:Q", scale=alt.Scale(zero=False)),
                    color=alt.Color(
                        "serie:N",
                        scale=alt.Scale(domain=["Singularidad"], range=["gold"]),
                        legend=alt.Legend(title=None),
                    ),
                    tooltip=[
                        alt.Tooltip("x:Q", title="X [m]"),
                        alt.Tooltip("h:Q", title="H [msnm]", format=".2f"),
                    ],
                )
                capas.append(puntos_sing)

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
