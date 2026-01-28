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
CLIENT_ID = st.secrets["CLIENT_ID"]
TENANT_ID = st.secrets["TENANT_ID"]
CLIENT_SECRET = st.secrets["CLIENT_SECRET"]
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPE = ["User.Read"]
REDIRECT_URI = st.secrets["REDIRECT_URI"]

# --- GESTOR DE COOKIES ---
cookies = EncryptedCookieManager(password=st.secrets.get("COOKIE_PASSWORD", "esandata_secret_key_2024"))

if not cookies.ready():
    with st.spinner("Cargando sistema de autenticación..."):
        st.stop()

# --- CONFIGURACIÓN DE ARCHIVOS Y LISTAS MAESTRAS ---
PLANTILLA_EXCEL = 'Acta de Asignación Equipos - V3.xlsx'

COLUMNAS = [
    "numero", "usuario", "equipo", "area", "direccion", "ubicacion", 
    "nuevo_activo", "activo", "tipo", "nro_serie", "marca", "modelo", 
    "anio_adquisicion", "procesador", "memoria_ram", "disco_duro", 
    "estado", "componente", "costo", "accesorios", "observaciones", 
    "acta_asignacion", "adm_local", "origen_hoja", "ultima_actualizacion", "modificado_por"
]

# Mapeo para mostrar nombres bonitos en la UI
COLUMNAS_DISPLAY = {
    "numero": "N°",
    "usuario": "USUARIO",
    "equipo": "EQUIPO",
    "area": "ÁREA",
    "direccion": "DIRECCIÓN",
    "ubicacion": "UBICACIÓN",
    "nuevo_activo": "NUEVO ACTIVO",
    "activo": "ACTIVO",
    "tipo": "TIPO",
    "nro_serie": "NRO DE SERIE",
    "marca": "MARCA",
    "modelo": "MODELO",
    "anio_adquisicion": "AÑO DE ADQUISICIÓN",
    "procesador": "PROCESADOR",
    "memoria_ram": "MEMORIA RAM",
    "disco_duro": "DISCO DURO",
    "estado": "ESTADO",
    "componente": "COMPONENTE",
    "costo": "COSTO",
    "accesorios": "ACCESORIOS",
    "observaciones": "OBSERVACIONES",
    "acta_asignacion": "ACTA DE ASIGNACIÓN",
    "adm_local": "ADM-LOCAL",
    "origen_hoja": "ORIGEN_HOJA",
    "ultima_actualizacion": "Ultima_Actualizacion",
    "modificado_por": "MODIFICADO_POR"
}

# --- LISTAS BASE (Para ingreso de datos, no para filtros de dashboard) ---
LISTAS_OPCIONES = {
    "tipo": ["LAPTOP", "DESKTOP", "MONITOR", "ALL IN ONE", "TABLET", "IMPRESORA", "PERIFERICO"],
    "estado": ["OPERATIVO", "EN REVISIÓN", "MANTENIMIENTO", "BAJA", "HURTO/ROBO", "ASIGNADO"],
    "marca": ["DELL", "HP", "LENOVO", "APPLE", "SAMSUNG", "LG", "EPSON", "LOGITECH"],
    "area": ["SOPORTE TI", "ADMINISTRACIÓN", "RECURSOS HUMANOS", "CONTABILIDAD", "COMERCIAL", "MARKETING", "LOGÍSTICA", "DIRECCIÓN", "ACADÉMICO"]
}

# --- FUNCIONES DE BASE DE DATOS ---

def registrar_log(accion, detalle):
    """Registra acción en la tabla de logs de Supabase"""
    try:
        usuario = st.session_state.get("usuario_actual", "Desconocido")
        log_entry = {
            "usuario": usuario,
            "accion": accion,
            "detalle": detalle
        }
        supabase.table('logs_auditoria').insert(log_entry).execute()
    except Exception as e:
        st.error(f"Error al registrar log: {e}")

@st.cache_data(ttl=60)
def cargar_inventario():
    """Carga todos los registros del inventario desde Supabase"""
    try:
        response = supabase.table('inventario').select("*").order('id', desc=False).execute()
        df = pd.DataFrame(response.data)
        
        # Renombrar columnas para coincidir con el formato original
        df = df.rename(columns={v: k for k, v in COLUMNAS_DISPLAY.items()})
        
        # Asegurar que existan todas las columnas esperadas
        for col in COLUMNAS_DISPLAY.values():
            if col not in df.columns:
                df[col] = ""
        
        return df
    except Exception as e:
        st.error(f"Error al cargar inventario: {e}")
        return pd.DataFrame(columns=list(COLUMNAS_DISPLAY.values()))

def cargar_usuarios():
    """Carga usuarios desde Supabase"""
    try:
        response = supabase.table('usuarios').select("*").execute()
        return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"Error al cargar usuarios: {e}")
        # Si falla, crear usuario admin por defecto
        return pd.DataFrame([{"usuario": "admin", "clave": "1234", "rol": "Administrador"}])

def guardar_nuevo_usuario(u, r):
    """Guarda un nuevo usuario autorizado en Supabase"""
    try:
        df_usuarios = cargar_usuarios()
        
        # Verificar si ya existe
        if u.lower() in df_usuarios["usuario"].str.lower().values:
            return False, "Este usuario ya tiene acceso autorizado."
        
        # Insertar nuevo usuario
        nuevo_usuario = {
            "usuario": u.lower(),
            "clave": "MS_365_ACCESS",
            "rol": r
        }
        supabase.table('usuarios').insert(nuevo_usuario).execute()
        st.cache_data.clear()  # Limpiar caché
        return True, f"Acceso autorizado para {u}"
        
    except Exception as e:
        return False, f"Error al guardar usuario: {e}"

def actualizar_mi_clave(u, nueva_c):
    """Actualiza la clave de un usuario local"""
    try:
        # Verificar si es usuario de Microsoft
        response = supabase.table('usuarios').select("*").eq('usuario', u).execute()
        
        if not response.data:
            return False, "Usuario no encontrado"
        
        usuario_data = response.data[0]
        
        if usuario_data["clave"] == "MS_365_ACCESS":
            return False, "Los usuarios de Microsoft gestionan su clave en Office 365."
        
        # Actualizar clave
        supabase.table('usuarios').update({"clave": nueva_c}).eq('usuario', u).execute()
        registrar_log("SEGURIDAD", "Cambio de clave local")
        return True, "Clave local actualizada"
        
    except Exception as e:
        return False, f"Error al actualizar clave: {e}"

def agregar_registro_inventario(nuevo_dato_dict):
    """Agrega un nuevo registro al inventario en Supabase"""
    try:
        # Convertir nombres de columnas al formato de BD
        nuevo_dato_bd = {}
        for display_name, db_name in COLUMNAS_DISPLAY.items():
            if display_name in nuevo_dato_dict:
                nuevo_dato_bd[db_name] = nuevo_dato_dict[display_name]
        
        # Agregar metadatos
        nuevo_dato_bd["ultima_actualizacion"] = datetime.now().isoformat()
        nuevo_dato_bd["modificado_por"] = st.session_state.get("usuario_actual", "Sistema")
        
        # Insertar en Supabase
        response = supabase.table('inventario').insert(nuevo_dato_bd).execute()
        st.cache_data.clear()  # Limpiar caché para refrescar datos
        return True
        
    except Exception as e:
        st.error(f"Error al agregar registro: {e}")
        return False

def editar_registro_inventario(id_registro, cambios_dict):
    """Edita un registro existente en Supabase"""
    try:
        # Convertir nombres de columnas al formato de BD si es necesario
        cambios_bd = {}
        for key, value in cambios_dict.items():
            # Buscar el nombre de columna en BD correspondiente
            db_column = None
            for db_col, display_col in COLUMNAS_DISPLAY.items():
                if display_col == key or db_col == key:
                    db_column = db_col
                    break
            
            if db_column:
                cambios_bd[db_column] = value
        
        # Actualizar en Supabase
        response = supabase.table('inventario').update(cambios_bd).eq('id', id_registro).execute()
        st.cache_data.clear()  # Limpiar caché
        return True
        
    except Exception as e:
        st.error(f"Error al editar registro: {e}")
        return False

def eliminar_registro_inventario(id_registro):
    """Elimina un registro del inventario"""
    try:
        supabase.table('inventario').delete().eq('id', id_registro).execute()
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error al eliminar registro: {e}")
        return False

# --- FUNCIONES UI (INTERFAZ DE USUARIO FLEXIBLE) ---

def campo_con_opcion_otro(label, lista_base, valor_actual=None, key_suffix=""):
    """Genera un selectbox con opción OTRO para entrada manual"""
    opciones = list(lista_base)
    opcion_otro = "OTRO (ESPECIFICAR)"
    if opcion_otro not in opciones:
        opciones.append(opcion_otro)
    
    idx = 0
    modo_manual = False
    
    if valor_actual:
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

# --- FUNCIÓN GENERAR ACTA EXCEL ---

def generar_acta_excel(registro, df_completo):
    """Genera el acta de asignación en formato Excel"""
    try:
        # Cargar plantilla (debe estar en el repositorio)
        wb = openpyxl.load_workbook(PLANTILLA_EXCEL)
        ws = wb.active
        
        # Mapeo de campos a celdas (ajusta según tu plantilla)
        mapeo_celdas = {
            "USUARIO": "C10",
            "ÁREA": "C11",
            "UBICACIÓN": "C12",
            "TIPO": "C15",
            "MARCA": "C16",
            "MODELO": "C17",
            "NRO DE SERIE": "C18",
            "PROCESADOR": "C19",
            "MEMORIA RAM": "C20",
            "DISCO DURO": "C21",
            "ESTADO": "C22",
            "OBSERVACIONES": "C25"
        }
        
        # Llenar datos básicos
        for campo, celda in mapeo_celdas.items():
            valor = registro.get(campo, "-")
            ws[celda] = str(valor)
        
        # Llenar accesorios (checkboxes)
        accesorios_str = str(registro.get("ACCESORIOS", "")).upper()
        accesorios_map = {
            "MOUSE": "C28",
            "TECLADO": "C29",
            "CADENA": "C30",
            "MALETÍN": "C31"
        }
        
        for accesorio, celda in accesorios_map.items():
            if accesorio in accesorios_str:
                ws[celda] = "X"
        
        # Guardar en memoria
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        
        return output.getvalue()
        
    except Exception as e:
        st.error(f"Error al generar acta: {e}")
        return None

# --- AUTENTICACIÓN MICROSOFT ---

def obtener_cliente_msal():
    """Crea cliente MSAL para autenticación"""
    return msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET
    )

def iniciar_sesion_microsoft():
    """Inicia el flujo de autenticación de Microsoft"""
    client = obtener_cliente_msal()
    auth_url = client.get_authorization_request_url(
        scopes=SCOPE,
        redirect_uri=REDIRECT_URI
    )
    st.markdown(f'<a href="{auth_url}" target="_self">🔐 Iniciar Sesión con Microsoft 365</a>', unsafe_allow_html=True)

def procesar_callback_microsoft(code):
    """Procesa el callback de Microsoft y obtiene el token"""
    client = obtener_cliente_msal()
    result = client.acquire_token_by_authorization_code(
        code,
        scopes=SCOPE,
        redirect_uri=REDIRECT_URI
    )
    
    if "access_token" in result:
        return result
    else:
        st.error("Error en autenticación Microsoft")
        return None

# --- LÓGICA DE AUTENTICACIÓN ---

def verificar_sesion():
    """Verifica si existe una sesión activa"""
    if "usuario_actual" not in st.session_state:
        st.session_state.usuario_actual = None
        st.session_state.rol_actual = None
        st.session_state.autenticado = False

def login_local(usuario, clave):
    """Autenticación local con usuario/clave"""
    df_usuarios = cargar_usuarios()
    user_row = df_usuarios[df_usuarios["usuario"] == usuario]
    
    if not user_row.empty:
        if user_row.iloc[0]["clave"] == clave:
            st.session_state.usuario_actual = usuario
            st.session_state.rol_actual = user_row.iloc[0]["rol"]
            st.session_state.autenticado = True
            registrar_log("LOGIN", "Ingreso local exitoso")
            return True
    
    return False

# --- INTERFAZ PRINCIPAL ---

def main():
    verificar_sesion()
    
    # Si hay código de Microsoft en la URL, procesarlo
    query_params = st.query_params
    if "code" in query_params and not st.session_state.autenticado:
        code = query_params["code"]
        result = procesar_callback_microsoft(code)
        
        if result and "id_token_claims" in result:
            email = result["id_token_claims"].get("preferred_username", "").lower()
            
            # Verificar si el usuario está autorizado
            df_usuarios = cargar_usuarios()
            if email in df_usuarios["usuario"].values:
                user_data = df_usuarios[df_usuarios["usuario"] == email].iloc[0]
                st.session_state.usuario_actual = email
                st.session_state.rol_actual = user_data["rol"]
                st.session_state.autenticado = True
                registrar_log("LOGIN", f"Ingreso Microsoft 365: {email}")
                st.rerun()
            else:
                st.error("❌ Su cuenta de Microsoft no está autorizada. Contacte al administrador.")
                st.stop()
    
    # Pantalla de login
    if not st.session_state.autenticado:
        st.markdown("<h1 style='text-align: center;'>🖥️ Sistema de Gestión de Inventario TI</h1>", unsafe_allow_html=True)
        st.markdown("<h3 style='text-align: center;'>ESAN Data</h3>", unsafe_allow_html=True)
        
        tab1, tab2 = st.tabs(["🔑 Acceso Local", "🌐 Microsoft 365"])
        
        with tab1:
            with st.form("login_form"):
                usuario = st.text_input("Usuario")
                clave = st.text_input("Contraseña", type="password")
                submit = st.form_submit_button("Ingresar", use_container_width=True)
                
                if submit:
                    if login_local(usuario, clave):
                        st.success("✅ Ingreso exitoso")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ Credenciales incorrectas")
        
        with tab2:
            st.info("Inicie sesión con su cuenta corporativa de Microsoft 365")
            iniciar_sesion_microsoft()
        
        st.stop()
    
    # APLICACIÓN PRINCIPAL (Usuario autenticado)
    st.sidebar.title(f"👤 {st.session_state.usuario_actual}")
    st.sidebar.caption(f"Rol: {st.session_state.rol_actual}")
    
    if st.sidebar.button("🚪 Cerrar Sesión"):
        st.session_state.clear()
        cookies.clear()
        st.rerun()
    
    # TABS PRINCIPALES
    tabs_names = ["📊 Dashboard", "➕ Ingresar Activo", "🔍 Consultar", "📤 Carga Masiva", "✏️ Editar / Acta"]
    
    if st.session_state.rol_actual == "Administrador":
        tabs_names.extend(["📜 Logs", "👥 Usuarios"])
    
    tabs = st.tabs(tabs_names)
    
    # Cargar datos
    df = cargar_inventario()
    
    # 1. DASHBOARD
    with tabs[0]:
        st.title("📊 Dashboard de Inventario")
        
        # Métricas principales
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Activos", len(df))
        col2.metric("Operativos", len(df[df["ESTADO"] == "OPERATIVO"]))
        col3.metric("En Revisión", len(df[df["ESTADO"] == "EN REVISIÓN"]))
        col4.metric("Mantenimiento", len(df[df["ESTADO"] == "MANTENIMIENTO"]))
        
        # Gráficos
        c1, c2 = st.columns(2)
        
        with c1:
            if not df.empty:
                fig_tipo = px.pie(df, names="TIPO", title="Distribución por Tipo")
                st.plotly_chart(fig_tipo, use_container_width=True)
        
        with c2:
            if not df.empty:
                fig_estado = px.bar(df, x="ESTADO", title="Activos por Estado")
                st.plotly_chart(fig_estado, use_container_width=True)
        
        # Filtros y tabla
        st.subheader("🔍 Filtros Avanzados")
        
        col_f1, col_f2, col_f3 = st.columns(3)
        
        with col_f1:
            filtro_tipo = st.multiselect("Tipo", df["TIPO"].unique())
        
        with col_f2:
            filtro_estado = st.multiselect("Estado", df["ESTADO"].unique())
        
        with col_f3:
            filtro_area = st.multiselect("Área", df["ÁREA"].unique())
        
        df_filtrado = df.copy()
        
        if filtro_tipo:
            df_filtrado = df_filtrado[df_filtrado["TIPO"].isin(filtro_tipo)]
        
        if filtro_estado:
            df_filtrado = df_filtrado[df_filtrado["ESTADO"].isin(filtro_estado)]
        
        if filtro_area:
            df_filtrado = df_filtrado[df_filtrado["ÁREA"].isin(filtro_area)]
        
        st.dataframe(df_filtrado, use_container_width=True)
        
        # Exportar
        csv = df_filtrado.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Descargar CSV", csv, "inventario.csv", "text/csv")
    
    # 2. INGRESAR ACTIVO
    with tabs[1]:
        st.subheader("➕ Ingresar Nuevo Activo")
        
        with st.form("form_ingreso"):
            c1, c2 = st.columns(2)
            
            nuevo_dato = {}
            
            with c1:
                nuevo_dato["USUARIO"] = st.text_input("Usuario").upper()
                nuevo_dato["NUEVO ACTIVO"] = st.text_input("Código Nuevo Activo").upper()
                nuevo_dato["TIPO"] = campo_con_opcion_otro("Tipo", LISTAS_OPCIONES["tipo"], key_suffix="ingreso")
                nuevo_dato["MARCA"] = campo_con_opcion_otro("Marca", LISTAS_OPCIONES["marca"], key_suffix="ingreso")
                nuevo_dato["MODELO"] = st.text_input("Modelo").upper()
                nuevo_dato["NRO DE SERIE"] = st.text_input("Nro de Serie").upper()
                nuevo_dato["PROCESADOR"] = st.text_input("Procesador").upper()
            
            with c2:
                nuevo_dato["ÁREA"] = campo_con_opcion_otro("Área", LISTAS_OPCIONES["area"], key_suffix="ingreso")
                nuevo_dato["UBICACIÓN"] = st.text_input("Ubicación").upper()
                nuevo_dato["ESTADO"] = campo_con_opcion_otro("Estado", LISTAS_OPCIONES["estado"], key_suffix="ingreso")
                nuevo_dato["MEMORIA RAM"] = st.text_input("Memoria RAM").upper()
                nuevo_dato["DISCO DURO"] = st.text_input("Disco Duro").upper()
                nuevo_dato["ACCESORIOS"] = st.text_input("Accesorios (ej: Mouse, Teclado)").upper()
                nuevo_dato["OBSERVACIONES"] = st.text_area("Observaciones").upper()
            
            if st.form_submit_button("💾 Guardar Activo"):
                if nuevo_dato["USUARIO"] and nuevo_dato["TIPO"]:
                    # Generar número automático
                    nuevo_dato["N°"] = len(df) + 1
                    nuevo_dato["ORIGEN_HOJA"] = "WEB"
                    nuevo_dato["MODIFICADO_POR"] = st.session_state.usuario_actual
                    
                    if agregar_registro_inventario(nuevo_dato):
                        registrar_log("INGRESO", f"Nuevo activo: {nuevo_dato.get('TIPO')} - {nuevo_dato.get('NRO DE SERIE')}")
                        st.success("✅ Activo registrado exitosamente")
                        time.sleep(1.5)
                        st.rerun()
                else:
                    st.error("⚠️ Complete al menos Usuario y Tipo")
    
    # 3. CONSULTAR
    with tabs[2]:
        st.subheader("🔍 Consultar Inventario")
        
        busqueda = st.text_input("Buscar por Usuario, Serie o Activo", placeholder="Ej: Juan, 4820W...")
        
        if busqueda:
            df_resultado = df[
                df["USUARIO"].str.contains(busqueda, case=False, na=False) |
                df["NRO DE SERIE"].str.contains(busqueda, case=False, na=False) |
                df["NUEVO ACTIVO"].str.contains(busqueda, case=False, na=False)
            ]
            
            st.dataframe(df_resultado, use_container_width=True)
            
            if not df_resultado.empty:
                csv = df_resultado.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Descargar Resultados", csv, "resultados.csv", "text/csv")
        else:
            st.info("Ingrese un término de búsqueda")
    
    # 4. CARGA MASIVA
    with tabs[3]:
        st.subheader("📤 Carga Masiva desde Excel")
        
        st.info("📋 Suba un archivo Excel con las columnas correspondientes al formato del sistema")
        
        archivo = st.file_uploader("Seleccione archivo Excel", type=["xlsx"])
        
        if archivo:
            try:
                df_upload = pd.read_excel(archivo)
                st.write("Vista previa:")
                st.dataframe(df_upload.head())
                
                if st.button("✅ Confirmar Carga Masiva"):
                    progreso = st.progress(0)
                    total = len(df_upload)
                    exitos = 0
                    
                    for idx, row in df_upload.iterrows():
                        registro = row.to_dict()
                        
                        # Asegurar que tenga las columnas necesarias
                        for col in COLUMNAS_DISPLAY.values():
                            if col not in registro:
                                registro[col] = ""
                        
                        if agregar_registro_inventario(registro):
                            exitos += 1
                        
                        progreso.progress((idx + 1) / total)
                    
                    registrar_log("CARGA_MASIVA", f"{exitos}/{total} registros cargados")
                    st.success(f"✅ {exitos} de {total} registros cargados exitosamente")
                    time.sleep(2)
                    st.rerun()
                    
            except Exception as e:
                st.error(f"Error al procesar archivo: {e}")
    
    # 5. EDITAR / ACTA
    with tabs[4]:
        st.subheader("✏️ Editar Activo / Generar Acta")
        
        busqueda_edit = st.text_input("Buscar activo a editar", placeholder="Usuario, Serie o Activo...")
        
        if busqueda_edit:
            df_edit = df[
                df["USUARIO"].str.contains(busqueda_edit, case=False, na=False) |
                df["NRO DE SERIE"].str.contains(busqueda_edit, case=False, na=False) |
                df["NUEVO ACTIVO"].str.contains(busqueda_edit, case=False, na=False)
            ]
            
            if not df_edit.empty:
                opciones = df_edit.apply(
                    lambda r: f"{r['N°']} | {r['USUARIO']} | {r['TIPO']} | {r['NRO DE SERIE']}", 
                    axis=1
                ).tolist()
                
                seleccion = st.selectbox("Seleccione el registro", opciones)
                idx_sel = df_edit.index[opciones.index(seleccion)]
                registro_sel = df.loc[idx_sel]
                id_registro = registro_sel.name  # Usar el index como ID
                
                col_edit, col_acta = st.columns([2, 1])
                
                with col_edit:
                    with st.form("form_editar"):
                        st.write("### Editar Datos")
                        
                        cambios = {}
                        
                        ce1, ce2 = st.columns(2)
                        
                        campos_edit = ["USUARIO", "ÁREA", "UBICACIÓN", "TIPO", "MARCA", "ESTADO", 
                                     "NUEVO ACTIVO", "NRO DE SERIE", "ACCESORIOS", "OBSERVACIONES"]
                        
                        for i, campo in enumerate(campos_edit):
                            valor_actual = registro_sel[campo]
                            
                            with [ce1, ce2][i % 2]:
                                campo_db = None
                                for db_col, display_col in COLUMNAS_DISPLAY.items():
                                    if display_col == campo:
                                        campo_db = db_col
                                        break
                                
                                if campo_db and campo_db in LISTAS_OPCIONES:
                                    cambios[campo] = campo_con_opcion_otro(
                                        campo, 
                                        LISTAS_OPCIONES[campo_db], 
                                        valor_actual=valor_actual,
                                        key_suffix=f"edit_{id_registro}"
                                    )
                                else:
                                    cambios[campo] = st.text_input(campo, value=str(valor_actual))
                        
                        if st.form_submit_button("💾 Guardar Cambios"):
                            # Filtrar solo los campos que cambiaron
                            cambios_reales = {}
                            for k, v in cambios.items():
                                if str(registro_sel[k]) != str(v):
                                    cambios_reales[k] = v
                            
                            if cambios_reales:
                                cambios_reales["MODIFICADO_POR"] = st.session_state.usuario_actual
                                cambios_reales["Ultima_Actualizacion"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                                
                                if editar_registro_inventario(id_registro, cambios_reales):
                                    registrar_log("EDICIÓN", f"ID {id_registro} | Cambios: {list(cambios_reales.keys())}")
                                    st.success("✅ Registro actualizado")
                                    time.sleep(1.5)
                                    st.rerun()
                            else:
                                st.info("No se detectaron cambios")
                
                with col_acta:
                    st.write("### Generar Acta")
                    st.write(f"Usuario: **{registro_sel['USUARIO']}**")
                    
                    acta_bytes = generar_acta_excel(registro_sel.to_dict(), df)
                    
                    if acta_bytes:
                        if st.download_button(
                            "📥 Descargar Acta",
                            acta_bytes,
                            file_name=f"Acta_{registro_sel['USUARIO']}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        ):
                            registrar_log("ACTA", f"Generada para {registro_sel['USUARIO']}")
                            st.toast("✅ Acta descargada")
    
    # 6. LOGS (Solo Administradores)
    if st.session_state.rol_actual == "Administrador":
        with tabs[5]:
            st.subheader("📜 Logs de Auditoría")
            
            try:
                response = supabase.table('logs_auditoria').select("*").order('fecha', desc=True).limit(500).execute()
                df_logs = pd.DataFrame(response.data)
                
                if not df_logs.empty:
                    col_f1, col_f2 = st.columns(2)
                    
                    with col_f1:
                        filtro_usuario = st.multiselect("Filtrar Usuario", df_logs["usuario"].unique())
                    
                    with col_f2:
                        filtro_accion = st.multiselect("Filtrar Acción", df_logs["accion"].unique())
                    
                    df_logs_filtrado = df_logs.copy()
                    
                    if filtro_usuario:
                        df_logs_filtrado = df_logs_filtrado[df_logs_filtrado["usuario"].isin(filtro_usuario)]
                    
                    if filtro_accion:
                        df_logs_filtrado = df_logs_filtrado[df_logs_filtrado["accion"].isin(filtro_accion)]
                    
                    st.dataframe(df_logs_filtrado, use_container_width=True)
                    
                    csv_logs = df_logs_filtrado.to_csv(index=False).encode('utf-8')
                    st.download_button("📥 Descargar Logs", csv_logs, "logs_auditoria.csv", "text/csv")
                else:
                    st.info("No hay logs registrados aún")
                    
            except Exception as e:
                st.error(f"Error al cargar logs: {e}")
        
        # 7. GESTIÓN DE USUARIOS
        with tabs[6]:
            st.subheader("👥 Gestión de Usuarios")
            
            col_u1, col_u2 = st.columns([1, 1.5])
            
            with col_u1:
                st.write("### Autorizar Nuevo Usuario")
                
                with st.form("form_nuevo_usuario"):
                    nuevo_email = st.text_input("Correo Microsoft", placeholder="usuario@esan.edu.pe")
                    nuevo_rol = st.selectbox("Rol", ["Soporte", "Administrador"])
                    
                    if st.form_submit_button("✅ Autorizar"):
                        if nuevo_email and "@" in nuevo_email:
                            exito, mensaje = guardar_nuevo_usuario(nuevo_email, nuevo_rol)
                            
                            if exito:
                                registrar_log("USUARIOS", f"Usuario autorizado: {nuevo_email}")
                                st.success(mensaje)
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(mensaje)
                        else:
                            st.warning("Ingrese un correo válido")
                
                st.write("---")
                st.write("### Eliminar Usuario")
                
                df_usuarios_list = cargar_usuarios()
                usuarios_disponibles = [
                    u for u in df_usuarios_list["usuario"].tolist() 
                    if u != st.session_state.usuario_actual
                ]
                
                usuario_eliminar = st.selectbox("Seleccione usuario", usuarios_disponibles)
                
                if st.button("❌ Eliminar Acceso", type="secondary"):
                    try:
                        supabase.table('usuarios').delete().eq('usuario', usuario_eliminar).execute()
                        registrar_log("USUARIOS", f"Usuario eliminado: {usuario_eliminar}")
                        st.cache_data.clear()
                        st.success(f"Usuario {usuario_eliminar} eliminado")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al eliminar usuario: {e}")
            
            with col_u2:
                st.write("### Usuarios Autorizados")
                df_usuarios_mostrar = cargar_usuarios()[["usuario", "rol"]]
                st.dataframe(df_usuarios_mostrar, use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
