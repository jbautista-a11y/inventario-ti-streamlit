import streamlit as st
import pandas as pd
from supabase import create_client, Client
import msal
import time
import plotly.express as px
from io import BytesIO
from datetime import datetime
from streamlit_cookies_manager import EncryptedCookieManager
import openpyxl
from openpyxl.worksheet.datavalidation import DataValidation

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Gestión de Inventario TI", layout="wide", page_icon="🖥️")

# --- CONFIGURACIÓN SUPABASE ---
@st.cache_resource
def init_supabase():
    """Inicializa conexión a Supabase usando secrets"""
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase: Client = init_supabase()

# --- CONFIGURACIÓN MICROSOFT (AZURE AD) ---
# Asegúrate de que estos nombres coincidan con tus secrets en Streamlit Cloud
CLIENT_ID = st.secrets["CLIENT_ID"]
TENANT_ID = st.secrets["TENANT_ID"]
CLIENT_SECRET = st.secrets["CLIENT_SECRET"]
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPE = ["User.Read"]
REDIRECT_URI = st.secrets["REDIRECT_URI"]

# --- GESTOR DE COOKIES ---
# Usa una clave secreta fuerte en tus secrets o usa el valor por defecto
cookies = EncryptedCookieManager(password=st.secrets.get("COOKIE_PASSWORD", "esandata_secret_key_2024"))

if not cookies.ready():
    with st.spinner("Cargando sistema de autenticación..."):
        st.stop()

# --- CONSTANTES Y LISTAS MAESTRAS ---
PLANTILLA_EXCEL = 'Acta de Asignación Equipos - V3.xlsx' # Debe estar en tu repo de GitHub

# Definimos las columnas EXACTAS que usa tu versión local para mantener compatibilidad
COLUMNAS_EXCEL = [
    "N°", "USUARIO", "EQUIPO", "ÁREA", "DIRECCIÓN", "UBICACIÓN", 
    "NUEVO ACTIVO", "ACTIVO", "TIPO", "NRO DE SERIE", "MARCA", "MODELO", 
    "AÑO DE ADQUISICIÓN", "PROCESADOR", "MEMORIA RAM", "DISCO DURO", 
    "ESTADO", "COMPONENTE", "COSTO", "ACCESORIOS", "OBSERVACIONES", 
    "ACTA DE  ASIGNACIÓN", "ADM- LOCAL", "ORIGEN_HOJA", "Ultima_Actualizacion", "MODIFICADO_POR"
]

# Mapeo: Nombre Columna Excel -> Nombre Columna Supabase (minusculas, sin espacios)
# IMPORTANTE: Tu tabla 'inventario' en Supabase debe tener estas columnas.
MAPEO_DB = {
    "N°": "numero",
    "USUARIO": "usuario",
    "EQUIPO": "equipo",
    "ÁREA": "area",
    "DIRECCIÓN": "direccion",
    "UBICACIÓN": "ubicacion",
    "NUEVO ACTIVO": "nuevo_activo",
    "ACTIVO": "activo",
    "TIPO": "tipo",
    "NRO DE SERIE": "nro_serie",
    "MARCA": "marca",
    "MODELO": "modelo",
    "AÑO DE ADQUISICIÓN": "anio_adquisicion",
    "PROCESADOR": "procesador",
    "MEMORIA RAM": "memoria_ram",
    "DISCO DURO": "disco_duro",
    "ESTADO": "estado",
    "COMPONENTE": "componente",
    "COSTO": "costo",
    "ACCESORIOS": "accesorios",
    "OBSERVACIONES": "observaciones",
    "ACTA DE  ASIGNACIÓN": "acta_asignacion",
    "ADM- LOCAL": "adm_local",
    "ORIGEN_HOJA": "origen_hoja",
    "Ultima_Actualizacion": "ultima_actualizacion",
    "MODIFICADO_POR": "modificado_por"
}

# Inverso para cuando traemos de DB a Pandas
MAPEO_DB_INVERSO = {v: k for k, v in MAPEO_DB.items()}

LISTAS_OPCIONES = {
    "TIPO": ["LAPTOP", "DESKTOP", "MONITOR", "ALL IN ONE", "TABLET", "IMPRESORA", "PERIFERICO"],
    "ESTADO": ["OPERATIVO", "EN REVISIÓN", "MANTENIMIENTO", "BAJA", "HURTO/ROBO", "ASIGNADO"],
    "MARCA": ["DELL", "HP", "LENOVO", "APPLE", "SAMSUNG", "LG", "EPSON", "LOGITECH"],
    "ÁREA": ["SOPORTE TI", "ADMINISTRACIÓN", "RECURSOS HUMANOS", "CONTABILIDAD", "COMERCIAL", "MARKETING", "LOGÍSTICA", "DIRECCIÓN", "ACADÉMICO"]
}

# --- FUNCIONES DE BASE DE DATOS (REEMPLAZAN A EXCEL/TXT) ---

def registrar_log(accion, detalle):
    """Registra en la tabla logs_auditoria de Supabase"""
    try:
        usuario = st.session_state.get("usuario_actual", "Desconocido")
        # Supabase maneja 'created_at' automático, pero mandamos fecha local si quieres consistencia visual
        log_entry = {
            "usuario": usuario,
            "accion": accion,
            "detalle": detalle,
            "fecha": datetime.now().isoformat()
        }
        supabase.table('logs_auditoria').insert(log_entry).execute()
    except Exception as e:
        print(f"Error log (no crítico): {e}")

@st.cache_data
def cargar_usuarios():
    """Carga usuarios desde Supabase y devuelve DataFrame compatible con local"""
    try:
        response = supabase.table('usuarios').select("*").execute()
        df = pd.DataFrame(response.data)
        if df.empty:
             return pd.DataFrame(columns=["usuario", "clave", "rol"])
        return df
    except Exception as e:
        st.error(f"Error conectando a usuarios: {e}")
        return pd.DataFrame([{"usuario": "admin", "clave": "1234", "rol": "Administrador"}])

def guardar_nuevo_usuario(u, r):
    try:
        df_u = cargar_usuarios()
        if not df_u.empty and u.lower() in df_u["usuario"].str.lower().values:
            return False, "Usuario ya existe"
        
        nuevo = {"usuario": u.lower(), "clave": "MS_365_ACCESS", "rol": r}
        supabase.table('usuarios').insert(nuevo).execute()
        st.cache_data.clear()
        return True, f"Acceso autorizado para {u}"
    except Exception as e:
        return False, f"Error DB: {e}"

def actualizar_mi_clave(u, nueva_c):
    try:
        # Validar lógica Microsoft
        df_u = cargar_usuarios()
        row = df_u[df_u["usuario"] == u]
        if not row.empty and row.iloc[0]["clave"] == "MS_365_ACCESS":
            return False, "Usuarios Microsoft no pueden cambiar clave aquí."
            
        supabase.table('usuarios').update({"clave": nueva_c}).eq('usuario', u).execute()
        registrar_log("SEGURIDAD", "Cambio de clave local")
        st.cache_data.clear()
        return True, "Clave actualizada"
    except Exception as e:
        return False, f"Error: {e}"

# --- NÚCLEO DE DATOS (EL CEREBRO DE LA APP) ---

@st.cache_data
def obtener_datos():
    """
    Trae todo el inventario de Supabase y lo convierte al formato EXACTO
    del Excel local para que los filtros y dashboards funcionen igual.
    """
    try:
        # Traemos todo. Si es mucha data, Supabase pagina (max 1000 por defecto), 
        # pero para empezar esto funciona.
        response = supabase.table('inventario').select("*").order('id', desc=False).execute()
        data = response.data
        
        if not data:
            return pd.DataFrame(columns=COLUMNAS_EXCEL)
            
        df = pd.DataFrame(data)
        
        # Renombramos columnas de DB (minusculas) a Excel (Mayusculas)
        df = df.rename(columns=MAPEO_DB_INVERSO)
        
        # Aseguramos que todas las columnas existan, llenando vacíos con "-"
        for col in COLUMNAS_EXCEL:
            if col not in df.columns:
                df[col] = "-"
        
        # Convertir NaN a "-" para evitar errores en filtros
        df = df.fillna("-")
        
        # Asegurar tipos string para búsquedas
        df = df.astype(str)
        
        # Preservar el ID de Supabase para poder editar/borrar luego
        # (Aunque no esté en COLUMNAS_EXCEL visualmente, lo mantenemos en el DF)
        if "id" in pd.DataFrame(data).columns:
             df["_supabase_id"] = pd.DataFrame(data)["id"]
        
        return df
        
    except Exception as e:
        st.error(f"Error cargando inventario: {e}")
        return pd.DataFrame(columns=COLUMNAS_EXCEL)

def agregar_registro_bd(nuevo_dato_dict):
    """Transforma el diccionario visual a formato DB e inserta"""
    try:
        registro_db = {}
        for col_excel, valor in nuevo_dato_dict.items():
            if col_excel in MAPEO_DB:
                registro_db[MAPEO_DB[col_excel]] = valor
        
        # Metadatos automáticos
        registro_db["ultima_actualizacion"] = datetime.now().isoformat()
        registro_db["modificado_por"] = st.session_state.get("usuario_actual", "Sistema")
        
        supabase.table('inventario').insert(registro_db).execute()
        st.cache_data.clear() # ¡CRUCIAL PARA VER EL CAMBIO AL INSTANTE!
        return True
    except Exception as e:
        st.error(f"Error guardando en Supabase: {e}")
        return False

def editar_registro_bd(id_supabase, diccionario_cambios):
    """Actualiza un registro usando su ID de Supabase"""
    try:
        cambios_db = {}
        for col_excel, valor in diccionario_cambios.items():
            if col_excel in MAPEO_DB:
                cambios_db[MAPEO_DB[col_excel]] = valor
        
        cambios_db["ultima_actualizacion"] = datetime.now().isoformat()
        cambios_db["modificado_por"] = st.session_state.get("usuario_actual", "Sistema")

        supabase.table('inventario').update(cambios_db).eq('id', id_supabase).execute()
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error actualizando: {e}")
        return False

def eliminar_registro_bd(id_supabase):
    try:
        supabase.table('inventario').delete().eq('id', id_supabase).execute()
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error eliminando: {e}")
        return False

# --- FUNCIONES UI & REPORTES (IDÉNTICAS AL LOCAL) ---

def campo_con_opcion_otro(label, lista_base, valor_actual=None, key_suffix=""):
    opciones = list(lista_base)
    opcion_otro = "OTRO (ESPECIFICAR)"
    if opcion_otro not in opciones: opciones.append(opcion_otro)
    
    idx = 0
    modo_manual = False
    
    # Lógica para preseleccionar valor
    if valor_actual and valor_actual != "-":
        if valor_actual in opciones:
            idx = opciones.index(valor_actual)
        else:
            idx = opciones.index(opcion_otro)
            modo_manual = True
            
    seleccion = st.selectbox(label, opciones, index=idx, key=f"sel_{label}_{key_suffix}")
    valor_final = seleccion
    
    if seleccion == opcion_otro:
        val_defecto = valor_actual if modo_manual else ""
        valor_final = st.text_input(f"Especifique {label}:", value=val_defecto, key=f"txt_{label}_{key_suffix}").upper()
        
    return valor_final

def generar_acta_excel(datos, df_completo):
    """Genera el Excel usando openpyxl (Igual que local)"""
    try:
        wb = openpyxl.load_workbook(PLANTILLA_EXCEL)
        ws = wb.active
        
        # Mapeo idéntico al local
        ws['P7'] = str(datos.get('USUARIO', '')).upper()
        ws['G12'] = datetime.now().strftime('%d/%m/%Y')
        ws['T12'], ws['AG12'] = datos.get('UBICACIÓN','-'), datos.get('DIRECCIÓN','-')
        ws['G14'], ws['T14'] = datos.get('ÁREA','-'), datos.get('ACTA DE  ASIGNACIÓN','-')
        
        # Lógica de componentes asociados
        e_u = df_completo[df_completo['USUARIO'] == datos.get('USUARIO')]
        mons = e_u[e_u['TIPO'].str.contains("MONITOR", case=False, na=False)]['NRO DE SERIE'].tolist()
        ws['Q18'] = " / ".join(mons) if mons else datos.get('COMPONENTE', '-')
        
        # Checkboxes
        t_p = str(datos.get('TIPO', '')).upper()
        ws['J20'] = "X" if any(x in t_p for x in ["AIO", "ALL IN ONE"]) else ""
        ws['J21'] = "X" if any(x in t_p for x in ["DESKTOP", "CPU"]) else ""
        ws['J22'] = "X" if "LAPTOP" in t_p else ""
        
        ws['R20'], ws['R21'], ws['R22'] = datos.get('NUEVO ACTIVO','-'), datos.get('NRO DE SERIE','-'), datos.get('EQUIPO','-')

        # Accesorios
        acc = str(datos.get('ACCESORIOS', '')).lower() 
        if "LAPTOP" in t_p: ws['O24'] = "X"
        else: ws['O24'] = "X" if "cargador" in acc else ""
        
        ws['R24'] = "X" if "cadena" in acc or "candado" in acc else ""
        ws['U24'] = "X" if "mouse" in acc or "ratón" in acc else ""
        ws['X24'] = "X" if "mochila" in acc or "maletín" in acc else ""
        ws['Z24'] = "X" if "teclado" in acc else ""

        out = BytesIO()
        wb.save(out)
        return out.getvalue()
    except Exception as e:
        st.error(f"Error generando acta (verificar plantilla): {e}")
        return None

# --- AUTH HÍBRIDA (PARIDAD TOTAL) ---

def verificar_sesion():
    if "autenticado" not in st.session_state:
        st.session_state.autenticado = False

    # Recuperar de cookies
    c_user = cookies.get("usuario_actual")
    c_rol = cookies.get("rol_actual")
    
    if c_user and c_rol and not st.session_state.autenticado:
        st.session_state.autenticado = True
        st.session_state.usuario_actual = c_user
        st.session_state.rol_actual = c_rol

    # Callback de Microsoft
    if "code" in st.query_params:
        try:
            ms_app = msal.ConfidentialClientApplication(CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET)
            res = ms_app.acquire_token_by_authorization_code(st.query_params["code"], scopes=SCOPE, redirect_uri=REDIRECT_URI)
            if "error" not in res:
                email = res.get("id_token_claims").get("preferred_username").lower()
                db = cargar_usuarios()
                user_match = db[db["usuario"].str.lower() == email]
                
                if not user_match.empty:
                    st.session_state.autenticado = True
                    st.session_state.usuario_actual = email
                    st.session_state.rol_actual = user_match.iloc[0]["rol"]
                    
                    cookies["usuario_actual"] = email
                    cookies["rol_actual"] = st.session_state.rol_actual
                    cookies.save()
                    
                    registrar_log("LOGIN_MS", "Inicio con Microsoft")
                    st.query_params.clear()
                    st.rerun()
                else:
                    st.error(f"El usuario {email} no tiene permisos configurados en la Base de Datos.")
        except Exception as e:
            st.error(f"Error Auth MS: {e}")

    # Pantalla Login
    if not st.session_state.autenticado:
        st.markdown("<h1 style='text-align: center;'>☁️ Gestión de Inventario TI (Nube)</h1>", unsafe_allow_html=True)
        
        _, col_login, _ = st.columns([1, 1.2, 1])
        with col_login:
            # Botón Microsoft
            ms_app = msal.ConfidentialClientApplication(CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET)
            url_auth = ms_app.get_authorization_request_url(SCOPE, redirect_uri=REDIRECT_URI)
            st.link_button("🟦 Iniciar Sesión con Microsoft 365", url_auth, use_container_width=True)
            
            st.divider()
            
            # Login Local
            with st.expander("🔐 Acceso Local"):
                with st.form("login_local"):
                    u = st.text_input("Usuario")
                    p = st.text_input("Clave", type="password")
                    if st.form_submit_button("Entrar", use_container_width=True):
                        db = cargar_usuarios()
                        row = db[(db["usuario"].str.lower() == u.lower()) & (db["clave"] == p)]
                        if not row.empty:
                            st.session_state.autenticado = True
                            st.session_state.usuario_actual = row.iloc[0]["usuario"]
                            st.session_state.rol_actual = row.iloc[0]["rol"]
                            cookies["usuario_actual"] = st.session_state.usuario_actual
                            cookies["rol_actual"] = st.session_state.rol_actual
                            cookies.save()
                            registrar_log("LOGIN_LOCAL", "Inicio de sesión manual")
                            st.rerun()
                        else:
                            st.error("Credenciales incorrectas")
        st.stop()
    return True

# --- MAIN APP ---

if verificar_sesion():
    # SIDEBAR
    with st.sidebar:
        st.title("⚙️ Opciones")
        st.write(f"Usuario: **{st.session_state.usuario_actual}**")
        st.write(f"Rol: `{st.session_state.rol_actual}`")
        
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            registrar_log("LOGOUT", "Sesión cerrada")
            for k in ["usuario_actual", "rol_actual"]: 
                if k in cookies: del cookies[k]
            cookies.save()
            st.session_state.clear()
            st.rerun()

    # CARGA DE DATOS CENTRALIZADA
    df = obtener_datos()
    
    # INTERFAZ PRINCIPAL
    titulos = ["📊 Dashboard", "🔎 Consultar", "➕ Nuevo", "📥 Carga Masiva", "✏️ Editar/Acta"]
    if st.session_state.rol_actual == "Administrador":
        titulos += ["📜 Logs", "👥 Usuarios"]
        
    tabs = st.tabs(titulos)
    
    # 1. DASHBOARD
    with tabs[0]:
        st.subheader("📊 Tablero de Control")
        # Filtros iguales al local
        with st.expander("🔎 Filtros"):
            c1, c2, c3 = st.columns(3)
            with c1: f_area = st.multiselect("Área", df["ÁREA"].unique())
            with c2: f_tipo = st.multiselect("Tipo", df["TIPO"].unique())
            with c3: f_estado = st.multiselect("Estado", df["ESTADO"].unique())
            
        df_view = df.copy()
        if f_area: df_view = df_view[df_view["ÁREA"].isin(f_area)]
        if f_tipo: df_view = df_view[df_view["TIPO"].isin(f_tipo)]
        if f_estado: df_view = df_view[df_view["ESTADO"].isin(f_estado)]
        
        # Métricas
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Activos", len(df_view))
        m2.metric("Laptops", len(df_view[df_view["TIPO"] == "LAPTOP"]))
        m3.metric("En Mantenimiento", len(df_view[df_view["ESTADO"] == "MANTENIMIENTO"]))
        m4.metric("Valor Total (Est)", f"S/ {pd.to_numeric(df_view['COSTO'], errors='coerce').sum():,.2f}")
        
        # Gráficos
        g1, g2 = st.columns(2)
        with g1:
            st.plotly_chart(px.pie(df_view, names="ESTADO", title="Estado de Equipos"), use_container_width=True)
        with g2:
            st.plotly_chart(px.bar(df_view, x="ÁREA", color="TIPO", title="Equipos por Área"), use_container_width=True)

    # 2. CONSULTAR
    with tabs[1]:
        st.dataframe(df.drop(columns=["_supabase_id"], errors="ignore"), use_container_width=True, hide_index=True)

    # 3. NUEVO REGISTRO
    with tabs[2]:
        st.markdown("### 🆕 Registro Individual")
        with st.form("frm_nuevo"):
            col1, col2 = st.columns(2)
            nuevo_dato = {}
            
            with col1:
                nuevo_dato["USUARIO"] = st.text_input("Usuario Asignado").upper()
                nuevo_dato["EQUIPO"] = st.text_input("Nombre Equipo (Hostname)").upper()
                nuevo_dato["TIPO"] = campo_con_opcion_otro("Tipo", LISTAS_OPCIONES["TIPO"], key_suffix="new")
                nuevo_dato["MARCA"] = campo_con_opcion_otro("Marca", LISTAS_OPCIONES["MARCA"], key_suffix="new")
                nuevo_dato["MODELO"] = st.text_input("Modelo").upper()
                nuevo_dato["NRO DE SERIE"] = st.text_input("Nro Serie").upper()
                
            with col2:
                nuevo_dato["ÁREA"] = st.selectbox("Área", LISTAS_OPCIONES["ÁREA"])
                nuevo_dato["ESTADO"] = st.selectbox("Estado", LISTAS_OPCIONES["ESTADO"])
                nuevo_dato["UBICACIÓN"] = st.text_input("Ubicación Física").upper()
                nuevo_dato["NUEVO ACTIVO"] = st.text_input("Código Patrimonial").upper()
                nuevo_dato["ACCESORIOS"] = st.text_area("Accesorios (separar por comas)").upper()
            
            nuevo_dato["OBSERVACIONES"] = st.text_area("Observaciones").upper()
            
            if st.form_submit_button("💾 Guardar Registro", use_container_width=True):
                if agregar_registro_bd(nuevo_dato):
                    st.success("Registro guardado en Nube!")
                    registrar_log("CREAR", f"Alta de equipo {nuevo_dato['EQUIPO']}")
                    time.sleep(1)
                    st.rerun()

    # 4. CARGA MASIVA
    with tabs[3]:
        st.info("Funcionalidad simplificada para Nube: Subir Excel con columnas exactas.")
        upl = st.file_uploader("Subir Excel", type=["xlsx"])
        if upl:
            df_up = pd.read_excel(upl)
            st.dataframe(df_up.head())
            if st.button("Procesar Carga"):
                count = 0
                progress = st.progress(0)
                for idx, row in df_up.iterrows():
                    # Convertimos la fila a dict y filtramos nan
                    d_row = row.dropna().to_dict()
                    # Aseguramos strings
                    d_row = {k: str(v) for k, v in d_row.items()}
                    agregar_registro_bd(d_row)
                    count += 1
                    progress.progress(min(count / len(df_up), 1.0))
                st.success(f"Se cargaron {count} registros.")
                st.rerun()

    # 5. EDITAR / ACTA
    with tabs[4]:
        st.markdown("### ✏️ Edición y Gestión de Actas")
        
        # Buscador inteligente
        busqueda = st.text_input("🔍 Buscar por Usuario, Serie o Activo:", placeholder="Escriba para filtrar...")
        
        if busqueda:
            mask = df.astype(str).apply(lambda x: x.str.contains(busqueda, case=False)).any(axis=1)
            df_filt = df[mask]
        else:
            df_filt = df.head(10) # Mostrar solo primeros 10 si no hay búsqueda para no saturar
            
        if not df_filt.empty:
            # Selector de registro para editar
            opciones_editar = df_filt.apply(lambda x: f"{x['USUARIO']} - {x['TIPO']} - {x['NRO DE SERIE']}", axis=1).tolist()
            seleccion = st.selectbox("Seleccione activo a gestionar:", opciones_editar)
            
            if seleccion:
                # Recuperar el ID original de Supabase
                idx_sel = opciones_editar.index(seleccion)
                registro_sel = df_filt.iloc[idx_sel]
                id_supabase = registro_sel.get("_supabase_id") 
                
                with st.expander("📝 Editar Datos", expanded=True):
                    with st.form("frm_edit"):
                        c_e1, c_e2 = st.columns(2)
                        with c_e1:
                            u_ed = st.text_input("Usuario", value=registro_sel["USUARIO"])
                            s_ed = st.text_input("Serie", value=registro_sel["NRO DE SERIE"])
                            e_ed = st.selectbox("Estado", LISTAS_OPCIONES["ESTADO"], index=LISTAS_OPCIONES["ESTADO"].index(registro_sel["ESTADO"]) if registro_sel["ESTADO"] in LISTAS_OPCIONES["ESTADO"] else 0)
                        with c_e2:
                            obs_ed = st.text_area("Observaciones", value=registro_sel["OBSERVACIONES"])
                            acc_ed = st.text_area("Accesorios", value=registro_sel["ACCESORIOS"])
                        
                        if st.form_submit_button("Actualizar Datos"):
                            cambios = {
                                "USUARIO": u_ed, "NRO DE SERIE": s_ed, 
                                "ESTADO": e_ed, "OBSERVACIONES": obs_ed, "ACCESORIOS": acc_ed
                            }
                            if editar_registro_bd(id_supabase, cambios):
                                st.success("Actualizado")
                                registrar_log("EDITAR", f"ID {id_supabase} actualizado")
                                time.sleep(1)
                                st.rerun()
                
                c_acta, c_borrar = st.columns(2)
                with c_acta:
                    excel_data = generar_acta_excel(registro_sel.to_dict(), df)
                    if excel_data:
                        n_file = f"Acta_{registro_sel['USUARIO']}_{registro_sel['TIPO']}.xlsx"
                        st.download_button("📥 Descargar Acta Excel", data=excel_data, file_name=n_file)
                
                with c_borrar:
                    if st.button("🗑️ Eliminar Registro", type="primary"):
                        eliminar_registro_bd(id_supabase)
                        registrar_log("ELIMINAR", f"ID {id_supabase} eliminado")
                        st.warning("Eliminado...")
                        time.sleep(1)
                        st.rerun()

    # TABS ADMIN
    if st.session_state.rol_actual == "Administrador":
        with tabs[5]: # LOGS
            st.write("### Auditoría")
            try:
                logs = supabase.table('logs_auditoria').select("*").order('fecha', desc=True).limit(50).execute()
                st.dataframe(pd.DataFrame(logs.data), use_container_width=True)
            except: st.error("No se pudo cargar logs")
            
        with tabs[6]: # USUARIOS
            st.write("### Gestión de Accesos")
            df_users = cargar_usuarios()
            st.dataframe(df_users, use_container_width=True)
            
            with st.form("add_user"):
                nu = st.text_input("Nuevo Correo/Usuario")
                nr = st.selectbox("Rol", ["Soporte", "Administrador"])
                if st.form_submit_button("Autorizar"):
                    ok, msg = guardar_nuevo_usuario(nu, nr)
                    if ok: st.success(msg); time.sleep(1); st.rerun()
                    else: st.error(msg)
