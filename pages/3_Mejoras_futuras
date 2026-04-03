import streamlit as st
import json
import os
from datetime import datetime

# --- Ruta para persistir las notas ---
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
PATH_NOTAS = os.path.join(BASE_DIR, "data", "notas_mejoras.json")
os.makedirs(os.path.dirname(PATH_NOTAS), exist_ok=True)

# --- Prioridades disponibles ---
PRIORIDADES = {
    "🔴 Alta":   "alta",
    "🟡 Media":  "media",
    "🟢 Baja":   "baja",
}

ESTADO_OPCIONES = ["Pendiente", "En progreso", "Completado"]

# --- Cargar / guardar notas ---
def cargar_notas():
    if os.path.exists(PATH_NOTAS):
        with open(PATH_NOTAS, "r", encoding="utf-8") as f:
            return json.load(f)
    # Notas iniciales predefinidas
    return [
        {
            "id": 1,
            "titulo": "Manejo de transientes hidráulicos",
            "descripcion": "",
            "prioridad": "alta",
            "estado": "Pendiente",
            "fecha": datetime.today().strftime("%d/%m/%Y"),
        },
        {
            "id": 2,
            "titulo": "Incluir presiones nominales y rugosidad del acero al carbono",
            "descripcion": "",
            "prioridad": "alta",
            "estado": "Pendiente",
            "fecha": datetime.today().strftime("%d/%m/%Y"),
        },
        {
            "id": 3,
            "titulo": "Arreglar aviso cuando se actualiza el gráfico",
            "descripcion": "",
            "prioridad": "media",
            "estado": "Pendiente",
            "fecha": datetime.today().strftime("%d/%m/%Y"),
        },
    ]

def guardar_notas(notas):
    with open(PATH_NOTAS, "w", encoding="utf-8") as f:
        json.dump(notas, f, ensure_ascii=False, indent=2)

def siguiente_id(notas):
    return max((n["id"] for n in notas), default=0) + 1

# --- Inicializar estado ---
if "notas" not in st.session_state:
    st.session_state.notas = cargar_notas()

if "editando_id" not in st.session_state:
    st.session_state.editando_id = None

notas = st.session_state.notas

# --- Estilos personalizados ---
st.markdown("""
<style>
    /* Tarjetas de notas */
    .nota-card {
        background: #1e1e2e;
        border: 1px solid #313244;
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 10px;
        transition: border-color 0.2s;
    }
    .nota-card:hover { border-color: #89b4fa; }

    /* Badges de prioridad */
    .badge {
        display: inline-block;
        font-size: 0.72rem;
        font-weight: 600;
        padding: 2px 10px;
        border-radius: 999px;
        letter-spacing: 0.04em;
        margin-right: 6px;
    }
    .badge-alta    { background:#3b1219; color:#f38ba8; border:1px solid #f38ba8; }
    .badge-media   { background:#2e2a14; color:#f9e2af; border:1px solid #f9e2af; }
    .badge-baja    { background:#132218; color:#a6e3a1; border:1px solid #a6e3a1; }

    /* Badge de estado */
    .estado-pendiente  { background:#1e1e2e; color:#cdd6f4; border:1px solid #585b70; }
    .estado-progreso   { background:#1e2a3a; color:#89b4fa; border:1px solid #89b4fa; }
    .estado-completado { background:#132218; color:#a6e3a1; border:1px solid #a6e3a1; }

    .nota-titulo { font-size:1rem; font-weight:600; color:#cdd6f4; margin:6px 0 4px 0; }
    .nota-desc   { font-size:0.85rem; color:#a6adc8; margin:0; }
    .nota-fecha  { font-size:0.75rem; color:#585b70; margin-top:6px; }

    /* Separador de sección */
    .seccion-header {
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: #585b70;
        margin: 22px 0 8px 0;
        padding-bottom: 4px;
        border-bottom: 1px solid #313244;
    }
</style>
""", unsafe_allow_html=True)

# ─── Encabezado ────────────────────────────────────────────────────────────────
st.title("📝 Notas de mejoras")
st.caption("Registro de funcionalidades pendientes, bugs y mejoras para la aplicación.")

# ─── Barra lateral: filtros + nueva nota ───────────────────────────────────────
with st.sidebar:
    st.header("➕ Nueva nota")
    nuevo_titulo = st.text_input("Título *", placeholder="Describí brevemente la mejora")
    nuevo_desc   = st.text_area("Descripción (opcional)", height=90)
    nueva_prior  = st.selectbox("Prioridad", list(PRIORIDADES.keys()))
    nuevo_estado = st.selectbox("Estado", ESTADO_OPCIONES)

    if st.button("Agregar nota", use_container_width=True, type="primary"):
        if nuevo_titulo.strip():
            notas.append({
                "id":          siguiente_id(notas),
                "titulo":      nuevo_titulo.strip(),
                "descripcion": nuevo_desc.strip(),
                "prioridad":   PRIORIDADES[nueva_prior],
                "estado":      nuevo_estado,
                "fecha":       datetime.today().strftime("%d/%m/%Y"),
            })
            guardar_notas(notas)
            st.success("Nota agregada.")
            st.rerun()
        else:
            st.warning("El título no puede estar vacío.")

    st.divider()
    st.header("🔍 Filtros")
    filtro_estado = st.multiselect(
        "Estado", ESTADO_OPCIONES, default=["Pendiente", "En progreso"]
    )
    filtro_prior = st.multiselect(
        "Prioridad", ["alta", "media", "baja"], default=["alta", "media", "baja"]
    )

# ─── Filtrar notas ─────────────────────────────────────────────────────────────
notas_filtradas = [
    n for n in notas
    if (not filtro_estado or n["estado"] in filtro_estado)
    and (not filtro_prior  or n["prioridad"] in filtro_prior)
]

# ─── Métricas rápidas ──────────────────────────────────────────────────────────
total      = len(notas)
pendientes = sum(1 for n in notas if n["estado"] == "Pendiente")
en_prog    = sum(1 for n in notas if n["estado"] == "En progreso")
completas  = sum(1 for n in notas if n["estado"] == "Completado")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total",        total)
m2.metric("Pendientes",   pendientes)
m3.metric("En progreso",  en_prog)
m4.metric("Completadas",  completas)

st.divider()

# ─── Listado de notas ──────────────────────────────────────────────────────────
if not notas_filtradas:
    st.info("No hay notas que coincidan con los filtros seleccionados.")
else:
    # Ordenar: alta → media → baja, luego por id
    orden_prior = {"alta": 0, "media": 1, "baja": 2}
    notas_filtradas = sorted(notas_filtradas, key=lambda n: (orden_prior[n["prioridad"]], n["id"]))

    for nota in notas_filtradas:
        estado_cls = {
            "Pendiente":   "estado-pendiente",
            "En progreso": "estado-progreso",
            "Completado":  "estado-completado",
        }.get(nota["estado"], "estado-pendiente")

        desc_html = f'<p class="nota-desc">{nota["descripcion"]}</p>' if nota["descripcion"] else ""

        st.markdown(f"""
        <div class="nota-card">
            <span class="badge badge-{nota['prioridad']}">{nota['prioridad'].upper()}</span>
            <span class="badge {estado_cls}">{nota['estado']}</span>
            <p class="nota-titulo">#{nota['id']} &nbsp; {nota['titulo']}</p>
            {desc_html}
            <p class="nota-fecha">📅 {nota['fecha']}</p>
        </div>
        """, unsafe_allow_html=True)

        col_e, col_d, _ = st.columns([2, 1, 4])

        # Cambiar estado rápido
        with col_e:
            opciones_sig = [o for o in ESTADO_OPCIONES if o != nota["estado"]]
            nuevo_est = st.selectbox(
                "Cambiar estado", opciones_sig,
                key=f"est_{nota['id']}",
                label_visibility="collapsed"
            )
            if st.button("Actualizar", key=f"upd_{nota['id']}", use_container_width=True):
                for n in notas:
                    if n["id"] == nota["id"]:
                        n["estado"] = nuevo_est
                guardar_notas(notas)
                st.rerun()

        # Eliminar
        with col_d:
            st.write("")  # espaciado vertical
            if st.button("🗑️ Eliminar", key=f"del_{nota['id']}", use_container_width=True):
                st.session_state.notas = [n for n in notas if n["id"] != nota["id"]]
                guardar_notas(st.session_state.notas)
                st.rerun()

        st.write("")  # espacio entre tarjetas
