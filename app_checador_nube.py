import streamlit as st
import streamlit.components.v1 as components
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import hashlib
import math
import json
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from streamlit_js_eval import get_geolocation

st.set_page_config(page_title="Checador Cloud GPS 2027", page_icon="📍", layout="wide")

ZONA_HORARIA = ZoneInfo("America/Mexico_City")

# --- 1. COORDENADAS GPS DE TUS SUCURSALES (GEOCERCA) ---
SUCURSALES_GPS = {
    "Tapachula": {"lat": 14.882420, "lon": -92.278300, "radio_metros": 150},
    "Tuxtla": {"lat": 16.764510, "lon": -93.153420, "radio_metros": 150},
    "Tonala": {"lat": 16.089850, "lon": -93.755430, "radio_metros": 150},
    "Villa Flores": {"lat": 16.233520, "lon": -93.268510, "radio_metros": 150},
    "Comitan": {"lat": 16.230710, "lon": -92.122130, "radio_metros": 150},
}

# --- 2. CATÁLOGO DE SALIDAS EXTRAS POR DEPARTAMENTO ---
CATALOGO_SALIDAS_EXTRAS = {
    "Administrativo": ["Bancos", "Compras", "Firma cheque", "Medico", "Otra"],
    "Taller": ["Reparaciones", "Mantenimiento", "Entrega", "Compra", "Medico", "Otra"],
    "Ventas": ["Compras", "Entrega", "Medico", "Otra"],
    "Refacciones": ["Compras", "Medico", "Otra"],
    "Vigilancia": ["Rondin", "Apoyo Sucursal", "Medico", "Otra"]
}

# --- 3. CONEXIÓN A GOOGLE SHEETS ---
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
    
    if "Horarios" not in nombres_hojas:
        h_hor = libro.add_worksheet(title="Horarios", rows="50", cols="5")
        h_hor.append_row(["Departamento", "Entrada", "Salida", "Inicio_Comida", "Fin_Comida"])
        
    if "Empleados" not in nombres_hojas:
        h_emp = libro.add_worksheet(title="Empleados", rows="200", cols="10")
        h_emp.append_row(["Codigo", "Nombre", "Puesto", "Departamento", "Sucursal", "PIN", "Activo"])
        h_emp.append_rows([
            ["001", "Laura Méndez", "Asistente", "Administrativo", "Tapachula", "1111", "1"],
            ["002", "Roberto Gómez", "Mecánico", "Taller", "Tuxtla", "2222", "1"],
            ["003", "Carlos Ruiz", "Vendedor", "Ventas", "Tonala", "3333", "1"],
            ["004", "Miguel Pérez", "Mostrador", "Refacciones", "Comitan", "4444", "1"],
            ["005", "Juan Torres", "Guardia", "Vigilancia", "Tapachula", "5555", "1"]
        ])
        
    if "Asistencias" not in nombres_hojas:
        h_asi = libro.add_worksheet(title="Asistencias", rows="5000", cols="16")
        h_asi.append_row([
            "Fecha", "Hora_Servidor", "Codigo", "Nombre", "Departamento", "Sucursal",
            "Tipo_Evento", "Depto_Salida_Extra", "Motivo_Salida_Extra", "Referencia",
            "Latitud", "Longitud", "Distancia_Sucursal_m", "Estado_Ubicacion",
            "Link_Mapa", "Hash_SHA256"
        ])

# --- 4. FÓRMULA DE DISTANCIA GPS Y HASH ---
def calcular_distancia_metros(lat1, lon1, lat2, lon2):
    R = 6371000
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
modo = st.sidebar.radio("Modo:", ["📱 Checar desde Celular", "💻 Panel Administrador"])

reloj_html = """
<div style="padding: 10px; background-color: #f0f2f6; border-radius: 5px; text-align: center;">
    <p style="margin: 0; font-size: 14px; font-family: sans-serif; color: #31333F;">🕒 <b>Hora Oficial:</b></p>
    <p id="reloj_vivo" style="margin: 0; font-size: 18px; font-weight: bold; font-family: monospace; color: #0068c9;"></p>
</div>
<script>
    function actualizarReloj() {
        var ahora = new Date();
        var opciones = { timeZone: 'America/Mexico_City', hour12: false, hour: '2-digit', minute:'2-digit', second:'2-digit' };
        var horaFmt = ahora.toLocaleTimeString('es-MX', opciones);
        var fechaFmt = ahora.toLocaleDateString('es-MX', {timeZone: 'America/Mexico_City'});
        document.getElementById('reloj_vivo').innerHTML = fechaFmt + "<br>" + horaFmt;
    }
    setInterval(actualizarReloj, 1000);
    actualizarReloj();
</script>
"""
with st.sidebar:
    st.write("<br>", unsafe_allow_html=True)
    components.html(reloj_html, height=85)

# ==============================================================================
# MÓDULO 1: CHECADOR MÓVIL
# ==============================================================================
if modo == "📱 Checar desde Celular":
    st.title("📱 Registro de Asistencia")
    
    st.markdown("##### 📍 1. Ubicación del Dispositivo")
    loc = get_geolocation()
    
    lat_actual, lon_actual, precision_m = None, None, None
    if loc and "coords" in loc:
        lat_actual = loc["coords"]["latitude"]
        lon_actual = loc["coords"]["longitude"]
        precision_m = round(loc["coords"].get("accuracy", 0), 1)
        st.success(f"🛰️ GPS Activo: `{lat_actual:.5f}, {lon_actual:.5f}` (Precisión: ±{precision_m} m)")
    else:
        st.warning("⚠️ Esperando GPS... (Requerido para Entradas y Comisiones).")

    st.divider()
    col1, col2 = st.columns([1, 1.3])
    
    with col1:
        st.markdown("##### 👤 2. Identificación")
        cod_in = st.text_input("Número de Empleado (Ej. 001):").strip()
        pin_in = st.text_input("PIN de Seguridad:", type="password").strip()
        
        hoja_emp = libro_bd.worksheet("Empleados")
        df_emp = pd.DataFrame(hoja_emp.get_all_records())
        
        emp_actual = None
        if cod_in and pin_in and not df_emp.empty:
            df_emp["Codigo_str"] = df_emp["Codigo"].astype(str).str.zfill(3)
            cod_busq = cod_in.zfill(3) if cod_in.isdigit() else cod_in
            match = df_emp[(df_emp["Codigo_str"] == cod_busq) & (df_emp["PIN"].astype(str) == pin_in)]
            if not match.empty:
                emp_actual = match.iloc[0].to_dict()
                puesto_txt = f" - {emp_actual.get('Puesto', '')}" if emp_actual.get('Puesto') else ""
                st.success(f"**{emp_actual['Nombre']}**\nDepto: {emp_actual['Departamento']}{puesto_txt} | {emp_actual['Sucursal']}")
            else:
                st.error("❌ Código o PIN incorrecto.")

    with col2:
        st.markdown("##### 📝 3. Tipo de Registro")
        evento = st.radio(
            "Selecciona el movimiento:",
            [
                "🟢 Entrada de Jornada",
                "🚗 Salida Operativa",
                "🔙 Regreso de Salida Operativa",
                "🍽️ Salida a Comer",
                "🍽️ Regreso de Comer",
                "🔴 Salida Definitiva"
            ]
        )
        
        depto_extra, motivo_extra, ref_extra = "", "", ""
        if evento == "🚗 Salida Operativa":
            deptos_lista = list(CATALOGO_SALIDAS_EXTRAS.keys())
            idx_d = deptos_lista.index(emp_actual["Departamento"]) if (emp_actual and emp_actual["Departamento"] in deptos_lista) else 0
            
            c1, c2 = st.columns(2)
            depto_extra = c1.selectbox("Área:", deptos_lista, index=idx_d)
            motivo_extra = c2.selectbox("Motivo de Salida:", CATALOGO_SALIDAS_EXTRAS[depto_extra])
            ref_extra = st.text_input("Referencia / Destino:").strip()
        elif evento == "🔙 Regreso de Salida Operativa":
            ref_extra = st.text_input("Observaciones de regreso:").strip()

        if st.button("✅ ENVIAR REGISTRO", type="primary", use_container_width=True):
            if not emp_actual:
                st.error("⚠️ Ingresa tu Código y PIN válidos primero.")
            elif (lat_actual is None or lon_actual is None) and evento not in ["🔴 Salida Definitiva", "🟢 Entrada de Jornada"]:
                st.error("⚠️ No se detectó tu ubicación GPS. Activa la ubicación para checar este movimiento.")
            else:
                suc_emp = emp_actual["Sucursal"]
                cfg_suc = SUCURSALES_GPS.get(suc_emp, list(SUCURSALES_GPS.values())[0])
                
                dentro_rango = False
                dist_m = 0
                estado_ubi = "📍 Remota / Sin GPS"
                link_maps = "N/A"

                if lat_actual is not None and lon_actual is not None:
                    dist_m = calcular_distancia_metros(lat_actual, lon_actual, cfg_suc["lat"], cfg_suc["lon"])
                    dentro_rango = dist_m <= cfg_suc["radio_metros"]
                    estado_ubi = f"✅ En Sucursal ({dist_m} m)" if dentro_rango else f"📍 Fuera de Sucursal ({dist_m} m)"
                    link_maps = f"https://www.google.com/maps?q={lat_actual},{lon_actual}"
                else:
                    lat_actual, lon_actual = 0.0, 0.0
                
                ahora = datetime.now(ZONA_HORARIA)
                f_str = ahora.strftime("%Y-%m-%d")
                hoja_asi = libro_bd.worksheet("Asistencias")

                # --- ESCENARIO 1: SALIDA DEFINITIVA REMOTA (-30 MIN DE TRAYECTO) ---
                if evento == "🔴 Salida Definitiva" and not dentro_rango:
                    ahora_regreso = ahora - timedelta(minutes=30)
                    h_auto_str = ahora_regreso.strftime("%Y-%m-%d %H:%M:%S")
                    sello_auto = generar_hash(f"{emp_actual['Codigo']}|{h_auto_str}|🔙 Regreso de Salida Operativa|||{lat_actual}|{lon_actual}")
                    
                    hoja_asi.append_row([
                        f_str, h_auto_str, str(emp_actual["Codigo"]), emp_actual["Nombre"],
                        emp_actual["Departamento"], suc_emp, "🔙 Regreso de Salida Operativa", "",
                        "", "Cierre automático (-30 min por trayecto)", lat_actual, lon_actual, dist_m, estado_ubi, link_maps, sello_auto
                    ])

                    h_str = ahora.strftime("%Y-%m-%d %H:%M:%S")
                    sello_sha = generar_hash(f"{emp_actual['Codigo']}|{h_str}|{evento}|{depto_extra}|{motivo_extra}|{lat_actual}|{lon_actual}")
                    hoja_asi.append_row([
                        f_str, h_str, str(emp_actual["Codigo"]), emp_actual["Nombre"],
                        emp_actual["Departamento"], suc_emp, evento, depto_extra,
                        motivo_extra, ref_extra, lat_actual, lon_actual, dist_m, estado_ubi, link_maps, sello_sha
                    ])
                    st.balloons()
                    st.success(f"✔️ Regreso Automático (-30 min) y Salida Definitiva guardados — {estado_ubi}")

                # --- ESCENARIO 2: ENTRADA DE JORNADA REMOTA (+10 MIN COMISIÓN AUTOMÁTICA) ---
                elif evento == "🟢 Entrada de Jornada" and not dentro_rango:
                    # 1. Guarda la entrada a la hora real
                    h_str = ahora.strftime("%Y-%m-%d %H:%M:%S")
                    sello_sha = generar_hash(f"{emp_actual['Codigo']}|{h_str}|{evento}|||{lat_actual}|{lon_actual}")
                    hoja_asi.append_row([
                        f_str, h_str, str(emp_actual["Codigo"]), emp_actual["Nombre"],
                        emp_actual["Departamento"], suc_emp, evento, "",
                        "", "Entrada Remota", lat_actual, lon_actual, dist_m, estado_ubi, link_maps, sello_sha
                    ])
                    
                    # 2. Asignar motivo según departamento
                    depto = emp_actual["Departamento"]
                    if depto == "Taller": motivo_auto = "Reparaciones"
                    elif depto == "Ventas": motivo_auto = "Entrega"
                    elif depto == "Refacciones": motivo_auto = "Compra"
                    else: motivo_auto = "Otra" # Para Administrativo y Vigilancia

                    # 3. Programa la Salida Operativa exactamente 10 min en el futuro
                    ahora_salida = ahora + timedelta(minutes=10)
                    h_auto_str = ahora_salida.strftime("%Y-%m-%d %H:%M:%S")
                    ref_auto = "Apertura automática de comisión (+10 min por entrada remota)"
                    sello_auto = generar_hash(f"{emp_actual['Codigo']}|{h_auto_str}|🚗 Salida Operativa|{depto}|{motivo_auto}|{lat_actual}|{lon_actual}")
                    
                    hoja_asi.append_row([
                        f_str, h_auto_str, str(emp_actual["Codigo"]), emp_actual["Nombre"],
                        emp_actual["Departamento"], suc_emp, "🚗 Salida Operativa", depto,
                        motivo_auto, ref_auto, lat_actual, lon_actual, dist_m, estado_ubi, link_maps, sello_auto
                    ])
                    
                    st.balloons()
                    st.success(f"✔️ Entrada guardada a las {h_str} y Comisión Automática ({motivo_auto}) programada para las {h_auto_str} — {estado_ubi}")

                # --- ESCENARIO 3: REGISTROS NORMALES ---
                else:
                    h_str = ahora.strftime("%Y-%m-%d %H:%M:%S")
                    sello_sha = generar_hash(f"{emp_actual['Codigo']}|{h_str}|{evento}|{depto_extra}|{motivo_extra}|{lat_actual}|{lon_actual}")
                    
                    hoja_asi.append_row([
                        f_str, h_str, str(emp_actual["Codigo"]), emp_actual["Nombre"],
                        emp_actual["Departamento"], suc_emp, evento, depto_extra,
                        motivo_extra, ref_extra, lat_actual, lon_actual,
                        dist_m, estado_ubi, link_maps, sello_sha
                    ])
                    st.balloons()
                    st.success(f"✔️ Registro guardado exitosamente a las {h_str} — {estado_ubi}")

# ==============================================================================
# MÓDULO 2: PANEL ADMINISTRADOR
# ==============================================================================
elif modo == "💻 Panel Administrador":
    pin_adm = st.sidebar.text_input("PIN Administrador:", type="password")
    if pin_adm != "1234":
        st.warning("🔒 Introduce el PIN de Administrador (1234).")
        st.stop()

    tab_historial, tab_horarios, tab_empleados = st.tabs([
        "📍 Historial en Vivo", 
        "⚙️ Horarios por Departamento",
        "👥 Alta de Personal"
    ])
    
    # --- PESTAÑA 1: HISTORIAL ---
    with tab_historial:
        st.subheader("📍 Historial y Salidas Extras")
        df_todo = pd.DataFrame(libro_bd.worksheet("Asistencias").get_all_records())
        if df_todo.empty:
            st.info("Aún no hay registros.")
        else:
            st.dataframe(df_todo.sort_values(by="Hora_Servidor", ascending=False), 
                         column_config={"Link_Mapa": st.column_config.LinkColumn("Mapa GPS")},
                         use_container_width=True, hide_index=True)

    # --- PESTAÑA 2: CONFIGURACIÓN DE HORARIOS ---
    with tab_horarios:
        st.subheader("⚙️ Configuración de Jornadas")
        st.caption("Define el horario de trabajo y tiempo de comida (Tolerancia eliminada por disposición SAT).")
        
        hoja_horarios = libro_bd.worksheet("Horarios")
        df_hor = pd.DataFrame(hoja_horarios.get_all_records())
        
        with st.form("form_horarios", clear_on_submit=True):
            col_h1, col_h2, col_h3 = st.columns(3)
            dep_sel = col_h1.selectbox("Departamento", list(CATALOGO_SALIDAS_EXTRAS.keys()))
            h_ent = col_h2.time_input("Hora de Entrada", value=time(8, 0))
            h_sal = col_h3.time_input("Hora de Salida", value=time(18, 0))
            
            col_h4, col_h5 = st.columns(2)
            h_com_ini = col_h4.time_input("Inicio de Comida", value=time(14, 0))
            h_com_fin = col_h5.time_input("Fin de Comida", value=time(15, 0))
            
            if st.form_submit_button("💾 Guardar Horario"):
                if not df_hor.empty and dep_sel in df_hor['Departamento'].values:
                    idx = df_hor[df_hor['Departamento'] == dep_sel].index[0]
                    fila_gsheet = int(idx) + 2
                    hoja_horarios.update(f"A{fila_gsheet}:E{fila_gsheet}", [[
                        dep_sel, h_ent.strftime("%H:%M"), h_sal.strftime("%H:%M"),
                        h_com_ini.strftime("%H:%M"), h_com_fin.strftime("%H:%M")
                    ]])
                else:
                    hoja_horarios.append_row([
                        dep_sel, h_ent.strftime("%H:%M"), h_sal.strftime("%H:%M"),
                        h_com_ini.strftime("%H:%M"), h_com_fin.strftime("%H:%M")
                    ])
                st.success(f"✅ Horario del departamento {dep_sel} actualizado correctamente.")
                st.rerun()

        if not df_hor.empty:
            st.markdown("**Horarios Registrados (Sin Tolerancia):**")
            st.dataframe(df_hor, use_container_width=True, hide_index=True)

    # --- PESTAÑA 3: ALTA DE EMPLEADOS ---
    with tab_empleados:
        st.subheader("👥 Gestión de Empleados")
        hoja_emp = libro_bd.worksheet("Empleados")
        df_emp = pd.DataFrame(hoja_emp.get_all_records())
        
        with st.form("form_alta", clear_on_submit=True):
            ce1, ce2 = st.columns(2)
            n_cod = ce1.text_input("Código de Empleado (Ej. 006)")
            n_nom = ce2.text_input("Nombre Completo")
            
            ce3, ce4, ce5 = st.columns(3)
            n_dep = ce3.selectbox("Departamento Asignado", list(CATALOGO_SALIDAS_EXTRAS.keys()))
            n_suc = ce4.selectbox("Sucursal Base", list(SUCURSALES_GPS.keys()))
            n_pin = ce5.text_input("PIN de 4 dígitos", type="password")
            
            quiere_puesto = st.checkbox("¿Especificar Puesto del Empleado?")
            n_puesto = st.text_input("Puesto (Ej. Guardia de Seguridad, Mecánico A, etc.)", disabled=not quiere_puesto)
            
            if st.form_submit_button("➕ Registrar Empleado"):
                if n_cod and n_nom and n_pin:
                    if not df_emp.empty and str(n_cod) in df_emp['Codigo'].astype(str).values:
                        st.error("⚠️ El código de empleado ya existe.")
                    else:
                        puesto_final = n_puesto if quiere_puesto else ""
                        hoja_emp.append_row([n_cod, n_nom, puesto_final, n_dep, n_suc, n_pin, "1"])
                        st.success(f"✅ Empleado {n_nom} ({n_dep}) registrado exitosamente.")
                        st.rerun()
                else:
                    st.error("Completa el Código, Nombre y PIN.")

        if not df_emp.empty:
            st.markdown("**Plantilla de Personal Activo:**")
            st.dataframe(df_emp, use_container_width=True, hide_index=True)
