# auth.py
import streamlit as st
import msal
from streamlit_cookies_manager import EncryptedCookieManager
import database as db

def init_cookies():
    cookies = EncryptedCookieManager(password=st.secrets.get("COOKIE_PASSWORD", "secret_key"))
    if not cookies.ready():
        st.stop()
    return cookies

def verificar_sesion(cookies):
    if "autenticado" not in st.session_state: st.session_state.autenticado = False

    # 1. Recuperar Cookie
    if not st.session_state.autenticado:
        c_user = cookies.get("usuario_actual")
        c_rol = cookies.get("rol_actual")
        if c_user and c_rol:
            st.session_state.autenticado = True
            st.session_state.usuario_actual = c_user
            st.session_state.rol_actual = c_rol

    # Configuracion MS
    try:
        CLIENT_ID = st.secrets["CLIENT_ID"]
        TENANT_ID = st.secrets["TENANT_ID"]
        CLIENT_SECRET = st.secrets["CLIENT_SECRET"]
        REDIRECT_URI = st.secrets["REDIRECT_URI"]
        AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
        SCOPE = ["User.Read"]
        ms_configured = True
    except:
        ms_configured = False

    # 2. Microsoft Callback
    if "code" in st.query_params and ms_configured:
        try:
            app = msal.ConfidentialClientApplication(CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET)
            result = app.acquire_token_by_authorization_code(st.query_params["code"], scopes=SCOPE, redirect_uri=REDIRECT_URI)
            if "error" not in result:
                email = result.get("id_token_claims").get("preferred_username").lower()
                df_u = db.cargar_usuarios()
                user_match = df_u[df_u["usuario"].str.lower() == email]
                if not user_match.empty:
                    st.session_state.autenticado = True
                    st.session_state.usuario_actual = email
                    st.session_state.rol_actual = user_match.iloc[0]["rol"]
                    cookies["usuario_actual"] = email
                    cookies["rol_actual"] = st.session_state.rol_actual
                    cookies.save()
                    st.query_params.clear()
                    st.rerun()
                else:
                    st.error("Usuario sin permisos.")
        except Exception as e:
            st.error(f"Error Login MS: {e}")

    # 3. Pantalla Login
    if not st.session_state.autenticado:
        st.markdown("<h1 style='text-align: center;'>☁️ Gestión de Inventario TI</h1>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 1.2, 1])
        with col2:
            if ms_configured:
                app = msal.ConfidentialClientApplication(CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET)
                auth_url = app.get_authorization_request_url(SCOPE, redirect_uri=REDIRECT_URI)
                st.link_button("🟦 Iniciar con Microsoft 365", auth_url, use_container_width=True)
            
            st.divider()
            with st.expander("🔐 Acceso Local"):
                with st.form("local_login"):
                    u = st.text_input("Usuario")
                    p = st.text_input("Clave", type="password")
                    if st.form_submit_button("Entrar", use_container_width=True):
                        df_u = db.cargar_usuarios()
                        match = df_u[(df_u["usuario"].str.lower() == u.lower()) & (df_u["clave"] == p)]
                        if not match.empty:
                            st.session_state.autenticado = True
                            st.session_state.usuario_actual = match.iloc[0]["usuario"]
                            st.session_state.rol_actual = match.iloc[0]["rol"]
                            cookies["usuario_actual"] = st.session_state.usuario_actual
                            cookies["rol_actual"] = st.session_state.rol_actual
                            cookies.save()
                            st.rerun()
                        else:
                            st.error("Credenciales incorrectas")
        st.stop()
    return True
