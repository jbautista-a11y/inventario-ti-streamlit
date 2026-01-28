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
        /* Ocultar índices numéricos automáticos de tablas */
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
    
    # --- CARGA DE DATOS ---
    df = db.obtener_datos()
    
    # --- PESTAÑAS ---
    pestanas = ["📊 Dashboard", "🔎 Consultar", "➕ Nuevo", "📥 Carga Masiva", "✏️ Editar/Acta"]
    if st.session_state.rol_actual == "Administrador":
        pestanas += ["📜 Logs", "👥 Usuarios"]
    
    tabs = st.tabs(pestanas)

    # --- UI HELPERS & VALIDACIONES ---
    
    def es_registro_valido(datos):
        """
        Valida que el registro tenga al menos UN campo crítico lleno.
        Ignoramos campos que suelen tener valores por defecto como 'ESTADO' o 'TIPO'
        si es lo único que hay.
        """
        campos_criticos = [
            datos.get("USUARIO", ""),
            datos.get("NRO DE SERIE", ""),
            datos.get("NUEVO ACTIVO", ""),
            datos.get("ACTIVO", ""),
            datos.get("EQUIPO", ""),
            datos.get("MODELO", ""),
            datos.get("OBSERVACIONES", ""),
            datos.get("ACCESORIOS", "")
        ]
        # Devuelve True si AL MENOS UNO tiene texto real (no espacios vacíos)
        return any(str(v).strip() != "" for v in campos_criticos)

    def obtener_opciones_filtro(dataframe, columna):
        if columna in dataframe.columns:
            valores = dataframe[columna].unique().tolist()
            valores = [x for x in valores if x and x != "" and x != "-" and x != "None"]
            return sorted(valores)
        return []

    def obtener_opciones_input(dataframe, columna, lista_base):
        existentes = obtener_opciones_filtro(dataframe, columna)
        combinados = sorted(list(set(lista_base + existentes)))
        return combinados

    def campo_con_opcion_otro(label, lista_opciones, valor_actual=None, key_suffix=""):
        opciones = list(lista_opciones)
        opcion_otro = "OTRO (ESPECIFICAR)"
        if opcion_otro not in opciones: opciones.append(opcion_otro)
        
        idx = 0
        modo_manual = False
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

    # 1. DASHBOARD
    with tabs[0]:
        st.subheader("Tablero de Control")
        with st.expander("🔎 Filtros", expanded=True):
            fc1, fc2, fc3 = st.columns(3)
            opts_area = obtener_opciones_filtro(df, "ÁREA")
            opts_tipo = obtener_opciones_filtro(df, "TIPO")
            opts_estado = obtener_opciones_filtro(df, "ESTADO")
            
            sel_area = fc1.multiselect("Área", opts_area)
            sel_tipo = fc2.multiselect("Tipo", opts_tipo)
            sel_estado = fc3.multiselect("Estado", opts_estado)
        
        df_d = df.copy()
        if sel_area: df_d = df_d[df_d["ÁREA"].isin(sel_area)]
        if sel_tipo: df_d = df_d[df_d["TIPO"].isin(sel_tipo)]
        if sel_estado: df_d = df_d[df_d["ESTADO"].isin(sel_estado)]
        
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
            if not df_d.empty: st.plotly_chart(px.pie(df_d, names="TIPO", title="Distribución por Tipo", hole=0.4), use_container_width=True)
            else: st.info("Sin datos")
        with g2:
            if not df_d.empty: 
                data_bar = df_d["ÁREA"].value_counts().head(10).reset_index()
                st.plotly_chart(px.bar(data_bar, x="count", y="ÁREA", orientation='h', title="Top Áreas"), use_container_width=True)
            else: st.info("Sin datos")

    # 2. CONSULTAR (CORREGIDO: COLUMNAS DUPLICADAS ELIMINADAS)
    with tabs[1]:
        st.subheader("🔎 Consulta Avanzada")
        
        # Filtros
        with st.expander("🎛️ Filtros", expanded=True):
            f1, f2, f3, f4 = st.columns(4)
            opts_tipo = obtener_opciones_filtro(df, "TIPO")
            opts_marca = obtener_opciones_filtro(df, "MARCA")
            opts_modelo = obtener_opciones_filtro(df, "MODELO")
            opts_area = obtener_opciones_filtro(df, "ÁREA")
            
            with f1: sel_tipo = st.multiselect("Tipo", opts_tipo, key="f_tipo")
            with f2: sel_marca = st.multiselect("Marca", opts_marca, key="f_marca")
            with f3: sel_modelo = st.multiselect("Modelo", opts_modelo, key="f_modelo")
            with f4: sel_area = st.multiselect("Área", opts_area, key="f_area")

        q_search = st.text_input("🔍 Buscar texto (Usuario, Serie, Activo...)", key="search_tab1").upper().strip()

        # --- AQUÍ ESTÁ EL CAMBIO PARA QUITAR COLUMNAS REPETIDAS ---
        # Borramos _supabase_id (interno) y 'id' (si viene de DB directa)
        columnas_a_ocultar = ["_supabase_id", "id"] 
        df_c = df.drop(columns=[c for c in columnas_a_ocultar if c in df.columns], errors="ignore")
        
        # Filtros
        if sel_tipo: df_c = df_c[df_c["TIPO"].isin(sel_tipo)]
        if sel_marca: df_c = df_c[df_c["MARCA"].isin(sel_marca)]
        if sel_modelo: df_c = df_c[df_c["MODELO"].isin(sel_modelo)]
        if sel_area: df_c = df_c[df_c["ÁREA"].isin(sel_area)]
        
        if q_search:
            mask = (
                df_c["USUARIO"].astype(str).str.contains(q_search, na=False) |
                df_c["NRO DE SERIE"].astype(str).str.contains(q_search, na=False) |
                df_c["ACTIVO"].astype(str).str.contains(q_search, na=False) |
                df_c["NUEVO ACTIVO"].astype(str).str.contains(q_search, na=False)
            )
            df_c = df_c[mask]

        st.caption(f"Registros encontrados: {len(df_c)}")
        st.dataframe(df_c, use_container_width=True, hide_index=True)

    # 3. NUEVO (CORREGIDO: VALIDACIÓN DE CAMPOS VACÍOS)
    with tabs[2]:
        st.subheader("Nuevo Ingreso")
        with st.form("new_entry"):
            c1, c2, c3 = st.columns(3)
            n = {}
            
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
                n["EQUIPO"] = st.text_input("Hostname").upper()
            with c3:
                n["NRO DE SERIE"] = st.text_input("Nro Serie").upper()
                n["NUEVO ACTIVO"] = st.text_input("Cód. Nuevo Activo").upper()
                n["ACTIVO"] = st.text_input("Cód. Antiguo").upper()
                n["ESTADO"] = campo_con_opcion_otro("Estado", lst_estado, key_suffix="n4")
            
            n["COSTO"] = st.text_input("Costo").upper()
            n["ACCESORIOS"] = st.text_area("Accesorios").upper()
            n["OBSERVACIONES"] = st.text_area("Observaciones").upper()
            
            if st.form_submit_button("💾 Guardar Registro"):
                # VALIDACIÓN 1: ¿Está vacío?
                if not es_registro_valido(n):
                    st.warning("⚠️ El registro está prácticamente vacío. Por favor, llene al menos un campo principal (Usuario, Serie, Equipo, etc).")
                    st.stop()
                
                # VALIDACIÓN 2: Duplicados
                if n["NRO DE SERIE"] and n["NRO DE SERIE"] in df["NRO DE SERIE"].values:
                    st.error(f"¡Error! La serie {n['NRO DE SERIE']} ya existe.")
                else:
                    if db.guardar_registro_db(n, True):
                        st.success("Guardado exitosamente"); 
                        db.registrar_log("CREAR", n["NRO DE SERIE"]); 
                        time.sleep(1.5); st.rerun()

    # 4. CARGA MASIVA (CORREGIDO: IGNORAR FILAS VACÍAS)
    with tabs[3]:
        st.subheader("Carga Masiva")
        c_d, c_u = st.columns(2)
        with c_d:
            st.download_button("📥 Plantilla", rep.generar_plantilla_carga(), "Plantilla_Inventario.xlsx")
        with c_u:
            upl = st.file_uploader("Subir Excel", type=["xlsx"])
            if upl and st.button("Procesar Carga"):
                try:
                    df_up = pd.read_excel(upl).fillna("").astype(str)
                    bar = st.progress(0)
                    total = len(df_up)
                    registros_guardados = 0
                    
                    for i, r in df_up.iterrows():
                        d = {k.strip().upper(): v.strip().upper() for k,v in r.to_dict().items()}
                        
                        # VALIDACIÓN: Solo guardamos si la fila tiene datos reales
                        if es_registro_valido(d):
                            db.guardar_registro_db(d, True)
                            registros_guardados += 1
                        
                        bar.progress((i+1)/total)
                    
                    if registros_guardados > 0:
                        st.success(f"Carga completada: {registros_guardados} registros válidos guardados.")
                        time.sleep(1.5); st.rerun()
                    else:
                        st.warning("No se encontraron registros válidos en el archivo (quizás estaba vacío).")

                except Exception as e: st.error(f"Error: {str(e)}")

    # 5. EDITAR / ACTA
    with tabs[4]:
        st.subheader("Gestión de Activos")
        q = st.text_input("🔍 Buscar Activo:", placeholder="Ej: Laptop Dell o Juan Perez").upper()
        
        if q:
            # Busqueda global en todas las columnas
            mask = df.astype(str).apply(lambda x: x.str.contains(q, na=False)).any(axis=1)
            df_res = df[mask]
        else:
            df_res = df.sort_values("Ultima_Actualizacion", ascending=False).head(5)
        
        if not df_res.empty:
            if q: st.info(f"Encontrados: {len(df_res)}")
            
            opts = df_res.apply(lambda x: f"{x['USUARIO']} | {x['TIPO']} | S/N: {x['NRO DE SERIE']}", axis=1).tolist()
            sel = st.selectbox("Seleccione para editar:", opts)
            
            if sel:
                row = df_res.iloc[opts.index(sel)]
                uid = row["_supabase_id"]
                st.divider()
                
                ce, ca = st.columns([1.5, 1])
                with ce:
                    with st.form("edit_form"):
                        # Listas inteligentes para edición
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
                            # VALIDACION EN EDICION TAMBIÉN
                            if not es_registro_valido(upd):
                                st.error("No puede dejar el registro vacío.")
                            else:
                                ful = row.to_dict()
                                ful.update(upd)
                                if db.guardar_registro_db(ful, False, uid):
                                    st.success("Actualizado"); db.registrar_log("EDITAR", ser); time.sleep(1); st.rerun()
                
                with ca:
                    st.write("#### Documentos")
                    xls = rep.generar_acta_excel(row.to_dict(), df)
                    if xls: 
                        st.download_button("📥 Acta Excel", xls, f"Acta_{row['USUARIO']}.xlsx", use_container_width=True)
                    
                    st.divider()
                    if st.button("🗑️ Eliminar Registro", type="primary", use_container_width=True):
                         if db.eliminar_registro_inventario(uid):
                             st.success("Borrado"); db.registrar_log("BORRAR", row['NRO DE SERIE']); time.sleep(1); st.rerun()
        elif q:
            st.warning("No hay resultados.")

    # TABS ADMIN
    if st.session_state.rol_actual == "Administrador":
        with tabs[5]:
            # Botón refrescar con limpieza de caché
            if st.button("🔄 Refrescar Datos", use_container_width=True):
                st.cache_data.clear()
                st.rerun()
                
            df_logs = db.obtener_logs() # Función directa sin caché
            if not df_logs.empty:
                st.dataframe(df_logs, use_container_width=True, hide_index=True)
            else: st.info("Sin logs.")

        with tabs[6]:
            c1, c2 = st.columns(2)
            with c1:
                with st.form("nu"):
                    st.write("##### Nuevo Usuario")
                    m = st.text_input("Email/Usuario"); r = st.selectbox("Rol", ["Soporte", "Administrador"])
                    if st.form_submit_button("Crear"): 
                        ok, msg = db.guardar_nuevo_usuario(m, r)
                        if ok: st.success(msg); time.sleep(1); st.rerun()
                        else: st.error(msg)
                
                st.write("##### Eliminar Usuario")
                df_u = db.cargar_usuarios()
                users_list = [x for x in df_u["usuario"].tolist() if x != st.session_state.usuario_actual]
                u_del = st.selectbox("Seleccione:", users_list) if users_list else None
                if u_del and st.button("Eliminar", type="primary"):
                    if db.eliminar_usuario(u_del):
                        st.success(f"Eliminado: {u_del}"); time.sleep(1); st.rerun()

            with c2: 
                st.dataframe(db.cargar_usuarios(), use_container_width=True, hide_index=True)
