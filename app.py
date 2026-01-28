import streamlit as st
import pandas as pd
import time
import plotly.express as px

# IMPORTAMOS NUESTROS MÓDULOS
import constantes as c
import database as db
import reportes as rep
import auth

# Configuración inicial
st.set_page_config(page_title="Gestión de Inventario TI", layout="wide", page_icon="🖥️")

# Estilos CSS
st.markdown("""
    <style>
        .block-container { padding-top: 2rem !important; }
        .stTabs { margin-top: 0px !important; }
        hr { margin-top: 10px !important; margin-bottom: 10px !important; }
        /* Ocultar índices de tablas */
        thead tr th:first-child {display:none}
        tbody tr td:first-child {display:none}
    </style>
    """, unsafe_allow_html=True)

# --- AUTH ---
cookies = auth.init_cookies()
if auth.verificar_sesion(cookies):
    
    # --- SIDEBAR ---
    with st.sidebar:
        st.title("⚙️ Panel")
        st.write(f"👤 **{st.session_state.usuario_actual}**")
        st.info(f"Rol: {st.session_state.rol_actual}")
        
        st.divider()
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            cookies["usuario_actual"] = ""
            cookies["rol_actual"] = ""
            cookies.save()
            st.session_state.clear()
            st.rerun()

    # --- HEADER ---
    c_head, c_logo = st.columns([3, 1])
    with c_head: st.title("🖥️ Gestión de Inventario TI")
    
    # --- CARGA DE DATOS CENTRALIZADA ---
    # Esta función ya trae TODOS los datos (sin limite de 1000) gracias a la paginación en database.py
    df = db.obtener_datos()
    
    # --- PESTAÑAS ---
    pestanas = ["📊 Dashboard", "🔎 Consultar", "➕ Nuevo", "📥 Carga Masiva", "✏️ Editar/Acta"]
    if st.session_state.rol_actual == "Administrador":
        pestanas += ["📜 Logs", "👥 Usuarios"]
    
    tabs = st.tabs(pestanas)

    # --- UI HELPERS ---
    def obtener_opciones_filtro(dataframe, columna):
        """Devuelve SOLO valores existentes en DB para filtros limpios"""
        if columna in dataframe.columns:
            valores = dataframe[columna].unique().tolist()
            # Limpiar vacíos o nulos
            valores = [x for x in valores if x and x != "" and x != "-" and x != "None"]
            return sorted(valores)
        return []

    def obtener_opciones_input(dataframe, columna, lista_base):
        """Devuelve valores DB + Lista Base para facilitar ingreso de datos nuevos"""
        existentes = obtener_opciones_filtro(dataframe, columna)
        combinados = sorted(list(set(lista_base + existentes)))
        return combinados

    def campo_con_opcion_otro(label, lista_opciones, valor_actual=None, key_suffix=""):
        """Selector inteligente con opción manual"""
        opciones = list(lista_opciones)
        opcion_otro = "OTRO (ESPECIFICAR)"
        if opcion_otro not in opciones: opciones.append(opcion_otro)
        
        idx = 0
        modo_manual = False
        
        # Lógica para seleccionar valor actual
        if valor_actual and valor_actual not in ["", "-", "NAN"]:
            if valor_actual in opciones:
                idx = opciones.index(valor_actual)
            else:
                idx = opciones.index(opcion_otro)
                modo_manual = True
                
        seleccion = st.selectbox(label, opciones, index=idx, key=f"sel_{label}_{key_suffix}")
        
        if seleccion == opcion_otro:
            val_defecto = valor_actual if modo_manual else ""
            return st.text_input(f"Especifique {label}", value=val_defecto, key=f"txt_{label}_{key_suffix}").upper()
        return seleccion

    # 1. DASHBOARD (FILTROS STRICTOS)
    with tabs[0]:
        st.subheader("Tablero de Control")
        
        with st.expander("🔎 Filtros (Basados en datos existentes)", expanded=True):
            fc1, fc2, fc3 = st.columns(3)
            
            # AQUI ESTA EL CAMBIO: Usamos solo 'obtener_opciones_filtro' (Solo DB)
            # No usamos c.LISTAS_OPCIONES aquí para evitar opciones vacías
            opts_area = obtener_opciones_filtro(df, "ÁREA")
            opts_tipo = obtener_opciones_filtro(df, "TIPO")
            opts_estado = obtener_opciones_filtro(df, "ESTADO")
            
            sel_area = fc1.multiselect("Área", opts_area)
            sel_tipo = fc2.multiselect("Tipo", opts_tipo)
            sel_estado = fc3.multiselect("Estado", opts_estado)
        
        # Aplicar Filtros
        df_d = df.copy()
        if sel_area: df_d = df_d[df_d["ÁREA"].isin(sel_area)]
        if sel_tipo: df_d = df_d[df_d["TIPO"].isin(sel_tipo)]
        if sel_estado: df_d = df_d[df_d["ESTADO"].isin(sel_estado)]
        
        # Métricas
        def to_float(val):
            try: return float(str(val).replace("S/", "").replace(",", ""))
            except: return 0.0
        
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total Activos", len(df_d))
        k2.metric("Asignados", len(df_d[df_d["USUARIO"].str.len() > 3]))
        k3.metric("Stock / Disponibles", len(df_d[df_d["ESTADO"].isin(["DISPONIBLE", "OPERATIVO", "EN REVISIÓN"]) & (df_d["USUARIO"].str.len() <= 3)]))
        k4.metric("Valor Inventario", f"S/ {df_d['COSTO'].apply(to_float).sum():,.2f}")
        
        st.divider()
        g1, g2 = st.columns(2)
        with g1:
            if not df_d.empty: 
                st.plotly_chart(px.pie(df_d, names="TIPO", title="Distribución por Tipo", hole=0.4), use_container_width=True)
            else: st.info("Sin datos para graficar")
        with g2:
            if not df_d.empty: 
                # Top 10 Áreas
                data_bar = df_d["ÁREA"].value_counts().head(10).reset_index()
                st.plotly_chart(px.bar(data_bar, x="count", y="ÁREA", orientation='h', title="Top Áreas con Equipos"), use_container_width=True)
            else: st.info("Sin datos para graficar")

    # 2. CONSULTAR
    with tabs[1]:
        st.subheader("Base de Datos")
        q_fast = st.text_input("Filtrar en tabla:", placeholder="Escriba marca, usuario, serie...", key="search_tab1").upper()
        
        df_view = df.drop(columns=["_supabase_id"], errors="ignore")
        if q_fast: 
            # Búsqueda visual rápida
            mask = df_view.astype(str).apply(lambda x: x.str.contains(q_fast, na=False)).any(axis=1)
            df_view = df_view[mask]
            
        st.dataframe(df_view, use_container_width=True, hide_index=True)

    # 3. NUEVO (AQUÍ SÍ USAMOS LISTAS PARA AYUDAR A ESCRIBIR)
    with tabs[2]:
        st.subheader("Nuevo Ingreso")
        with st.form("new_entry"):
            c1, c2, c3 = st.columns(3)
            n = {}
            
            # Preparamos listas inteligentes (Base + DB)
            lst_area = obtener_opciones_input(df, "ÁREA", c.LISTAS_OPCIONES["ÁREA"])
            lst_tipo = obtener_opciones_input(df, "TIPO", c.LISTAS_OPCIONES["TIPO"])
            lst_marca = obtener_opciones_input(df, "MARCA", c.LISTAS_OPCIONES["MARCA"])
            lst_estado = obtener_opciones_input(df, "ESTADO", c.LISTAS_OPCIONES["ESTADO"])
            
            with c1:
                n["USUARIO"] = st.text_input("Usuario Asignado").upper()
                n["ÁREA"] = campo_con_opcion_otro("Área", lst_area, key_suffix="n1")
                n["UBICACIÓN"] = st.text_input("Ubicación").upper()
                n["DIRECCIÓN"] = st.text_input("Dirección").upper()
            with c2:
                n["TIPO"] = campo_con_opcion_otro("Tipo", lst_tipo, key_suffix="n2")
                n["MARCA"] = campo_con_opcion_otro("Marca", lst_marca, key_suffix="n3")
                n["MODELO"] = st.text_input("Modelo").upper()
                n["EQUIPO"] = st.text_input("Hostname (Equipo)").upper()
            with c3:
                n["NRO DE SERIE"] = st.text_input("Nro Serie").upper()
                n["NUEVO ACTIVO"] = st.text_input("Cód. Nuevo Activo").upper()
                n["ACTIVO"] = st.text_input("Cód. Antiguo").upper()
                n["ESTADO"] = campo_con_opcion_otro("Estado", lst_estado, key_suffix="n4")
            
            n["COSTO"] = st.text_input("Costo").upper()
            n["ACCESORIOS"] = st.text_area("Accesorios").upper()
            n["OBSERVACIONES"] = st.text_area("Observaciones").upper()
            
            if st.form_submit_button("💾 Guardar Registro"):
                if n["NRO DE SERIE"] and n["NRO DE SERIE"] in df["NRO DE SERIE"].values:
                    st.error(f"¡Error! La serie {n['NRO DE SERIE']} ya existe.")
                else:
                    if db.guardar_registro_db(n, True):
                        st.success("Guardado exitosamente"); 
                        db.registrar_log("CREAR", n["NRO DE SERIE"]); 
                        time.sleep(1.5); st.rerun()

    # 4. CARGA MASIVA
    with tabs[3]:
        st.subheader("Carga Masiva")
        c_d, c_u = st.columns(2)
        with c_d:
            st.info("Descargue la plantilla oficial.")
            st.download_button("📥 Plantilla.xlsx", rep.generar_plantilla_carga(), "Plantilla_Inventario.xlsx")
        with c_u:
            upl = st.file_uploader("Subir Excel lleno", type=["xlsx"])
            if upl and st.button("Procesar Carga"):
                try:
                    df_up = pd.read_excel(upl).fillna("").astype(str)
                    bar = st.progress(0)
                    total = len(df_up)
                    for i, r in df_up.iterrows():
                        d = {k.strip().upper(): v.strip().upper() for k,v in r.to_dict().items()}
                        db.guardar_registro_db(d, True)
                        bar.progress((i+1)/total)
                    st.success(f"Carga completada: {total} registros."); 
                    time.sleep(1.5); st.rerun()
                except Exception as e: st.error(f"Error: {str(e)}")

    # 5. EDITAR / ACTA
    with tabs[4]:
        st.subheader("Gestión de Activos")
        q = st.text_input("🔍 Buscar Activo:", help="Busca por Usuario, Serie, Codigo, Marca...", placeholder="Ej: Laptop Dell o Juan Perez").upper()
        
        # Búsqueda Global Robusta
        if q:
            mask = df.astype(str).apply(lambda x: x.str.contains(q, na=False)).any(axis=1)
            df_res = df[mask]
        else:
            df_res = df.sort_values("Ultima_Actualizacion", ascending=False).head(5)
        
        if not df_res.empty:
            if q: st.info(f"Encontrados: {len(df_res)}")
            
            # Selector
            opts = df_res.apply(lambda x: f"{x['USUARIO']} | {x['TIPO']} | {x['MARCA']} | S/N: {x['NRO DE SERIE']}", axis=1).tolist()
            sel = st.selectbox("Seleccione para editar:", opts)
            
            if sel:
                row = df_res.iloc[opts.index(sel)]
                uid = row["_supabase_id"]
                st.divider()
                
                ce, ca = st.columns([1.5, 1])
                with ce:
                    st.write("#### 📝 Datos del Activo")
                    with st.form("edit_form"):
                        # Listas inteligentes también aquí para editar
                        lst_area_ed = obtener_opciones_input(df, "ÁREA", c.LISTAS_OPCIONES["ÁREA"])
                        lst_est_ed = obtener_opciones_input(df, "ESTADO", c.LISTAS_OPCIONES["ESTADO"])
                        
                        u = st.text_input("Usuario", row["USUARIO"])
                        ce1, ce2 = st.columns(2)
                        with ce1:
                            ser = st.text_input("Serie", row["NRO DE SERIE"])
                            na = st.text_input("Nuevo Activo", row["NUEVO ACTIVO"])
                            ar = campo_con_opcion_otro("Área", lst_area_ed, row["ÁREA"], "e1")
                        with ce2:
                            hst = st.text_input("Hostname", row["EQUIPO"])
                            aa = st.text_input("Activo Antiguo", row["ACTIVO"])
                            est = campo_con_opcion_otro("Estado", lst_est_ed, row["ESTADO"], "e2")
                        
                        obs = st.text_area("Observaciones", row["OBSERVACIONES"])
                        acc = st.text_area("Accesorios", row["ACCESORIOS"])
                        
                        if st.form_submit_button("💾 Actualizar"):
                            upd = {
                                "USUARIO":u, "NRO DE SERIE":ser, "NUEVO ACTIVO":na, "ACTIVO":aa, 
                                "EQUIPO":hst, "ÁREA":ar, "ESTADO":est, "OBSERVACIONES":obs, "ACCESORIOS":acc
                            }
                            # Mezclar con datos originales para no perder info no editada
                            ful = row.to_dict()
                            ful.update(upd)
                            
                            if db.guardar_registro_db(ful, False, uid):
                                st.success("Actualizado"); db.registrar_log("EDITAR", ser); time.sleep(1); st.rerun()
                
                with ca:
                    st.write("#### 📄 Documentos")
                    xls = rep.generar_acta_excel(row.to_dict(), df)
                    if xls: 
                        st.download_button("📥 Descargar Acta", xls, f"Acta_{row['USUARIO']}.xlsx", use_container_width=True)
                    else: 
                        st.warning("⚠️ Falta plantilla 'Acta de Asignación Equipos - V3.xlsx' en GitHub.")
                    
                    st.write("#### 🗑️ Zona de Peligro")
                    if st.button("Eliminar Definitivamente", type="primary", use_container_width=True):
                         if db.eliminar_registro_inventario(uid):
                             st.success("Registro Borrado"); db.registrar_log("BORRAR", row['NRO DE SERIE']); time.sleep(1); st.rerun()
        elif q:
            st.warning("No se encontraron resultados.")

    # TABS ADMIN
    if st.session_state.rol_actual == "Administrador":
        with tabs[5]:
            if st.button("🔄 Refrescar"): st.rerun()
            try: st.dataframe(pd.DataFrame(db.supabase.table('logs_auditoria').select("*").order('fecha', desc=True).limit(100).execute().data), use_container_width=True)
            except: pass
        with tabs[6]:
            c1, c2 = st.columns(2)
            with c1:
                with st.form("nu"):
                    st.write("##### Nuevo Acceso")
                    m = st.text_input("Email/Usuario"); r = st.selectbox("Rol", ["Soporte", "Administrador"])
                    if st.form_submit_button("Crear Usuario"): 
                        ok, msg = db.guardar_nuevo_usuario(m, r)
                        if ok: st.success(msg); time.sleep(1); st.rerun()
                        else: st.error(msg)
                
                st.write("##### Eliminar Acceso")
                # Selección de usuario para eliminar (evitando eliminarse a sí mismo)
                df_u = db.cargar_usuarios()
                users_list = [x for x in df_u["usuario"].tolist() if x != st.session_state.usuario_actual]
                u_del = st.selectbox("Seleccione usuario:", users_list) if users_list else None
                
                if u_del and st.button("Eliminar Usuario", type="primary"):
                    if db.eliminar_usuario(u_del):
                        st.success(f"Eliminado: {u_del}"); time.sleep(1); st.rerun()

            with c2: 
                st.write("##### Usuarios Activos")
                st.dataframe(db.cargar_usuarios(), use_container_width=True, hide_index=True)
