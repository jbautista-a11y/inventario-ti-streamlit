# app.py
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
st.markdown("""<style>.block-container { padding-top: 2rem !important; } .stTabs { margin-top: 0px !important; } hr { margin-top: 10px !important; margin-bottom: 10px !important; }</style>""", unsafe_allow_html=True)

# Auth
cookies = auth.init_cookies()
if auth.verificar_sesion(cookies):
    
    # Sidebar
    with st.sidebar:
        st.title("⚙️ Panel")
        st.write(f"👤 **{st.session_state.usuario_actual}**")
        st.info(f"Rol: {st.session_state.rol_actual}")
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            cookies["usuario_actual"] = ""
            cookies["rol_actual"] = ""
            cookies.save()
            st.session_state.clear()
            st.rerun()

    c_head, c_logo = st.columns([3, 1])
    with c_head: st.title("🖥️ Gestión de Inventario TI")
    
    # Cargar Datos
    df = db.obtener_datos()
    
    # Pestañas
    pestanas = ["📊 Dashboard", "🔎 Consultar", "➕ Nuevo", "📥 Carga Masiva", "✏️ Editar/Acta"]
    if st.session_state.rol_actual == "Administrador":
        pestanas += ["📜 Logs", "👥 Usuarios"]
    
    tabs = st.tabs(pestanas)

    # --- UI HELPERS ---
    def campo_con_opcion_otro(label, lista_base, valor_actual=None, key_suffix=""):
        opciones = list(lista_base)
        opcion_otro = "OTRO (ESPECIFICAR)"
        if opcion_otro not in opciones: opciones.append(opcion_otro)
        idx = 0
        modo_manual = False
        if valor_actual and valor_actual not in ["", "-", "NAN"]:
            if valor_actual in opciones: idx = opciones.index(valor_actual)
            else: idx = opciones.index(opcion_otro); modo_manual = True
        seleccion = st.selectbox(label, opciones, index=idx, key=f"sel_{label}_{key_suffix}")
        if seleccion == opcion_otro:
            val = valor_actual if modo_manual else ""
            return st.text_input(f"Especifique {label}", value=val, key=f"txt_{label}_{key_suffix}").upper()
        return seleccion

    # 1. DASHBOARD
    with tabs[0]:
        st.subheader("Tablero de Control")
        with st.expander("🔎 Filtros Avanzados", expanded=False):
            fc1, fc2, fc3 = st.columns(3)
            opts_area = sorted(list(set(c.LISTAS_OPCIONES["ÁREA"] + df["ÁREA"].unique().tolist())))
            opts_tipo = sorted(list(set(c.LISTAS_OPCIONES["TIPO"] + df["TIPO"].unique().tolist())))
            opts_estado = sorted(list(set(c.LISTAS_OPCIONES["ESTADO"] + df["ESTADO"].unique().tolist())))
            if "" in opts_area: opts_area.remove("")
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
        k2.metric("Asignados", len(df_d[df_d["USUARIO"].str.len() > 2]))
        k3.metric("Stock/Mtto", len(df_d[df_d["ESTADO"].isin(["EN REVISIÓN", "MANTENIMIENTO", "OPERATIVO", "DISPONIBLE"]) & (df_d["USUARIO"].str.len() <= 2)]))
        k4.metric("Valor Total", f"S/ {df_d['COSTO'].apply(to_float).sum():,.2f}")
        
        g1, g2 = st.columns(2)
        with g1:
            if not df_d.empty: st.plotly_chart(px.pie(df_d, names="TIPO", title="Por Tipo"), use_container_width=True)
        with g2:
            if not df_d.empty: st.plotly_chart(px.bar(df_d["ÁREA"].value_counts().reset_index(), x="count", y="ÁREA", orientation='h', title="Por Área"), use_container_width=True)

    # 2. CONSULTAR
    with tabs[1]:
        q = st.text_input("Filtrar tabla:", key="search_tab1").upper()
        df_v = df.drop(columns=["_supabase_id"], errors="ignore")
        if q: df_v = df_v[df_v.astype(str).apply(lambda x: x.str.contains(q, na=False)).any(axis=1)]
        st.dataframe(df_v, use_container_width=True, hide_index=True)

    # 3. NUEVO
    with tabs[2]:
        st.subheader("Registrar")
        with st.form("new"):
            c1, c2, c3 = st.columns(3)
            n = {}
            with c1:
                n["USUARIO"] = st.text_input("Usuario").upper()
                n["ÁREA"] = campo_con_opcion_otro("Área", c.LISTAS_OPCIONES["ÁREA"], key_suffix="n1")
                n["UBICACIÓN"] = st.text_input("Ubicación").upper()
                n["DIRECCIÓN"] = st.text_input("Dirección").upper()
            with c2:
                n["TIPO"] = campo_con_opcion_otro("Tipo", c.LISTAS_OPCIONES["TIPO"], key_suffix="n2")
                n["MARCA"] = campo_con_opcion_otro("Marca", c.LISTAS_OPCIONES["MARCA"], key_suffix="n3")
                n["MODELO"] = st.text_input("Modelo").upper()
                n["EQUIPO"] = st.text_input("Hostname").upper()
            with c3:
                n["NRO DE SERIE"] = st.text_input("Serie").upper()
                n["NUEVO ACTIVO"] = st.text_input("Nuevo Activo").upper()
                n["ACTIVO"] = st.text_input("Activo Antiguo").upper()
                n["ESTADO"] = campo_con_opcion_otro("Estado", c.LISTAS_OPCIONES["ESTADO"], key_suffix="n4")
            
            n["COSTO"] = st.text_input("Costo").upper()
            n["ACCESORIOS"] = st.text_area("Accesorios").upper()
            n["OBSERVACIONES"] = st.text_area("Observaciones").upper()
            
            if st.form_submit_button("💾 Guardar"):
                if n["NRO DE SERIE"] and n["NRO DE SERIE"] in df["NRO DE SERIE"].values:
                    st.error("Serie duplicada")
                else:
                    if db.guardar_registro_db(n, True):
                        st.success("Guardado"); db.registrar_log("CREAR", n["NRO DE SERIE"]); time.sleep(1); st.rerun()

    # 4. CARGA MASIVA
    with tabs[3]:
        c_d, c_u = st.columns(2)
        with c_d:
            st.download_button("📥 Plantilla", rep.generar_plantilla_carga(), "Plantilla.xlsx")
        with c_u:
            upl = st.file_uploader("Subir Excel", type=["xlsx"])
            if upl and st.button("Procesar"):
                try:
                    df_up = pd.read_excel(upl).fillna("").astype(str)
                    bar = st.progress(0)
                    for i, r in df_up.iterrows():
                        d = {k.strip().upper(): v.strip().upper() for k,v in r.to_dict().items()}
                        db.guardar_registro_db(d, True)
                        bar.progress((i+1)/len(df_up))
                    st.success("Carga OK"); time.sleep(1); st.rerun()
                except Exception as e: st.error(str(e))

    # 5. EDITAR / ACTA
    with tabs[4]:
        q = st.text_input("🔍 Buscar Global:", help="Busca en todos los campos").upper()
        df_res = df if not q else df[pd.Series(False, df.index) | df.apply(lambda r: r.astype(str).str.contains(q, na=False).any(), axis=1)]
        if not q: df_res = df_res.sort_values("Ultima_Actualizacion", ascending=False).head(5)
        
        if not df_res.empty:
            opts = df_res.apply(lambda x: f"{x['USUARIO']} | {x['TIPO']} | S/N: {x['NRO DE SERIE']}", axis=1).tolist()
            sel = st.selectbox("Seleccione:", opts)
            if sel:
                row = df_res.iloc[opts.index(sel)]
                uid = row["_supabase_id"]
                st.divider()
                ce, ca = st.columns([1.5, 1])
                with ce:
                    with st.form("ed"):
                        u = st.text_input("Usuario", row["USUARIO"])
                        ce1, ce2 = st.columns(2)
                        with ce1:
                            ser = st.text_input("Serie", row["NRO DE SERIE"])
                            na = st.text_input("Nuevo Activo", row["NUEVO ACTIVO"])
                            ar = campo_con_opcion_otro("Área", c.LISTAS_OPCIONES["ÁREA"], row["ÁREA"], "e1")
                        with ce2:
                            hst = st.text_input("Hostname", row["EQUIPO"])
                            aa = st.text_input("Activo Antiguo", row["ACTIVO"])
                            est = campo_con_opcion_otro("Estado", c.LISTAS_OPCIONES["ESTADO"], row["ESTADO"], "e2")
                        obs = st.text_area("Observaciones", row["OBSERVACIONES"])
                        acc = st.text_area("Accesorios", row["ACCESORIOS"])
                        if st.form_submit_button("Actualizar"):
                            upd = {"USUARIO":u, "NRO DE SERIE":ser, "NUEVO ACTIVO":na, "ACTIVO":aa, "EQUIPO":hst, "ÁREA":ar, "ESTADO":est, "OBSERVACIONES":obs, "ACCESORIOS":acc}
                            ful = row.to_dict(); ful.update(upd)
                            if db.guardar_registro_db(ful, False, uid):
                                st.success("OK"); db.registrar_log("EDITAR", ser); time.sleep(1); st.rerun()
                with ca:
                    xls = rep.generar_acta_excel(row.to_dict(), df)
                    if xls: st.download_button("📥 Acta Excel", xls, f"Acta_{row['USUARIO']}.xlsx", use_container_width=True)
                    else: st.warning("Falta plantilla en repo")
                    st.divider()
                    if st.button("🗑️ Eliminar", type="primary", use_container_width=True):
                         if db.eliminar_registro_inventario(uid):
                             st.success("Borrado"); db.registrar_log("BORRAR", row['NRO DE SERIE']); time.sleep(1); st.rerun()

    # ADMIN
    if st.session_state.rol_actual == "Administrador":
        with tabs[5]:
            try: st.dataframe(pd.DataFrame(db.supabase.table('logs_auditoria').select("*").order('fecha', desc=True).limit(100).execute().data))
            except: pass
        with tabs[6]:
            c1, c2 = st.columns(2)
            with c1:
                with st.form("nu"):
                    m = st.text_input("Email"); r = st.selectbox("Rol", ["Soporte", "Administrador"])
                    if st.form_submit_button("Crear"): 
                        ok, msg = db.guardar_nuevo_usuario(m, r)
                        if ok: st.success(msg); time.sleep(1); st.rerun()
                        else: st.error(msg)
                if st.button("Borrar Usuario"):
                    st.info("Use selectbox en app completa")
            with c2: st.dataframe(db.cargar_usuarios())
