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
        .block-container { padding-top: 1.5rem !important; }
        thead tr th:first-child {display:none}
        tbody tr td:first-child {display:none}
        section[data-testid="stSidebar"] .stRadio label {
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 2px;
        }
    </style>
    """, unsafe_allow_html=True)

# --- AUTH ---
cookies = auth.init_cookies()
if auth.verificar_sesion(cookies):
    
    # --- SIDEBAR ---
    with st.sidebar:
        st.title("🖥️ Inventario TI")
        st.write(f"👤 **{st.session_state.usuario_actual}**")
        st.caption(f"Rol: {st.session_state.rol_actual}")
        st.divider()
        
        opciones_menu = ["📊 Dashboard", "🔎 Consultar", "➕ Nuevo Ingreso", "📥 Carga Masiva", "✏️ Editar / Acta"]
        if st.session_state.rol_actual == "Administrador":
            opciones_menu += ["📜 Logs / Auditoría", "👥 Gestión Usuarios"]
            
        menu = st.radio("Navegación:", opciones_menu, label_visibility="collapsed")
        
        st.divider()
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            cookies["usuario_actual"] = ""
            cookies["rol_actual"] = ""
            cookies.save()
            st.session_state.clear()
            st.rerun()

    # --- CARGA DE DATOS ---
    if menu != "📥 Carga Masiva":
        df = db.obtener_datos()
    else:
        df = pd.DataFrame()

    # --- HELPERS ---
    def es_registro_valido(datos):
        campos_criticos = [
            datos.get("USUARIO", ""), datos.get("NRO DE SERIE", ""),
            datos.get("NUEVO ACTIVO", ""), datos.get("ACTIVO", ""),
            datos.get("EQUIPO", ""), datos.get("MODELO", "")
        ]
        return any(str(v).strip() != "" for v in campos_criticos)

    def obtener_opciones_filtro(dataframe, columna):
        """Obtiene opciones únicas de un dataframe YA FILTRADO"""
        if not dataframe.empty and columna in dataframe.columns:
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
            if valor_actual in opciones: idx = opciones.index(valor_actual)
            else: idx = opciones.index(opcion_otro); modo_manual = True
        seleccion = st.selectbox(label, opciones, index=idx, key=f"sel_{label}_{key_suffix}")
        if seleccion == opcion_otro:
            val_defecto = valor_actual if modo_manual else ""
            return st.text_input(f"Especifique {label}", value=val_defecto, key=f"txt_{label}_{key_suffix}").upper()
        return seleccion

    # 1. DASHBOARD (FILTROS EN CASCADA: AREA -> TIPO -> ESTADO)
    if menu == "📊 Dashboard":
        st.subheader("📊 Tablero de Control")
        
        with st.expander("🔎 Filtros Dinámicos (Cascada)", expanded=True):
            fc1, fc2, fc3 = st.columns(3)
            
            # 1. ÁREA (Filtro Padre)
            # Toma opciones de todo el DF
            opts_area = obtener_opciones_filtro(df, "ÁREA")
            with fc1: 
                sel_area = st.multiselect("1. Área", opts_area)
            
            # Recortamos la data para el siguiente filtro
            df_paso1 = df[df["ÁREA"].isin(sel_area)] if sel_area else df
            
            # 2. TIPO (Depende de Área)
            # Toma opciones solo de las áreas seleccionadas
            opts_tipo = obtener_opciones_filtro(df_paso1, "TIPO")
            with fc2:
                sel_tipo = st.multiselect("2. Tipo", opts_tipo)
                
            # Recortamos la data para el siguiente filtro
            df_paso2 = df_paso1[df_paso1["TIPO"].isin(sel_tipo)] if sel_tipo else df_paso1
            
            # 3. ESTADO (Depende de Área y Tipo)
            opts_estado = obtener_opciones_filtro(df_paso2, "ESTADO")
            with fc3:
                sel_estado = st.multiselect("3. Estado", opts_estado)
                
            # DATAFRAME FINAL VISUAL
            df_d = df_paso2[df_paso2["ESTADO"].isin(sel_estado)] if sel_estado else df_paso2
        
        # --- MÉTRICAS Y GRÁFICOS ---
        def to_float(val):
            try: return float(str(val).replace("S/", "").replace(",", ""))
            except: return 0.0
        
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total Activos", len(df_d))
        k2.metric("Asignados", len(df_d[df_d["USUARIO"].str.len() > 3]))
        k3.metric("Disponibles", len(df_d[df_d["ESTADO"].isin(["DISPONIBLE", "OPERATIVO", "EN REVISIÓN"]) & (df_d["USUARIO"].str.len() <= 3)]))
        k4.metric("Valor Total", f"S/ {df_d['COSTO'].apply(to_float).sum():,.2f}")
        
        st.divider()
        g1, g2 = st.columns(2)
        with g1:
            if not df_d.empty: st.plotly_chart(px.pie(df_d, names="TIPO", title="Distribución por Tipo", hole=0.4), use_container_width=True)
            else: st.info("Sin datos para mostrar gráficos")
        with g2:
            if not df_d.empty: 
                data_bar = df_d["ÁREA"].value_counts().head(10).reset_index()
                st.plotly_chart(px.bar(data_bar, x="count", y="ÁREA", orientation='h', title="Top Áreas"), use_container_width=True)

    # 2. CONSULTAR (FILTROS EN CASCADA: TIPO -> MARCA -> MODELO -> AREA)
    elif menu == "🔎 Consultar":
        st.subheader("🔎 Consulta Avanzada")
        
        with st.expander("🎛️ Filtros Inteligentes (Selecciona en orden)", expanded=True):
            f1, f2, f3, f4 = st.columns(4)
            
            # LÓGICA DE CASCADA (Waterfall)
            
            # PASO 1: TIPO (El más general)
            opts_tipo = obtener_opciones_filtro(df, "TIPO")
            with f1: sel_tipo = st.multiselect("1. Tipo", opts_tipo, key="f_tipo")
            
            # Data filtrada por Tipo
            df_c1 = df[df["TIPO"].isin(sel_tipo)] if sel_tipo else df
            
            # PASO 2: MARCA (Solo marcas de ese Tipo)
            opts_marca = obtener_opciones_filtro(df_c1, "MARCA")
            with f2: sel_marca = st.multiselect("2. Marca", opts_marca, key="f_marca")
            
            # Data filtrada por Tipo + Marca
            df_c2 = df_c1[df_c1["MARCA"].isin(sel_marca)] if sel_marca else df_c1
            
            # PASO 3: MODELO (Solo modelos de esa Marca y Tipo)
            opts_modelo = obtener_opciones_filtro(df_c2, "MODELO")
            with f3: sel_modelo = st.multiselect("3. Modelo", opts_modelo, key="f_modelo")
            
            # Data filtrada por Tipo + Marca + Modelo
            df_c3 = df_c2[df_c2["MODELO"].isin(sel_modelo)] if sel_modelo else df_c2
            
            # PASO 4: ÁREA (Solo áreas donde existan esos equipos)
            opts_area = obtener_opciones_filtro(df_c3, "ÁREA")
            with f4: sel_area = st.multiselect("4. Área", opts_area, key="f_area")
            
            # Data Final Filtrada
            df_final_filtros = df_c3[df_c3["ÁREA"].isin(sel_area)] if sel_area else df_c3

        # Búsqueda Texto
        q_search = st.text_input("🔍 Buscar texto (Usuario, Serie, Activo...)", key="search_tab1").upper().strip()

        # Limpieza
        columnas_a_ocultar = ["_supabase_id", "id"] 
        df_view = df_final_filtros.drop(columns=[c for c in columnas_a_ocultar if c in df.columns], errors="ignore")
        
        # Aplicar búsqueda texto sobre lo ya filtrado
        if q_search:
            mask = (
                df_view["USUARIO"].astype(str).str.contains(q_search, na=False) |
                df_view["NRO DE SERIE"].astype(str).str.contains(q_search, na=False) |
                df_view["ACTIVO"].astype(str).str.contains(q_search, na=False) |
                df_view["NUEVO ACTIVO"].astype(str).str.contains(q_search, na=False)
            )
            df_view = df_view[mask]

        st.caption(f"Registros encontrados: {len(df_view)}")
        st.dataframe(df_view, use_container_width=True, hide_index=True)

    # 3. NUEVO INGRESO
    elif menu == "➕ Nuevo Ingreso":
        st.subheader("➕ Registrar Nuevo Activo")
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
                if not es_registro_valido(n):
                    st.warning("⚠️ Registro vacío.")
                    st.stop()
                
                if n["NRO DE SERIE"] and n["NRO DE SERIE"] in df["NRO DE SERIE"].values:
                    st.error(f"¡Error! La serie {n['NRO DE SERIE']} ya existe.")
                else:
                    if db.guardar_registro_db(n, True):
                        st.success("Guardado exitosamente"); db.registrar_log("CREAR", n["NRO DE SERIE"]); time.sleep(1.5); st.rerun()

    # 4. CARGA MASIVA
    elif menu == "📥 Carga Masiva":
        st.subheader("📥 Carga Masiva")
        c_d, c_u = st.columns(2)
        with c_d:
            st.download_button("📥 Descargar Plantilla", rep.generar_plantilla_carga(), "Plantilla_Inventario.xlsx")
        with c_u:
            upl = st.file_uploader("Subir Excel", type=["xlsx"])
            if upl and st.button("Procesar"):
                try:
                    df_up = pd.read_excel(upl).fillna("").astype(str)
                    bar = st.progress(0)
                    tot, guardados = len(df_up), 0
                    for i, r in df_up.iterrows():
                        d = {k.strip().upper(): v.strip().upper() for k,v in r.to_dict().items()}
                        if es_registro_valido(d):
                            db.guardar_registro_db(d, True); guardados += 1
                        bar.progress((i+1)/tot)
                    if guardados > 0: st.success(f"Cargados: {guardados}"); time.sleep(1.5); st.rerun()
                    else: st.warning("Archivo sin datos válidos.")
                except Exception as e: st.error(f"Error: {str(e)}")

    # 5. EDITAR / ACTA
    elif menu == "✏️ Editar / Acta":
        st.subheader("✏️ Edición")
        q = st.text_input("🔍 Buscar Activo:", placeholder="Ej: Laptop Dell o Juan Perez").upper()
        
        if q:
            mask = df.astype(str).apply(lambda x: x.str.contains(q, na=False)).any(axis=1)
            df_res = df[mask]
        else:
            df_res = df.sort_values("Ultima_Actualizacion", ascending=False).head(5)
        
        if not df_res.empty:
            opts = df_res.apply(lambda x: f"{x['USUARIO']} | {x['TIPO']} | S/N: {x['NRO DE SERIE']}", axis=1).tolist()
            sel = st.selectbox("Seleccione:", opts)
            
            if sel:
                row = df_res.iloc[opts.index(sel)]
                uid = row["_supabase_id"]
                st.divider()
                ce, ca = st.columns([1.5, 1])
                with ce:
                    with st.form("edit"):
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
                            upd = {"USUARIO":u, "NRO DE SERIE":ser, "NUEVO ACTIVO":na, "ACTIVO":aa, "EQUIPO":hst, "ÁREA":ar, "ESTADO":est, "OBSERVACIONES":obs, "ACCESORIOS":acc}
                            if es_registro_valido(upd):
                                ful = row.to_dict(); ful.update(upd)
                                if db.guardar_registro_db(ful, False, uid): st.success("Actualizado"); db.registrar_log("EDITAR", ser); time.sleep(1); st.rerun()
                            else: st.error("No dejar vacío.")
                with ca:
                    xls = rep.generar_acta_excel(row.to_dict(), df)
                    if xls: st.download_button("📥 Acta", xls, f"Acta_{row['USUARIO']}.xlsx", use_container_width=True)
                    st.write("---")
                    if st.button("🗑️ Eliminar", type="primary", use_container_width=True):
                         if db.eliminar_registro_inventario(uid): st.success("Borrado"); db.registrar_log("BORRAR", row['NRO DE SERIE']); time.sleep(1); st.rerun()

    # 6. LOGS
    elif menu == "📜 Logs / Auditoría":
        st.subheader("📜 Auditoría")
        if st.button("🔄 Refrescar"): st.cache_data.clear(); st.rerun()
        df_logs = db.obtener_logs()
        if not df_logs.empty: st.dataframe(df_logs, use_container_width=True, hide_index=True)
        else: st.info("Sin logs.")

    # 7. USUARIOS
    elif menu == "👥 Gestión Usuarios":
        st.subheader("👥 Usuarios")
        c1, c2 = st.columns(2)
        with c1:
            with st.form("nu"):
                m = st.text_input("Email/Usuario"); r = st.selectbox("Rol", ["Soporte", "Administrador"])
                if st.form_submit_button("Crear"): 
                    ok, msg = db.guardar_nuevo_usuario(m, r)
                    if ok: st.success(msg); time.sleep(1); st.rerun()
                    else: st.error(msg)
            df_u = db.cargar_usuarios()
            users_list = [x for x in df_u["usuario"].tolist() if x != st.session_state.usuario_actual]
            u_del = st.selectbox("Eliminar:", users_list) if users_list else None
            if u_del and st.button("Eliminar", type="primary"):
                if db.eliminar_usuario(u_del): st.success("Eliminado"); time.sleep(1); st.rerun()
        with c2: st.dataframe(db.cargar_usuarios(), use_container_width=True, hide_index=True)
