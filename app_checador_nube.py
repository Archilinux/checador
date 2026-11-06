import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import hashlib
import math
import json
import io
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from streamlit_js_eval import get_geolocation

st.set_page_config(page_title="Checador Cloud GPS 2027", page_icon="📍", layout="wide")

ZONA_HORARIA = ZoneInfo("America/Mexico_City")

# --- 1. COORDENADAS GPS DE TUS SUCURSALES (GEOCERCA) ---
# Ajusta la latitud y longitud exacta de cada una de tus 6 sucursales
SUCURSALES_GPS = {
    "Tapachula Matriz": {"lat": 14.9069, "lon": -92.2628, "radio_metros": 120},
    "Sucursal 2": {"lat": 14.9120, "lon": -92.2550, "radio_metros": 120},
    "Sucursal 3": {"lat": 14.8950, "lon": -92.2710, "radio_metros": 120},
}

# --- 2. CATÁLOGO DE SALIDAS EXTRAS POR DEPARTAMENTO ---
CATALOGO_SALIDAS_EXTRAS = {
    "Administrativo": ["Bancos", "Compras", "Firma cheque"],
    "Taller": ["Reparaciones", "Mantenimiento", "Entrega", "Compra"],
    "Ventas": ["Compras", "Entrega"],
    "Refacciones": ["Compras"]
}

# --- 3. CONEXIÓN A GOOGLE SHEETS (USANDO TU SECRET ACTUAL) ---
@st.cache_resource
def conectar_bd_nube():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        creds_dict = json.loads(st.secrets["google_json"])
        credenciales = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        cliente = gspread.authorize(credenciales)
        libro = cliente.open("Checador_Activo")
        return libro, True, ""
    except Exception as e:
        return None, False, str(e)

def inicializar_pestanas(libro):
    nombres_hojas = [h.title for h in libro.worksheets()]
    
    if "Empleados" not in nombres_hojas:
        h_emp = libro.add_worksheet(title="Empleados", rows="200", cols="10")
        h_emp.append_row(["Codigo", "Nombre", "RFC_CURP", "Departamento", "Sucursal", "PIN", "Activo"])
        # Empleados iniciales de prueba
        h_emp.append_rows([
            ["001", "Laura Méndez", "MEL880101XXX", "Administrativo", "Tapachula Matriz", "1111", "1"],
            ["002", "Roberto Gómez", "GOR900512XXX", "Taller", "Tapachula Matriz", "2222", "1"],
            ["003", "Carlos Ruiz", "RUC850920XXX", "Ventas", "Tapachula Matriz", "3333", "1"],
            ["004", "Miguel Pérez", "PEM921103XXX", "Refacciones", "Tapachula Matriz", "4444", "1"]
        ])
        
    if "Asistencias" not in nombres_hojas:
        h_asi = libro.add_worksheet(title="Asistencias", rows="5000", cols="16")
        h_asi.append_row([
            "Fecha", "Hora_Servidor", "Codigo", "Nombre", "Departamento", "Sucursal",
            "Tipo_Evento", "Depto_Salida_Extra", "Motivo_Salida_Extra", "Referencia",
            "Latitud", "Longitud", "Distancia_Sucursal_m", "Estado_Ubicacion",
            "Link_Mapa", "Hash_SHA256"
        ])

# --- 4. FÓRMULA DE DISTANCIA GPS (HAVERSINE) Y HASH SHA-256 ---
def calcular_distancia_metros(lat1, lon1, lat2, lon2):
    R = 6371000  # Radio de la Tierra en metros
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    return round(2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 1)

def generar_hash(cadena_datos):
    return hashlib.sha256(cadena_datos.encode("utf-8")).hexdigest()

# Iniciar conexión
libro_bd, ok_conn, err_msg = conectar_bd_nube()
if not ok_conn:
    st.error("❌ No se pudo conectar al archivo 'Checador_Activo' en Google Drive.")
    st.caption(f"Detalle técnico: {err_msg}")
    st.stop()

inicializar_pestanas(libro_bd)

# --- MENÚ LATERAL ---
st.sidebar.title("📍 Checador Cloud 2027")
modo = st.sidebar.radio("Modo:", ["📱 Checar desde Celular", "💻 Panel Administrador (RH / SAT)"])
ahora_srv = datetime.now(ZONA_HORARIA)
st.sidebar.info(f"🕒 **Hora Oficial Servidor:**\n{ahora_srv.strftime('%d/%m/%Y %H:%M:%S')}")

# ==============================================================================
# MÓDULO 1: CHECADOR MÓVIL CON VERIFICACIÓN DE UBICACIÓN GPS
# ==============================================================================
if modo == "📱 Checar desde Celular":
    st.title("📱 Registro de Asistencia y Salidas con GPS")
    
    # 1. Capturar GPS del navegador del celular en tiempo real
    st.markdown("##### 📍 1. Verificación de Ubicación del Dispositivo")
    loc = get_geolocation()
    
    lat_actual, lon_actual, precision_m = None, None, None
    if loc and "coords" in loc:
        lat_actual = loc["coords"]["latitude"]
        lon_actual = loc["coords"]["longitude"]
        precision_m = round(loc["coords"].get("accuracy", 0), 1)
        st.success(f"🛰️ GPS Activo: `{lat_actual:.5f}, {lon_actual:.5f}` (Precisión: ±{precision_m} m)")
    else:
        st.warning("⚠️ Esperando permiso de ubicación GPS en tu celular... (Asegúrate de aceptar el permiso en el navegador).")

    st.divider()
    col1, col2 = st.columns([1, 1.3])
    
    with col1:
        st.markdown("##### 👤 2. Identificación")
        cod_in = st.text_input("Número de Empleado (Ej. 001):").strip()
        pin_in = st.text_input("PIN de Seguridad:", type="password").strip()
        
        # Cargar catálogo de empleados
        hoja_emp = libro_bd.worksheet("Empleados")
        df_emp = pd.DataFrame(hoja_emp.get_all_records())
        
        emp_actual = None
        if cod_in and pin_in and not df_emp.empty:
            df_emp["Codigo_str"] = df_emp["Codigo"].astype(str).str.zfill(3)
            cod_busq = cod_in.zfill(3) if cod_in.isdigit() else cod_in
            match = df_emp[(df_emp["Codigo_str"] == cod_busq) & (df_emp["PIN"].astype(str) == pin_in)]
            if not match.empty:
                emp_actual = match.iloc[0].to_dict()
                st.success(f"**{emp_actual['Nombre']}**\nDepto: {emp_actual['Departamento']} | Sucursal: {emp_actual['Sucursal']}")
            else:
                st.error("❌ Código o PIN incorrecto.")

    with col2:
        st.markdown("##### 📝 3. Tipo de Registro")
        evento = st.radio(
            "Selecciona el movimiento:",
            [
                "🟢 Entrada de Jornada",
                "🚗 Salida Extra (Operativa / Comisión)",
                "🔙 Regreso de Salida Extra",
                "🍽️ Salida a Comer",
                "🍽️ Regreso de Comer",
                "🔴 Salida Definitiva"
            ]
        )
        
        depto_extra, motivo_extra, ref_extra = "", "", ""
        if evento == "🚗 Salida Extra (Operativa / Comisión)":
            deptos_lista = list(CATALOGO_SALIDAS_EXTRAS.keys())
            idx_d = deptos_lista.index(emp_actual["Departamento"]) if (emp_actual and emp_actual["Departamento"] in deptos_lista) else 0
            
            c1, c2 = st.columns(2)
            depto_extra = c1.selectbox("Área:", deptos_lista, index=idx_d)
            motivo_extra = c2.selectbox("Motivo de Salida:", CATALOGO_SALIDAS_EXTRAS[depto_extra])
            ref_extra = st.text_input("Folio / Cliente / Banco / Destino:").strip()
        elif evento == "🔙 Regreso de Salida Extra":
            ref_extra = st.text_input("Observaciones o folio de regreso:").strip()

        # Bloqueo por Geocerca si quieres obligar a que chequen dentro de la sucursal
        exigir_geocerca = st.checkbox("Validar cercanía a sucursal asignada", value=True, disabled=True)

        if st.button("✅ ENVIAR REGISTRO A LA NUBE", type="primary", use_container_width=True):
            if not emp_actual:
                st.error("⚠️ Ingresa tu Código y PIN válidos primero.")
            elif lat_actual is None or lon_actual is None:
                st.error("⚠️ No se detectó tu ubicación GPS. Activa la ubicación en tu celular para poder checar.")
            else:
                suc_emp = emp_actual["Sucursal"]
                cfg_suc = SUCURSALES_GPS.get(suc_emp, list(SUCURSALES_GPS.values())[0])
                
                dist_m = calcular_distancia_metros(lat_actual, lon_actual, cfg_suc["lat"], cfg_suc["lon"])
                dentro_rango = dist_m <= cfg_suc["radio_metros"]
                
                # Evaluar si está en sucursal o en comisión externa
                if dentro_rango:
                    estado_ubi = f"✅ En Sucursal ({dist_m} m)"
                else:
                    estado_ubi = f"📍 Fuera de Sucursal ({dist_m} m)"
                
                # Si es Entrada o Salida Definitiva y está muy lejos, puedes bloquearlo o marcar alerta
                ahora = datetime.now(ZONA_HORARIA)
                f_str = ahora.strftime("%Y-%m-%d")
                h_str = ahora.strftime("%Y-%m-%d %H:%M:%S")
                link_maps = f"https://www.google.com/maps?q={lat_actual},{lon_actual}"
                
                cadena = f"{emp_actual['Codigo']}|{h_str}|{evento}|{depto_extra}|{motivo_extra}|{lat_actual}|{lon_actual}"
                sello_sha = generar_hash(cadena)
                
                hoja_asi = libro_bd.worksheet("Asistencias")
                hoja_asi.append_row([
                    f_str, h_str, str(emp_actual["Codigo"]), emp_actual["Nombre"],
                    emp_actual["Departamento"], suc_emp, evento, depto_extra,
                    motivo_extra, ref_extra, lat_actual, lon_actual,
                    dist_m, estado_ubi, link_maps, sello_sha
                ])
                
                st.balloons()
                st.success(f"✔️ Registro guardado a las {h_str} — {estado_ubi}")
                st.markdown(f"🗺️ [Ver ubicación exacta registrada en Google Maps]({link_maps})")
                st.caption(f"🔒 Sello SHA-256 STPS/SAT: `{sello_sha[:30]}...`")

# ==============================================================================
# MÓDULO 2: PANEL ADMINISTRADOR (AUDITORÍA GPS, SALIDAS EXTRAS Y SAT 46H)
# ==============================================================================
elif modo == "💻 Panel Administrador (RH / SAT)":
    pin_adm = st.sidebar.text_input("PIN Administrador:", type="password")
    if pin_adm != "1234":
        st.warning("🔒 Introduce el PIN de Administrador (1234).")
        st.stop()
        
    hoja_asi = libro_bd.worksheet("Asistencias")
    df_todo = pd.DataFrame(hoja_asi.get_all_records())
    
    st.subheader("📍 Historial en Vivo con Ubicación GPS y Salidas Extras")
    if df_todo.empty:
        st.info("Aún no hay registros en la nube.")
    else:
        st.dataframe(
            df_todo,
            column_config={
                "Link_Mapa": st.column_config.LinkColumn("Mapa GPS", display_text="📍 Abrir en Google Maps")
            },
            use_container_width=True,
            hide_index=True
        )
