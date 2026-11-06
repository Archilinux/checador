import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import date, time

st.set_page_config(page_title="Agro Equipos - Dashboard Administrador", layout="wide")

st.header("⚙️ Panel de Administrador - Horarios y Reportes")

# --- CONEXIÓN A GOOGLE SHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)

def cargar_hoja(nombre_hoja):
    try:
        df = conn.read(worksheet=nombre_hoja)
        return df
    except Exception as e:
        return pd.DataFrame()

# ==========================================
# 1. CONFIGURACIÓN DE HORARIOS Y ÁREAS
# ==========================================
st.subheader("1. Configuración de ÁREAS y HORARIOS")
with st.expander("Haz clic aquí para agregar o editar Áreas y Horarios", expanded=False):
    st.markdown("Configura las áreas disponibles para las encuestas y sus horarios correspondientes.")
    
    with st.form("form_horarios", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            nueva_area = st.text_input("Nombre del Área (Ej. Ventas, Taller, Vigilancia)")
        with c2:
            hora_inicio = st.time_input("Hora de Inicio de Jornada", value=time(8, 0))
            hora_fin = st.time_input("Hora de Fin de Jornada", value=time(18, 0))
        with c3:
            hora_ini_comida = st.time_input("Inicio Hora de Comida", value=time(14, 0))
            hora_fin_comida = st.time_input("Fin Hora de Comida", value=time(15, 0))
            
        tolerancia = st.number_input("Minutos de Tolerancia para Retardo", min_value=0, value=15, step=5)
        
        if st.form_submit_button("Guardar Configuración"):
            if nueva_area:
                df_areas = cargar_hoja("Areas_Horarios")
                
                datos_area = {
                    "Area": nueva_area,
                    "Hora_Inicio": hora_inicio.strftime("%H:%M"),
                    "Hora_Fin": hora_fin.strftime("%H:%M"),
                    "Hora_Inicio_Comida": hora_ini_comida.strftime("%H:%M"),
                    "Hora_Fin_Comida": hora_fin_comida.strftime("%H:%M"),
                    "Tolerancia_Minutos": tolerancia
                }
                
                # Si el área ya existe, la actualiza; si no, la agrega.
                if not df_areas.empty and nueva_area in df_areas['Area'].values:
                    indice = df_areas[df_areas['Area'] == nueva_area].index[0]
                    for key, val in datos_area.items():
                        df_areas.at[indice, key] = val
                    df_actualizado = df_areas
                    mensaje = f"✅ Horario del área '{nueva_area}' actualizado."
                else:
                    df_nuevo = pd.DataFrame([datos_area])
                    df_actualizado = pd.concat([df_areas, df_nuevo], ignore_index=True) if not df_areas.empty else df_nuevo
                    mensaje = f"✅ Nueva área '{nueva_area}' agregada."
                
                try:
                    conn.update(worksheet="Areas_Horarios", data=df_actualizado)
                    st.cache_data.clear()
                    st.success(mensaje)
                except Exception as e:
                    st.error("Error al guardar. Asegúrate de crear una pestaña llamada 'Areas_Horarios' en tu Excel.")
            else:
                st.error("Por favor, ingresa el nombre del área.")

    # Mostrar la tabla actual de configuraciones
    df_areas_actual = cargar_hoja("Areas_Horarios")
    if not df_areas_actual.empty:
        st.markdown("**Áreas y Horarios Registrados Actualmente:**")
        st.dataframe(df_areas_actual, use_container_width=True, hide_index=True)

st.divider()

# ==========================================
# 2. DASHBOARD DE ENCUESTAS (CON FILTROS)
# ==========================================
st.subheader("2. Reportes de Encuestas y Satisfacción")

# Filtros de fecha en la parte superior
col1, col2, col3 = st.columns(3)
with col1:
    fecha_inicio = st.date_input("Desde la fecha:", date(date.today().year, date.today().month, 1))
with col2:
    fecha_fin = st.date_input("Hasta la fecha:", date.today())
with col3:
    st.write("")
    st.write("")
    if st.button("🔄 Actualizar Datos"):
        st.cache_data.clear()

st.divider()

mapa_valores = {"Muy mala": 1, "Mala": 2, "Regular": 3, "Buena": 4, "Muy buena": 5}

# --- PESTAÑAS PARA CADA MÓDULO ---
tab_refacciones, tab_maquinaria, tab_servicios, tab_reclamos = st.tabs([
    "🛠️ Refacciones", "🚜 Maquinaria", "🔧 Servicios", "⚠️ Reclamos"
])

def generar_metricas_y_graficas(df_filtrado, columna_persona, titulo_persona):
    if df_filtrado.empty:
        st.info("No hay datos en este rango de fechas.")
        return

    # Contar respuestas negativas (Mala o Muy mala) en TODAS las preguntas de la encuesta
    columnas_preguntas = [col for col in df_filtrado.columns if col not in ['Fecha', 'Cliente', 'Pieza', 'Vendedor', 'Equipo', 'Tecnico', 'Servicio', 'Mejoras', 'Recomendacion', 'Puesto']]
    
    total_respuestas = 0
    total_malas = 0
    
    for col in columnas_preguntas:
        if col in df_filtrado.columns:
            respuestas_columna = df_filtrado[col].dropna()
            total_respuestas += len(respuestas_columna)
            total_malas += respuestas_columna.isin(["Mala", "Muy mala"]).sum()
            df_filtrado.loc[:, f'Num_{col}'] = df_filtrado[col].map(mapa_valores)

    # Panel superior de métricas
    k1, k2, k3 = st.columns(3)
    k1.metric("Total Encuestas Recibidas", len(df_filtrado))
    k2.metric("Respuestas Críticas (Malas/Muy Malas)", f"{total_malas} de {total_respuestas}")
    if 'Experiencia' in df_filtrado.columns:
        promedio_gral = df_filtrado['Num_Experiencia'].mean()
        k3.metric("Promedio General (Sobre 5)", f"{promedio_gral:.2f}" if pd.notna(promedio_gral) else "N/A")

    st.markdown("---")
    
    # Gráficas por pregunta en columnas (De 2 en 2)
    st.markdown("#### 📊 Desempeño por Pregunta (Promedio sobre 5)")
    for i in range(0, len(columnas_preguntas), 2):
        c1, c2 = st.columns(2)
        
        # Primera pregunta de la fila
        col_actual_1 = columnas_preguntas[i]
        col_num_1 = f'Num_{col_actual_1}'
        if col_num_1 in df_filtrado.columns:
            promedios_1 = df_filtrado.groupby(columna_persona)[col_num_1].mean()
            with c1:
                st.markdown(f"**{col_actual_1}**")
                st.bar_chart(promedios_1)
        
        # Segunda pregunta de la fila (si existe)
        if i + 1 < len(columnas_preguntas):
            col_actual_2 = columnas_preguntas[i+1]
            col_num_2 = f'Num_{col_actual_2}'
            if col_num_2 in df_filtrado.columns:
                promedios_2 = df_filtrado.groupby(columna_persona)[col_num_2].mean()
                with c2:
                    st.markdown(f"**{col_actual_2}**")
                    st.bar_chart(promedios_2)

    st.markdown("---")
    
    # Comentarios de mejora
    with st.expander("💬 Ver Sugerencias y Comentarios de Mejora"):
        if 'Mejoras' in df_filtrado.columns:
            comentarios = df_filtrado[['Fecha', columna_persona, 'Mejoras']].dropna(subset=['Mejoras'])
            comentarios = comentarios[comentarios['Mejoras'].astype(str).str.strip() != ""]
            if not comentarios.empty:
                st.dataframe(comentarios, use_container_width=True, hide_index=True)
            else:
                st.write("No hay comentarios registrados en este periodo.")

# --- TAB REFACCIONES ---
with tab_refacciones:
    df_ref = cargar_hoja("Refacciones")
    if not df_ref.empty and "Fecha" in df_ref.columns:
        df_ref['Fecha'] = pd.to_datetime(df_ref['Fecha']).dt.date
        df_ref_filtrado = df_ref[(df_ref['Fecha'] >= fecha_inicio) & (df_ref['Fecha'] <= fecha_fin)].copy()
        
        # Si no hay vendedor, usamos "Equipo de Refacciones" como pivote para las gráficas
        if 'Vendedor' not in df_ref_filtrado.columns:
            df_ref_filtrado['Vendedor'] = "Asesores Refacciones"
            
        generar_metricas_y_graficas(df_ref_filtrado, "Vendedor", "Asesor")
    else:
        st.warning("No se pudo cargar el reporte de Refacciones o está vacío.")

# --- TAB MAQUINARIA ---
with tab_maquinaria:
    df_maq = cargar_hoja("Maquinaria")
    if not df_maq.empty and "Fecha" in df_maq.columns:
        df_maq['Fecha'] = pd.to_datetime(df_maq['Fecha']).dt.date
        df_maq_filtrado = df_maq[(df_maq['Fecha'] >= fecha_inicio) & (df_maq['Fecha'] <= fecha_fin)].copy()
        generar_metricas_y_graficas(df_maq_filtrado, "Vendedor", "Vendedor")
    else:
        st.warning("No se pudo cargar el reporte de Maquinaria o está vacío.")

# --- TAB SERVICIOS ---
with tab_servicios:
    df_serv = cargar_hoja("Servicios")
    if not df_serv.empty and "Fecha" in df_serv.columns:
        df_serv['Fecha'] = pd.to_datetime(df_serv['Fecha']).dt.date
        df_serv_filtrado = df_serv[(df_serv['Fecha'] >= fecha_inicio) & (df_serv['Fecha'] <= fecha_fin)].copy()
        generar_metricas_y_graficas(df_serv_filtrado, "Tecnico", "Técnico")
    else:
        st.warning("No se pudo cargar el reporte de Servicios o está vacío.")

# --- TAB RECLAMOS ---
with tab_reclamos:
    df_rec = cargar_hoja("Reclamos")
    if not df_rec.empty and "Fecha" in df_rec.columns:
        df_rec['Fecha'] = pd.to_datetime(df_rec['Fecha']).dt.date
        df_rec_filtrado = df_rec[(df_rec['Fecha'] >= fecha_inicio) & (df_rec['Fecha'] <= fecha_fin)].copy()
        
        st.subheader(f"⚠️ Reclamos Recibidos ({len(df_rec_filtrado)})")
        
        if not df_rec_filtrado.empty:
            st.dataframe(df_rec_filtrado, use_container_width=True, hide_index=True)
            
            # Resumen por departamento
            st.markdown("**Reclamos por Departamento:**")
            conteo_deptos = df_rec_filtrado['Departamento'].value_counts()
            st.bar_chart(conteo_deptos)
        else:
            st.info("No hay reclamos en este rango de fechas.")
    else:
        st.warning("No se pudo cargar el reporte de Reclamos o está vacío.")
